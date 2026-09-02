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

    class Meta:
        model  = Round
        fields = [
            'id', 'variation', 'status',
            'seed_hash',          # provably fair — public
            'entry_fee', 'max_slots', 'slots_filled', 'slots_available',
            'reward_info', 'draw_at', 'created_at', 'pool',
            'pool_name', 'pool_id',
        ]
        # server_seed EXCLUDED — never expose

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
        fields = ['id', 'name', 'variation', 'description', 'is_active', 'created_at']


class PoolSerializer(serializers.ModelSerializer):
    game_name = serializers.CharField(source='game.name', read_only=True)
    game_variation = serializers.CharField(source='game.variation', read_only=True)
    participants_count = serializers.SerializerMethodField()

    class Meta:
        model = Pool
        fields = [
            'id', 'game', 'game_name', 'game_variation', 'name', 'entry_fee',
            'max_players', 'duration_minutes', 'rounds_count', 'round_duration_seconds',
            'status', 'created_at', 'start_time', 'end_time', 'participants_count'
        ]

    def get_participants_count(self, obj):
        return obj.participants.count()


class PoolParticipantSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = PoolParticipant
        fields = ['id', 'pool', 'username', 'total_points', 'rank', 'reward_paid', 'joined_at']


