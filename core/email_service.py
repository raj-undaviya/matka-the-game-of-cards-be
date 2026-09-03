"""
core/email_service.py
======================
Central Email Service — saari emails yahan se jaati hain.

Har function ek specific event ke liye email bhejta hai.
Gmail SMTP use karta hai (settings.py se config).

Usage:
    from core.email_service import EmailService

    EmailService.send_welcome(user)
    EmailService.send_registration_otp(user, otp="482916")
    EmailService.send_win_notification(user, round_id="V1", amount="500.00")
"""

from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.utils import timezone

from .email_template import EmailTemplates

import logging
logger = logging.getLogger(__name__)


def _send(to_email: str, subject: str, html_body: str) -> bool:
    """
    Internal sender — HTML email bhejta hai.
    Returns True on success, False on failure.
    """
    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body="Please view this email in an HTML-compatible client.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"Email sent: {subject} → {to_email}")
        return True
    except Exception as e:
        logger.error(f"Email failed: {subject} → {to_email} | Error: {e}")
        return False


# ─────────────────────────────────────────────────────────────
#  Auth Emails
# ─────────────────────────────────────────────────────────────

class EmailService:

    # ── 1. Welcome / Registration ────────────────────────────────────────────
    @staticmethod
    def send_welcome(user, login_url: str = "") -> bool:
        """
        Registration ke baad welcome email.
        Call: EmailService.send_welcome(user)
        """
        subject, html = EmailTemplates.user_registration(
            user_name=user.get_full_name() or user.username,
            email=user.email,
            login_url=login_url or settings.FRONTEND_URL + "/login",
        )
        return _send(user.email, subject, html)

    # ── 2. Registration OTP ──────────────────────────────────────────────────
    @staticmethod
    def send_registration_otp(user, otp: str) -> bool:
        """
        Email verification OTP.
        Call: EmailService.send_registration_otp(user, otp="482916")
        """
        subject, html = EmailTemplates.registration_otp(
            user_name=user.get_full_name() or user.username,
            otp=otp,
        )
        return _send(user.email, subject, html)

    # ── 3. Forgot Password OTP ───────────────────────────────────────────────
    @staticmethod
    def send_forgot_password_otp(user, otp: str) -> bool:
        """
        Password reset OTP.
        Call: EmailService.send_forgot_password_otp(user, otp="739201")
        """
        subject, html = EmailTemplates.forgot_password_otp(
            user_name=user.get_full_name() or user.username,
            otp=otp,
        )
        return _send(user.email, subject, html)

    # ── 4. Login Alert ───────────────────────────────────────────────────────
    @staticmethod
    def send_login_alert(user, request=None, was_successful: bool = True) -> bool:
        """
        Login hone par security alert.
        Call: EmailService.send_login_alert(user, request, was_successful=True)
        """
        now = timezone.now().strftime("%d %b %Y, %I:%M %p")

        # IP aur device request se nikalo
        ip = "Unknown"
        device = "Unknown"
        if request:
            ip = (
                request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
                or request.META.get("REMOTE_ADDR", "Unknown")
            )
            ua = request.META.get("HTTP_USER_AGENT", "Unknown")
            device = ua[:80] if ua else "Unknown"

        subject, html = EmailTemplates.login_attempt(
            user_name=user.get_full_name() or user.username,
            login_time=now,
            ip_address=ip,
            device=device,
            location="India",   # Production mein ip-api.com se fetch karo
            was_successful=was_successful,
        )
        return _send(user.email, subject, html)


# ─────────────────────────────────────────────────────────────
#  Wallet Emails
# ─────────────────────────────────────────────────────────────

    # ── 5. Wallet Created ────────────────────────────────────────────────────
    @staticmethod
    def send_wallet_created(user, wallet) -> bool:
        """
        Wallet pehli baar create hone par.
        Call: EmailService.send_wallet_created(user, wallet)
        """
        now = timezone.now().strftime("%d %b %Y, %I:%M %p")
        subject, html = EmailTemplates.wallet_creation_success(
            user_name=user.get_full_name() or user.username,
            wallet_id=f"WLT-{str(wallet.id)[:8].upper()}" if hasattr(wallet, 'id') else "WLT-NEW",
            wallet_type="Standard Wallet",
            created_at=now,
        )
        return _send(user.email, subject, html)

    # ── 6. Deposit Success ───────────────────────────────────────────────────
    @staticmethod
    def send_deposit_success(user, transaction) -> bool:
        """
        Razorpay deposit success ke baad.
        Call: EmailService.send_deposit_success(user, transaction)
        """
        now = timezone.now().strftime("%d %b %Y, %I:%M %p")
        subject, html = EmailTemplates.deposit_success(
            user_name=user.get_full_name() or user.username,
            amount=f"{transaction.amount:,.2f}",
            currency="INR",
            transaction_id=transaction.razorpay_payment_id or str(transaction.id)[:8],
            wallet_balance=f"{transaction.balance_after:,.2f}",
            deposited_at=now,
        )
        return _send(user.email, subject, html)

    # ── 7. Deposit Failed ────────────────────────────────────────────────────
    @staticmethod
    def send_deposit_failed(user, amount: str, reason: str = "Payment could not be processed") -> bool:
        """
        Razorpay deposit fail hone par.
        Call: EmailService.send_deposit_failed(user, amount="500.00")
        """
        now = timezone.now().strftime("%d %b %Y, %I:%M %p")
        subject, html = EmailTemplates.deposit_failed(
            user_name=user.get_full_name() or user.username,
            amount=amount,
            currency="INR",
            reason=reason,
            attempted_at=now,
        )
        return _send(user.email, subject, html)

    # ── 8. Withdraw Success ──────────────────────────────────────────────────
    @staticmethod
    def send_withdraw_success(user, withdraw_request) -> bool:
        """
        Withdrawal process hone ke baad.
        Call: EmailService.send_withdraw_success(user, withdraw_request)
        """
        now = timezone.now().strftime("%d %b %Y, %I:%M %p")

        # Bank ya UPI details
        bank_info = ""
        if withdraw_request.mode == "upi":
            bank_info = f"UPI: {withdraw_request.upi_id}"
        elif withdraw_request.mode == "bank_account":
            bank_info = f"{withdraw_request.account_holder} — ****{str(withdraw_request.account_number)[-4:]}"

        subject, html = EmailTemplates.withdraw_success(
            user_name=user.get_full_name() or user.username,
            amount=f"{withdraw_request.amount:,.2f}",
            currency="INR",
            transaction_id=withdraw_request.razorpay_payout_id or "",
            withdrawn_at=now,
            bank_account=bank_info,
        )
        return _send(user.email, subject, html)

    # ── 9. Withdraw Failed ───────────────────────────────────────────────────
    @staticmethod
    def send_withdraw_failed(user, withdraw_request, reason: str = "") -> bool:
        """
        Withdrawal fail hone par.
        Call: EmailService.send_withdraw_failed(user, withdraw_request)
        """
        now = timezone.now().strftime("%d %b %Y, %I:%M %p")
        subject, html = EmailTemplates.withdraw_failed(
            user_name=user.get_full_name() or user.username,
            amount=f"{withdraw_request.amount:,.2f}",
            currency="INR",
            reason=reason or withdraw_request.admin_note or "Request could not be processed",
            attempted_at=now,
        )
        return _send(user.email, subject, html)

    # ── 10. Admin: Withdraw Approved ─────────────────────────────────────────
    @staticmethod
    def send_withdraw_approved(user, withdraw_request, eta: str = "Within 24 hours") -> bool:
        """
        Admin ne withdraw approve kiya.
        Call: EmailService.send_withdraw_approved(user, withdraw_request)
        """
        now = timezone.now().strftime("%d %b %Y, %I:%M %p")
        bank_info = ""
        if withdraw_request.mode == "upi":
            bank_info = f"UPI: {withdraw_request.upi_id}"
        elif withdraw_request.mode == "bank_account":
            bank_info = f"{withdraw_request.account_holder} — ****{str(withdraw_request.account_number)[-4:]}"

        txn_id = withdraw_request.razorpay_payout_id or f"WD-{withdraw_request.id}"

        subject, html = EmailTemplates.admin_withdraw_approved(
            user_name=user.get_full_name() or user.username,
            amount=f"{withdraw_request.amount:,.2f}",
            currency="INR",
            transaction_id=txn_id,
            approved_at=now,
            bank_account=bank_info,
            eta=eta,
        )
        return _send(user.email, subject, html)

    # ── 11. Admin: Withdraw Rejected ─────────────────────────────────────────
    @staticmethod
    def send_withdraw_rejected(user, withdraw_request) -> bool:
        """
        Admin ne withdraw reject kiya.
        Call: EmailService.send_withdraw_rejected(user, withdraw_request)
        """
        now = timezone.now().strftime("%d %b %Y, %I:%M %p")
        subject, html = EmailTemplates.admin_withdraw_rejected(
            user_name=user.get_full_name() or user.username,
            amount=f"{withdraw_request.amount:,.2f}",
            currency="INR",
            reason=withdraw_request.admin_note or "Request did not meet approval criteria",
            rejected_at=now,
        )
        return _send(user.email, subject, html)


# ─────────────────────────────────────────────────────────────
#  Game Emails
# ─────────────────────────────────────────────────────────────

    # ── 12. Win Notification ─────────────────────────────────────────────────
    @staticmethod
    def send_win_notification(user, bet, round_obj) -> bool:
        """
        Game jeetneke baad winner ko email.
        Call: EmailService.send_win_notification(user, bet, round_obj)
        """
        now = timezone.now().strftime("%d %b %Y, %I:%M %p")
        subject, html = EmailTemplates.account_credit(
            user_name=user.get_full_name() or user.username,
            amount=f"{bet.reward_amount:,.2f}",
            currency="INR",
            credit_reason=f"Game Win — {round_obj.get_variation_display()} ({bet.win_type})",
            transaction_id=str(round_obj.id)[:8].upper(),
            credited_at=now,
        )
        return _send(user.email, subject, html)