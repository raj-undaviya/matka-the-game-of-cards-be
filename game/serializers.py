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
    slot_number     = serializers.SerializerMethodField()
    win_prize       = serializers.SerializerMethodField()
    expires_at      = serializers.SerializerMethodField()
    remaining_seconds = serializers.SerializerMethodField()

    class Meta:
        model  = Round
        fields = [
            'id', 'variation', 'status',
            'seed_hash',          # provably fair — public
            'entry_fee', 'max_slots', 'slots_filled', 'slots_available',
            'reward_info', 'draw_at', 'created_at', 'pool',
            'pool_name', 'pool_id', 'slot_number', 'win_prize',
            'expires_at', 'remaining_seconds',
        ]

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
    round_id         = serializers.UUIDField()
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

    class Meta:
        model = Pool
        fields = [
            'id', 'game', 'game_name', 'game_variation', 'name', 'slot_number',
            'entry_fee', 'win_prize', 'max_players', 'duration_minutes', 'rounds_count',
            'round_duration_seconds', 'status', 'is_recurring', 'expires_at',
            'remaining_seconds', 'created_at', 'start_time', 'end_time', 'participants_count'
        ]

    def get_participants_count(self, obj):
        return obj.participants.count()

    def get_remaining_seconds(self, obj):
        from django.utils import timezone
        if obj.expires_at:
            delta = (obj.expires_at - timezone.now()).total_seconds()
            return max(0, int(delta))
        return 60


class PoolParticipantSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = PoolParticipant
        fields = ['id', 'pool', 'username', 'total_points', 'rank', 'reward_paid', 'joined_at']
