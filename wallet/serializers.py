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
            "status", "razorpay_order_id",
            "razorpay_payment_id", "note", "created_at"
        ]


class DepositInitSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=1)


class WithdrawSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=1)
    note   = serializers.CharField(required=False, allow_blank=True)


class RazorpayVerifySerializer(serializers.Serializer):
    razorpay_order_id   = serializers.CharField()
    razorpay_payment_id = serializers.CharField()
    razorpay_signature  = serializers.CharField()

# ── Withdraw Request Serializers ──────────────────────────
class WithdrawRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model  = WithdrawRequest
        fields = [
            "id", "amount", "status", "mode",
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