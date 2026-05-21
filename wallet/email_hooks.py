"""
wallet/views.py (email hooks)
==============================
Deposit aur Withdraw ke saath email triggers.
Sirf yeh functions apne existing wallet views mein add karo.

Razorpay webhook ya payment verify hone ke baad in functions ko call karo.
"""
from core.email_service import EmailService


# ── Deposit Success ke baad call karo ────────────────────────────────────────
def on_deposit_success(user, transaction):
    """
    Jab Razorpay payment verify ho jaaye aur Transaction.status = 'success' ho.

    Example:
        transaction.status = 'success'
        transaction.save()
        on_deposit_success(request.user, transaction)
    """
    EmailService.send_deposit_success(user, transaction)


# ── Deposit Fail ke baad call karo ───────────────────────────────────────────
def on_deposit_failed(user, amount: str, reason: str = ""):
    """
    Jab Razorpay payment fail ho.

    Example:
        on_deposit_failed(request.user, amount="500.00", reason="Card declined")
    """
    EmailService.send_deposit_failed(user, amount=amount, reason=reason)


# ── Withdraw Request submit hone par ─────────────────────────────────────────
def on_withdraw_success(user, withdraw_request):
    """
    Jab withdrawal process ho jaaye (Razorpay payout success).

    Example:
        withdraw_request.status = 'paid'
        withdraw_request.save()
        on_withdraw_success(request.user, withdraw_request)
    """
    EmailService.send_withdraw_success(user, withdraw_request)


def on_withdraw_failed(user, withdraw_request, reason: str = ""):
    """
    Jab withdrawal fail ho.
    """
    EmailService.send_withdraw_failed(user, withdraw_request, reason=reason)


# ── Admin actions ─────────────────────────────────────────────────────────────
def on_admin_withdraw_approved(user, withdraw_request):
    """
    Admin ne approve kiya — wallet/admin.py ke save() ke baad call karo.

    wallet/admin.py mein add karo:
        def save_model(self, request, obj, form, change):
            old_status = WithdrawRequest.objects.get(pk=obj.pk).status if change else None
            super().save_model(request, obj, form, change)
            if change and old_status != 'approved' and obj.status == 'approved':
                on_admin_withdraw_approved(obj.wallet.user, obj)
            elif change and old_status != 'rejected' and obj.status == 'rejected':
                on_admin_withdraw_rejected(obj.wallet.user, obj)
    """
    EmailService.send_withdraw_approved(user, withdraw_request)


def on_admin_withdraw_rejected(user, withdraw_request):
    """
    Admin ne reject kiya.
    """
    EmailService.send_withdraw_rejected(user, withdraw_request)