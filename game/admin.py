"""
Matka Game — Django Admin
==========================
Admin panel mein game manage karo.
server_seed admin mein bhi readonly + masked hai — extra safety.

NOTE: Wallet aur Transaction admin → wallet/admin.py mein hai.
      Yahan sirf Round aur Bet ka admin hai.
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import Round, Bet   # ← sirf matka models, Wallet/WalletTransaction nahi


class BetInline(admin.TabularInline):
    model           = Bet
    extra           = 0
    fields          = ['user', 'selected_numbers', 'entry_fee', 'status', 'reward_amount', 'win_type']
    readonly_fields = ['user', 'selected_numbers', 'entry_fee', 'status', 'reward_amount', 'win_type']
    can_delete      = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    list_display  = [
        'short_id', 'variation', 'status_badge',
        'slots_progress', 'total_pool_display',
        'drawn_numbers', 'created_at'
    ]
    list_filter   = ['variation', 'status']
    search_fields = ['id']
    readonly_fields = [
        'id', 'seed_hash',
        'server_seed_masked',
        'drawn_numbers', 'winners_data',
        'created_at', 'completed_at'
    ]
    inlines = [BetInline]
    actions = ['trigger_draw_action']

    fieldsets = (
        ('Round Info', {
            'fields': ('id', 'variation', 'status', 'draw_at')
        }),
        ('Provably Fair', {
            'fields': ('seed_hash', 'server_seed_masked'),
            'description': 'seed_hash is PUBLIC — show to users. server_seed is MASKED — never expose.'
        }),
        ('Result', {
            'fields': ('drawn_numbers', 'winners_data')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'completed_at')
        }),
    )

    def short_id(self, obj):
        return str(obj.id)[:8] + '...'
    short_id.short_description = 'ID'

    def status_badge(self, obj):
        colors = {
            'betting_open': '#28a745',
            'drawing':      '#ffc107',
            'completed':    '#6c757d',
        }
        color = colors.get(obj.status, '#333')
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:4px;font-size:12px">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def slots_progress(self, obj):
        filled = obj.slots_filled
        total  = obj.config.max_slots
        pct    = int((filled / total) * 100) if total else 0
        return format_html(
            '{}/{} <span style="color:#999;font-size:11px">({}%)</span>',
            filled, total, pct
        )
    slots_progress.short_description = 'Slots'

    def total_pool_display(self, obj):
        return f"₹{obj.total_pool}"
    total_pool_display.short_description = 'Pool'

    def server_seed_masked(self, obj):
        """Full seed kabhi show mat karo — sirf first 8 chars"""
        if obj.server_seed:
            return obj.server_seed[:8] + '...[MASKED]'
        return '-'
    server_seed_masked.short_description = 'Server seed (masked)'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('bets')

    def trigger_draw_action(self, request, queryset):
        from .services import RoundService
        count = 0
        for round_obj in queryset.filter(status=Round.Status.BETTING_OPEN):
            RoundService._trigger_draw(round_obj)
            count += 1
        self.message_user(request, f"{count} round(s) drawn successfully.")
    trigger_draw_action.short_description = "Trigger draw for selected rounds"

    def has_delete_permission(self, request, obj=None):
        return False  # Rounds delete nahi honge


@admin.register(Bet)
class BetAdmin(admin.ModelAdmin):
    list_display    = ['short_id', 'user', 'round_variation', 'selected_numbers',
                       'entry_fee', 'status_badge', 'reward_amount', 'placed_at']
    list_filter     = ['status', 'round__variation']
    search_fields   = ['user__username', 'round__id']
    readonly_fields = ['id', 'round', 'user', 'selected_numbers',
                       'entry_fee', 'status', 'reward_amount', 'win_type', 'placed_at']

    def short_id(self, obj):
        return str(obj.id)[:8]
    short_id.short_description = 'ID'

    def round_variation(self, obj):
        return obj.round.get_variation_display()
    round_variation.short_description = 'Variation'

    def status_badge(self, obj):
        colors = {'pending': '#ffc107', 'won': '#28a745', 'lost': '#dc3545'}
        color  = colors.get(obj.status, '#333')
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def has_add_permission(self, request):
        return False  # Bets sirf API se place honge

    def has_delete_permission(self, request, obj=None):
        return False  # Audit trail intact rakho