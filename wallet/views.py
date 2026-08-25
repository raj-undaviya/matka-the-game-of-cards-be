import datetime
from time import timezone
import json
import uuid

import requests

from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import (
    IsAuthenticated,
    IsAdminUser
)
from rest_framework import status

from .models import (
    Wallet,
    Transaction,
    WithdrawRequest 
)

from .serializers import (
    WalletSerializer, TransactionSerializer,
    DepositInitSerializer, DepositVerifySerializer,
    WithdrawSerializer, WithdrawRequestSerializer,
    AdminWithdrawActionSerializer
)
from .phonepe import build_payment_payload, build_request_header, verify_phonepe_signature


# ─────────────────────────────────────────────────────────
# PhonePe Client helpers
# ─────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────

def get_wallet(user):

    wallet, _ = Wallet.objects.get_or_create(
        user=user
    )

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

# ─────────────────────────────────────────────────────────
# Wallet Balance
# ─────────────────────────────────────────────────────────

class WalletBalanceView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        wallet = get_wallet(request.user)

        return Response(
            WalletSerializer(wallet).data
        )


# ─────────────────────────────────────────────────────────
# Deposit Init
# ─────────────────────────────────────────────────────────

class DepositInitView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        ser = DepositInitSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=400)

        amount = ser.validated_data["amount"]            
        provider = ser.validated_data.get("provider", "razorpay")
        wallet = get_wallet(request.user)     

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

        ser.is_valid(raise_exception=True)

        amount = serializer.validated_data["amount"]

        wallet = get_wallet(request.user)

        receipt_id = (
            f"user_{request.user.id}_"
            f"{datetime.datetime.now().timestamp()}"
        )

        try:

            txn = Transaction.objects.create(

                wallet=wallet,

                transaction_type="deposit",

                amount=amount,

                balance_before=wallet.balance,

                balance_after=wallet.balance,
                status="pending",
                note="Wallet Deposit"

            )

            payload = build_payment_payload(
                merchant_transaction_id=f"txn_{txn.id}",
                amount=int(amount * 100),
                callback_url=f"{settings.FRONTEND_URL or 'http://localhost:3000'}/wallet/deposit/callback",
                user_phone=getattr(request.user, "phone_number", "") or "9999999999",
                merchant_user_id=str(request.user.id),
            )

            headers = build_request_header(payload, settings.PHONEPE_SALT_KEY)
            response = requests.post(
                f"{settings.PHONEPE_API_URL}/pg/v1/pay",
                json=payload,
                headers=headers,
                timeout=10,
            )
            response_data = response.json()
            txn.razorpay_order_id = response_data.get("data", {}).get("merchantTransactionId") or f"txn_{txn.id}"
            txn.save(update_fields=["razorpay_order_id"])

            return Response({

                "success": True,
                "transaction_id": txn.id,
                "merchant_transaction_id": txn.razorpay_order_id,
                "amount": int(amount * 100),
                "redirect_url": response_data.get("data", {}).get("instrumentResponse", {}).get("redirectInfo", {}).get("url"),
                "response": response_data,

            })

        except Exception as e:

            return Response({

                "success": False,

                "message": str(e)

            }, status=500)


# ─────────────────────────────────────────────────────────
# Deposit Verify
# ─────────────────────────────────────────────────────────

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

        serializer.is_valid(raise_exception=True)

        merchant_transaction_id = serializer.validated_data[
            "merchantTransactionId"
        ]
        payment_id = serializer.validated_data.get(
            "transactionId", ""
        )
        signature = request.headers.get("X-VERIFY", "")

        payload = request.data
        if not verify_phonepe_signature(json.dumps(payload, separators=(",", ":"), sort_keys=True), settings.PHONEPE_SALT_KEY, signature):
            return Response({

                "success": False,

                "message": "Invalid payment signature"

            }, status=400)

        try:

            with db_transaction.atomic():

                txn = Transaction.objects.select_for_update().get(

                    wallet__user=request.user,
                    razorpay_order_id=merchant_transaction_id,
                    status="pending"

                )

                wallet = txn.wallet

                balance_before = wallet.balance

                balance_after = (
                    balance_before + txn.amount
                )

                wallet.balance = balance_after

                wallet.save()

                txn.balance_before = balance_before

                txn.balance_after = balance_after

                txn.status = "success"

                txn.razorpay_payment_id = payment_id

                txn.save()

                return Response({

                    "success": True,

                    "message": "Deposit Successful",

                    "balance": wallet.balance

                })

        except Transaction.DoesNotExist:

            return Response({

                "success": False,

                "message": "Transaction not found"

            }, status=404)


# ─────────────────────────────────────────────────────────
# Withdraw Request
# ─────────────────────────────────────────────────────────

class WithdrawRequestView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        wallet = get_wallet(request.user)

        withdraws = wallet.withdraw_requests.all()

        return Response(

            WithdrawRequestSerializer(
                withdraws,
                many=True
            ).data
        )

    def post(self, request):

        serializer = WithdrawRequestSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data["amount"]

        wallet = get_wallet(request.user)

        if wallet.balance < amount:

            return Response({

                "success": False,

                "message": (
                    f"Insufficient Balance. "
                    f"Available ₹{wallet.balance}"
                )

            }, status=400)

        with db_transaction.atomic():

            balance_before = wallet.balance

            balance_after = (
                balance_before - amount
            )

            wallet.balance = balance_after

            wallet.save()

            withdraw_request = (
                WithdrawRequest.objects.create(

                    wallet=wallet,

                    amount=amount,

                    mode=serializer.validated_data[
                        "mode"
                    ],

                    upi_id=serializer.validated_data.get(
                        "upi_id"
                    ),

                    account_number=serializer.validated_data.get(
                        "account_number"
                    ),

                    ifsc_code=serializer.validated_data.get(
                        "ifsc_code"
                    ),

                    account_holder=serializer.validated_data.get(
                        "account_holder"
                    ),

                    note=serializer.validated_data.get(
                        "note"
                    )
                )
            )

            Transaction.objects.create(

                wallet=wallet,

                transaction_type="withdraw",

                amount=amount,

                balance_before=balance_before,

                balance_after=balance_after,

                status="pending",

                reference=str(withdraw_request.id),

                note=(
                    f"Withdraw Request "
                    f"#{withdraw_request.id}"
                )
            )

        return Response({

            "success": True,

            "message": (
                "Withdraw request submitted"
            )

        })


# ─────────────────────────────────────────────────────────
# Transaction History
# ─────────────────────────────────────────────────────────

class TransactionHistoryView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        wallet = get_wallet(request.user)

        txns = wallet.transactions.all()

        txn_type = request.query_params.get(
            "type"
        )

        if txn_type:

            txns = txns.filter(
                transaction_type=txn_type
            )

        return Response(

            TransactionSerializer(
                txns,
                many=True
            ).data
        )


# ─────────────────────────────────────────────────────────
# Razorpay Contact
# ─────────────────────────────────────────────────────────

def create_razorpay_contact(user):

    data = {

        "name": (
            user.get_full_name()
            or user.username
        ),

        "email": user.email,

        "contact": getattr(
            user,
            "phone_number",
            "9999999999"
        ),

        "type": "customer"
    }

    response = requests.post(

        "https://api.razorpay.com/v1/contacts",

        json=data,

        auth=(

            settings.RAZORPAY_KEY_ID,

            settings.RAZORPAY_KEY_SECRET
        )
    )

    result = response.json()

    return result.get("id")


# ─────────────────────────────────────────────────────────
# Razorpay Fund Account
# ─────────────────────────────────────────────────────────

def create_fund_account(withdraw_request):

    contact_id = create_razorpay_contact(
        withdraw_request.wallet.user
    )

    if withdraw_request.mode == "upi":

        payload = {

            "contact_id": contact_id,

            "account_type": "vpa",

            "vpa": {

                "address":
                withdraw_request.upi_id

            }
        }

    else:

        payload = {

            "contact_id": contact_id,

            "account_type": "bank_account",

            "bank_account": {

                "name":
                withdraw_request.account_holder,

                "ifsc":
                withdraw_request.ifsc_code,

                "account_number":
                withdraw_request.account_number

            }
        }

    response = requests.post(

        "https://api.razorpay.com/v1/fund_accounts",

        json=payload,

        auth=(

            settings.RAZORPAY_KEY_ID,

            settings.RAZORPAY_KEY_SECRET
        )
    )

    result = response.json()

    return result.get("id")


# ─────────────────────────────────────────────────────────
# Razorpay Payout
# ─────────────────────────────────────────────────────────

def create_payout(withdraw_request):

    fund_account_id = create_fund_account(
        withdraw_request
    )

    payload = {

        "account_number":
        settings.RAZORPAY_ACCOUNT_NUMBER,

        "fund_account_id":
        fund_account_id,

        "amount":
        int(withdraw_request.amount * 100),

        "currency": "INR",

        "mode":
        "UPI"
        if withdraw_request.mode == "upi"
        else "NEFT",

        "purpose": "payout",

        "queue_if_low_balance": True,

        "reference_id":
        str(withdraw_request.id),

        "narration":
        f"Withdraw #{withdraw_request.id}"
    }

    response = requests.post(

        "https://api.razorpay.com/v1/payouts",

        json=payload,

        auth=(

            settings.RAZORPAY_KEY_ID,

            settings.RAZORPAY_KEY_SECRET
        )
    )

    return response.json()


# ─────────────────────────────────────────────────────────
# Admin Withdraw List
# ─────────────────────────────────────────────────────────

class AdminWithdrawListView(APIView):

    permission_classes = [IsAdminUser]

    def get(self, request):

        status_filter = request.GET.get(
            "status",
            "pending"
        )

        requests_list = (
            WithdrawRequest.objects.filter(
                status=status_filter
            )
            .select_related("wallet__user")
            .order_by("-requested_at")
        )

        return Response(

            WithdrawRequestSerializer(
                requests_list,
                many=True
            ).data
        )


# ─────────────────────────────────────────────────────────
# Admin Withdraw Action
# ─────────────────────────────────────────────────────────

class AdminWithdrawActionView(APIView):

    permission_classes = [IsAdminUser]

    def post(self, request, pk):

        serializer = (
            AdminWithdrawActionSerializer(
                data=request.data
            )
        )

        serializer.is_valid(
            raise_exception=True
        )

        action = serializer.validated_data[
            "action"
        ]

        admin_note = (
            serializer.validated_data.get(
                "admin_note",
                ""
            )
        )

        try:

            withdraw_request = (
                WithdrawRequest.objects.get(

                    id=pk,

                    status="pending"
                )
            )

        except WithdrawRequest.DoesNotExist:

            return Response({

                "success": False,

                "message":
                "Withdraw request not found"

            }, status=404)

        with db_transaction.atomic():

            wallet = withdraw_request.wallet

            if action == "reject":

                balance_before = wallet.balance

                balance_after = (
                    balance_before
                    + withdraw_request.amount
                )

                wallet.balance = balance_after

                wallet.save()

                withdraw_request.status = (
                    "rejected"
                )

                withdraw_request.admin_note = (
                    admin_note
                )

                withdraw_request.processed_at = (
                    timezone.now()
                )

                withdraw_request.save()

                txn = Transaction.objects.filter(

                    wallet=wallet,

                    reference=str(
                        withdraw_request.id
                    ),

                    status="pending"

                ).first()

                if txn:

                    txn.status = "failed"

                    txn.balance_after = (
                        balance_after
                    )

                    txn.save()

                return Response({

                    "success": True,

                    "message":
                    "Withdraw Rejected"

                })

            elif action == "approve":

                payout_response = create_payout(
                    withdraw_request
                )

                payout_id = payout_response.get(
                    "id"
                )

                if not payout_id:

                    wallet.balance += (
                        withdraw_request.amount
                    )

                    wallet.save()

                    return Response({

                        "success": False,

                        "message":
                        "Payout failed",

                        "response":
                        payout_response

                    }, status=500)

                withdraw_request.status = (
                    "paid"
                )

                withdraw_request.admin_note = (
                    admin_note
                )

                withdraw_request.processed_at = (
                    timezone.now()
                )

                withdraw_request.razorpay_payout_id = (
                    payout_id
                )

                withdraw_request.payout_response = (
                    payout_response
                )

                withdraw_request.save()

                Transaction.objects.filter(

                    wallet=wallet,

                    reference=str(
                        withdraw_request.id
                    ),

                    status="pending"

                ).update(

                    status="success"
                )

                return Response({

                    "success": True,

                    "message":
                    "Withdraw Paid",

                    "payout_id": payout_id

                })


# ─────────────────────────────────────────────────────────
# Admin Manual Paid
# ─────────────────────────────────────────────────────────

class AdminMarkPaidView(APIView):

    permission_classes = [IsAdminUser]

    def post(self, request, pk):

        try:

            withdraw_request = (
                WithdrawRequest.objects.get(

                    id=pk,

                    status="pending"
                )
            )

        except WithdrawRequest.DoesNotExist:

            return Response({

                "success": False,

                "message":
                "Withdraw request not found"

            }, status=404)

        withdraw_request.status = "paid"

        withdraw_request.admin_note = (
            request.data.get(
                "admin_note",
                "Manually Paid"
            )
        )

        withdraw_request.processed_at = (
            timezone.now()
        )

        withdraw_request.save()

        Transaction.objects.filter(

            wallet=withdraw_request.wallet,

            reference=str(
                withdraw_request.id
            ),

            status="pending"

        ).update(

            status="success"
        )

        return Response({

            "success": True,

            "message":
            "Marked as paid"

        })