from django.urls import path
from .views import LoginView, RegisterView,OTPSendView, VerifyOTPView \
    ,ProfileView, TokenRefreshView, ForgetPasswordOTPView \
        , ForgetPasswordVerifyOTPView, ForgetPasswordResetView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('otp/', OTPSendView.as_view(), name='otp-send'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    
    # path('logout/', LogoutView.as_view(), name='logout'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('forget-password/otp/', ForgetPasswordOTPView.as_view(), name='forget-password-otp'),
    path('forget-password/verify-otp/', ForgetPasswordVerifyOTPView.as_view(), name='forget-password-verify-otp'),
    path('forget-password/reset/', ForgetPasswordResetView.as_view(), name='forget-password-reset'),
]