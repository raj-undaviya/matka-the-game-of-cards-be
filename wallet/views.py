import datetime
from time import timezone
import json
import uuid

import razorpay
import hmac
import hashlib

from django.conf import settings
from django.db import transaction as db_transaction
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework import status
from .models import Wallet, Transaction, WithdrawRequest

from .serializers import (
    WalletSerializer, TransactionSerializer,
    DepositInitSerializer, DepositVerifySerializer,
    WithdrawSerializer, WithdrawRequestSerializer,
    AdminWithdrawActionSerializer
)

rz_client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)


def get_or_create_wallet(user):
    wallet, _ = Wallet.objects.get_or_create(user=user)
    return wallet


def cashfree_base_url():
    if settings.CASHFREE_MODE and settings.CASHFREE_MODE.lower() == 'production':
        return 'https://api.cashfree.com'
    return 'https://sandbox.cashfree.com'


def create_cashfree_order(amount, user):
    if not settings.CASHFREE_APP_ID or not settings.CASHFREE_SECRET_KEY:
        raise ValueError('Cashfree credentials not configured')

    order_id = f"cf_{uuid.uuid4().hex[:18]}"
    customer_details = {
        'customer_id': str(user.id),
        'customer_email': user.email or f'user{user.id}@example.com',
        'customer_phone': getattr(user, 'phone_number', '9999999999'),
    }

    body = {
        'order_id': order_id,
        'order_amount': str(amount),
        'order_currency': 'INR',
        'customer_details': customer_details,
        'order_note': f'Matka deposit for {user.username}'
    }

    headers = {
        'Content-Type': 'application/json',
        'x-client-id': settings.CASHFREE_APP_ID,
        'x-client-secret': settings.CASHFREE_SECRET_KEY,
        'x-api-version': getattr(settings, 'CASHFREE_API_VERSION', '2022-01-01'),
    }

    response = requests.post(
        f"{cashfree_base_url()}/pg/orders",
        json=body,
        headers=headers,
        timeout=20,
    )
    try:
        data = response.json()
    except Exception:
        data = {'raw_text': response.text}

    # Treat a valid order response as success even when Cashfree does not return a top-level status field.
    if response.status_code in (200, 201) and (
        data.get('order_id') or data.get('data', {}).get('order_id')
    ):
        return data, response.status_code

    return data, response.status_code


def create_cashfree_payment_session(order_id, amount, user):
    headers = {
        'Content-Type': 'application/json',
        'x-client-id': settings.CASHFREE_APP_ID,
        'x-client-secret': settings.CASHFREE_SECRET_KEY,
        'x-api-version': getattr(settings, 'CASHFREE_API_VERSION', '2022-01-01'),
    }

    customer_details = {
        'customer_id': str(user.id),
        'customer_email': user.email or f'user{user.id}@example.com',
        'customer_phone': getattr(user, 'phone_number', '9999999999'),
    }

    body = {
        'order_id': order_id,
        'order_amount': str(amount),
        'order_currency': 'INR',
        'customer_details': customer_details,
    }

    response = requests.post(
        f"{cashfree_base_url()}/pg/orders/{order_id}/session",
        json=body,
        headers=headers,
        timeout=20,
    )
    try:
        data = response.json()
    except Exception:
        data = {'raw_text': response.text}

    return data, response.status_code


def fire_razorpay_payout(withdraw_request):
    """Razorpay Payout API call karo."""

    headers = {
        "Content-Type": "application/json",
        "X-Payout-Idempotency": f"withdraw_{withdraw_request.id}"
    }

    # Fund account banao (UPI ya Bank)
    if withdraw_request.mode == "upi":
        fund_account = {
            "account_type": "vpa",
            "vpa": {"address": withdraw_request.upi_id},
            "contact_id": get_or_create_razorpay_contact(withdraw_request)
        }
    else:
        fund_account = {
            "account_type": "bank_account",
            "bank_account": {
                "name":           withdraw_request.account_holder,
                "ifsc":           withdraw_request.ifsc_code,
                "account_number": withdraw_request.account_number,
            },
            "contact_id": get_or_create_razorpay_contact(withdraw_request)
        }

    # Fund account create karo
    fa_response = requests.post(
        "https://api.razorpay.com/v1/fund_accounts",
        json=fund_account,
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    ).json()

    fund_account_id = fa_response.get("id")
    if not fund_account_id:
        raise Exception(f"Fund account create failed: {fa_response}")

    # Payout create karo
    payout_data = {
        "account_number":  settings.RAZORPAY_ACCOUNT_NUMBER,  # tumhara Razorpay account
        "fund_account_id": fund_account_id,
        "amount":          int(withdraw_request.amount * 100),  # paise me
        "currency":        "INR",
        "mode":            "UPI" if withdraw_request.mode == "upi" else "NEFT",
        "purpose":         "payout",
        "queue_if_low_balance": True,
        "narration":       f"Matka Wallet Withdrawal #{withdraw_request.id}"
    }

    payout_response = requests.post(
        "https://api.razorpay.com/v1/payouts",
        json=payout_data,
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
        headers=headers
    ).json()

    return payout_response


def get_or_create_razorpay_contact(withdraw_request):
    """User ka Razorpay contact ID lo ya banao."""
    user = withdraw_request.wallet.user
    contact_data = {
        "name":         user.get_full_name() or user.username,
        "email":        user.email,
        "contact":      getattr(user, "phone_number", "9999999999"),
        "type":         "customer",
        "reference_id": str(user.id)
    }
    response = requests.post(
        "https://api.razorpay.com/v1/contacts",
        json=contact_data,
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    ).json()
    return response.get("id")
    


# ── 1. Balance ────────────────────────────────────────────
class WalletBalanceView(APIView):

    permission_classes = [IsAuthenticated]     

    def get(self, request):                    
        wallet = get_or_create_wallet(request.user)   
        return Response(WalletSerializer(wallet).data)
    



# ── 2. Deposit Init ───────────────────────────────────────
class DepositInitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = DepositInitSerializer(data=request.data)  
        if not ser.is_valid():                           
            return Response(ser.errors, status=400)

        amount = ser.validated_data["amount"]            
        provider = ser.validated_data.get("provider", "razorpay")
        wallet = get_or_create_wallet(request.user)     

        if provider == 'cashfree':
            cashfree_order, ord_status = create_cashfree_order(amount, request.user)
            order_id = (
                cashfree_order.get('order_id')
                or cashfree_order.get('data', {}).get('order_id')
                or cashfree_order.get('data', {}).get('orderId')
            )
            payment_link = (
                cashfree_order.get('payment_link')
                or cashfree_order.get('paymentLink')
                or cashfree_order.get('paymentURL')
                or cashfree_order.get('data', {}).get('payment_link')
                or cashfree_order.get('data', {}).get('paymentLink')
                or cashfree_order.get('data', {}).get('url')
            )

            if ord_status not in (200, 201) or not order_id:
                return Response({"error": "Cashfree order creation failed", "details": cashfree_order}, status=ord_status or 400)

            session_id = None
            payment_url = payment_link

            payment_session, sess_status = create_cashfree_payment_session(order_id, amount, request.user)
            if sess_status in (200, 201):
                session_id = (
                    payment_session.get('payment_session_id')
                    or payment_session.get('paymentSessionId')
                    or payment_session.get('payment_sessionId')
                    or payment_session.get('paymentSessionID')
                    or payment_session.get('data', {}).get('payment_session_id')
                    or payment_session.get('data', {}).get('paymentSessionId')
                    or payment_session.get('data', {}).get('session_id')
                    or payment_session.get('data', {}).get('sessionId')
                    or payment_session.get('data', {}).get('id')
                )
                payment_url = payment_url or (
                    payment_session.get('payment_url')
                    or payment_session.get('paymentUrl')
                    or payment_session.get('paymentURL')
                    or payment_session.get('data', {}).get('payment_url')
                    or payment_session.get('data', {}).get('paymentUrl')
                    or payment_session.get('data', {}).get('url')
                )

            if not session_id and not payment_url:
                return Response({"error": "Cashfree checkout initialization failed", "details": {"order": cashfree_order, "session": payment_session}}, status=400)

            txn = Transaction.objects.create(
                wallet=wallet,
                transaction_type="deposit",
                amount=amount,
                status="pending",
                provider='cashfree',
                cashfree_order_id=order_id,
                cashfree_payment_session_id=session_id
            )

            return Response({
                "order_id": order_id,
                "payment_session_id": session_id,
                "paymentSessionId": session_id,
                "payment_url": payment_url,
                "paymentUrl": payment_url,
                "payment_link": payment_link,
                "amount": str(amount),
                "currency": "INR",
                "key_id": settings.CASHFREE_APP_ID,
                "transaction_id": txn.id,
                "mode": settings.CASHFREE_MODE or 'sandbox',
            }, status=status.HTTP_201_CREATED)

        rz_order = rz_client.order.create({
            "amount":          int(amount) * 100,  # paise me
            "currency":        "INR",
            "payment_capture": 1
        })
        print("Razorpay Order Created:", rz_order)

        txn = Transaction.objects.create(
            wallet=wallet,
            transaction_type="deposit",
            amount=amount,
            status="pending",
            razorpay_order_id=rz_order["id"]
        )

        return Response({
            "order_id":       rz_order["id"],
            "amount":         int(amount) * 100,  # paise me
            "currency":       "INR",
            "key_id":         settings.RAZORPAY_KEY_ID,
            "transaction_id": txn.id,
            "razorpay_payment_id": txn.razorpay_payment_id
        }, status=status.HTTP_201_CREATED)


# ── 3. Deposit Verify ─────────────────────────────────────
class DepositVerifyView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = DepositVerifySerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=400)

        provider = ser.validated_data.get('provider', 'razorpay')

        if provider == 'cashfree':
            order_id = ser.validated_data.get('order_id')
            payment_session_id = ser.validated_data.get('payment_session_id')
            result = ser.validated_data.get('result')

            if not order_id or not payment_session_id or not result:
                return Response({"error": "Cashfree verification details missing."}, status=400)

            try:
                with db_transaction.atomic():
                    txn = Transaction.objects.select_for_update().get(
                        cashfree_order_id=order_id,
                        cashfree_payment_session_id=payment_session_id,
                        wallet__user=request.user,
                        status="pending"
                    )
                    txn.cashfree_payment_id = result.get('payment_id') or result.get('paymentSessionId') or result.get('reference_id')
                    txn.status = "success"
                    txn.save()

                    wallet = txn.wallet
                    wallet.balance += txn.amount
                    wallet.save()

            except Transaction.DoesNotExist:
                return Response({"error": "Transaction nahi mili"}, status=404)

            return Response({
                "message": "Deposit successful!",
                "balance": str(txn.wallet.balance)
            })

        order_id   = ser.validated_data.get("razorpay_order_id")
        payment_id = ser.validated_data.get("razorpay_payment_id")
        signature  = ser.validated_data.get("razorpay_signature")

        if not order_id or not payment_id or not signature:
            return Response({"error": "Razorpay verification details missing."}, status=400)

        body     = f"{order_id}|{payment_id}"
        expected = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()

        if expected != signature:
            return Response({"error": "Invalid signature"}, status=400)

        try:
            with db_transaction.atomic():
                txn = Transaction.objects.select_for_update().get(
                    razorpay_order_id=order_id,
                    wallet__user=request.user,
                    status="pending"
                )
                txn.razorpay_payment_id = payment_id
                txn.status = "success"
                txn.save()

                wallet = txn.wallet
                wallet.balance += txn.amount
                wallet.save()

        except Transaction.DoesNotExist:
            return Response({"error": "Transaction nahi mili"}, status=404)

        return Response({
            "message": "Deposit successful!",
            "balance": str(txn.wallet.balance)
        })

# ── 4. Withdraw Request ───────────────────────────────────

class WithdrawRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Apni saari withdraw requests dekho."""
        wallet   = get_or_create_wallet(request.user)
        requests_ = wallet.withdraw_requests.all().order_by("-requested_at")
        return Response(WithdrawRequestSerializer(requests_, many=True).data)

    def post(self, request):
        """Nayi withdraw request banao."""
        ser = WithdrawRequestSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=400)

        amount = ser.validated_data["amount"]
        wallet = get_or_create_wallet(request.user)

        # Balance check
        if wallet.balance < amount:
            return Response(
                {"error": f"Insufficient balance. Available: ₹{wallet.balance}"},
                status=400
            )

        with db_transaction.atomic():
            # Balance hold karo (deduct kar do — pending me)
            wallet.balance -= amount
            wallet.save()

            withdraw_req = WithdrawRequest.objects.create(
                wallet=wallet,
                amount=amount,
                status="pending",
                mode=ser.validated_data.get("mode", "upi"),
                upi_id=ser.validated_data.get("upi_id"),
                account_number=ser.validated_data.get("account_number"),
                ifsc_code=ser.validated_data.get("ifsc_code"),
                account_holder=ser.validated_data.get("account_holder"),
                note=ser.validated_data.get("note", "")
            )

            # Transaction record bhi banao
            Transaction.objects.create(
                wallet=wallet,
                transaction_type="withdraw",
                amount=amount,
                status="pending",
                note=f"Withdraw request #{withdraw_req.id}"
            )

        return Response({
            "message":    "Withdraw request submit ho gayi! Admin approve karega.",
            "request_id": withdraw_req.id,
            "amount":     str(amount),
            "status":     "pending"
        }, status=201)

# ── 5. Admin — Sabhi Withdraw Requests dekho ─────────────
class AdminWithdrawListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        status_filter = request.query_params.get("status", "pending")
        requests_ = WithdrawRequest.objects.filter(
            status=status_filter
        ).select_related("wallet__user").order_by("-requested_at")
        return Response(WithdrawRequestSerializer(requests_, many=True).data)
    
# ── 6. Admin — Approve / Reject ───────────────────────────
class AdminWithdrawActionView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        ser = AdminWithdrawActionSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=400)

        action     = ser.validated_data["action"]
        admin_note = ser.validated_data.get("admin_note", "")

        try:
            withdraw_req = WithdrawRequest.objects.get(
                id=pk, status="pending"
            )
        except WithdrawRequest.DoesNotExist:
            return Response({"error": "Request nahi mili ya already processed hai"}, status=404)

        with db_transaction.atomic():
            if action == "reject":
                # Balance wapas karo
                wallet = withdraw_req.wallet
                wallet.balance += withdraw_req.amount
                wallet.save()

                withdraw_req.status     = "rejected"
                withdraw_req.admin_note = admin_note
                withdraw_req.processed_at = timezone.now()
                withdraw_req.save()

                # Transaction update
                Transaction.objects.filter(
                    wallet=wallet,
                    note=f"Withdraw request #{withdraw_req.id}",
                    status="pending"
                ).update(status="failed")

                return Response({
                    "message": "Request reject kar di — balance wapas add ho gaya.",
                    "balance": str(wallet.balance)
                })

            elif action == "approve":
                # Razorpay Payout fire karo
                try:
                    payout_response = fire_razorpay_payout(withdraw_req)
                    payout_id = payout_response.get("id")

                    if not payout_id:
                        raise Exception(f"Payout failed: {payout_response}")

                    withdraw_req.status             = "paid"
                    withdraw_req.razorpay_payout_id = payout_id
                    withdraw_req.payout_response    = payout_response
                    withdraw_req.admin_note         = admin_note
                    withdraw_req.processed_at       = datetime.now()
                    withdraw_req.save()

                    # Transaction success karo
                    Transaction.objects.filter(
                        wallet=withdraw_req.wallet,
                        note=f"Withdraw request #{withdraw_req.id}",
                        status="pending"
                    ).update(status="success")

                    return Response({
                        "message":   "Payout successful! Paisa user ke account me ja raha hai.",
                        "payout_id": withdraw_req
                    })

                except Exception as e:
                    withdraw_req.status     = "failed"
                    withdraw_req.admin_note = str(e)
                    withdraw_req.processed_at = datetime.datetime.now()
                    withdraw_req.save()

                    # Balance wapas karo
                    wallet = withdraw_req.wallet
                    wallet.balance += withdraw_req.amount
                    wallet.save()

                    return Response({"error": f"Payout failed: {str(e)}"}, status=500)

# ── 7. Transaction History ────────────────────────────────
class TransactionHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet   = get_or_create_wallet(request.user)
        txns     = wallet.transactions.all().order_by("-created_at")
        txn_type = request.query_params.get("type")

        if txn_type in ["deposit", "withdraw"]:
            txns = txns.filter(transaction_type=txn_type)

        return Response(TransactionSerializer(txns, many=True).data)

# Admin manually paid mark kare
class AdminMarkPaidView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            withdraw_req = WithdrawRequest.objects.get(
                id=pk, status="pending"
            )
        except WithdrawRequest.DoesNotExist:
            return Response({"error": "Request nahi mili"}, status=404)

        with db_transaction.atomic():
            withdraw_req.status       = "paid"
            withdraw_req.admin_note   = request.data.get("admin_note", "Manually paid")
            withdraw_req.processed_at = timezone.now()
            withdraw_req.save()

            Transaction.objects.filter(
                wallet=withdraw_req.wallet,
                note=f"Withdraw request #{withdraw_req.id}",
                status="pending"
            ).update(status="success")

        return Response({
            "message": "Withdraw request paid mark ho gayi ✅",
            "request_id": withdraw_req.id
        })