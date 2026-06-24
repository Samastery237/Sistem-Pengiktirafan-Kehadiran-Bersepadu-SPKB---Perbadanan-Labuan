import logging
import time
from datetime import timedelta
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger('security')

# Abuse protection configuration
ABUSE_WINDOW_SECONDS = 60          # 1-minute sliding window
ABUSE_MAX_REQUESTS = 100           # max requests per IP per window
ABUSE_BLOCK_DURATION = 300         # 5-minute block when exceeded
ABUSE_CACHE_PREFIX = 'abuse:ip:'

# Traffic anomaly detection thresholds
ANOMALY_404_THRESHOLD = 10         # 404s per IP within window before flagging
ANOMALY_404_WINDOW = 60            # 60-second window for 404 counting
ANOMALY_SCAN_PATHS = (
    'wp-admin', 'wp-login', 'phpmyadmin', 'administrator', '.env',
    '.git', 'wp-config', 'config.xml', 'server-status', 'actuator',
    'debug', 'trace', 'info.php', 'phpinfo', '.htaccess',
)

# User-Agent substrings that indicate bots/scrapers (lowercase)
BLOCKED_UA_PATTERNS = (
    'python-requests', 'python-urllib', 'curl/', 'wget/', 'scrapy',
    'httpclient/', 'java/', 'go-http-client', 'php/', 'ruby', 'perl',
    'libwww', 'apache-httpclient', 'okhttp', 'node-fetch', 'axios/',
)


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def _is_suspicious_user_agent(user_agent):
    """Check if the User-Agent string looks like a bot/scraper."""
    if not user_agent:
        return True  # Browsers always send a UA; empty UA is suspicious
    ua_lower = user_agent.lower()
    for pattern in BLOCKED_UA_PATTERNS:
        if pattern in ua_lower:
            return True
    return False


class SecurityLoggingMiddleware:
    """
    Middleware to log security-relevant events like rate limiting (429)
    and add security headers to all responses.

    Also detects unusual traffic patterns:
      - Multiple 404s from same IP (enumeration/scanning)
      - Requests to known attack paths (wp-admin, .env, etc.)
      - Authentication failures (401/403)
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

        # Log and detect anomalies based on response status
        ip = get_client_ip(request)
        user = request.user.username if request.user.is_authenticated else 'Anonymous'

        if response.status_code == 401:
            logger.warning(
                f"AUTH_FAILURE: IP={ip}, User={user}, Path={request.path}"
            )
        elif response.status_code == 403:
            logger.warning(
                f"ACCESS_DENIED: IP={ip}, User={user}, Path={request.path}"
            )
        elif response.status_code == 429:
            logger.warning(
                f"RATE_LIMITED: IP={ip}, User={user}, Path={request.path}"
            )
        elif response.status_code >= 500:
            logger.error(
                f"SERVER_ERROR: IP={ip}, User={user}, Path={request.path}, "
                f"Status={response.status_code}"
            )
        elif response.status_code == 404:
            self._detect_enumeration(ip, request.path)

        self._detect_attack_path(ip, request.path)

        return response

    def _detect_enumeration(self, ip, path):
        """Detect if an IP is scanning for endpoints (many 404s)."""
        try:
            key = f"anomaly:404:{ip}"
            count = cache.get(key, 0) + 1
            cache.set(key, count, ANOMALY_404_WINDOW)

            if count == ANOMALY_404_THRESHOLD:
                logger.warning(
                    f"SCANNING_DETECTED: IP={ip}, "
                    f"Count={count} 404s in {ANOMALY_404_WINDOW}s, "
                    f"LastPath={path}"
                )
        except Exception:
            pass  # Fail-open on cache errors

    def _detect_attack_path(self, ip, path):
        """Detect requests to known attack paths."""
        path_lower = path.lower()
        for scan_path in ANOMALY_SCAN_PATHS:
            if scan_path in path_lower:
                logger.warning(
                    f"ATTACK_PATH: IP={ip}, Path={path}, Pattern={scan_path}"
                )
                break


class AbuseProtectionMiddleware:
    """
    IP-level abuse protection middleware.

    Tracks requests per IP using the Django cache and enforces a global
    rate limit. Also blocks requests with suspicious User-Agent strings
    (known bots, scrapers, and empty UAs).

    This complements DRF's per-endpoint throttles by catching:
      - Distributed bots that rotate through many endpoints from one IP
      - Scrapers that stay under per-endpoint limits but hammer the server
      - Automated scripts with no/fake User-Agent strings

    Fail-open: if the cache is unavailable, requests pass through.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only protect API paths (not admin, static, etc.)
        if not request.path.startswith('/api/'):
            return self.get_response(request)

        ip = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')

        # Determine if the request is from an authenticated user.
        # The AuthenticationMiddleware runs before us in the middleware chain,
        # so request.user is available.
        is_authenticated = (
            hasattr(request, 'user')
            and request.user.is_authenticated
        )

        # For unauthenticated requests: apply full abuse protection
        # (IP rate limiting + User-Agent bot detection).
        # Authenticated users are protected by DRF's per-endpoint throttles
        # and session security, so we only add rate limit headers for them.
        if not is_authenticated:
            # Check IP-level rate limit
            if self._is_ip_blocked(ip):
                logger.warning(f"BOT BLOCKED (Rate Limit): IP={ip}, Path={request.path}")
                return self._blocked_response(request)

            # Check User-Agent for bot patterns
            if _is_suspicious_user_agent(user_agent):
                logger.warning(
                    f"BOT BLOCKED (User-Agent): IP={ip}, "
                    f"UA='{user_agent[:80] if user_agent else '<empty>'}', "
                    f"Path={request.path}"
                )
                return self._blocked_response(request)

            # Track this request for rate limiting
            self._track_request(ip, request.path, user_agent)

        # Process the request
        response = self.get_response(request)

        # Add rate limit headers for client awareness (only for unauthenticated)
        if not is_authenticated:
            remaining = self._get_remaining_requests(ip)
            response['X-RateLimit-Limit'] = str(ABUSE_MAX_REQUESTS)
            response['X-RateLimit-Remaining'] = str(max(0, remaining))

        return response

    def _get_cache_key(self, ip):
        return f"{ABUSE_CACHE_PREFIX}{ip}"

    def _is_ip_blocked(self, ip):
        """Check if the IP is currently in a block period."""
        try:
            data = cache.get(self._get_cache_key(ip))
            if data and data.get('blocked_until'):
                blocked_until = data['blocked_until']
                if time.time() < blocked_until:
                    return True
            return False
        except Exception:
            # Fail-open on cache errors
            return False

    def _track_request(self, ip, path, user_agent):
        """Increment the request counter for this IP."""
        try:
            key = self._get_cache_key(ip)
            data = cache.get(key)

            now = time.time()

            if data is None:
                # First request in a new window
                cache.set(key, {
                    'count': 1,
                    'window_start': now,
                    'blocked_until': None,
                    'last_path': path,
                    'user_agent': user_agent[:200] if user_agent else None,
                }, ABUSE_WINDOW_SECONDS + 10)
            else:
                window_start = data.get('window_start', now)
                # Reset window if expired
                if now - window_start > ABUSE_WINDOW_SECONDS:
                    data = {
                        'count': 1,
                        'window_start': now,
                        'blocked_until': data.get('blocked_until'),
                        'last_path': path,
                        'user_agent': user_agent[:200] if user_agent else None,
                    }
                else:
                    data['count'] = data.get('count', 0) + 1
                    data['last_path'] = path

                    # Check if we should block this IP
                    if data['count'] > ABUSE_MAX_REQUESTS and not data.get('blocked_until'):
                        data['blocked_until'] = now + ABUSE_BLOCK_DURATION
                        logger.warning(
                            f"IP BLOCKED: IP={ip}, Requests={data['count']}, "
                            f"Duration={ABUSE_BLOCK_DURATION}s"
                        )

                cache.set(key, data, ABUSE_WINDOW_SECONDS + 10)
        except Exception:
            # Fail-open on cache errors
            pass

    def _get_remaining_requests(self, ip):
        """Get remaining requests for this IP in the current window."""
        try:
            data = cache.get(self._get_cache_key(ip))
            if data:
                return ABUSE_MAX_REQUESTS - data.get('count', 0)
            return ABUSE_MAX_REQUESTS
        except Exception:
            return ABUSE_MAX_REQUESTS

    def _blocked_response(self, request):
        """Return a 429 response for blocked requests."""
        import json
        from django.http import HttpResponse

        body = json.dumps({
            'status': 'error',
            'message': 'Terlalu banyak permintaan. Sila tunggu sebentar dan cuba lagi.',
            'retry_after': ABUSE_BLOCK_DURATION,
        })
        response = HttpResponse(
            body,
            content_type='application/json',
            status=429,
        )
        response['Retry-After'] = str(ABUSE_BLOCK_DURATION)
        return response
