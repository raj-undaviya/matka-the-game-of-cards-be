class AutoRefreshTokenMiddleware:
    """
    Middleware that inspects if request._new_access_token was generated during authentication
    (e.g., when an expired access token was automatically refreshed).
    If present, sets X-Access-Token and X-Refresh-Token response headers so the client
    automatically stores the new tokens without needing a separate refresh request.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        new_access = getattr(request, '_new_access_token', None)
        new_refresh = getattr(request, '_new_refresh_token', None)

        if new_access:
            response['X-Access-Token'] = new_access
            if new_refresh:
                response['X-Refresh-Token'] = new_refresh

            # Expose custom headers to CORS clients
            existing_expose = response.get('Access-Control-Expose-Headers', '')
            expose_list = [h.strip() for h in existing_expose.split(',') if h.strip()]
            for h in ['X-Access-Token', 'X-Refresh-Token', 'x-access-token', 'x-refresh-token']:
                if h not in expose_list:
                    expose_list.append(h)
            response['Access-Control-Expose-Headers'] = ', '.join(expose_list)

        return response
