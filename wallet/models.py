from django.db import models
from django.conf import settings
from decimal import Decimal


class Wallet(models.Model):
    user       = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wallet")
    balance    = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - ₹{self.balance}"


class Transaction(models.Model):
    TYPE_CHOICES = [
        ("deposit",    "Deposit"),
        ("withdraw",   "Withdraw"),
        # ── Matka game ke liye naye types ──
        ("bet_debit",  "Bet Placed"),
        ("win_credit", "Win Credited"),
        ("refund",     "Refund"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed",  "Failed"),
    ]

    wallet               = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")
    transaction_type     = models.CharField(max_length=15, choices=TYPE_CHOICES)
    amount               = models.DecimalField(max_digits=12, decimal_places=2)
    # Audit trail — nayi wali se liya
    balance_before       = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    balance_after        = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    status               = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    provider             = models.CharField(
        max_length=20,
        choices=[('razorpay', 'razorpay'), ('cashfree', 'cashfree')],
        default='razorpay'
    )
    razorpay_order_id    = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id  = models.CharField(max_length=100, blank=True, null=True)
    cashfree_order_id    = models.CharField(max_length=100, blank=True, null=True)
    cashfree_payment_id  = models.CharField(max_length=100, blank=True, null=True)
    cashfree_payment_session_id = models.CharField(max_length=200, blank=True, null=True)
    # reference: bet_id ya round_id (Matka ke liye)
    reference            = models.CharField(max_length=100, blank=True)
    note                 = models.TextField(blank=True, null=True)
    created_at           = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.wallet.user.username} | {self.transaction_type} | ₹{self.amount} | {self.status}"


# ── NEW: Withdraw Request Model ───────────────────────────
class WithdrawRequest(models.Model):
    STATUS_CHOICES = [
        ("pending",  "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("paid",     "Paid"),
        ("failed",   "Failed"),
    ]
    MODE_CHOICES = [
        ("upi",          "UPI"),
        ("bank_account", "Bank Account"),
    ]

    wallet             = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="withdraw_requests")
    amount             = models.DecimalField(max_digits=12, decimal_places=2)
    status             = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    mode               = models.CharField(max_length=15, choices=MODE_CHOICES, default="upi")

    # UPI details
    upi_id             = models.CharField(max_length=100, blank=True, null=True)

    # Bank details
    account_number     = models.CharField(max_length=20,  blank=True, null=True)
    ifsc_code          = models.CharField(max_length=15,  blank=True, null=True)
    account_holder     = models.CharField(max_length=100, blank=True, null=True)

    # Razorpay Payout
    razorpay_payout_id = models.CharField(max_length=100, blank=True, null=True)
    payout_response    = models.JSONField(blank=True, null=True)

    note               = models.TextField(blank=True, null=True)
    admin_note         = models.TextField(blank=True, null=True)
    requested_at       = models.DateTimeField(auto_now_add=True)
    processed_at       = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.wallet.user.username} | ₹{self.amount} | {self.status}"
