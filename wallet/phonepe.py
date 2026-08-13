import hashlib
import hmac
import json

from django.conf import settings


def build_payment_payload(merchant_transaction_id, amount, callback_url, user_phone, merchant_user_id):
    return {
        "merchantId": settings.PHONEPE_MERCHANT_ID,
        "merchantTransactionId": merchant_transaction_id,
        "merchantUserId": merchant_user_id,
        "amount": int(amount),
        "callbackUrl": callback_url,
        "mobileNumber": user_phone,
        "paymentInstrument": {"type": "PAY_PAGE"},
    }


def build_request_header(payload, salt_key):
    payload_string = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return {
        "Content-Type": "application/json",
        "X-VERIFY": hmac.new(
            salt_key.encode("utf-8"),
            payload_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest(),
    }


def verify_phonepe_signature(payload, salt_key, signature=None):
    expected_signature = hmac.new(
        salt_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if signature is None:
        return expected_signature
    return hmac.compare_digest(expected_signature, signature)
