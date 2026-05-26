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
from django.utils import timezone
from decimal import Decimal
from django.db import transaction as db_transaction

from .models import Round, Bet
from wallet.models import Wallet, Transaction
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
    Platform ka overview — revenue, active rounds, users.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        # Revenue stats
        total_bets_amount = Bet.objects.aggregate(
            total=Sum('entry_fee')
        )['total'] or 0

        total_winnings = Bet.objects.filter(
            status=Bet.Status.WON
        ).aggregate(total=Sum('reward_amount'))['total'] or 0

        # Round stats
        rounds_by_status = {
            s: Round.objects.filter(status=s).count()
            for s, _ in Round.Status.choices
        }

        # Active rounds with slot info
        active_rounds = Round.objects.filter(
            status=Round.Status.BETTING_OPEN
        )
        active_rounds_data = []
        for r in active_rounds:
            active_rounds_data.append({
                "id":              str(r.id),
                "variation":       r.variation,
                "slots_filled":    r.slots_filled,
                "slots_available": r.slots_available,
                "total_pool":      r.total_pool,
                "draw_at":         r.draw_at,
            })

        # User stats
        total_users    = User.objects.count()
        active_today   = User.objects.filter(
            last_login__date=timezone.now().date()
        ).count()

        # Wallet stats
        total_balance  = Wallet.objects.aggregate(
            total=Sum('balance')
        )['total'] or Decimal('0.00')

        return Response({
            "revenue": {
                "total_bets_collected": total_bets_amount,
                "total_winnings_paid":  total_winnings,
                "platform_profit":      total_bets_amount - total_winnings,
            },
            "rounds": {
                "by_status":    rounds_by_status,
                "active_rounds": active_rounds_data,
            },
            "users": {
                "total":        total_users,
                "active_today": active_today,
            },
            "wallet": {
                "total_balance_in_system": str(total_balance),
            }
        })


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