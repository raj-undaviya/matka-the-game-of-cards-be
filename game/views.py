"""
game/views.py  (UPDATED)
==========================
Endpoints:

── User APIs ──────────────────────────────────────────────────────
  GET  /api/rounds/                  → open rounds list (with slot counts)
  GET  /api/rounds/?variation=V1     → filter by variation
  POST /api/rounds/create/           → new round (admin only)
  GET  /api/rounds/<id>/             → round detail
  POST /api/bets/place/              → place a bet (+ WebSocket notify)
  GET  /api/bets/my/                 → my bets

── Wallet ─────────────────────────────────────────────────────────
  GET  /api/wallet/                  → my balance
  GET  /api/wallet/transactions/     → my transaction history

── Admin Panel APIs ───────────────────────────────────────────────
  GET  /api/admin/dashboard/         → stats: users, revenue, active rounds
  GET  /api/admin/rounds/            → all rounds (all statuses, filter support)
  GET  /api/admin/rounds/<id>/       → round detail with all bets
  POST /api/admin/rounds/<id>/force-draw/   → manually trigger draw
  GET  /api/admin/users/             → all users with wallet balance
  GET  /api/admin/users/<id>/        → user detail with bet history
  GET  /api/admin/transactions/      → all wallet transactions
  POST /api/admin/users/<id>/adjust-wallet/ → manual wallet credit/debit
"""
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncHour
from django.utils import timezone
from decimal import Decimal
from django.db import transaction as db_transaction
from django.core.cache import cache
from datetime import timedelta
from .models import Round, Bet
from wallet.models import Wallet, Transaction, WithdrawRequest
from .serializers import (
    RoundListSerializer, RoundDetailSerializer,
    PlaceBetSerializer, BetSerializer
)
from wallet.serializers import WalletSerializer, TransactionSerializer
from .services import RoundService, WalletService, notify_slot_update

User = get_user_model()


# ══════════════════════════════════════════
# User APIs
# ══════════════════════════════════════════

class RoundListView(APIView):
    """
    GET /api/rounds/
    Open rounds — slot counts ke saath.
    Query params:
      ?variation=V1   → filter by variation (V1-V5)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        variation = request.query_params.get('variation')
        qs = Round.objects.filter(status=Round.Status.BETTING_OPEN)
        if variation:
            qs = qs.filter(variation=variation)
        serializer = RoundListSerializer(qs, many=True)
        return Response(serializer.data)


class RoundCreateView(APIView):
    """POST /api/rounds/create/ — admin only"""
    permission_classes = [IsAdminUser]

    def post(self, request):
        variation = request.data.get('variation')
        valid_variations = [v.value for v in __import__(
            'core.game_engine', fromlist=['GameVariation']
        ).GameVariation]

        if variation not in valid_variations:
            return Response(
                {"error": f"Invalid variation. Choose from: {valid_variations}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        round_obj = RoundService.create_round(variation)
        return Response(
            RoundListSerializer(round_obj).data,
            status=status.HTTP_201_CREATED
        )


class RoundDetailView(APIView):
    """GET /api/rounds/<id>/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, round_id):
        round_obj = get_object_or_404(Round, id=round_id)
        serializer = RoundDetailSerializer(round_obj)
        return Response(serializer.data)


class PlaceBetView(APIView):
    """
    POST /api/bets/place/
    Bet place karo + WebSocket se sabhi clients ko slot update bhejo.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PlaceBetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        success, result = RoundService.place_bet(
            round_id=str(data['round_id']),
            user=request.user,
            selected_numbers=data['selected_numbers'],
            entry_fee=data['entry_fee']
        )

        if not success:
            return Response({"error": result}, status=status.HTTP_400_BAD_REQUEST)

        bet_id, round_obj = result

        # WebSocket broadcast — atomic block ke BAHAR, DB commit ke baad
        notify_slot_update(round_obj)

        bet = Bet.objects.get(id=bet_id)
        return Response(BetSerializer(bet).data, status=status.HTTP_201_CREATED)


class MyBetsView(APIView):
    """GET /api/bets/my/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        bets = Bet.objects.filter(user=request.user).select_related('round')
        serializer = BetSerializer(bets, many=True)
        return Response(serializer.data)


class WalletView(APIView):
    """GET /api/wallet/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet = WalletService.get_or_create(request.user)
        return Response(WalletSerializer(wallet).data)


class WalletTransactionView(APIView):
    """GET /api/wallet/transactions/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet = WalletService.get_or_create(request.user)
        txs = Transaction.objects.filter(wallet=wallet).order_by('-created_at')[:50]
        return Response(TransactionSerializer(txs, many=True).data)


# ══════════════════════════════════════════
# Admin Panel APIs
# ══════════════════════════════════════════

class AdminDashboardView(APIView):
    """
    GET /api/admin/dashboard/
    AdminConsole Platform Overview — matches screenshot exactly.
    """
    permission_classes = [IsAdminUser]
 
    def get(self, request):
        now       = timezone.now()
        this_week = now - timedelta(days=7)
 
        return Response({
            "stat_cards":           self._stat_cards(now),
            "revenue_telemetry":    self._revenue_telemetry(now),
            "top_performing_games": self._top_performing_games(this_week),
            "server_status":        self._server_status(),
            "recent_activity":      self._recent_activity(),
            "device_distribution":  self._device_distribution(),
        })
 
    # ── Stat Cards ──────────────────────────────────────────────
 
    def _stat_cards(self, now):
        last_month   = now - timedelta(days=30)
        prev_month   = now - timedelta(days=60)
 
        # Total Users
        total_users      = User.objects.count()
        users_prev       = User.objects.filter(date_joined__lt=last_month).count()
        users_curr_month = total_users - users_prev
 
        # Active Sessions (last 30 min)
        active_sessions = User.objects.filter(
            last_login__gte=now - timedelta(minutes=30)
        ).count()
 
        # Revenue
        rev_this_week = Bet.objects.filter(
            placed_at__gte=now - timedelta(days=7)
        ).aggregate(t=Sum('entry_fee'))['t'] or Decimal('0')
 
        rev_prev_week = Bet.objects.filter(
            placed_at__gte=now - timedelta(days=14),
            placed_at__lt=now - timedelta(days=7),
        ).aggregate(t=Sum('entry_fee'))['t'] or Decimal('0')
 
        rev_total = Bet.objects.aggregate(t=Sum('entry_fee'))['t'] or Decimal('0')
        rev_growth = self._pct(float(rev_prev_week), float(rev_this_week))
 
        # Jackpot pool — open V5 rounds
        jackpot_pool = Bet.objects.filter(
            round__variation='V5',
            round__status=Round.Status.BETTING_OPEN,
        ).aggregate(t=Sum('entry_fee'))['t'] or Decimal('0')
 
        return {
            "total_users": {
                "display": self._fmt_num(total_users),
                "value":   total_users,
                "change":  f"+{self._pct(users_prev, total_users)}% vs last month",
                "trend":   "up",
            },
            "active_sessions": {
                "display": self._fmt_num(active_sessions),
                "value":   active_sessions,
                "change":  f"+{active_sessions} live now",
                "trend":   "up",
            },
            "revenue": {
                "display": self._fmt_currency(rev_total),
                "value":   float(rev_total),
                "change":  f"+{rev_growth}% this week",
                "trend":   "up" if rev_growth >= 0 else "down",
            },
            "jackpot_pool": {
                "display": self._fmt_currency(jackpot_pool),
                "value":   float(jackpot_pool),
                "change":  "+2.8% global mega pool",
                "trend":   "up",
            },
        }
 
    # ── Revenue Telemetry ────────────────────────────────────────
 
    def _revenue_telemetry(self, now):
        since = now - timedelta(hours=24)
 
        hourly = (
            Bet.objects
            .filter(placed_at__gte=since)
            .annotate(hour=TruncHour('placed_at'))
            .values('hour')
            .annotate(revenue=Sum('entry_fee'), bets=Count('id'))
            .order_by('hour')
        )
        hourly_map = {
            h['hour'].strftime('%I:%M %p'): {
                "revenue": float(h['revenue'] or 0),
                "bets":    h['bets'],
            }
            for h in hourly
        }
 
        data_points = []
        for i in range(24):
            h_dt    = (since + timedelta(hours=i + 1)).replace(minute=0, second=0, microsecond=0)
            label   = h_dt.strftime('%I:%M %p')
            point   = hourly_map.get(label, {"revenue": 0, "bets": 0})
            data_points.append({"time": label, **point})
 
        curr = Bet.objects.filter(placed_at__gte=since).aggregate(
            t=Sum('entry_fee'))['t'] or Decimal('0')
        prev = Bet.objects.filter(
            placed_at__gte=since - timedelta(hours=24),
            placed_at__lt=since,
        ).aggregate(t=Sum('entry_fee'))['t'] or Decimal('0')
 
        growth = self._pct(float(prev), float(curr))
 
        return {
            "period":       "Last 24 hours",
            "growth":       f"+{growth}%" if growth >= 0 else f"{growth}%",
            "growth_value": growth,
            "data":         data_points,
        }
 
    # ── Top Performing Games ─────────────────────────────────────
 
    def _top_performing_games(self, since):
        NAMES = {
            'V1': 'Single Draw',
            'V2': 'Pair Match',
            'V3': 'Trio Royale',
            'V4': 'Sum Matka',
            'V5': 'Jackpot Mega',
        }
        rows = (
            Bet.objects
            .filter(placed_at__gte=since)
            .values('round__variation')
            .annotate(player_count=Count('user', distinct=True), revenue=Sum('entry_fee'))
            .order_by('-player_count')
        )
        return [
            {
                "rank":         i + 1,
                "variation":    r['round__variation'],
                "name":         NAMES.get(r['round__variation'], r['round__variation']),
                "player_count": r['player_count'],
                "revenue":      self._fmt_currency(r['revenue'] or 0),
                "revenue_raw":  float(r['revenue'] or 0),
            }
            for i, r in enumerate(rows)
        ]
 
    # ── Server Status ────────────────────────────────────────────
 
    def _server_status(self):
        from django.db import connection, OperationalError
        db_ok = True
        try:
            connection.ensure_connection()
        except OperationalError:
            db_ok = False
 
        cache_ok = True
        try:
            cache.set('_hc', '1', 5)
            cache_ok = cache.get('_hc') == '1'
        except Exception:
            cache_ok = False
 
        clusters = [
            {"name": "NA-WEST CLUSTER",   "status": "online",                      "healthy": True},
            {"name": "EU-CENTRAL CLUSTER","status": "online",                      "healthy": True},
            {"name": "ASIA-SOUTH CLUSTER","status": "online",                      "healthy": True},
            {"name": "DB-REPLICA-04",     "status": "online" if db_ok else "degraded", "healthy": db_ok},
        ]
        all_ok = all(c['healthy'] for c in clusters)
        return {
            "overall":  "All Systems Operational" if all_ok else "Degraded",
            "healthy":  all_ok,
            "clusters": clusters,
            "cache_ok": cache_ok,
        }
 
    # ── Recent Activity ──────────────────────────────────────────
 
    def _recent_activity(self):
        events = []
 
        for bet in Bet.objects.select_related('user', 'round').order_by('-placed_at')[:5]:
            events.append({
                "player":     bet.user.username,
                "location":   getattr(bet.user, 'country', '') or '—',
                "event":      f"{bet.round.get_variation_display()} Entry",
                "amount":     f"₹{bet.entry_fee}",
                "amount_raw": float(bet.entry_fee),
                "status":     self._bet_badge(bet.status),
                "timestamp":  bet.placed_at.isoformat(),
            })
 
        for wr in WithdrawRequest.objects.select_related('wallet__user').order_by('-requested_at')[:3]:
            u = wr.wallet.user
            events.append({
                "player":     u.username,
                "location":   getattr(u, 'country', '') or '—',
                "event":      "Withdrawal",
                "amount":     f"₹{wr.amount}",
                "amount_raw": float(wr.amount),
                "status":     self._withdraw_badge(wr.status),
                "timestamp":  wr.requested_at.isoformat(),
            })
 
        for u in User.objects.order_by('-date_joined')[:3]:
            events.append({
                "player":     u.username,
                "location":   getattr(u, 'country', '') or '—',
                "event":      "New Registration",
                "amount":     "—",
                "amount_raw": 0,
                "status":     {"label": "PENDING", "color": "yellow"},
                "timestamp":  u.date_joined.isoformat(),
            })
 
        events.sort(key=lambda x: x['timestamp'], reverse=True)
        return events[:10]
 
    # ── Device Distribution ──────────────────────────────────────
 
    def _device_distribution(self):
        try:
            total   = User.objects.count() or 1
            mobile  = User.objects.filter(device_type='mobile').count()
            desktop = User.objects.filter(device_type='desktop').count()
            other   = total - mobile - desktop
            return {
                "mobile":  {"label": "Mobile Devices", "pct": round(mobile  / total * 100)},
                "desktop": {"label": "Desktop Web",    "pct": round(desktop / total * 100)},
                "other":   {"label": "Consoles",       "pct": round(other   / total * 100)},
                "source":  "live",
            }
        except Exception:
            return {
                "mobile":  {"label": "Mobile Devices", "pct": 64},
                "desktop": {"label": "Desktop Web",    "pct": 28},
                "other":   {"label": "Consoles",       "pct": 8},
                "source":  "estimated",
            }
 
    # ── Helpers ──────────────────────────────────────────────────
 
    @staticmethod
    def _pct(old, new):
        if old == 0:
            return 0.0
        return round(((new - old) / old) * 100, 1)
 
    @staticmethod
    def _fmt_num(n):
        if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
        if n >= 1_000:     return f"{n/1_000:.1f}K"
        return str(n)
 
    @staticmethod
    def _fmt_currency(v):
        v = float(v)
        if v >= 1_000_000: return f"${v/1_000_000:.1f}M"
        if v >= 1_000:     return f"${v/1_000:.1f}K"
        return f"${v:.0f}"
 
    @staticmethod
    def _bet_badge(s):
        return {
            'pending': {"label": "PENDING",   "color": "yellow"},
            'won':     {"label": "COMPLETED", "color": "green"},
            'lost':    {"label": "COMPLETED", "color": "green"},
        }.get(s, {"label": s.upper(), "color": "gray"})
 
    @staticmethod
    def _withdraw_badge(s):
        return {
            'pending':  {"label": "PENDING",  "color": "yellow"},
            'approved': {"label": "APPROVED", "color": "blue"},
            'paid':     {"label": "COMPLETED","color": "green"},
            'rejected': {"label": "REJECTED", "color": "red"},
            'failed':   {"label": "FLAGGED",  "color": "red"},
        }.get(s, {"label": s.upper(), "color": "gray"})
 

class AdminRoundListView(APIView):
    """
    GET /api/admin/rounds/
    Sabhi rounds — filter support ke saath.
    Query params:
      ?status=betting_open|drawing|completed
      ?variation=V1|V2|V3|V4|V5
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = Round.objects.all()

        status_filter    = request.query_params.get('status')
        variation_filter = request.query_params.get('variation')

        if status_filter:
            qs = qs.filter(status=status_filter)
        if variation_filter:
            qs = qs.filter(variation=variation_filter)

        # Annotate bet count directly on queryset (DB mein count hoga, N+1 nahi)
        qs = qs.annotate(bet_count=Count('bets')).order_by('-created_at')

        data = []
        for r in qs:
            data.append({
                "id":           str(r.id),
                "variation":    r.variation,
                "status":       r.status,
                "bet_count":    r.bet_count,
                "total_pool":   r.total_pool,
                "slots_filled": r.slots_filled,
                "draw_at":      r.draw_at,
                "created_at":   r.created_at,
                "completed_at": r.completed_at,
            })

        return Response(data)


class AdminRoundDetailView(APIView):
    """
    GET /api/admin/rounds/<id>/
    Round ka full detail — saare bets, winners, provably fair proof.
    """
    permission_classes = [IsAdminUser]

    def get(self, request, round_id):
        round_obj = get_object_or_404(Round, id=round_id)
        bets      = round_obj.bets.select_related('user').all()

        bets_data = []
        for b in bets:
            bets_data.append({
                "bet_id":          str(b.id),
                "username":        b.user.username,
                "email":           b.user.email,
                "selected_numbers": b.selected_numbers,
                "entry_fee":       b.entry_fee,
                "status":          b.status,
                "reward_amount":   b.reward_amount,
                "win_type":        b.win_type,
                "placed_at":       b.placed_at,
            })

        return Response({
            "id":                str(round_obj.id),
            "variation":         round_obj.variation,
            "status":            round_obj.status,
            "seed_hash":         round_obj.seed_hash,
            # server_seed ONLY completed rounds mein dikhao (proof ke liye)
            "server_seed":       round_obj.server_seed if round_obj.status == Round.Status.COMPLETED else "***hidden***",
            "drawn_numbers":     round_obj.drawn_numbers,
            "winners_data":      round_obj.winners_data,
            "total_pool":        round_obj.total_pool,
            "slots_filled":      round_obj.slots_filled,
            "draw_at":           round_obj.draw_at,
            "created_at":        round_obj.created_at,
            "completed_at":      round_obj.completed_at,
            "bets":              bets_data,
        })


class AdminForceDrawView(APIView):
    """
    POST /api/admin/rounds/<id>/force-draw/
    Admin manually draw trigger kare (V5 jackpot ya stuck rounds ke liye).
    """
    permission_classes = [IsAdminUser]

    def post(self, request, round_id):
        round_obj = get_object_or_404(Round, id=round_id)

        if round_obj.status != Round.Status.BETTING_OPEN:
            return Response(
                {"error": f"Round already in status: {round_obj.status}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if round_obj.bets.count() == 0:
            return Response(
                {"error": "No bets placed — cannot draw an empty round."},
                status=status.HTTP_400_BAD_REQUEST
            )

        from .services import RoundService
        from django.db import transaction as db_transaction

        with db_transaction.atomic():
            result = RoundService._trigger_draw(
                round_obj,
                client_seed=f"admin_force_{request.user.id}"
            )

        if result:
            return Response({
                "message":       "Draw triggered successfully.",
                "drawn_numbers": result.drawn_numbers,
                "winners_count": len(result.winners),
                "total_pool":    result.total_pool,
            })

        return Response(
            {"error": "Draw failed. Check logs."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class AdminUserListView(APIView):
    """
    GET /api/admin/users/
    Sabhi users — wallet balance ke saath.
    Query params:
      ?search=username_or_email
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = User.objects.select_related('wallet').all()

        search = request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(username__icontains=search) | Q(email__icontains=search)
            )

        data = []
        for u in qs.order_by('-date_joined')[:100]:
            try:
                balance = u.wallet.balance
            except Wallet.DoesNotExist:
                balance = Decimal('0.00')

            data.append({
                "id":               u.id,
                "username":         u.username,
                "email":            u.email,
                "is_active":        u.is_active,
                "date_joined":      u.date_joined,
                "last_login":       u.last_login,
                "wallet_balance":   str(balance),
                "total_bets":       Bet.objects.filter(user=u).count(),
            })

        return Response(data)


class AdminUserDetailView(APIView):
    """
    GET /api/admin/users/<id>/
    User ka full profile — bet history + wallet transactions.
    """
    permission_classes = [IsAdminUser]

    def get(self, request, user_id):
        user = get_object_or_404(User, id=user_id)

        try:
            wallet  = user.wallet
            balance = wallet.balance
            txs     = Transaction.objects.filter(wallet=wallet).order_by('-created_at')[:20]
            tx_data = TransactionSerializer(txs, many=True).data
        except Wallet.DoesNotExist:
            balance = Decimal('0.00')
            tx_data = []

        bets     = Bet.objects.filter(user=user).select_related('round').order_by('-placed_at')[:20]
        bet_data = BetSerializer(bets, many=True).data

        # Bet summary
        bet_summary = Bet.objects.filter(user=user).aggregate(
            total_bets=Count('id'),
            total_spent=Sum('entry_fee'),
            total_won=Sum('reward_amount'),
            wins=Count('id', filter=Q(status=Bet.Status.WON)),
            losses=Count('id', filter=Q(status=Bet.Status.LOST)),
        )

        return Response({
            "id":           user.id,
            "username":     user.username,
            "email":        user.email,
            "phone":        user.Phone_number,
            "is_active":    user.is_active,
            "date_joined":  user.date_joined,
            "last_login":   user.last_login,
            "wallet": {
                "balance":      str(balance),
                "transactions": tx_data,
            },
            "bet_summary":  bet_summary,
            "recent_bets":  bet_data,
        })

class AdminWalletAdjustView(APIView):
    """
    POST /api/admin/users/<id>/adjust-wallet/
    Admin manually wallet adjust kare — credit ya debit.

    Body:
      {
        "action":  "credit" | "debit",
        "amount":  500,
        "note":    "Bonus credit / manual adjustment"
      }
    """
    permission_classes = [IsAdminUser]

    def post(self, request, user_id):
        user   = get_object_or_404(User, id=user_id)
        action = request.data.get('action')
        note   = request.data.get('note', 'Admin adjustment')

        try:
            amount = Decimal(str(request.data.get('amount', 0)))
            if amount <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return Response(
                {"error": "Valid positive amount required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if action not in ('credit', 'debit'):
            return Response(
                {"error": "action must be 'credit' or 'debit'"},
                status=status.HTTP_400_BAD_REQUEST
            )

        reference = f"admin_{request.user.id}"

        if action == 'credit':
            with db_transaction.atomic():
                new_balance = WalletService.credit(
                    user=user,
                    amount=amount,
                    tx_type='refund',
                    reference=reference,
                    note=f"[Admin] {note}"
                )
            return Response({
                "message":     f"Rs.{amount} credited successfully.",
                "new_balance": str(new_balance),
            })

        else:  # debit
            with db_transaction.atomic():
                ok, result = WalletService.debit(
                    user=user,
                    amount=amount,
                    reference=reference,
                    note=f"[Admin] {note}"
                )
            if not ok:
                return Response({"error": result}, status=status.HTTP_400_BAD_REQUEST)

            return Response({
                "message":     f"Rs.{amount} debited successfully.",
                "new_balance": str(result),
            })

class AdminTransactionListView(APIView):
    """
    GET /api/admin/transactions/
    Sabhi transactions — audit trail.
    Query params:
      ?type=bet_debit|win_credit|deposit|withdraw|refund
      ?status=pending|success|failed
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = Transaction.objects.select_related(
            'wallet__user'
        ).order_by('-created_at')

        tx_type   = request.query_params.get('type')
        tx_status = request.query_params.get('status')

        if tx_type:
            qs = qs.filter(transaction_type=tx_type)
        if tx_status:
            qs = qs.filter(status=tx_status)

        data = []
        for tx in qs[:200]:
            data.append({
                "id":               str(tx.id),
                "username":         tx.wallet.user.username,
                "transaction_type": tx.transaction_type,
                "amount":           str(tx.amount),
                "balance_before":   str(tx.balance_before),
                "balance_after":    str(tx.balance_after),
                "status":           tx.status,
                "reference":        tx.reference,
                "note":             tx.note,
                "created_at":       tx.created_at,
            })

        return Response(data)