import logging
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.settings import api_settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


class AutoRefreshTokenAuthentication(JWTAuthentication):
    """
    Custom JWT Authentication that:
    1. First validates if the access token (Authorization: Bearer <token>) is valid and not expired.
    2. If the access token is expired, checks if a valid refresh token is available:
       - Via X-Refresh-Token header (or HTTP_X_REFRESH_TOKEN, HTTP_REFRESH_TOKEN)
       - Via cookies (refresh_token or refresh)
       - Via Authorization Bearer header itself (if the refresh token was passed)
    3. If a valid refresh token exists:
       - Uses the refresh token to authenticate the user
       - Generates a fresh new access token
       - Generates a fresh new rotated refresh token
       - Attaches new tokens to request._new_access_token and request._new_refresh_token
         so AutoRefreshTokenMiddleware sets X-Access-Token and X-Refresh-Token in response headers
       - Seamlessly returns (user, new_validated_access_token).
    """

    def authenticate(self, request):
        header = self.get_header(request)
        refresh_header = (
            request.META.get('HTTP_X_REFRESH_TOKEN') or
            request.META.get('HTTP_REFRESH_TOKEN') or
            request.COOKIES.get('refresh_token') or
            request.COOKIES.get('refresh')
        )

        if header is None:
            # Check if refresh token header is present
            if refresh_header:
                return self._authenticate_via_refresh_token(request, refresh_header)
            return None

        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None

        raw_token_str = raw_token.decode('utf-8') if isinstance(raw_token, bytes) else str(raw_token)
        raw_token_str = raw_token_str.strip()

        try:
            # 1. First make sure that the access token is not expired
            validated_token = self.get_validated_token(raw_token)
            user = self.get_user(validated_token)
            return (user, validated_token)
        except (InvalidToken, TokenError) as exc:
            # 2. Access token is expired or invalid.
            # Fallback to refresh token (from X-Refresh-Token header, cookie, or the raw_token itself)
            candidates = [refresh_header, raw_token_str]
            for candidate in candidates:
                if candidate:
                    clean_candidate = candidate.strip()
                    if clean_candidate.startswith('Bearer '):
                        clean_candidate = clean_candidate[7:].strip()
                    result = self._authenticate_via_refresh_token(request, clean_candidate)
                    if result is not None:
                        return result

            # If refresh token fallback also fails or is not present, raise original exception
            raise exc

    def _authenticate_via_refresh_token(self, request, refresh_token_str):
        if not refresh_token_str:
            return None

        try:
            clean_str = refresh_token_str.strip()
            if clean_str.startswith('Bearer '):
                clean_str = clean_str[7:].strip()

            refresh = RefreshToken(clean_str)
            user_id = refresh.payload.get(api_settings.USER_ID_CLAIM, None)
            if not user_id:
                return None

            try:
                user = User.objects.get(**{api_settings.USER_ID_FIELD: user_id})
            except Exception:
                # Fallback to MongoDB ObjectId or string id lookup
                user = User.objects.filter(id=user_id).first()

            if not user or not user.is_active:
                return None

            # Generate fresh new tokens for the user (new access token + rotated new refresh token)
            new_refresh_obj = RefreshToken.for_user(user)
            new_access_token = str(new_refresh_obj.access_token)
            new_refresh_token = str(new_refresh_obj)

            # Attach new tokens to request for middleware to send in response headers
            request._new_access_token = new_access_token
            request._new_refresh_token = new_refresh_token

            # Return user and validated new access token
            new_validated_access = AccessToken(new_access_token)
            return (user, new_validated_access)
        except Exception as e:
            logger.debug(f"Refresh token authentication fallback failed: {e}")
            return None

