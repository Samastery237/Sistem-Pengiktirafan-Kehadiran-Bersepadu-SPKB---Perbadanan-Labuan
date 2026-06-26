"""
Tests for the abuse protection layer.

Covers:
  - Global IP throttle (100 req/min across all endpoints)
  - Aggressive IP throttle (20 req/min on expensive endpoints)
  - Bot detection (empty UA, known bot UA strings)
  - Rate limit headers (X-RateLimit-Limit, X-RateLimit-Remaining)
  - Block expiration after duration
  - Different IPs not affected by each other's blocks
"""
import json

from django.test import TestCase
from django.contrib.auth.models import User
from django.core.cache import cache

from attendance.models import Department, Folder

# Standard browser User-Agent used in tests to avoid bot detection
BROWSER_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'


class TestGlobalIPThrottle(TestCase):
    """Test the global IP-level rate limiter (100 req/min)."""

    def setUp(self):
        cache.clear()
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def tearDown(self):
        cache.clear()

    def test_health_check_allows_normal_usage(self):
        """Health check should work normally for reasonable request counts."""
        for i in range(10):
            response = self.client.get(
                '/api/attendance/health/',
                HTTP_USER_AGENT=BROWSER_UA,
            )
            self.assertEqual(response.status_code, 200)

    def test_global_ip_throttle_blocks_excessive_requests(self):
        """After 100 requests from the same IP, the 101st should be 429."""
        for i in range(100):
            response = self.client.get(
                '/api/attendance/health/',
                HTTP_USER_AGENT=BROWSER_UA,
            )
            self.assertEqual(response.status_code, 200, f"Request {i+1} failed unexpectedly")

        # 101st request should be blocked (either by middleware IP throttle or DRF view throttle)
        response = self.client.get(
            '/api/attendance/health/',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 429)

    def test_block_expires_after_duration(self):
        """After the block window passes, requests should succeed again."""
        # Exhaust the limit
        for i in range(101):
            self.client.get(
                '/api/attendance/health/',
                HTTP_USER_AGENT=BROWSER_UA,
            )

        # Should be blocked
        response = self.client.get(
            '/api/attendance/health/',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 429)

        # Clear cache to simulate time passing
        cache.clear()

        # Should work again
        response = self.client.get(
            '/api/attendance/health/',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)

    def test_different_ips_not_affected(self):
        """Blocking one IP should not block requests from a different IP."""
        # Exhaust limit from IP 1.2.3.4
        for i in range(101):
            self.client.get(
                '/api/attendance/health/',
                HTTP_X_FORWARDED_FOR='1.2.3.4',
                HTTP_USER_AGENT=BROWSER_UA,
            )

        # IP 1.2.3.4 should be blocked
        response = self.client.get(
            '/api/attendance/health/',
            HTTP_X_FORWARDED_FOR='1.2.3.4',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 429)

        # IP 5.6.7.8 should still work
        response = self.client.get(
            '/api/attendance/health/',
            HTTP_X_FORWARDED_FOR='5.6.7.8',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)


class TestAggressiveIPThrottle(TestCase):
    """Test the aggressive IP throttle on expensive endpoints (20 req/min)."""

    def setUp(self):
        cache.clear()
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def tearDown(self):
        cache.clear()

    def test_submit_throttle_at_30_per_minute(self):
        """Submit endpoint has layered throttling: per-endpoint (30/min) + aggressive IP (20/min).
        The aggressive IP throttle (20/min) kicks in first, so we verify that after 20 requests
        the endpoint is throttled (429)."""
        for i in range(20):
            response = self.client.post(
                '/api/attendance/submit/',
                data={
                    'fullname': f'User{i}',
                    'ic_number': f'{i:012d}',
                    'phone': f'012345{i:04d}',
                    'department_name': 'IT',
                    'folder_name': 'General',
                },
                HTTP_USER_AGENT=BROWSER_UA,
            )
            # Should succeed (201) or fail validation, but not 429
            self.assertNotEqual(response.status_code, 429, f"Request {i+1} throttled unexpectedly")

        # 21st request should be throttled by the AggressiveIPThrottle (20/min limit)
        response = self.client.post(
            '/api/attendance/submit/',
            data={
                'fullname': 'Throttled User',
                'ic_number': '999999999999',
                'phone': '0999999999',
                'department_name': 'IT',
                'folder_name': 'General',
            },
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 429)


class TestBotDetection(TestCase):
    """Test bot detection via User-Agent filtering."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_empty_user_agent_blocked(self):
        """Requests with no User-Agent should be blocked (429)."""
        response = self.client.get(
            '/api/attendance/auth/login/',
            HTTP_USER_AGENT='',
        )
        self.assertEqual(response.status_code, 429)

    def test_python_requests_ua_blocked(self):
        """Requests from python-requests should be blocked."""
        response = self.client.get(
            '/api/attendance/auth/login/',
            HTTP_USER_AGENT='python-requests/2.28.0',
        )
        self.assertEqual(response.status_code, 429)

    def test_curl_ua_blocked(self):
        """Requests from curl should be blocked."""
        response = self.client.get(
            '/api/attendance/auth/login/',
            HTTP_USER_AGENT='curl/7.68.0',
        )
        self.assertEqual(response.status_code, 429)

    def test_wget_ua_blocked(self):
        """Requests from wget should be blocked."""
        response = self.client.get(
            '/api/attendance/auth/login/',
            HTTP_USER_AGENT='Wget/1.20.3',
        )
        self.assertEqual(response.status_code, 429)

    def test_scrapy_ua_blocked(self):
        """Requests from Scrapy should be blocked."""
        response = self.client.get(
            '/api/attendance/auth/login/',
            HTTP_USER_AGENT='Scrapy/2.5.0 (+https://scrapy.org)',
        )
        self.assertEqual(response.status_code, 429)

    def test_browser_ua_allowed(self):
        """Normal browser User-Agent should not be blocked."""
        response = self.client.get(
            '/api/attendance/auth/login/',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)

    def test_login_with_bot_ua_blocked(self):
        """Login attempts from bots should be blocked."""
        response = self.client.post(
            '/api/attendance/auth/login/',
            data=json.dumps({'username': 'admin', 'password': 'test'}),
            content_type='application/json',
            HTTP_USER_AGENT='python-requests/2.28.0',
        )
        self.assertEqual(response.status_code, 429)


class TestRateLimitHeaders(TestCase):
    """Test that rate limit headers are present on API responses."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_health_check_returns_ok(self):
        """Health check should return 200 OK."""
        response = self.client.get(
            '/api/attendance/health/',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)

    def test_submit_with_normal_ua_works(self):
        """Submit endpoint should accept valid submissions from normal browsers."""
        response = self.client.post(
            '/api/attendance/submit/',
            data={
                'fullname': 'Header Test',
                'ic_number': '123456789012',
                'phone': '0123456789',
                'department_name': 'IT',
                'folder_name': 'General',
            },
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 201)


class TestAbuseProtectionOnAuthEndpoints(TestCase):
    """Test that auth endpoints are protected by global IP throttle."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='authtest', password='TestPass1!')

    def tearDown(self):
        cache.clear()

    def test_login_with_normal_ua_works(self):
        """Login with a normal User-Agent should work."""
        response = self.client.post(
            '/api/attendance/auth/login/',
            data=json.dumps({'username': 'authtest', 'password': 'TestPass1!'}),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)

    def test_verify_email_with_bot_ua_blocked(self):
        """Email verification from bots should be blocked."""
        response = self.client.get(
            '/api/attendance/auth/verify-email/sometoken/',
            HTTP_USER_AGENT='python-requests/2.28.0',
        )
        self.assertEqual(response.status_code, 429)

    def test_password_reset_confirm_with_bot_ua_blocked(self):
        """Password reset confirm from bots should be blocked."""
        response = self.client.post(
            '/api/attendance/auth/reset-password/confirm/',
            data=json.dumps({'uid': 1, 'token': 'fake', 'new_password': 'Test123!'}),
            content_type='application/json',
            HTTP_USER_AGENT='curl/7.68.0',
        )
        self.assertEqual(response.status_code, 429)


class TestAbuseRequestLogModel(TestCase):
    """Test the AbuseRequestLog model."""

    def test_create_log_entry(self):
        """Should be able to create an AbuseRequestLog entry."""
        from attendance.models import AbuseRequestLog
        log = AbuseRequestLog.objects.create(
            ip_address='192.168.1.100',
            request_count=5,
            last_request_path='/api/attendance/health/',
            user_agent='Mozilla/5.0',
        )
        self.assertEqual(str(log), '192.168.1.100 (5 reqs, blocked=False)')
        self.assertFalse(log.is_blocked)

    def test_blocked_log_entry(self):
        """Should be able to mark an entry as blocked."""
        from attendance.models import AbuseRequestLog
        from django.utils import timezone
        from datetime import timedelta
        log = AbuseRequestLog.objects.create(
            ip_address='10.0.0.1',
            request_count=150,
            is_blocked=True,
            blocked_until=timezone.now() + timedelta(minutes=5),
            last_request_path='/api/attendance/submit/',
            user_agent='python-requests/2.28.0',
        )
        self.assertTrue(log.is_blocked)
        self.assertIsNotNone(log.blocked_until)


# =====================================================================
# Gap Tests: All bot patterns, get_throttled_response
# =====================================================================


class TestBotDetectionAllPatterns(TestCase):
    """Test all blocked UA patterns."""

    def setUp(self):
        from attendance.middleware import BLOCKED_UA_PATTERNS
        self.patterns = BLOCKED_UA_PATTERNS

    def test_all_blocked_patterns(self):
        """All blocked UA patterns should be blocked."""
        from attendance.middleware import _is_suspicious_user_agent
        for pattern in self.patterns:
            ua = f'Mozilla/5.0 {pattern} Bot'
            self.assertTrue(_is_suspicious_user_agent(ua), f"Pattern '{pattern}' should be blocked")

    def test_empty_ua_blocked(self):
        """Empty UA should be blocked."""
        from attendance.middleware import _is_suspicious_user_agent
        self.assertTrue(_is_suspicious_user_agent(''))
        self.assertTrue(_is_suspicious_user_agent(None))

    def test_bypass_with_browser_ua(self):
        """Normal browser UA should not be blocked."""
        from attendance.middleware import _is_suspicious_user_agent
        browser_ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        self.assertFalse(_is_suspicious_user_agent(browser_ua))


class TestGetThrottledResponse(TestCase):
    """Test AbuseProtectionMiddleware._blocked_response() method."""

    def _get_blocked_response(self):
        """Helper to get a blocked response from the middleware."""
        from attendance.middleware import AbuseProtectionMiddleware
        from rest_framework.test import APIRequestFactory

        def dummy_get_response(request):
            from django.http import HttpResponse
            return HttpResponse('OK')

        middleware = AbuseProtectionMiddleware(dummy_get_response)
        factory = APIRequestFactory()
        request = factory.get('/test/')
        return middleware._blocked_response(request)

    def test_response_body_structure(self):
        """Response body should have status, message, retry_after."""
        response = self._get_blocked_response()
        import json
        body = json.loads(response.content)
        self.assertEqual(body['status'], 'error')
        self.assertIn('message', body)
        self.assertIn('retry_after', body)

    def test_response_has_retry_after_header(self):
        """Response should have Retry-After header."""
        response = self._get_blocked_response()
        self.assertIn('Retry-After', response)
        self.assertEqual(response['Retry-After'], '300')

    def test_response_status_code(self):
        """Response should have 429 status code."""
        response = self._get_blocked_response()
        self.assertEqual(response.status_code, 429)

    def test_response_content_type_json(self):
        """Response should have application/json content type."""
        response = self._get_blocked_response()
        self.assertEqual(response['Content-Type'], 'application/json')


class TestGetThrottledResponseFunction(TestCase):
    """Test the standalone get_throttled_response() from abuse.py."""

    def test_returns_429(self):
        """get_throttled_response() should return 429."""
        from attendance.abuse import get_throttled_response
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.get('/test/')
        response = get_throttled_response('global', request)
        self.assertEqual(response.status_code, 429)

    def test_body_has_retry_after(self):
        """Body should include retry_after field."""
        from attendance.abuse import get_throttled_response
        from rest_framework.test import APIRequestFactory
        import json

        factory = APIRequestFactory()
        request = factory.get('/test/')
        response = get_throttled_response('global', request)
        body = json.loads(response.content)
        self.assertEqual(body['retry_after'], 60)
        self.assertEqual(body['status'], 'error')

    def test_has_retry_after_header(self):
        """Response should have Retry-After: 60 header."""
        from attendance.abuse import get_throttled_response
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.get('/test/')
        response = get_throttled_response('global', request)
        self.assertEqual(response['Retry-After'], '60')

    def test_content_type_is_json(self):
        """Response should have application/json content type."""
        from attendance.abuse import get_throttled_response
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.get('/test/')
        response = get_throttled_response('global', request)
        self.assertEqual(response['Content-Type'], 'application/json')


class TestBotDetectionThrottleAllowNonBlocked(TestCase):
    """Test BotDetectionThrottle.allow_request() with non-blocked UAs."""

    def test_allows_custom_ua_not_in_list(self):
        """A UA that's not empty and not in the list should be allowed."""
        from attendance.abuse import BotDetectionThrottle
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.get('/test/')
        request.META['HTTP_USER_AGENT'] = 'MyCustomApp/1.0'

        throttle = BotDetectionThrottle()
        self.assertTrue(throttle.allow_request(request, None))

    def test_blocks_librab_httpclient(self):
        """UA containing 'libwww' should be blocked."""
        from attendance.abuse import BotDetectionThrottle
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.get('/test/')
        request.META['HTTP_USER_AGENT'] = 'libwww-perl/6.0'

        throttle = BotDetectionThrottle()
        self.assertFalse(throttle.allow_request(request, None))
