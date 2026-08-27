import uuid

import requests

from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import (
    IsAuthenticated,
    IsAdminUser,
    AllowAny
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


def check_cashfree_order_status(order_id):
    if not settings.CASHFREE_APP_ID or not settings.CASHFREE_SECRET_KEY:
        raise ValueError('Cashfree credentials not configured')

    headers = {
        'x-client-id': settings.CASHFREE_APP_ID,
        'x-client-secret': settings.CASHFREE_SECRET_KEY,
        'x-api-version': getattr(settings, 'CASHFREE_API_VERSION', '2022-01-01'),
    }

    url = f"{cashfree_base_url()}/pg/orders/{order_id}"
    response = requests.get(url, headers=headers, timeout=20)
    try:
        data = response.json()
    except Exception:
        data = {'raw_text': response.text}

    if response.status_code == 200:
        return data, True
    return data, False


def cashfree_payout_base_url():
    if settings.CASHFREE_MODE and settings.CASHFREE_MODE.lower() == 'production':
        return 'https://api.cashfree.com/payout'
    return 'https://sandbox.cashfree.com/payout'


def trigger_cashfree_payout(withdraw_request):
    if not settings.CASHFREE_PAYOUT_CLIENT_ID or not settings.CASHFREE_PAYOUT_CLIENT_SECRET_KEY:
        raise ValueError('Cashfree payout credentials not configured')

    headers = {
        'Content-Type': 'application/json',
        'x-client-id': settings.CASHFREE_PAYOUT_CLIENT_ID,
        'x-client-secret': settings.CASHFREE_PAYOUT_CLIENT_SECRET_KEY,
        'x-api-version': '2024-01-01',
    }

    base_url = cashfree_payout_base_url()
    
    # 1. Create Beneficiary
    beneficiary_id = f"bene_wd_{withdraw_request.id}"
    beneficiary_name = withdraw_request.account_holder or withdraw_request.wallet.user.username or "Player"
    
    bene_instrument = {}
    if withdraw_request.mode == 'upi':
        bene_instrument = {
            'vpa': withdraw_request.upi_id
        }
    else:
        bene_instrument = {
            'bank_account_number': withdraw_request.account_number,
            'bank_ifsc': withdraw_request.ifsc_code
        }

    bene_payload = {
        'beneficiary_id': beneficiary_id,
        'beneficiary_name': beneficiary_name,
        'beneficiary_instrument_details': bene_instrument
    }

    # Post beneficiary
    try:
        requests.post(f"{base_url}/beneficiaries", json=bene_payload, headers=headers, timeout=20)
    except Exception as e:
        print(f"Beneficiary create exception: {str(e)}")
    
    # 2. Initiate Transfer
    transfer_payload = {
        'transfer_id': f"tx_wd_{withdraw_request.id}",
        'transfer_amount': float(withdraw_request.amount),
        'beneficiary_details': {
            'beneficiary_id': beneficiary_id
        }
    }

    transfer_resp = requests.post(f"{base_url}/transfers", json=transfer_payload, headers=headers, timeout=20)
    
    try:
        data = transfer_resp.json()
    except Exception:
        data = {'raw_text': transfer_resp.text}
        
    return data, transfer_resp.status_code


def create_cashfree_order(amount, user, return_url=None):
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

    if return_url:
        body['order_meta'] = {
            'return_url': return_url
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

        # Get host from request to construct return_url dynamically
        host = request.get_host()
        protocol = 'https' if request.is_secure() else 'http'
        return_url = f"{protocol}://{host}/api/wallet/deposit/callback/?order_id={{order_id}}"

        cashfree_order, ord_status = create_cashfree_order(amount, request.user, return_url=return_url)
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
# Deposit Callback
# ─────────────────────────────────────────────────────────

class DepositCallbackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        order_id = request.GET.get('order_id')
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Payment Completed</title>
            <style>
                body {{
                    background-color: #121212;
                    color: #ffffff;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                }}
                .container {{
                    text-align: center;
                    padding: 30px 20px;
                    border: 2px solid #D4AF37;
                    border-radius: 12px;
                    background-color: #0F0F0F;
                    max-width: 90%;
                    box-shadow: 0 0 20px rgba(212, 175, 55, 0.25);
                }}
                h1 {{
                    color: #D4AF37;
                    font-size: 24px;
                    margin-top: 0;
                    margin-bottom: 10px;
                    letter-spacing: 1px;
                }}
                p {{
                    color: rgba(255, 255, 255, 0.7);
                    font-size: 15px;
                    margin-bottom: 20px;
                }}
                .spinner {{
                    border: 4px solid rgba(255, 255, 255, 0.1);
                    width: 40px;
                    height: 40px;
                    border-radius: 50%;
                    border-left-color: #D4AF37;
                    animation: spin 1s linear infinite;
                    margin: 20px auto;
                }}
                @keyframes spin {{
                    0% {{ transform: rotate(0deg); }}
                    100% {{ transform: rotate(360deg); }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="spinner"></div>
                <h1>Payment Completed</h1>
                <p>Returning to your wallet. Please wait...</p>
            </div>
            <script>
                setTimeout(function() {{
                    try {{
                        window.ReactNativeWebView.postMessage(JSON.stringify({{
                            status: 'success',
                            order_id: '{order_id}'
                        }}));
                    }} catch (e) {{
                        console.error('Not in WebView', e);
                    }}
                }}, 1500);
            </script>
        </body>
        </html>
        """
        from django.http import HttpResponse
        return HttpResponse(html_content, content_type="text/html")


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
        if not order_id:
            return Response({"error": "order_id is required."}, status=400)

        # Call Cashfree API to verify the order status directly
        try:
            cf_data, success = check_cashfree_order_status(order_id)
            if not success:
                return Response({"error": "Failed to fetch order status from Cashfree", "details": cf_data}, status=400)
            
            order_status = cf_data.get('order_status')
            if order_status != 'PAID':
                return Response({"error": f"Payment not paid. Status: {order_status}"}, status=400)

            with db_transaction.atomic():
                txn = Transaction.objects.select_for_update().get(
                    cashfree_order_id=order_id,
                    wallet__user=request.user,
                    status="pending"
                )
                
                payment_id = None
                cf_payment_id = cf_data.get('cf_payment_id')
                if cf_payment_id and not isinstance(cf_payment_id, dict):
                    payment_id = cf_payment_id
                else:
                    payment_id = cf_data.get('payment_session_id') if not isinstance(cf_data.get('payment_session_id'), dict) else None

                txn.cashfree_payment_id = payment_id
                txn.status = "success"
                txn.save()

                wallet = txn.wallet
                wallet.balance += txn.amount
                wallet.save()

        except Transaction.DoesNotExist:
            try:
                txn = Transaction.objects.get(
                    cashfree_order_id=order_id,
                    wallet__user=request.user
                )
                if txn.status == "success":
                    return Response({
                        "message": "Deposit successful!",
                        "balance": str(txn.wallet.balance)
                    })
            except Transaction.DoesNotExist:
                pass
            return Response({"error": "Transaction not found"}, status=404)
        except Exception as e:
            return Response({"error": f"Verification failed: {str(e)}"}, status=500)

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
                # Trigger the payout API
                try:
                    payout_data, status_code = trigger_cashfree_payout(withdraw_request)
                except Exception as e:
                    return Response({
                        "success": False,
                        "message": f"Payout error: {str(e)}"
                    }, status=400)

                # Save payout response log
                withdraw_request.payout_response = payout_data
                withdraw_request.admin_note = admin_note
                
                if status_code in (200, 201, 202):
                    # Extract payout identifier
                    transfer_obj = payout_data.get('transfer', payout_data)
                    cf_transfer_id = transfer_obj.get('cf_transfer_id') or transfer_obj.get('transfer_id')
                    
                    withdraw_request.status = "approved"
                    withdraw_request.razorpay_payout_id = str(cf_transfer_id) if cf_transfer_id else ""
                    withdraw_request.processed_at = timezone.now()
                    withdraw_request.save()

                    # Update associated transaction status to success
                    txn = Transaction.objects.filter(
                        wallet=wallet,
                        reference=str(withdraw_request.id),
                        status="pending"
                    ).first()
                    if txn:
                        txn.status = "success"
                        txn.save()

                    # Trigger email notification
                    try:
                        from .email_hooks import on_admin_withdraw_approved
                        on_admin_withdraw_approved(withdraw_request.wallet.user, withdraw_request)
                    except Exception as email_err:
                        print(f"Failed to send withdraw approved email: {str(email_err)}")

                    return Response({
                        "success": True,
                        "message": "Withdraw approved and Cashfree Payout initiated",
                        "data": payout_data
                    })
                else:
                    # Mark request as failed and return failure message
                    withdraw_request.status = "failed"
                    withdraw_request.processed_at = timezone.now()
                    withdraw_request.save()
                    
                    # Also mark ledger txn as failed
                    txn = Transaction.objects.filter(
                        wallet=wallet,
                        reference=str(withdraw_request.id),
                        status="pending"
                    ).first()
                    if txn:
                        # Revert balance back to user if payout request failed completely at initiation
                        balance_before = wallet.balance
                        balance_after = balance_before + withdraw_request.amount
                        wallet.balance = balance_after
                        wallet.save()
                        
                        txn.status = "failed"
                        txn.balance_after = balance_after
                        txn.save()
                        
                    return Response({
                        "success": False,
                        "message": f"Cashfree Payout initiation failed: {payout_data.get('message', 'Unknown error')}",
                        "details": payout_data
                    }, status=status_code if (status_code and status_code >= 400) else 400)


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