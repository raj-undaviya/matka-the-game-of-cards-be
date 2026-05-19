from .models import User, PasswordResetOTP
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.mail import send_mail
from django.conf import settings

from datetime import datetime
import random

from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from .serializers import RegisterSerializer, UserSerializer


class RegisterView(APIView):

    permission_classes = [AllowAny]
    """
    POST /api/auth/register/
    Body: { "username": "", "email": "", "password": ""}
    """

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                {
                    "message": "User registered successfully.",
                    "user": UserSerializer(user).data,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """
    POST /api/auth/login/
    Body: { "username": "", "password": "" }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        user = User.objects.filter(email=email).first()
        print("Found user for email:", email, "User:", user)

        if user and user.check_password(password):

            serializer = UserSerializer(user)
            print("User serializer data:", serializer.data)

            user.token = serializer.data["token"]
            print("Serializer token:", serializer.data["token"])
            user.is_active = True
            user.last_login = datetime.now()
            user.save()

            return Response(
                {"message": "Login successful", "data": serializer.data},
                status=status.HTTP_200_OK,
            )

        return Response(
            {"message": "Invalid email or password", "errors": {"email": ["Invalid email or password"]}},
            status=status.HTTP_401_UNAUTHORIZED,
        )

class OTPSendView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")

        if not email:
            return Response(
                {"message": "Email is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)

        except User.DoesNotExist:
            return Response(
                {"message": "No user found with this email"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Invalidate old OTPs
        PasswordResetOTP.objects.filter(
            user=user,
            is_used=False
        ).update(is_used=True)

        # Generate 6-digit OTP
        otp = str(random.randint(100000, 999999))

        # Save OTP
        PasswordResetOTP.objects.create(
            user=user,
            otp=otp
        )

        try:
            send_mail(
                subject="Password Reset OTP",
                message=f"""
                        Hello {user.username},

                        Your OTP for password reset is:

                        {otp}

                        This OTP will expire in 10 minutes.

                        If you did not request this, please ignore this email.
            """,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )

            return Response(
                {"message": "OTP sent successfully"},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {
                    "message": "Failed to send OTP email",
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class VerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):

        email = request.data.get("email")
        otp = request.data.get("otp")

        if not email or not otp:
            return Response(
                {"message": "Email and OTP are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)

            otp_record = PasswordResetOTP.objects.filter(
                user=user,
                otp=otp,
                is_used=False
            ).first()

            if not otp_record:
                return Response(
                    {"message": "Invalid OTP"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if otp_record.is_expired():

                otp_record.is_used = True
                otp_record.save()

                return Response(
                    {"message": "OTP has expired"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Mark OTP as used
            otp_record.is_used = True
            otp_record.save()
            user.is_email_verified = True
            user.save()

            return Response(
                {"message": "OTP verified successfully"},
                status=status.HTTP_200_OK,
            )

        except User.DoesNotExist:
            return Response(
                {"message": "No user found with this email"},
                status=status.HTTP_404_NOT_FOUND,
            )

# class LogoutView(APIView):
#     """
#     POST /api/auth/logout/
#     Header: Authorization: Bearer <access_token>
#     Body:   { "refresh": "<refresh_token>" }
#     Blacklists the refresh token so it can't be reused.
#     """

#     permission_classes = [IsAuthenticated]

#     def post(self, request):
#         refresh_token = request.data.get("refresh")
#         if not refresh_token:
#             return Response(
#                 {"error": "Refresh token is required."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )
#         try:
#             token = RefreshToken(refresh_token)
#             token.blacklist()
#             return Response(
#                 {"message": "Logged out successfully."},
#                 status=status.HTTP_200_OK,
#             )
#         except Exception:
#             return Response(
#                 {"error": "Invalid or expired refresh token."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )


class ProfileView(APIView):
    """
    GET  /api/auth/profile/  — get logged-in user's profile
    PUT  /api/auth/profile/  — update first_name, last_name, email
    Header: Authorization: Bearer <access_token>
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

        # Ensure email uniqueness (exclude current user)
        if User.objects.filter(email=email).exclude(pk=user.pk).exists():
            return Response(
                {"error": "This email is already in use."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.email = email
        user.save()
        return Response(
            {"message": "Profile updated.", "user": UserSerializer(user).data},
            status=status.HTTP_200_OK,
        )


class TokenRefreshView(APIView):

    permission_classes = [AllowAny]
    
    """
    POST /api/auth/token/refresh/
    Body: { "refresh": "<refresh_token>" }
    Returns a new access token.
    """

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"error": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            refresh = RefreshToken(refresh_token)
            return Response(
                {"access": str(refresh.access_token)},
                status=status.HTTP_200_OK,
            )
        except Exception:
            return Response(
                {"error": "Invalid or expired refresh token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

class ForgetPasswordOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")

        if not email:
            return Response(
                {"message": "Email is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)

        except User.DoesNotExist:
            return Response(
                {"message": "No user found with this email"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Invalidate old OTPs
        PasswordResetOTP.objects.filter(
            user=user,
            is_used=False
        ).update(is_used=True)

        # Generate 6-digit OTP
        otp = str(random.randint(100000, 999999))

        # Save OTP
        PasswordResetOTP.objects.create(
            user=user,
            otp=otp
        )

        try:
            send_mail(
                subject="Password Reset OTP",
                message=f"""
                        Hello {user.username},

                        Your OTP for password reset is:

                        {otp}

                        This OTP will expire in 10 minutes.

                        If you did not request this, please ignore this email.
            """,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )

            return Response(
                {"message": "OTP sent successfully"},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {
                    "message": "Failed to send OTP email",
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class ForgetPasswordVerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):

        email = request.data.get("email")
        otp = request.data.get("otp")

        if not email or not otp:
            return Response(
                {"message": "Email and OTP are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)

            otp_record = PasswordResetOTP.objects.filter(
                user=user,
                otp=otp,
                is_used=False
            ).first()

            if not otp_record:
                return Response(
                    {"message": "Invalid OTP"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if otp_record.is_expired():

                otp_record.is_used = True
                otp_record.save()

                return Response(
                    {"message": "OTP has expired"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Mark OTP as used
            otp_record.is_used = True
            otp_record.save()

            return Response(
                {"message": "OTP verified successfully"},
                status=status.HTTP_200_OK,
            )

        except User.DoesNotExist:
            return Response(
                {"message": "No user found with this email"},
                status=status.HTTP_404_NOT_FOUND,
            )

class ForgetPasswordResetView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        new_password = request.data.get("new_password")

        if not email or not new_password:
            return Response(
                {"message": "Email and new password are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)

            if not user.is_email_verified:
                return Response(
                    {"message": "Email not verified. Please verify OTP first."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.set_password(new_password)
            user.save()

            return Response(
                {"message": "Password reset successfully"},
                status=status.HTTP_200_OK,
            )

        except User.DoesNotExist:
            return Response(
                {"message": "No user found with this email"},
                status=status.HTTP_404_NOT_FOUND,
            )
