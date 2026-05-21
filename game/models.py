"""
Matka Game — Django Models
===========================
Tables:
  Round      → ek game session (V1-V5)
  Bet        → user ki ek entry in a round
  Wallet     → user ka balance
  WalletTx   → har transaction ka record (audit trail)
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
import uuid

User = get_user_model()


class Round(models.Model):

    class Variation(models.TextChoices):
        SINGLE     = 'V1', 'Single'
        PAIR       = 'V2', 'Pair'
        TRIO       = 'V3', 'Trio'
        SUM_MATKA  = 'V4', 'Sum Matka'
        JACKPOT    = 'V5', 'Jackpot'

    class Status(models.TextChoices):
        BETTING_OPEN = 'betting_open', 'Betting Open'
        DRAWING      = 'drawing',      'Drawing'
        COMPLETED    = 'completed',    'Completed'

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    variation      = models.CharField(max_length=2, choices=Variation.choices)
    status         = models.CharField(max_length=20, choices=Status.choices,
                                      default=Status.BETTING_OPEN)

    # Provably fair — seed_hash is PUBLIC, server_seed is PRIVATE
    server_seed    = models.CharField(max_length=64)   # Encrypted in prod (use django-encrypted-fields)
    seed_hash      = models.CharField(max_length=64)   # SHA256(server_seed) — show to users

    # Draw result
    drawn_numbers  = models.JSONField(null=True, blank=True)   # e.g. [7] or [3, 8] or [5, 5, 5]
    winners_data   = models.JSONField(null=True, blank=True)   # Full result snapshot

    # Timing
    draw_at        = models.DateTimeField(null=True, blank=True)   # V5 jackpot timer
    created_at     = models.DateTimeField(auto_now_add=True)
    completed_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Round {self.variation} [{self.status}] — {str(self.id)[:8]}"

    @property
    def config(self):
        from core.game_engine import GAME_CONFIGS, GameVariation
        return GAME_CONFIGS[GameVariation(self.variation)]

    @property
    def slots_filled(self):
        return self.bets.count()

    @property
    def slots_available(self):
        return self.config.max_slots - self.slots_filled

    @property
    def total_pool(self):
        from django.db.models import Sum
        return self.bets.aggregate(total=Sum('entry_fee'))['total'] or 0


class Bet(models.Model):

    class Status(models.TextChoices):
        PENDING  = 'pending',  'Pending'
        WON      = 'won',      'Won'
        LOST     = 'lost',     'Lost'

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    round            = models.ForeignKey(Round, on_delete=models.PROTECT,
                                         related_name='bets')
    user             = models.ForeignKey(User, on_delete=models.PROTECT,
                                         related_name='bets')
    selected_numbers = models.JSONField()          # [6] or [3,7] or [5,5,5]
    entry_fee        = models.PositiveIntegerField()
    status           = models.CharField(max_length=10, choices=Status.choices,
                                        default=Status.PENDING)
    reward_amount    = models.PositiveIntegerField(default=0)
    win_type         = models.CharField(max_length=30, blank=True)
    placed_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        # One user, one bet per round (except V5 jackpot — handled in service layer)
        ordering = ['placed_at']

    def __str__(self):
        return f"Bet by {self.user} on Round {str(self.round_id)[:8]} — {self.status}"
