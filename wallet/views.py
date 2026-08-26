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


# ─────────────────────────────────────────────────────────
# Wallet Balance
# ─────────────────────────────────────────────────────────

class WalletBalanceView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        wallet = get_wallet(request.user)
        print(wallet) 

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
        wallet = get_wallet(request.user)     

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


# ─────────────────────────────────────────────────────────
# Deposit Verify
# ─────────────────────────────────────────────────────────

class DepositVerifyView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = DepositVerifySerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=400)

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
                return Response({

                    "success": False,

                    "message":
                    "Automatic payouts are not configured. Use the manual paid action."

                }, status=400)


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