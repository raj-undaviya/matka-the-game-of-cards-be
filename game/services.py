"""
game/services.py  (UPDATED)
=============================
Changes vs previous version:
  + notify_slot_update() — bet place hone ke baad WebSocket broadcast
  + place_bet() return value updated: (True, (bet_id, round_obj))
"""
import uuid
import logging
import re
from decimal import Decimal
from datetime import timedelta, time

from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from .models import Round, Bet, Game, Pool, PoolParticipant
from wallet.models import Wallet, Transaction
from core.rng_engine import ProvablyFairRNG, SeedCommitment
from core.game_engine import (
    GameEngine, GameVariation, BetRecord,
    GAME_CONFIGS, RoundResult
)
from core.email_service import EmailService

User = get_user_model()
engine = GameEngine()
logger = logging.getLogger(__name__)

TX_BET_DEBIT  = 'bet_debit'
TX_WIN_CREDIT = 'win_credit'
TX_REFUND     = 'refund'


# ─────────────────────────────────────────
# WebSocket Notifier
# ─────────────────────────────────────────

def notify_slot_update(round_obj: Round):
    """
    Bet place hone ke baad sabhi connected WebSocket clients ko
    updated slot count push karo.

    IMPORTANT: Yeh @transaction.atomic ke BAHAR call hota hai
    (view mein, place_bet return ke baad) — DB commit guarantee hai.
    Agar atomic block ke andar call karo toh race condition possible hai.
    """
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        from .consumers import ROUNDS_GROUP

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            ROUNDS_GROUP,
            {
                "type":             "slot_update",
                "round_id":         str(round_obj.id),
                "variation":        round_obj.variation,
                "slots_filled":     round_obj.slots_filled,
                "slots_available":  round_obj.slots_available,
                "status":           round_obj.status,
            }
        )
    except Exception as e:
        logger.warning(f"WebSocket notify failed for round {round_obj.id}: {e}")


# ─────────────────────────────────────────
# Wallet Service
# ─────────────────────────────────────────

class WalletService:

    @staticmethod
    def get_or_create(user) -> Wallet:
        wallet, _ = Wallet.objects.get_or_create(user=user)
        return wallet

    @staticmethod
    def debit(user, amount, reference: str, note: str = '') -> tuple:
        wallet, _ = Wallet.objects.select_for_update().get_or_create(user=user)
        amount = Decimal(str(amount))

        if wallet.balance < amount:
            return False, f"Insufficient balance. Available: Rs.{wallet.balance}"

        before = wallet.balance
        wallet.balance -= amount
        wallet.save()

        Transaction.objects.create(
            wallet=wallet,
            transaction_type=TX_BET_DEBIT,
            amount=amount,
            balance_before=before,
            balance_after=wallet.balance,
            status='success',
            reference=str(reference)[:100],
            note=note,
        )
        return True, wallet.balance

    @staticmethod
    def credit(user, amount, tx_type: str, reference: str, note: str = ''):
        wallet, _ = Wallet.objects.select_for_update().get_or_create(user=user)
        amount = Decimal(str(amount))

        before = wallet.balance
        wallet.balance += amount
        wallet.save()

        Transaction.objects.create(
            wallet=wallet,
            transaction_type=tx_type,
            amount=amount,
            balance_before=before,
            balance_after=wallet.balance,
            status='success',
            reference=str(reference)[:100],
            note=note,
        )
        return wallet.balance


# ─────────────────────────────────────────
# Round Service
# ─────────────────────────────────────────

class RoundService:

    @staticmethod
    def create_round(variation: str) -> Round:
        game_var = GameVariation(variation)
        round_id_str = str(uuid.uuid4())
        server_seed, commitment = ProvablyFairRNG.create_commitment(round_id_str)

        draw_at = None
        if game_var == GameVariation.JACKPOT:
            from datetime import timedelta
            draw_at = timezone.now() + timedelta(minutes=10)

        round_obj = Round.objects.create(
            id=uuid.UUID(round_id_str),
            variation=variation,
            status=Round.Status.BETTING_OPEN,
            server_seed=server_seed,
            seed_hash=commitment.server_seed_hash,
            draw_at=draw_at
        )
        print("Round Created ->", round_obj.id, round_obj)
        return round_obj

    @staticmethod
    @transaction.atomic
    def place_bet(round_id: str, user, selected_numbers: list, entry_fee) -> tuple:
        """
        Returns:
          (False, "error message")
          (True,  (bet_id_str, round_obj))  ← round_obj notify ke liye
        """
        round_obj = None
        # 1. Try finding round by UUID
        try:
            round_obj = Round.objects.select_for_update().get(id=uuid.UUID(str(round_id)))
            print("Round 1 Found ->", round_obj.id, round_obj)
        except Exception:
            try:
                round_obj = Round.objects.select_for_update().get(id=round_id)
                print("Round 2 Found ->", round_obj.id, round_obj)
            except Exception:
                pass

        # 2. If not found, check if round_id is actually a Pool ID
        if not round_obj:
            pool = None
            try:
                pool = Pool.objects.get(id=round_id)
            except Exception:
                try:
                    from bson import ObjectId
                    pool = Pool.objects.get(id=ObjectId(round_id))
                except Exception:
                    pool = None

            if pool:
                round_obj = pool.rounds.select_for_update().filter(status=Round.Status.BETTING_OPEN).order_by('-round_number').first()
                print("Round 3 Found ->", round_obj.id, round_obj)
                if not round_obj:
                    round_obj = PoolService.create_next_round(pool, 1)
                    print("Round 4 Found ->", round_obj.id, round_obj)

        if not round_obj:
            return False, "Round not found."

        if round_obj.status != Round.Status.BETTING_OPEN:
            return False, "Betting is closed for this round."

        # If it's a pool, check if player is a participant; auto-join if not yet joined
        if round_obj.pool:
            if not round_obj.pool.participants.filter(user=user).exists():
                ok, res = PoolService.join_pool(str(round_obj.pool.id), user)
                if not ok:
                    return False, res

        game_var = GameVariation(round_obj.variation)
        config = GAME_CONFIGS[game_var]

        max_slots = round_obj.pool.max_players if round_obj.pool else config.max_slots
        current_count = round_obj.bets.count()
        if current_count >= max_slots:
            return False, "Round is full."

        if game_var != GameVariation.JACKPOT:
            if round_obj.bets.filter(user=user).exists():
                return False, "You already placed a bet in this round."

        temp_bet = BetRecord(
            user_id=str(user.id),
            round_id=str(round_obj.id),
            variation=game_var,
            selected_numbers=selected_numbers,
            entry_fee=int(entry_fee),
            bet_id=str(uuid.uuid4())
        )
        valid, msg = engine.validate_bet(temp_bet)
        if not valid:
            return False, msg

        if not round_obj.pool:
            ok, result = WalletService.debit(
                user=user,
                amount=entry_fee,
                reference=str(round_obj.id),
                note=f"Bet on round {str(round_obj.id)[:8]} ({round_obj.variation})"
            )
            if not ok:
                return False, result

        bet = Bet.objects.create(
            round=round_obj,
            user=user,
            selected_numbers=selected_numbers,
            entry_fee=Decimal(str(entry_fee)),
            status=Bet.Status.PENDING
        )

        if round_obj.pool:
            RoundService._simulate_pool_competitor_bets(round_obj, exclude_user=user)
            RoundService._trigger_draw(round_obj)
        elif game_var != GameVariation.JACKPOT:
            RoundService._simulate_standard_round_bets(round_obj, exclude_user=user)
            RoundService._trigger_draw(round_obj)

        round_obj.refresh_from_db()
        return True, (str(bet.id), round_obj)

    @staticmethod
    def _ensure_pool_bots(pool: Pool, target_count: int = None):
        """Ensure up to target_count (default pool.max_players or 150) simulated competitor players exist in this pool."""
        if target_count is None:
            target_count = min(150, pool.max_players or 150)
            
        current_count = pool.participants.count()
        needed = target_count - current_count
        if needed <= 0:
            return

        bot_names = [
            "Vikram_Ace", "Pooja_Sharma", "Rajesh_Matka", "Anil_K", "Kavita_99",
            "Deepak_King", "Sunil_Pro", "Ritu_Queen", "Amit_Roy", "Neha_Singh",
            "Sanjay_D", "Priya_Patel", "Manish_Kumar", "Simran_K", "Rohit_Sharma",
            "Sneha_Verma", "Vikas_Jain", "Anjali_Mehta", "Karan_Malhotra", "Shweta_Rao"
        ]
        for i in range(needed):
            base_name = bot_names[i % len(bot_names)]
            bot_username = f"{base_name}_{i+1}" if i >= len(bot_names) else base_name
            bot_email = f"{bot_username.lower()}@matka.com"
            bot_user, _ = User.objects.get_or_create(username=bot_username, defaults={'email': bot_email, 'is_active': True})
            WalletService.get_or_create(bot_user)
            if not pool.participants.filter(user=bot_user).exists():
                PoolParticipant.objects.create(pool=pool, user=bot_user, total_points=0)

    @staticmethod
    def _simulate_pool_competitor_bets(round_obj: Round, exclude_user):
        """Generate random bets for bot participants in the pool for this round."""
        import random
        pool = round_obj.pool
        if not pool:
            return
        RoundService._ensure_pool_bots(pool)
        game_var = GameVariation(round_obj.variation)
        req_numbers = {
            GameVariation.SINGLE: 1,
            GameVariation.PAIR: 2,
            GameVariation.TRIO: 3,
            GameVariation.SUM_MATKA: 1,
            GameVariation.JACKPOT: 1,
        }.get(game_var, 1)

        participants = pool.participants.exclude(user=exclude_user).select_related('user')
        for part in participants:
            if not round_obj.bets.filter(user=part.user).exists():
                nums = [random.randint(1, 10) for _ in range(req_numbers)]
                Bet.objects.create(
                    round=round_obj,
                    user=part.user,
                    selected_numbers=nums,
                    entry_fee=Decimal(str(pool.entry_fee)),
                    status=Bet.Status.PENDING
                )

    @staticmethod
    def _simulate_standard_round_bets(round_obj: Round, exclude_user):
        """Simulate remaining slots for standard round so single player game completes immediately."""
        import random
        game_var = GameVariation(round_obj.variation)
        config = GAME_CONFIGS[game_var]
        req_numbers = {
            GameVariation.SINGLE: 1,
            GameVariation.PAIR: 2,
            GameVariation.TRIO: 3,
            GameVariation.SUM_MATKA: 1,
            GameVariation.JACKPOT: 1,
        }.get(game_var, 1)

        needed = max(0, config.max_slots - round_obj.bets.count())
        if needed > 0:
            for i in range(1, needed + 1):
                b_user, _ = User.objects.get_or_create(username=f"Player_{i}", defaults={'email': f"p{i}@matka.com", 'is_active': True})
                WalletService.get_or_create(b_user)
                if not round_obj.bets.filter(user=b_user).exists():
                    nums = [random.randint(1, 10) for _ in range(req_numbers)]
                    Bet.objects.create(
                        round=round_obj,
                        user=b_user,
                        selected_numbers=nums,
                        entry_fee=Decimal(str(config.entry_fee)),
                        status=Bet.Status.PENDING
                    )

    @staticmethod
    @transaction.atomic
    def _trigger_draw(round_obj: Round, client_seed: str = "global"):
        if round_obj.status != Round.Status.BETTING_OPEN:
            return

        round_obj.status = Round.Status.DRAWING
        round_obj.save(update_fields=['status'])

        commitment = SeedCommitment(
            round_id=str(round_obj.id),
            server_seed_hash=round_obj.seed_hash,
            created_at=round_obj.created_at.isoformat()
        )

        game_var = GameVariation(round_obj.variation)
        bet_records = [
            BetRecord(
                user_id=str(b.user_id),
                round_id=str(round_obj.id),
                variation=game_var,
                selected_numbers=b.selected_numbers,
                entry_fee=int(b.entry_fee),
                bet_id=str(b.id)
            )
            for b in round_obj.bets.select_related('user').all()
        ]

        result: RoundResult = engine.resolve_round(
            round_id=str(round_obj.id),
            variation=game_var,
            bets=bet_records,
            server_seed=round_obj.server_seed,
            commitment=commitment,
            client_seed=client_seed
        )

        round_obj.drawn_numbers = result.drawn_numbers
        round_obj.winners_data = {
            "winners": result.winners,
            "total_pool": str(result.total_pool),
            "provably_fair_proof": result.verified_seed
        }
        round_obj.status = Round.Status.COMPLETED
        round_obj.completed_at = timezone.now()
        round_obj.save(update_fields=[
            'drawn_numbers', 'winners_data', 'status', 'completed_at'
        ])

        winner_map = {w['user_id']: w for w in result.winners}
        drawn_raw = round_obj.drawn_numbers or []

        for bet in round_obj.bets.select_related('user').all():
            uid = str(bet.user_id)
            user_selected = bet.selected_numbers or []

            if round_obj.pool:
                points = 0
                if game_var == GameVariation.PAIR:
                    # User selects 2 cards, 2 cards drawn
                    # If 1 card matches -> 50 pts, if 2 cards match -> 100 pts, else 0 pts
                    matched_count = sum(1 for n in user_selected if n in drawn_raw)
                    if matched_count == 1:
                        points = 50
                    elif matched_count >= 2:
                        points = 100
                    else:
                        points = 0
                elif game_var == GameVariation.SINGLE:
                    if len(drawn_raw) > 0 and len(user_selected) > 0 and user_selected[0] == drawn_raw[0]:
                        points = 50
                    else:
                        points = 0
                elif game_var == GameVariation.TRIO:
                    matched_count = sum(1 for n in user_selected if n in drawn_raw)
                    if matched_count == 3:
                        points = 150
                    elif matched_count > 0:
                        points = matched_count * 50
                    else:
                        points = 0
                elif game_var == GameVariation.SUM_MATKA:
                    sum_val = sum(drawn_raw) % 10
                    target_digit = 10 if sum_val == 0 else sum_val
                    if len(user_selected) > 0 and user_selected[0] == target_digit:
                        points = 50
                    else:
                        points = 0
                elif game_var == GameVariation.JACKPOT:
                    if len(drawn_raw) > 0 and len(user_selected) > 0 and user_selected[0] == drawn_raw[0]:
                        points = 50
                    else:
                        points = 0

                bet.points_earned = points
                if points > 0:
                    bet.status = Bet.Status.WON
                    bet.reward_amount = Decimal(str(points))
                else:
                    bet.status = Bet.Status.LOST
                    bet.reward_amount = Decimal('0.00')
                bet.save(update_fields=['status', 'reward_amount', 'points_earned'])
            else:
                if uid in winner_map:
                    win_data = winner_map[uid]
                    bet.status = Bet.Status.WON
                    bet.reward_amount = Decimal(str(win_data['reward_amount']))
                    bet.win_type = win_data['win_type']
                    bet.points_earned = int(win_data['reward_amount'])
                    bet.save(update_fields=['status', 'reward_amount', 'win_type', 'points_earned'])

                    WalletService.credit(
                        user=bet.user,
                        amount=win_data['reward_amount'],
                        tx_type=TX_WIN_CREDIT,
                        reference=str(round_obj.id),
                        note=f"Won {win_data['win_type']} — Round {str(round_obj.id)[:8]}"
                    )
                else:
                    bet.status = Bet.Status.LOST
                    bet.points_earned = 0
                    bet.save(update_fields=['status', 'points_earned'])

        if round_obj.pool:
            pool = round_obj.pool
            from django.db.models import Sum
            # Update participants' points
            for participant in pool.participants.all():
                total_pts = Bet.objects.filter(
                    round__pool=pool,
                    user=participant.user,
                    status=Bet.Status.WON
                ).aggregate(total=Sum('points_earned'))['total'] or 0
                participant.total_points = total_pts
                participant.save(update_fields=['total_points'])

            # Rank participants
            pool_participants = list(pool.participants.order_by('-total_points', 'joined_at'))
            for idx, part in enumerate(pool_participants):
                part.rank = idx + 1
                part.save(update_fields=['rank'])

            # Check if this was the last round
            if round_obj.round_number >= pool.rounds_count:
                PoolService.resolve_pool(pool)
            else:
                PoolService.create_next_round(pool, round_obj.round_number + 1)

        return result

    @staticmethod
    def trigger_jackpot_draw(round_id: str):
        try:
            with transaction.atomic():
                round_obj = Round.objects.select_for_update().get(
                    id=round_id,
                    variation=Round.Variation.JACKPOT,
                    status=Round.Status.BETTING_OPEN
                )
                return RoundService._trigger_draw(round_obj, client_seed="jackpot_timer")
        except Round.DoesNotExist:
            return None


class PoolService:

    @staticmethod
    @transaction.atomic
    def join_pool(pool_id: str, user) -> tuple:
        """
        Deduct entry fee from wallet and create PoolParticipant.
        Enforces 150 player capacity, 1 play per day for Daily Mega Pool.
        """
        pool = None
        try:
            pool = Pool.objects.select_for_update().get(id=pool_id)
        except Exception:
            try:
                from bson import ObjectId
                pool = Pool.objects.select_for_update().get(id=ObjectId(pool_id))
            except Exception:
                return False, "Pool not found."

        if not pool:
            return False, "Pool not found."

        if pool.status not in (Pool.Status.UPCOMING, Pool.Status.ACTIVE):
            return False, "Cannot join. Pool is already completed."

        if pool.participants.count() >= pool.max_players:
            return False, f"Pool is full ({pool.max_players}/{pool.max_players} players max)."

        # Check single entry per pool
        if pool.participants.filter(user=user).exists():
            return False, "You have already joined this pool."

        # Check once-per-day constraint for Daily Mega Pool
        if pool.once_per_day or pool.is_daily_mega or pool.pool_type == 'mega_daily':
            today = timezone.localdate()
            has_played_today = PoolParticipant.objects.filter(
                pool__is_daily_mega=True,
                user=user,
                joined_at__date=today
            ).exists() or PoolParticipant.objects.filter(
                pool=pool,
                user=user,
                joined_at__date=today
            ).exists()
            if has_played_today:
                return False, "You can only participate in the Daily Mega Pool once per day. It will open again tomorrow at 1:30 PM."

        # Debit entry fee from user wallet
        ok, result = WalletService.debit(
            user=user,
            amount=pool.entry_fee,
            reference=f"pool_join:{pool.id}",
            note=f"Joined pool {pool.name} (Entry fee: ₹{pool.entry_fee})"
        )
        if not ok:
            return False, result

        participant = PoolParticipant.objects.create(
            pool=pool,
            user=user
        )
        RoundService._ensure_pool_bots(pool)

        return True, participant

    @staticmethod
    @transaction.atomic
    def start_pool(pool_id: str) -> bool:
        pool = None
        try:
            pool = Pool.objects.select_for_update().get(id=pool_id)
        except Exception:
            try:
                from bson import ObjectId
                pool = Pool.objects.select_for_update().get(id=ObjectId(pool_id))
            except Exception:
                return False

        if not pool or pool.status != Pool.Status.UPCOMING:
            return False

        pool.status = Pool.Status.ACTIVE
        pool.start_time = timezone.now()
        # Set 5 minutes duration countdown if not set
        if not pool.expires_at or pool.expires_at <= timezone.now():
            pool.expires_at = timezone.now() + timedelta(minutes=pool.duration_minutes or 5)
        pool.save(update_fields=['status', 'start_time', 'expires_at'])

        # Create round 1 if not exists
        if not pool.rounds.filter(status=Round.Status.BETTING_OPEN).exists():
            PoolService.create_next_round(pool, 1)
        return True

    @staticmethod
    def sync_pools_for_variation(variation: str):
        """
        Ensures there is an active upcoming pool for this variation.
        If the current upcoming pool's countdown has expired (expires_at <= now),
        it automatically completes the round/pool and generates the next Slot pool (Dream11 style).
        Also initializes / maintains the Daily Mega Pool for Pair Selection (V2).
        """
        import datetime
        now = timezone.now()
        game = Game.objects.filter(variation=variation, is_active=True).first()
        if not game:
            names = {
                'V1': 'SINGLE CARD GAME',
                'V2': 'PAIR SELECTION',
                'V3': 'TRIO GAME TION AU',
                'V4': 'LAST DIGIT SUM',
                'V5': 'LUCKLY DRAW JACCPOT',
            }
            rewards = {'V1': '30x', 'V2': '20x', 'V3': '32x', 'V4': '33x', 'V5': '23x'}
            sub_titles = {'V1': 'ENTRY FEES.🪙100', 'V2': 'ENTRY FEES.🪙100', 'V3': 'ENTRY FEES.🪙100', 'V4': 'ENTRY FEES.🪙100', 'V5': 'ENTRY FEES.🪙100'}
            pool_vals = {'V1': '🪙2,109', 'V2': '🪙2,105', 'V3': '🪙2,105', 'V4': '🪙875', 'V5': '🪙805'}
            reward_labels = {'V1': '10x', 'V2': '20x', 'V3': '50x', 'V4': '80x', 'V5': '80x'}

            game = Game.objects.create(
                name=names.get(variation, f"Game {variation}"),
                variation=variation,
                sub_title=sub_titles.get(variation, 'ENTRY FEES.🪙100'),
                rewards=rewards.get(variation, '10x'),
                pool_value=pool_vals.get(variation, '🪙1,000'),
                reward_label=reward_labels.get(variation, '10x'),
                is_active=True
            )

        # ── 1. Check ALL active pools for this game and roll over expired 5-min slots ──
        all_active = list(Pool.objects.filter(
            game=game,
            status__in=[Pool.Status.UPCOMING, Pool.Status.ACTIVE]
        ))

        for existing in all_active:
            is_regular_type = existing.pool_type in ['regular_pool', 'regular_5min'] or 'Regular' in (existing.name or '')
            if is_regular_type:
                # Force regular pool parameters to strictly 5 minutes & 0 interval
                fix_needed = False
                if existing.duration_minutes != 5:
                    existing.duration_minutes = 5
                    fix_needed = True
                if existing.interval_minutes != 0:
                    existing.interval_minutes = 0
                    fix_needed = True
                if not existing.expires_at or (existing.expires_at - now).total_seconds() > 300:
                    existing.expires_at = now + timedelta(minutes=5)
                    fix_needed = True
                if fix_needed:
                    existing.save(update_fields=['duration_minutes', 'interval_minutes', 'expires_at'])

            is_full = existing.participants.count() >= existing.max_players
            is_expired = existing.expires_at and existing.expires_at <= now

            if is_full or is_expired:
                try:
                    open_round = existing.rounds.filter(status=Round.Status.BETTING_OPEN).first()
                    if open_round:
                        RoundService._trigger_draw(open_round)
                    PoolService.resolve_pool(existing)
                except Exception:
                    existing.status = Pool.Status.COMPLETED
                    existing.end_time = now
                    existing.save(update_fields=['status', 'end_time'])

                if existing.is_recurring and not existing.once_per_day:
                    next_slot = (existing.slot_number or 1) + 1
                    base_name = re.sub(r'\s*-\s*Slot\s*#\d+', '', existing.name).strip()
                    dur = 5 if is_regular_type else (existing.duration_minutes or 5)
                    if existing.pool_type == 'hourly_pool' or (existing.interval_minutes and existing.interval_minutes >= 60):
                        interval_m = existing.interval_minutes or 120
                        new_start = now + timedelta(minutes=interval_m)
                        new_expires = new_start + timedelta(minutes=dur)
                    else:
                        new_start = None
                        new_expires = now + timedelta(minutes=dur)

                    new_pool = Pool.objects.create(
                        game=game,
                        name=f"{base_name} - Slot #{next_slot}",
                        slot_number=next_slot,
                        pool_type=existing.pool_type,
                        is_daily_mega=existing.is_daily_mega,
                        entry_fee=existing.entry_fee,
                        win_prize=existing.win_prize,
                        max_players=existing.max_players,
                        duration_minutes=dur,
                        interval_minutes=0 if is_regular_type else (existing.interval_minutes or 0),
                        scheduled_start_time=new_start,
                        rounds_count=existing.rounds_count or 10,
                        round_duration_seconds=30,
                        status=Pool.Status.UPCOMING,
                        is_recurring=True,
                        daily_start_time=existing.daily_start_time,
                        once_per_day=existing.once_per_day,
                        expires_at=new_expires,
                        prize_distribution=existing.prize_distribution
                    )
                    PoolService.create_next_round(new_pool, 1)

        # ── 2. Cleanup duplicate auto-provisioned slots (regular_pool and mega_daily) ──
        seen_regular = False
        seen_mega = False
        for pool in Pool.objects.filter(game=game, status__in=[Pool.Status.UPCOMING, Pool.Status.ACTIVE]).order_by('-slot_number', '-created_at'):
            if pool.pool_type in ['regular_pool', 'regular_5min']:
                if seen_regular:
                    pool.status = Pool.Status.COMPLETED
                    pool.end_time = now
                    pool.save(update_fields=['status', 'end_time'])
                else:
                    seen_regular = True
            elif pool.pool_type == 'mega_daily' or pool.is_daily_mega:
                if seen_mega:
                    pool.status = Pool.Status.COMPLETED
                    pool.end_time = now
                    pool.save(update_fields=['status', 'end_time'])
                else:
                    seen_mega = True

        # ── 3. Standard / Mega / Regular Pool Provisioning if missing ──
        pool_definitions = [
            {
                'type': 'mega_daily',
                'name': 'Daily Mega Pool',
                'entry': 200,
                'win_prize': Decimal('12000.00'),
                'max_players': 150,
                'duration': 5,
                'interval_hours': 24,
                'rounds': 1,
                'once_per_day': True,
                'daily_start_time': time(13, 30),
                'prizes': {"1": 6000, "2": 4000, "3": 2000, "multipliers": {"1": "30x", "2": "20x", "3": "10x"}},
                'is_mega': True,
            },
            {
                'type': 'regular_pool',
                'name': 'Regular Pool',
                'entry': 10,
                'win_prize': Decimal('600.00'),
                'max_players': 500,
                'duration': 5,
                'interval_hours': 0,
                'rounds': 10,
                'once_per_day': False,
                'daily_start_time': None,
                'prizes': {"1": 300, "2": 200, "3": 100, "multipliers": {"1": "30x", "2": "20x", "3": "10x"}},
                'is_mega': False,
            },
        ]

        for pdef in pool_definitions:
            pool_type = pdef['type']
            has_active = Pool.objects.filter(
                game=game,
                pool_type=pool_type,
                status__in=[Pool.Status.UPCOMING, Pool.Status.ACTIVE]
            ).exists()

            if not has_active:
                new_expires = now + timedelta(minutes=pdef['duration'])
                new_pool = Pool.objects.create(
                    game=game,
                    name=f"{pdef['name']} - Slot #1",
                    slot_number=1,
                    pool_type=pool_type,
                    is_daily_mega=pdef['is_mega'],
                    entry_fee=pdef['entry'],
                    win_prize=pdef['win_prize'],
                    max_players=pdef['max_players'],
                    duration_minutes=pdef['duration'],
                    interval_minutes=0,
                    rounds_count=pdef['rounds'],
                    round_duration_seconds=30,
                    status=Pool.Status.UPCOMING,
                    is_recurring=True,
                    daily_start_time=pdef['daily_start_time'],
                    once_per_day=pdef['once_per_day'],
                    expires_at=new_expires,
                    prize_distribution=pdef['prizes']
                )
                PoolService.create_next_round(new_pool, 1)

        return Pool.objects.filter(game=game, status__in=[Pool.Status.UPCOMING, Pool.Status.ACTIVE]).first()

    @staticmethod
    def create_next_round(pool: Pool, round_num: int):
        """
        Creates and opens the next round in a pool.
        """
        round_id_str = str(uuid.uuid4())
        server_seed, commitment = ProvablyFairRNG.create_commitment(round_id_str)

        round_obj = Round.objects.create(
            id=uuid.UUID(round_id_str),
            variation=pool.game.variation,
            status=Round.Status.BETTING_OPEN,
            server_seed=server_seed,
            seed_hash=commitment.server_seed_hash,
            pool=pool,
            round_number=round_num
        )
        return round_obj

    @staticmethod
    @transaction.atomic
    def resolve_pool(pool: Pool):
        """
        Rank participants, pay rewards to top 3, and mark completed.
        Supports 1st: ₹6000 (30x) / 2nd: ₹4000 (20x) / 3rd: ₹2000 (10x) for Daily Mega Pool.
        """
        if pool.status == Pool.Status.COMPLETED:
            return

        participants = list(pool.participants.select_for_update().order_by('-total_points', 'joined_at'))
        total_participants = len(participants)

        if total_participants == 0:
            pool.status = Pool.Status.COMPLETED
            pool.end_time = timezone.now()
            pool.save(update_fields=['status', 'end_time'])
            return

        # Calculate ranks
        for idx, part in enumerate(participants):
            part.rank = idx + 1
            part.save(update_fields=['rank'])

        # Total pool amount / prize to distribute
        collected = Decimal(str(pool.entry_fee * total_participants))
        total_prize = pool.win_prize if (pool.win_prize and pool.win_prize > collected) else collected

        # Check for custom prize distribution (e.g. Daily Mega Pool ₹6000 / ₹4000 / ₹2000 or Regular Pool ₹300 / ₹200 / ₹100)
        custom_prizes = None
        if pool.prize_distribution and isinstance(pool.prize_distribution, dict) and '1' in pool.prize_distribution:
            custom_prizes = pool.prize_distribution
        elif pool.is_daily_mega or pool.pool_type == 'mega_daily':
            custom_prizes = {"1": 6000, "2": 4000, "3": 2000}
        elif pool.entry_fee == 10 and (pool.game.variation == 'V2' or 'Regular' in (pool.name or '')):
            custom_prizes = {"1": 300, "2": 200, "3": 100}

        percentages = [0.50, 0.30, 0.20]

        for rank_idx in range(min(3, total_participants)):
            part = participants[rank_idx]
            rank_str = str(rank_idx + 1)

            if custom_prizes and rank_str in custom_prizes:
                payout = Decimal(str(custom_prizes[rank_str]))
            else:
                payout = Decimal(str(total_prize)) * Decimal(str(percentages[rank_idx]))

            part.reward_paid = payout
            part.save(update_fields=['reward_paid'])

            # Credit wallet
            WalletService.credit(
                user=part.user,
                amount=payout,
                tx_type=TX_WIN_CREDIT,
                reference=f"pool_win:{pool.id}",
                note=f"Won rank {rank_idx + 1} in pool {pool.name} — Prize: ₹{payout}"
            )

        pool.status = Pool.Status.COMPLETED
        pool.end_time = timezone.now()
        pool.save(update_fields=['status', 'end_time'])