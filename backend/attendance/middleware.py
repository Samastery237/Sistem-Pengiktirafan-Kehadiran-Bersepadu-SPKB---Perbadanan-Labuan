import logging
from datetime import timedelta
from django.utils import timezone

logger = logging.getLogger('security')


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


class SecurityLoggingMiddleware:
    """
    Middleware to log security-relevant events like rate limiting (429)
    and add security headers to all responses.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Add security headers to every response
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'

        # Prevent caching of authenticated responses
        if request.path.startswith('/api/'):
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'

        # Log rate limit violations
        if response.status_code == 429:
            ip = get_client_ip(request)
            user = request.user.username if request.user.is_authenticated else 'Anonymous'
            path = request.path
            logger.warning(f"RATE LIMIT TRIGGERED: IP={ip}, User={user}, Path={path}")

        return response
