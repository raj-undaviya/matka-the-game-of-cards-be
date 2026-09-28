"""
Matka Game — DRF Serializers
==============================
IMPORTANT: server_seed field kisi bhi serializer mein NAHI hai.
"""
from rest_framework import serializers
from .models import Round, Bet, Game, Pool, PoolParticipant
from core.game_engine import GAME_CONFIGS, GameVariation


class RoundListSerializer(serializers.ModelSerializer):
    slots_filled    = serializers.ReadOnlyField()
    slots_available = serializers.ReadOnlyField()
    entry_fee       = serializers.SerializerMethodField()
    max_slots       = serializers.SerializerMethodField()
    reward_info     = serializers.SerializerMethodField()
    pool_name       = serializers.SerializerMethodField()
    pool_id         = serializers.SerializerMethodField()
    pool_type       = serializers.SerializerMethodField()
    is_daily_mega   = serializers.SerializerMethodField()
    country         = serializers.SerializerMethodField()
    prize_distribution = serializers.SerializerMethodField()
    slot_number     = serializers.SerializerMethodField()
    win_prize       = serializers.SerializerMethodField()
    expires_at      = serializers.SerializerMethodField()
    remaining_seconds = serializers.SerializerMethodField()
    round_number    = serializers.IntegerField(read_only=True)
    rounds_count    = serializers.SerializerMethodField()

    class Meta:
        model  = Round
        fields = [
            'id', 'variation', 'status',
            'seed_hash',          # provably fair — public
            'entry_fee', 'max_slots', 'slots_filled', 'slots_available',
            'reward_info', 'draw_at', 'created_at', 'pool',
            'pool_name', 'pool_id', 'pool_type', 'is_daily_mega', 'country',
            'prize_distribution', 'slot_number', 'win_prize',
            'expires_at', 'remaining_seconds', 'round_number', 'rounds_count',
        ]

    def get_rounds_count(self, obj):
        return obj.pool.rounds_count if obj.pool else 1

    def get_entry_fee(self, obj):
        if obj.pool:
            return obj.pool.entry_fee
        config = GAME_CONFIGS[GameVariation(obj.variation)]
        return config.entry_fee

    def get_max_slots(self, obj):
        if obj.pool:
            return obj.pool.max_players
        config = GAME_CONFIGS[GameVariation(obj.variation)]
        return config.max_slots

    def get_reward_info(self, obj):
        if obj.pool and obj.pool.is_daily_mega:
            return {
                "multiplier": 30,
                "first_prize": 6000,
                "second_prize": 4000,
                "third_prize": 2000,
                "first_multiplier": "30x",
                "second_multiplier": "20x",
                "third_multiplier": "10x",
            }
        elif obj.pool and (obj.pool.entry_fee == 10 or (obj.pool.prize_distribution and "1" in obj.pool.prize_distribution)):
            first_p = obj.pool.prize_distribution.get("1", 300) if obj.pool.prize_distribution else 300
            second_p = obj.pool.prize_distribution.get("2", 200) if obj.pool.prize_distribution else 200
            third_p = obj.pool.prize_distribution.get("3", 100) if obj.pool.prize_distribution else 100
            return {
                "multiplier": 30,
                "first_prize": first_p,
                "second_prize": second_p,
                "third_prize": third_p,
                "first_multiplier": "30x",
                "second_multiplier": "20x",
                "third_multiplier": "10x",
            }
        config = GAME_CONFIGS[GameVariation(obj.variation)]
        info = {"multiplier": config.reward_multiplier}
        if config.reward_multiplier_small:
            info["multiplier_small"] = config.reward_multiplier_small
        return info

    def get_pool_name(self, obj):
        if obj.pool:
            return obj.pool.name
        names = {
            'V1': 'Single Card Arena',
            'V2': 'Pair Selection Arena',
            'V3': 'Trio Game Arena',
            'V4': 'Last Digit Sum Arena',
            'V5': 'Lucky Draw Jackpot',
        }
        return names.get(obj.variation, 'Standard Arena')

    def get_pool_id(self, obj):
        return str(obj.pool.id) if obj.pool else None

    def get_pool_type(self, obj):
        return obj.pool.pool_type if obj.pool else 'standard'

    def get_is_daily_mega(self, obj):
        return obj.pool.is_daily_mega if obj.pool else False

    def get_country(self, obj):
        return obj.pool.country if obj.pool else 'India'

    def get_prize_distribution(self, obj):
        if obj.pool and obj.pool.prize_distribution:
            return obj.pool.prize_distribution
        if obj.pool and obj.pool.is_daily_mega:
            return {
                "1": 6000,
                "2": 4000,
                "3": 2000,
                "multipliers": {"1": "30x", "2": "20x", "3": "10x"}
            }
        if obj.pool and obj.pool.entry_fee == 10:
            return {
                "1": 300,
                "2": 200,
                "3": 100,
                "multipliers": {"1": "30x", "2": "20x", "3": "10x"}
            }
        return {}

    def get_slot_number(self, obj):
        return obj.pool.slot_number if obj.pool else 1

    def get_win_prize(self, obj):
        if obj.pool and obj.pool.win_prize > 0:
            return float(obj.pool.win_prize)
        config = GAME_CONFIGS[GameVariation(obj.variation)]
        entry = obj.pool.entry_fee if obj.pool else config.entry_fee
        return float(entry * config.reward_multiplier)

    def get_expires_at(self, obj):
        if obj.pool and obj.pool.expires_at:
            return obj.pool.expires_at.isoformat()
        if obj.draw_at:
            return obj.draw_at.isoformat()
        return None

    def get_remaining_seconds(self, obj):
        from django.utils import timezone
        target = None
        if obj.pool and obj.pool.expires_at:
            target = obj.pool.expires_at
        elif obj.draw_at:
            target = obj.draw_at
        if target:
            delta = (target - timezone.now()).total_seconds()
            return max(0, int(delta))
        return 60


class RoundDetailSerializer(RoundListSerializer):
    """Completed round mein drawn_numbers aur proof dikhao"""
    provably_fair_proof = serializers.SerializerMethodField()

    class Meta(RoundListSerializer.Meta):
        fields = RoundListSerializer.Meta.fields + [
            'drawn_numbers', 'provably_fair_proof', 'completed_at'
        ]

    def get_provably_fair_proof(self, obj):
        if obj.winners_data:
            return obj.winners_data.get('provably_fair_proof')
        return None


class PlaceBetSerializer(serializers.Serializer):
    round_id         = serializers.CharField()
    selected_numbers = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=10),
        min_length=1,
        max_length=3
    )
    entry_fee        = serializers.IntegerField(min_value=1)


class BetSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model  = Bet
        fields = [
            'id', 'round_id', 'username',
            'selected_numbers', 'entry_fee',
            'status', 'reward_amount', 'win_type',
            'placed_at', 'points_earned'
        ]


class GameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Game
        fields = [
            'id', 'name', 'variation', 'description', 'sub_title',
            'rewards', 'pool_value', 'reward_label', 'image_url',
            'bg_colors', 'sphere_colors', 'is_active', 'created_at'
        ]


class PoolSerializer(serializers.ModelSerializer):
    game_name = serializers.CharField(source='game.name', read_only=True)
    game_variation = serializers.CharField(source='game.variation', read_only=True)
    participants_count = serializers.SerializerMethodField()
    remaining_seconds = serializers.SerializerMethodField()
    starts_in_seconds = serializers.SerializerMethodField()
    countdown_label = serializers.SerializerMethodField()
    user_has_played_today = serializers.SerializerMethodField()
    schedule_display = serializers.SerializerMethodField()

    class Meta:
        model = Pool
        fields = [
            'id', 'game', 'game_name', 'game_variation', 'name', 'slot_number',
            'pool_type', 'interval_minutes', 'is_entry_enabled', 'scheduled_start_time',
            'is_daily_mega', 'country', 'daily_start_time', 'once_per_day',
            'prize_distribution', 'entry_fee', 'win_prize', 'max_players', 'duration_minutes',
            'rounds_count', 'round_duration_seconds', 'status', 'is_recurring', 'expires_at',
            'remaining_seconds', 'starts_in_seconds', 'countdown_label', 'user_has_played_today', 'schedule_display',
            'created_at', 'start_time', 'end_time', 'participants_count'
        ]

    def get_participants_count(self, obj):
        return obj.participants.count()

    def get_remaining_seconds(self, obj):
        from django.utils import timezone
        if obj.expires_at:
            delta = (obj.expires_at - timezone.now()).total_seconds()
            if obj.pool_type in ['regular_5min', 'regular_pool'] and delta > 300:
                return 300
            return max(0, int(delta))
        return 300 if (obj.is_daily_mega or obj.pool_type in ['regular_5min', 'regular_pool']) else 60

    def get_starts_in_seconds(self, obj):
        from django.utils import timezone
        if obj.pool_type in ['regular_5min', 'regular_pool']:
            return 0
        if obj.scheduled_start_time:
            delta = (obj.scheduled_start_time - timezone.now()).total_seconds()
            return max(0, int(delta))
        if obj.expires_at and (obj.pool_type == 'hourly_pool' or obj.pool_type in ['hourly', '2_hourly', '5_hourly', '10_hourly'] or (obj.interval_minutes and obj.interval_minutes >= 60 and obj.pool_type not in ['regular_5min', 'regular_pool'])):
            delta = (obj.expires_at - timezone.now()).total_seconds()
            return max(0, int(delta))
        return 0

    def get_countdown_label(self, obj):
        from django.utils import timezone
        if obj.pool_type in ['regular_5min', 'regular_pool']:
            rem = self.get_remaining_seconds(obj)
            mins = rem // 60
            secs = rem % 60
            return f"{mins:02d}:{secs:02d} Left"
        target = obj.scheduled_start_time or obj.expires_at
        if target:
            delta = (target - timezone.now()).total_seconds()
            if delta > 0:
                hrs = int(delta // 3600)
                mins = int((delta % 3600) // 60)
                if hrs > 0:
                    return f"Starts in {hrs:02d}h:{mins:02d}m"
                return f"{mins:02d}m Left"
        return "Active"

    def get_user_has_played_today(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return False
        if obj.once_per_day or obj.is_daily_mega:
            from django.utils import timezone
            today = timezone.localdate()
            return obj.participants.filter(user=request.user, joined_at__date=today).exists()
        return False

    def get_schedule_display(self, obj):
        if obj.is_daily_mega or obj.pool_type == 'mega_daily':
            return "Daily at 1:30 PM (5 mins entry window)"
        if obj.pool_type in ['regular_5min', 'regular_pool'] or 'Regular' in (obj.name or ''):
            return f"Every 5 Minutes • Entry ₹{obj.entry_fee}"
        if obj.pool_type == 'hourly':
            return f"Every 1 Hour • Entry ₹{obj.entry_fee}"
        if obj.pool_type == '2_hourly':
            return f"Every 2 Hours • Entry ₹{obj.entry_fee}"
        if obj.pool_type == '5_hourly':
            return f"Every 5 Hours • Entry ₹{obj.entry_fee}"
        if obj.pool_type == '10_hourly':
            return f"Every 10 Hours • Entry ₹{obj.entry_fee}"
        if obj.pool_type == 'hourly_pool' or (obj.interval_minutes and obj.interval_minutes >= 60):
            hrs = (obj.interval_minutes // 60) if obj.interval_minutes else 1
            return f"Every {hrs} Hour{'s' if hrs > 1 else ''} • Entry ₹{obj.entry_fee}"
        return f"{obj.duration_minutes or 5} min slot"


class PoolParticipantSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = PoolParticipant
        fields = ['id', 'pool', 'username', 'total_points', 'rank', 'reward_paid', 'joined_at']
