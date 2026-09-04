"""
Wallet App — Django Admin
==========================
Wallet, Transaction, aur WithdrawRequest ka admin panel.
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import Wallet, Transaction, WithdrawRequest


class TransactionInline(admin.TabularInline):
    model           = Transaction
    extra           = 0
    readonly_fields = [
        'transaction_type', 'amount',
        'balance_before', 'balance_after',
        'status', 'reference', 'note', 'created_at'
    ]
    can_delete = False
    ordering   = ['-created_at']
    max_num    = 20  # Inline mein sirf last 20

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display    = ['user', 'balance', 'created_at', 'updated_at']
    search_fields   = ['user__username', 'user__email']
    readonly_fields = ['user', 'created_at', 'updated_at']
    inlines         = [TransactionInline]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display  = [
        'short_id', 'wallet_user', 'transaction_type_badge',
        'amount', 'balance_before', 'balance_after',
        'status_badge', 'created_at'
    ]
    list_filter   = ['transaction_type', 'status']
    search_fields = ['wallet__user__username', 'reference', 'razorpay_order_id']
    readonly_fields = [f.name for f in Transaction._meta.fields]
    ordering      = ['-created_at']

    def short_id(self, obj):
        return str(obj.id)[:8] if hasattr(obj, 'id') else '-'
    short_id.short_description = 'ID'

    def wallet_user(self, obj):
        return obj.wallet.user.username
    wallet_user.short_description = 'User'

    def transaction_type_badge(self, obj):
        colors = {
            'deposit':    '#28a745',
            'withdraw':   '#dc3545',
            'bet_debit':  '#fd7e14',
            'win_credit': '#007bff',
            'refund':     '#6c757d',
        }
        color = colors.get(obj.transaction_type, '#333')
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:4px;font-size:11px">{}</span>',
            color, obj.get_transaction_type_display()
        )
    transaction_type_badge.short_description = 'Type'

    def status_badge(self, obj):
        colors = {'pending': '#ffc107', 'success': '#28a745', 'failed': '#dc3545'}
        color  = colors.get(obj.status, '#333')
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            color, obj.status.upper()
        )
    status_badge.short_description = 'Status'

    def has_add_permission(self, request):
        return False  # Transactions sirf system banaye

    def has_delete_permission(self, request, obj=None):
        return False  # Audit trail delete nahi


@admin.register(WithdrawRequest)
class WithdrawRequestAdmin(admin.ModelAdmin):
    list_display  = [
        'id', 'wallet_user', 'amount', 'mode',
        'status_badge', 'requested_at', 'processed_at'
    ]
    list_filter   = ['status', 'mode']
    search_fields = ['wallet__user__username', 'upi_id', 'account_number', 'razorpay_payout_id']
    readonly_fields = [
        'wallet', 'amount', 'mode',
        'upi_id', 'account_number', 'ifsc_code', 'account_holder',
        'razorpay_payout_id', 'payout_response',
        'requested_at',
    ]
    # Admin sirf status, admin_note, processed_at update kar sakta hai
    fields = [
        'wallet', 'amount', 'mode',
        'upi_id', 'account_number', 'ifsc_code', 'account_holder',
        'status', 'admin_note', 'processed_at',
        'razorpay_payout_id', 'payout_response',
        'note', 'requested_at',
    ]
    ordering = ['-requested_at']

    def wallet_user(self, obj):
        return obj.wallet.user.username
    wallet_user.short_description = 'User'

    def status_badge(self, obj):
        colors = {
            'pending':  '#ffc107',
            'approved': '#17a2b8',
            'rejected': '#dc3545',
            'paid':     '#28a745',
            'failed':   '#6c757d',
        }
        color = colors.get(obj.status, '#333')
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:4px;font-size:11px">{}</span>',
            color, obj.status.upper()
        )
    status_badge.short_description = 'Status'

    def save_model(self, request, obj, form, change):
        old_status = WithdrawRequest.objects.get(pk=obj.pk).status if change else None
        super().save_model(request, obj, form, change)
        if change and old_status != 'approved' and obj.status in ('approved', 'paid'):
            try:
                from .email_hooks import on_admin_withdraw_approved
                on_admin_withdraw_approved(obj.wallet.user, obj)
            except Exception as e:
                print(f"Failed to send withdraw approved email: {e}")
        elif change and old_status != 'rejected' and obj.status == 'rejected':
            try:
                from .email_hooks import on_admin_withdraw_rejected
                on_admin_withdraw_rejected(obj.wallet.user, obj)
            except Exception as e:
                print(f"Failed to send withdraw rejected email: {e}")