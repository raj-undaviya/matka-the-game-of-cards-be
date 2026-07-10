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


class Game(models.Model):
    name = models.CharField(max_length=100)
    variation = models.CharField(max_length=2, choices=[
        ('V1', 'Single'),
        ('V2', 'Pair'),
        ('V3', 'Trio'),
        ('V4', 'Sum Matka'),
        ('V5', 'Jackpot')
    ])
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.variation})"


class Pool(models.Model):
    class Status(models.TextChoices):
        UPCOMING = 'upcoming', 'Upcoming'
        ACTIVE = 'active', 'Active'
        COMPLETED = 'completed', 'Completed'

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='pools')
    name = models.CharField(max_length=100)
    entry_fee = models.PositiveIntegerField(default=10)
    max_players = models.PositiveIntegerField(default=100)
    duration_minutes = models.PositiveIntegerField(default=5)
    rounds_count = models.PositiveIntegerField(default=10)
    round_duration_seconds = models.PositiveIntegerField(default=30)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPCOMING)
    created_at = models.DateTimeField(auto_now_add=True)
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} - Fee: ₹{self.entry_fee} [{self.status}]"


class PoolParticipant(models.Model):
    pool = models.ForeignKey(Pool, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pool_participations')
    joined_at = models.DateTimeField(auto_now_add=True)
    total_points = models.IntegerField(default=0)
    rank = models.PositiveIntegerField(null=True, blank=True)
    reward_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    class Meta:
        unique_together = ('pool', 'user')
        ordering = ['-total_points', 'joined_at']

    def __str__(self):
        return f"{self.user.username} in {self.pool.name} - Points: {self.total_points}"


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

    # Pool association
    pool           = models.ForeignKey(Pool, on_delete=models.CASCADE, null=True, blank=True, related_name='rounds')
    round_number   = models.PositiveIntegerField(default=1)

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
        pool_str = f" Pool {self.pool.name} R{self.round_number}" if self.pool else ""
        return f"Round {self.variation}{pool_str} [{self.status}] — {str(self.id)[:8]}"

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

    # Pool association and Points
    pool             = models.ForeignKey(Pool, on_delete=models.CASCADE, null=True, blank=True, related_name='bets')
    points_earned    = models.IntegerField(default=0)

    class Meta:
        # One user, one bet per round (except V5 jackpot — handled in service layer)
        ordering = ['placed_at']

    def __str__(self):
        return f"Bet by {self.user} on Round {str(self.round_id)[:8]} — {self.status}"
