"""
game/services.py  (UPDATED)
=============================
Changes vs previous version:
  + notify_slot_update() — bet place hone ke baad WebSocket broadcast
  + place_bet() return value updated: (True, (bet_id, round_obj))
"""
import uuid
import logging
from decimal import Decimal
from datetime import timedelta

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
        print(f"User of {user.id} ")
        wallet = Wallet.objects.select_for_update().get(user=user)
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
        wallet = Wallet.objects.select_for_update().get(user=user)
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
        return round_obj

    @staticmethod
    @transaction.atomic
    def place_bet(round_id: str, user, selected_numbers: list, entry_fee) -> tuple:
        """
        Returns:
          (False, "error message")
          (True,  (bet_id_str, round_obj))  ← round_obj notify ke liye
        """
        try:
            round_obj = Round.objects.select_for_update().get(id=round_id)
        except Round.DoesNotExist:
            return False, "Round not found."

        if round_obj.status != Round.Status.BETTING_OPEN:
            return False, "Betting is closed for this round."

        # If it's a pool, check if player is a participant
        if round_obj.pool:
            if not round_obj.pool.participants.filter(user=user).exists():
                return False, "You are not a participant in this pool."

        game_var = GameVariation(round_obj.variation)
        config = GAME_CONFIGS[game_var]

        max_slots = round_obj.pool.participants.count() if round_obj.pool else config.max_slots
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
            status=Bet.Status.PENDING,
            pool=round_obj.pool
        )

        new_count = current_count + 1
        if game_var != GameVariation.JACKPOT and new_count >= max_slots:
            RoundService._trigger_draw(round_obj)

        round_obj.refresh_from_db()
        return True, (str(bet.id), round_obj)

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

        for bet in round_obj.bets.select_related('user').all():
            uid = str(bet.user_id)
            if uid in winner_map:
                win_data = winner_map[uid]
                bet.status        = Bet.Status.WON
                bet.reward_amount = Decimal(str(win_data['reward_amount']))
                bet.win_type      = win_data['win_type']
                if round_obj.pool:
                    bet.points_earned = int(win_data['reward_amount'])
                bet.save(update_fields=['status', 'reward_amount', 'win_type', 'points_earned'])

                if not round_obj.pool:
                    WalletService.credit(
                        user=bet.user,
                        amount=win_data['reward_amount'],
                        tx_type=TX_WIN_CREDIT,
                        reference=str(round_obj.id),
                        note=f"Won {win_data['win_type']} — Round {str(round_obj.id)[:8]}"
                    )

                try:
                    EmailService.send_win_notification(
                        user=bet.user, bet=bet, round_obj=round_obj,
                    )
                except Exception as e:
                    logger.error(f"Win email failed for {bet.user}: {e}")
            else:
                bet.status = Bet.Status.LOST
                if round_obj.pool:
                    bet.points_earned = 0
                bet.save(update_fields=['status', 'points_earned'])

        if round_obj.pool:
            pool = round_obj.pool
            from django.db.models import Sum
            # Update participants' points
            for participant in pool.participants.all():
                total_pts = Bet.objects.filter(
                    pool=pool,
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

        if pool.status != Pool.Status.UPCOMING:
            return False, "Cannot join. Pool is already active or completed."

        if pool.participants.count() >= pool.max_players:
            return False, "Pool is full."

        if pool.participants.filter(user=user).exists():
            return False, "You have already joined this pool."

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
        pool.save(update_fields=['status', 'start_time'])

        # Create round 1
        PoolService.create_next_round(pool, 1)
        return True

    @staticmethod
    def sync_pools_for_variation(variation: str):
        """
        Ensures there is an active upcoming pool for this variation.
        If the current upcoming pool's 1-minute countdown has expired (expires_at <= now),
        it automatically completes the round/pool and generates the next Slot pool (Dream11 style).
        """
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

        # Check existing upcoming pools for this game
        upcoming_pool = Pool.objects.filter(game=game, status=Pool.Status.UPCOMING).order_by('-slot_number').first()

        if upcoming_pool:
            if upcoming_pool.expires_at and upcoming_pool.expires_at <= now:
                # 1-minute countdown expired! Complete previous slot
                upcoming_pool.status = Pool.Status.COMPLETED
                upcoming_pool.end_time = now
                upcoming_pool.save(update_fields=['status', 'end_time'])

                # Complete round attached to it if open
                open_round = upcoming_pool.rounds.filter(status=Round.Status.BETTING_OPEN).first()
                if open_round:
                    try:
                        RoundService._trigger_draw(open_round)
                    except Exception:
                        pass

                # Auto-spawn NEXT slot pool (e.g. Slot #2) with fresh 1-min countdown
                next_slot = (upcoming_pool.slot_number or 1) + 1
                duration = upcoming_pool.duration_minutes or 1
                new_expires = now + timedelta(minutes=duration)
                new_pool = Pool.objects.create(
                    game=game,
                    name=f"{game.name} - Slot #{next_slot}",
                    slot_number=next_slot,
                    entry_fee=upcoming_pool.entry_fee,
                    win_prize=upcoming_pool.win_prize,
                    max_players=upcoming_pool.max_players,
                    duration_minutes=duration,
                    rounds_count=1,
                    round_duration_seconds=30,
                    status=Pool.Status.UPCOMING,
                    is_recurring=True,
                    expires_at=new_expires
                )
                PoolService.create_next_round(new_pool, 1)
                return new_pool
            else:
                # Still active and counting down — ensure round exists
                if not upcoming_pool.rounds.filter(status=Round.Status.BETTING_OPEN).exists():
                    PoolService.create_next_round(upcoming_pool, 1)
                return upcoming_pool
        else:
            # Create initial Slot #1 with 1-minute countdown
            duration = 1
            expires = now + timedelta(minutes=duration)
            try:
                config = GAME_CONFIGS.get(GameVariation(variation))
                entry_fee = config.entry_fee if config else 100
                mult = config.reward_multiplier if config else 10
            except Exception:
                entry_fee = 100
                mult = 10

            new_pool = Pool.objects.create(
                game=game,
                name=f"{game.name} - Slot #1",
                slot_number=1,
                entry_fee=entry_fee,
                win_prize=Decimal(str(entry_fee * mult)),
                max_players=config.max_slots if 'config' in locals() and config else 100,
                duration_minutes=duration,
                rounds_count=1,
                round_duration_seconds=30,
                status=Pool.Status.UPCOMING,
                is_recurring=True,
                expires_at=expires
            )
            PoolService.create_next_round(new_pool, 1)
            return new_pool

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

        # Total pool amount collected
        total_collected = pool.entry_fee * total_participants

        # Reward distribution for top 3
        # 1st: 50%, 2nd: 30%, 3rd: 20%
        percentages = [0.50, 0.30, 0.20]

        for rank_idx in range(min(3, total_participants)):
            part = participants[rank_idx]
            payout = Decimal(str(total_collected)) * Decimal(str(percentages[rank_idx]))
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