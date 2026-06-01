"""
auths/views.py
===============
Authentication views — EmailService se saari emails jaati hain.
"""
from django.conf import settings
from django.contrib.auth import authenticate
from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

import random
from datetime import datetime

from .models import User, PasswordResetOTP
from .serializers import RegisterSerializer, UserSerializer
from core.email_service import EmailService   # ← central email service


class RegisterView(APIView):
    """
    POST /api/auth/register/
    Body: { "username": "", "email": "", "password": "" }
    """

    permission_classes = [AllowAny]
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()

        # ── OTP generate karo aur email bhejo ────────────────────────────────
        otp = str(random.randint(100000, 999999))
        PasswordResetOTP.objects.create(user=user, otp=otp)
        EmailService.send_registration_otp(user, otp=otp)   # ← registration OTP

        return Response(
            {
                "message": "Registration successful. OTP sent to your email for verification.",
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """
    POST /api/auth/login/
    Body: { "email": "", "password": "" }
    """

    permission_classes = [AllowAny]
    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        user = User.objects.filter(email=email).first()

        if user and user.check_password(password):
            serializer = UserSerializer(user)
            user.last_login = datetime.now()
            user.is_active = True
            user.save()

            # ── Login success alert ───────────────────────────────────────────
            # EmailService.send_login_alert(user, request=request, was_successful=True)

            return Response(
                {"message": "Login successful", "data": serializer.data},
                status=status.HTTP_200_OK,
            )

        # ── Failed login alert ────────────────────────────────────────────────
        if user:  # User exists but wrong password
            EmailService.send_login_alert(user, request=request, was_successful=False)

        return Response(
            {
                "message": "Invalid email or password",
                "errors": {"email": ["Invalid email or password"]},
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )


class OTPSendView(APIView):
    """
    POST /api/auth/otp/send/
    Body: { "email": "" }
    Registration OTP resend.
    """

    permission_classes = [AllowAny]
    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response({"message": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"message": "No user found with this email"}, status=status.HTTP_404_NOT_FOUND)

        # Purane OTPs invalidate karo
        PasswordResetOTP.objects.filter(user=user, is_used=False).update(is_used=True)

        otp = str(random.randint(100000, 999999))
        PasswordResetOTP.objects.create(user=user, otp=otp)

        # ── Registration OTP email ────────────────────────────────────────────
        sent = EmailService.send_registration_otp(user, otp=otp)

        if not sent:
            return Response({"message": "Failed to send OTP email"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"message": "OTP sent successfully"}, status=status.HTTP_200_OK)


class VerifyOTPView(APIView):
    """
    POST /api/auth/otp/verify/
    Body: { "email": "", "otp": "" }
    Registration email verify karo.
    """

    permission_classes = [AllowAny]
    def post(self, request):
        email = request.data.get("email")
        otp = request.data.get("otp")

        if not email or not otp:
            return Response({"message": "Email and OTP are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"message": "No user found with this email"}, status=status.HTTP_404_NOT_FOUND)

        otp_record = PasswordResetOTP.objects.filter(user=user, otp=otp, is_used=False).first()
        if not otp_record:
            return Response({"message": "Invalid OTP"}, status=status.HTTP_400_BAD_REQUEST)

        if otp_record.is_expired():
            otp_record.is_used = True
            otp_record.save()
            return Response({"message": "OTP has expired"}, status=status.HTTP_400_BAD_REQUEST)

        otp_record.is_used = True
        otp_record.save()
        user.is_email_verified = True
        user.save()

        # ── Welcome email OTP verify ke baad ─────────────────────────────────
        EmailService.send_welcome(user)

        return Response({"message": "Email verified successfully. Welcome!"}, status=status.HTTP_200_OK)


class ForgetPasswordOTPView(APIView):
    """
    POST /api/auth/password/forgot/
    Body: { "email": "" }
    Password reset OTP bhejo.
    """

    permission_classes = [AllowAny]
    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response({"message": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"message": "No user found with this email"}, status=status.HTTP_404_NOT_FOUND)

        PasswordResetOTP.objects.filter(user=user, is_used=False).update(is_used=True)

        otp = str(random.randint(100000, 999999))
        PasswordResetOTP.objects.create(user=user, otp=otp)

        # ── Forgot password OTP email ─────────────────────────────────────────
        sent = EmailService.send_forgot_password_otp(user, otp=otp)

        if not sent:
            return Response({"message": "Failed to send OTP email"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"message": "Password reset OTP sent successfully"}, status=status.HTTP_200_OK)


class ForgetPasswordVerifyOTPView(APIView):
    """
    POST /api/auth/password/verify-otp/
    Body: { "email": "", "otp": "" }
    """
    
    permission_classes = [AllowAny]
    def post(self, request):
        email = request.data.get("email")
        otp = request.data.get("otp")

        if not email or not otp:
            return Response({"message": "Email and OTP are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"message": "No user found with this email"}, status=status.HTTP_404_NOT_FOUND)

        otp_record = PasswordResetOTP.objects.filter(user=user, otp=otp, is_used=False).first()
        if not otp_record:
            return Response({"message": "Invalid OTP"}, status=status.HTTP_400_BAD_REQUEST)

        if otp_record.is_expired():
            otp_record.is_used = True
            otp_record.save()
            return Response({"message": "OTP has expired"}, status=status.HTTP_400_BAD_REQUEST)

        otp_record.is_used = True
        otp_record.save()
        user.is_email_verified = True
        user.save()

        return Response({"message": "OTP verified successfully"}, status=status.HTTP_200_OK)


class ForgetPasswordResetView(APIView):
    """
    POST /api/auth/password/reset/
    Body: { "email": "", "new_password": "" }
    """

    permission_classes = [AllowAny]
    def post(self, request):
        email = request.data.get("email")
        new_password = request.data.get("new_password")

        if not email or not new_password:
            return Response({"message": "Email and new password are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"message": "No user found with this email"}, status=status.HTTP_404_NOT_FOUND)

        if not user.is_email_verified:
            return Response(
                {"message": "Email not verified. Please verify OTP first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.is_email_verified = False   # Reset for security
        user.save()

        return Response({"message": "Password reset successfully"}, status=status.HTTP_200_OK)


class ProfileView(APIView):
    """
    GET  /api/auth/profile/
    PUT  /api/auth/profile/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)

    def put(self, request):
        user = request.user
        data = request.data

        user.first_name = data.get("first_name", user.first_name)
        user.last_name = data.get("last_name", user.last_name)
        email = data.get("email", user.email)

        if User.objects.filter(email=email).exclude(pk=user.pk).exists():
            return Response({"error": "This email is already in use."}, status=status.HTTP_400_BAD_REQUEST)

        user.email = email
        user.save()
        return Response(
            {"message": "Profile updated.", "user": UserSerializer(user).data},
            status=status.HTTP_200_OK,
        )


class TokenRefreshView(APIView):
    """
    POST /api/auth/token/refresh/
    Body: { "refresh": "<refresh_token>" }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"error": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            refresh = RefreshToken(refresh_token)
            return Response({"access": str(refresh.access_token)}, status=status.HTTP_200_OK)
        except Exception:
            return Response({"error": "Invalid or expired refresh token."}, status=status.HTTP_400_BAD_REQUEST)
