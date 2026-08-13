import hashlib

from django.test import SimpleTestCase

from wallet.phonepe import build_payment_payload, verify_phonepe_signature


class PhonePeHelperTests(SimpleTestCase):
    def test_build_payment_payload_includes_required_fields(self):
        payload = build_payment_payload(
            merchant_transaction_id="txn-123",
            amount=10000,
            callback_url="https://example.com/phonepe/callback",
            user_phone="9999999999",
            merchant_user_id="user-42",
        )

        self.assertEqual(payload["merchantTransactionId"], "txn-123")
        self.assertEqual(payload["amount"], 10000)
        self.assertEqual(payload["merchantUserId"], "user-42")
        self.assertEqual(payload["callbackUrl"], "https://example.com/phonepe/callback")
        self.assertEqual(payload["paymentInstrument"]["type"], "PAY_PAGE")

    def test_verify_phonepe_signature_works_for_expected_payload(self):
        payload = '{"merchantTransactionId":"txn-123","amount":10000}'
        salt_key = "test-salt"
        signature = hashlib.sha256(f"{payload}###{salt_key}".encode("utf-8")).hexdigest()

        self.assertTrue(verify_phonepe_signature(payload, salt_key, signature))
