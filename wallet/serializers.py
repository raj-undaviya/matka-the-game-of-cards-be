from rest_framework import serializers
from .models import Wallet, Transaction, WithdrawRequest


class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Wallet
        fields = ["id", "balance", "created_at", "updated_at"]


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Transaction
        fields = [
            "id", "transaction_type", "amount",
            "balance_before", "balance_after",
            "status", "provider",
            "cashfree_order_id", "cashfree_payment_id",
            "razorpay_order_id", "razorpay_payment_id",
            "reference", "note", "created_at"
        ]


class DepositInitSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=1)
    provider = serializers.ChoiceField(
        choices=[('razorpay', 'razorpay'), ('cashfree', 'cashfree')],
        default='razorpay',
        required=False,
    )


class PhonePeVerifySerializer(serializers.Serializer):
    merchantTransactionId = serializers.CharField()
    transactionId = serializers.CharField(required=False, allow_blank=True)
    code = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.IntegerField(required=False)
    merchantId = serializers.CharField(required=False, allow_blank=True)
    state = serializers.CharField(required=False, allow_blank=True)


class WithdrawSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=1)
    note   = serializers.CharField(required=False, allow_blank=True)


class DepositVerifySerializer(serializers.Serializer):
    provider = serializers.ChoiceField(
        choices=[('razorpay', 'razorpay'), ('cashfree', 'cashfree')],
        default='razorpay'
    )
    razorpay_order_id   = serializers.CharField(required=False, allow_blank=True)
    razorpay_payment_id = serializers.CharField(required=False, allow_blank=True)
    razorpay_signature  = serializers.CharField(required=False, allow_blank=True)
    order_id = serializers.CharField(required=False, allow_blank=True)
    payment_session_id = serializers.CharField(required=False, allow_blank=True)
    result = serializers.JSONField(required=False)

# ── Withdraw Request Serializers ──────────────────────────
class WithdrawRequestSerializer(serializers.ModelSerializer):
    wallet_user = serializers.CharField(source="wallet.user.username", read_only=True)
    user_email  = serializers.CharField(source="wallet.user.email", read_only=True)
    user_id     = serializers.CharField(source="wallet.user.id", read_only=True)

    class Meta:
        model  = WithdrawRequest
        fields = [
            "id", "wallet_user", "user_email", "user_id", "amount", "status", "mode",
            "upi_id", "account_number", "ifsc_code", "account_holder",
            "razorpay_payout_id", "note", "admin_note",
            "requested_at", "processed_at"
        ]
        read_only_fields = [
            "status", "razorpay_payout_id",
            "admin_note", "requested_at", "processed_at"
        ]

    def validate(self, data):
        mode = data.get("mode")
        if mode == "upi" and not data.get("upi_id"):
            raise serializers.ValidationError({"upi_id": "UPI ID required hai."})
        if mode == "bank_account":
            if not data.get("account_number"):
                raise serializers.ValidationError({"account_number": "Account number required hai."})
            if not data.get("ifsc_code"):
                raise serializers.ValidationError({"ifsc_code": "IFSC code required hai."})
            if not data.get("account_holder"):
                raise serializers.ValidationError({"account_holder": "Account holder name required hai."})
        return data


class AdminWithdrawActionSerializer(serializers.Serializer):
    action     = serializers.ChoiceField(choices=["approve", "reject"])
    admin_note = serializers.CharField(required=False, allow_blank=True)