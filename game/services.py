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

from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from .models import Round, Bet
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

        game_var = GameVariation(round_obj.variation)
        config = GAME_CONFIGS[game_var]

        current_count = round_obj.bets.count()
        if current_count >= config.max_slots:
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

        new_count = current_count + 1
        if game_var != GameVariation.JACKPOT and new_count >= config.max_slots:
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
                bet.save(update_fields=['status', 'reward_amount', 'win_type'])

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
                bet.save(update_fields=['status'])

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