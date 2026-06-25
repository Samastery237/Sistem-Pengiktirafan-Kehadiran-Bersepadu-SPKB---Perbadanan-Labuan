"""
Abuse protection throttles for the SPKB Attendance API.

Provides IP-based rate throttling that complements DRF's per-endpoint throttles.
These throttles key on the client IP (via get_client_ip) rather than the user,
catching distributed bots that rotate endpoints but come from the same source.

Layered defense:
  - Per-endpoint throttles (existing in views.py/auth_views.py) limit specific actions.
  - GlobalIPThrottle limits total requests per IP across ALL endpoints.
  - AggressiveIPThrottle limits expensive/sensitive endpoints more strictly.
  - BotDetectionThrottle blocks requests with suspicious User-Agent strings.
"""
import logging

from rest_framework.throttling import AnonRateThrottle

from .middleware import get_client_ip

logger = logging.getLogger('security')


class IPRateThrottle(AnonRateThrottle):
    """
    Base throttle keyed by client IP address instead of the default
    DRF cache key (which uses the user or a generic anonymous key).

    This ensures rate limits apply per-IP regardless of which endpoint
    is being hit — a bot cannot bypass per-endpoint throttles by rotating
    through different URLs.
    """

    def get_cache_key(self, request, view):
        ip = get_client_ip(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': ip,
        }

    def get_rate(self):
        return self.THROTTLE_RATES.get(self.scope, self.THROTTLE_RATES.get('anon', '100/day'))

    def allow_request(self, request, view):
        from django.conf import settings
        if settings.DEBUG:
            return True
        return super().allow_request(request, view)


class GlobalIPThrottle(IPRateThrottle):
    """
    Global rate limit per IP across all endpoints.
    100 requests/minute — generous for normal browser usage but stops
    aggressive scraping or botnets hitting many endpoints.
    """
    scope = 'global_ip'


class AggressiveIPThrottle(IPRateThrottle):
    """
    Strict rate limit per IP for expensive/sensitive endpoints.
    20 requests/minute — applied to form submission and PDF generation.
    """
    scope = 'aggressive_ip'


class BotDetectionThrottle(IPRateThrottle):
    """
    Blocks requests from known bot/scraper User-Agent strings.
    30 requests/minute — but most bots will be blocked before hitting
    this limit because the middleware rejects empty/suspicious UAs.
    """
    scope = 'bot_detection'

    # Known bot/scraper User-Agent substrings (lowercase for matching)
    BLOCKED_UA_PATTERNS = (
        'python-requests',
        'python-urllib',
        'curl/',
        'wget/',
        'scrapy',
        'httpclient/',
        'java/',
        'go-http-client',
        'php/',
        'ruby',
        'perl',
        'libwww',
        'apache-httpclient',
        'okhttp',
        'node-fetch',
        'axios/',
        'bot',
        'crawler',
        'spider',
    )

    def allow_request(self, request, view):
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()

        # Block empty User-Agent strings (browsers always send one)
        if not user_agent:
            ip = get_client_ip(request)
            logger.warning(f"BOT DETECTED (Empty User-Agent): IP={ip}, Path={request.path}")
            return False

        # Block known bot User-Agent strings
        for pattern in self.BLOCKED_UA_PATTERNS:
            if pattern in user_agent:
                ip = get_client_ip(request)
                logger.warning(
                    f"BOT DETECTED (User-Agent): IP={ip}, "
                    f"UA='{user_agent[:80]}', Path={request.path}"
                )
                return False

        return True


def get_throttled_response(scope, request):
    """
    Return a 429 response with a localized abuse-protection message.
    Used by the middleware when blocking at the IP level.
    """
    import json
    from django.http import HttpResponse

    ip = get_client_ip(request)
    logger.warning(f"ABUSE PROTECTION TRIGGERED: Scope={scope}, IP={ip}, Path={request.path}")

    body = json.dumps({
        'status': 'error',
        'message': 'Terlalu banyak permintaan. Sila tunggu sebentar dan cuba lagi.',
        'retry_after': 60,
    })
    response = HttpResponse(
        body,
        content_type='application/json',
        status=429,
    )
    response['Retry-After'] = '60'
    return response
