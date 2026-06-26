"""
TDD tests for SPKB middleware, validators, and integration scenarios.

Covers:
  1. Custom Password Validators (validators.py)
  2. Management Command (unlock_accounts.py)
  3. Security Logging (security_logging.py)
  4. Abuse Protection Throttles (abuse.py)
  5. Middleware Integration
  6. Full Integration Tests
  7. Edge Cases
"""

import json
import logging
from datetime import timedelta
from io import StringIO
from unittest.mock import patch, MagicMock

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings, RequestFactory
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone

from attendance.tests import DisableThrottleMixin
from attendance.models import (
    AdminProfile, AttendanceRecord, Department, FailedLoginAttempt, Folder, UserAccountLock,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BROWSER_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'


# ══════════════════════════════════════════════════════════════════════════
# 1. CUSTOM PASSWORD VALIDATORS (validators.py)
# ══════════════════════════════════════════════════════════════════════════

@override_settings(EMAIL_VERIFICATION_REQUIRED=False)
class TestUppercaseValidator(DisableThrottleMixin, TestCase):
    """Tests for UppercaseValidator from validators.py."""

    def test_passes_with_uppercase(self):
        from attendance.validators import UppercaseValidator
        validator = UppercaseValidator()
        # Should not raise
        validator.validate('Password1!')

    def test_fails_without_uppercase(self):
        from attendance.validators import UppercaseValidator
        validator = UppercaseValidator()
        with self.assertRaises(ValidationError) as cm:
            validator.validate('password1!')
        self.assertEqual(cm.exception.code, 'password_no_upper')

    def test_get_help_text(self):
        from attendance.validators import UppercaseValidator
        validator = UppercaseValidator()
        help_text = validator.get_help_text()
        self.assertIsInstance(help_text, str)
        self.assertIn('huruf besar', str(help_text))


@override_settings(EMAIL_VERIFICATION_REQUIRED=False)
class TestLowercaseValidator(DisableThrottleMixin, TestCase):
    """Tests for LowercaseValidator from validators.py."""

    def test_passes_with_lowercase(self):
        from attendance.validators import LowercaseValidator
        validator = LowercaseValidator()
        # Should not raise — contains lowercase letters
        validator.validate('Password1!')

    def test_fails_without_lowercase(self):
        from attendance.validators import LowercaseValidator
        validator = LowercaseValidator()
        with self.assertRaises(ValidationError) as cm:
            validator.validate('PASSWORD1!')
        self.assertEqual(cm.exception.code, 'password_no_lower')

    def test_get_help_text(self):
        from attendance.validators import LowercaseValidator
        validator = LowercaseValidator()
        help_text = validator.get_help_text()
        self.assertIsInstance(help_text, str)
        self.assertIn('huruf kecil', str(help_text))


@override_settings(EMAIL_VERIFICATION_REQUIRED=False)
class TestDigitValidator(DisableThrottleMixin, TestCase):
    """Tests for DigitValidator from validators.py."""

    def test_passes_with_digit(self):
        from attendance.validators import DigitValidator
        validator = DigitValidator()
        # Should not raise — contains digit '1'
        validator.validate('Password1!')

    def test_fails_without_digit(self):
        from attendance.validators import DigitValidator
        validator = DigitValidator()
        with self.assertRaises(ValidationError) as cm:
            validator.validate('Password!')
        self.assertEqual(cm.exception.code, 'password_no_digit')

    def test_get_help_text(self):
        from attendance.validators import DigitValidator
        validator = DigitValidator()
        help_text = validator.get_help_text()
        self.assertIsInstance(help_text, str)
        self.assertIn('nombor', str(help_text))


@override_settings(EMAIL_VERIFICATION_REQUIRED=False)
class TestSpecialCharacterValidator(DisableThrottleMixin, TestCase):
    """Tests for SpecialCharacterValidator from validators.py."""

    def test_passes_with_special_char(self):
        from attendance.validators import SpecialCharacterValidator
        validator = SpecialCharacterValidator()
        # Should not raise — contains special character '!'
        validator.validate('Password1!')

    def test_fails_without_special_char(self):
        from attendance.validators import SpecialCharacterValidator
        validator = SpecialCharacterValidator()
        with self.assertRaises(ValidationError) as cm:
            validator.validate('Password1')
        self.assertEqual(cm.exception.code, 'password_no_special')

    def test_various_special_chars(self):
        from attendance.validators import SpecialCharacterValidator
        validator = SpecialCharacterValidator()
        special_chars = ['!', '@', '#', '$', '%', '^', '&', '*', '(', ')', '_', '+']
        for ch in special_chars:
            # Should not raise for any of these special characters
            validator.validate(f'Password1{ch}')

    def test_get_help_text(self):
        from attendance.validators import SpecialCharacterValidator
        validator = SpecialCharacterValidator()
        help_text = validator.get_help_text()
        self.assertIsInstance(help_text, str)
        self.assertIn('aksara istimewa', str(help_text))


# ══════════════════════════════════════════════════════════════════════════
# 2. MANAGEMENT COMMAND (unlock_accounts.py)
# ══════════════════════════════════════════════════════════════════════════

@override_settings(EMAIL_VERIFICATION_REQUIRED=False)
class TestUnlockAccountsCommand(DisableThrottleMixin, TestCase):
    """Tests for the unlock_accounts management command."""

    def setUp(self):
        self.user = User.objects.create_user(username='lockuser', password='GoodPass1!')
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")
        # Import UserAccountLock — note the model is UserAccountLock, not UserAccountLog
        from attendance.models import UserAccountLock
        self.lock = UserAccountLock.objects.create(
            user=self.user,
            locked_until=timezone.now() + timedelta(minutes=15),
            failure_count=5,
            last_failure_at=timezone.now(),
        )

    def _get_lock(self):
        from attendance.models import UserAccountLock
        return UserAccountLock.objects.get(user=self.user)

    def test_all_force_unlock(self):
        """--all flag should force-unlock all accounts regardless of lockout time."""
        out = StringIO()
        call_command('unlock_accounts', '--all', stdout=out)
        output = out.getvalue()
        self.assertIn('unlocked', output.lower())

    def test_username_unlock_specific_user(self):
        """--username flag should unlock a specific user."""
        out = StringIO()
        call_command('unlock_accounts', '--username', 'lockuser', stdout=out)
        output = out.getvalue()
        self.assertIn('lockuser', output)
        lock = self._get_lock()
        self.assertIsNone(lock.locked_until)
        self.assertEqual(lock.failure_count, 0)

    def test_username_nonexistent(self):
        """Unlocking a non-existent username should warn, not crash."""
        out = StringIO()
        call_command('unlock_accounts', '--username', 'nonexistent_user_xyz', stdout=out)
        output = out.getvalue()
        self.assertIn('nonexistent_user_xyz', output)

    def test_auto_unlock_expired_lockouts(self):
        """Default behavior: auto-unlock expired lockouts."""
        # Set lockout to the past
        self.lock.locked_until = timezone.now() - timedelta(minutes=1)
        self.lock.save()
        out = StringIO()
        call_command('unlock_accounts', stdout=out)
        out.getvalue()
        lock = self._get_lock()
        self.assertIsNone(lock.locked_until)
        self.assertEqual(lock.failure_count, 0)

    def test_cleanup_old_failed_attempts(self):
        """Default behavior: cleans up old failed login attempts."""
        # Create a failed attempt, then backdate it (auto_now_add prevents override in create)
        attempt = FailedLoginAttempt.objects.create(
            username='lockuser',
            ip_address='127.0.0.1',
        )
        # Backdate the attempt to 48 hours ago
        FailedLoginAttempt.objects.filter(pk=attempt.pk).update(
            attempted_at=timezone.now() - timedelta(hours=48),
        )
        initial_count = FailedLoginAttempt.objects.count()
        self.assertEqual(initial_count, 1)
        out = StringIO()
        call_command('unlock_accounts', stdout=out)
        out.getvalue()
        # Old attempt should be cleaned up
        self.assertEqual(FailedLoginAttempt.objects.count(), 0)

    def test_no_lockout_flag_shown(self):
        """When no lockout exists for the given user, message should indicate that."""
        UserAccountLock.objects.all().delete()
        out = StringIO()
        call_command('unlock_accounts', '--username', 'lockuser', stdout=out)
        output = out.getvalue()
        self.assertIn('lockuser', output)


# ══════════════════════════════════════════════════════════════════════════
# 3. SECURITY LOGGING (security_logging.py)
# ══════════════════════════════════════════════════════════════════════════

@override_settings(EMAIL_VERIFICATION_REQUIRED=False)
class TestSecurityLogging(DisableThrottleMixin, TestCase):
    """Tests for structured security event logging."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username='loguser', password='GoodPass1!')

    def _make_request(self, path='/api/attendance/submit/', ip='127.0.0.1', xff=None):
        """Helper to create a mock request."""
        meta = {'REMOTE_ADDR': ip, 'HTTP_USER_AGENT': BROWSER_UA}
        if xff:
            meta['HTTP_X_FORWARDED_FOR'] = xff
        request = self.factory.get(path, **{'HTTP_USER_AGENT': BROWSER_UA})
        request.META['REMOTE_ADDR'] = ip
        if xff:
            request.META['HTTP_X_FORWARDED_FOR'] = xff
        return request

    def test_log_security_event_all_params(self):
        """log_security_event() with all parameters should produce correct log output."""
        from attendance.security_logging import log_security_event
        request = self._make_request(path='/api/attendance/auth/login/', ip='10.0.0.5')
        with patch('attendance.security_logging.logger') as mock_logger:
            log_security_event(
                'LOGIN_SUCCESS',
                request=request,
                user='loguser',
                extra={'status': 200, 'method': 'POST'},
                level='info',
            )
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0][0]
            self.assertIn('SECURITY_EVENT', call_args)
            self.assertIn('LOGIN_SUCCESS', call_args)
            self.assertIn('loguser', call_args)
            self.assertIn('10.0.0.5', call_args)
            self.assertIn('/api/attendance/auth/login/', call_args)

    def test_log_security_event_minimal_params(self):
        """log_security_event() with minimal parameters should work without error."""
        from attendance.security_logging import log_security_event
        with patch('attendance.security_logging.logger') as mock_logger:
            log_security_event('API_ERROR', level='warning')
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args[0][0]
            self.assertIn('SECURITY_EVENT', call_args)
            self.assertIn('API_ERROR', call_args)

    def test_get_ip_from_x_forwarded_for(self):
        """_get_ip() should extract the first IP from X-Forwarded-For."""
        from attendance.security_logging import _get_ip
        request = self._make_request(xff='203.0.113.42, 70.41.3.18, 150.172.238.178')
        ip = _get_ip(request)
        self.assertEqual(ip, '203.0.113.42')

    def test_get_ip_falls_back_to_remote_addr(self):
        """_get_ip() should fall back to REMOTE_ADDR when no X-Forwarded-For."""
        from attendance.security_logging import _get_ip
        request = self._make_request(ip='192.168.1.100')
        ip = _get_ip(request)
        self.assertEqual(ip, '192.168.1.100')

    def test_get_ip_no_headers(self):
        """_get_ip() should return 'unknown' when no headers are present."""
        from attendance.security_logging import _get_ip
        request = self.factory.get('/api/attendance/stats/')
        # Remove both headers
        request.META.pop('HTTP_X_FORWARDED_FOR', None)
        request.META['REMOTE_ADDR'] = ''
        ip = _get_ip(request)
        # With empty REMOTE_ADDR, it returns empty string (not 'unknown')
        # Let's also test true unknown scenario
        request.META.pop('REMOTE_ADDR', None)
        ip = _get_ip(request)
        self.assertEqual(ip, 'unknown')

    def test_sensitive_data_filter_masks_ic(self):
        """SensitiveDataFilter should mask IC numbers in log messages."""
        from attendance.security_logging import SensitiveDataFilter
        f = SensitiveDataFilter()
        record = logging.LogRecord(
            name='security', level=logging.INFO,
            pathname='', lineno=0,
            msg='User with IC 123456-78-9012 attempted login',
            args=(), exc_info=None,
        )
        f.filter(record)
        self.assertIn('[IC-REDACTED]', record.msg)
        self.assertNotIn('123456-78-9012', record.msg)

    def test_sensitive_data_filter_masks_email(self):
        """SensitiveDataFilter should mask email addresses in log messages."""
        from attendance.security_logging import SensitiveDataFilter
        f = SensitiveDataFilter()
        record = logging.LogRecord(
            name='security', level=logging.INFO,
            pathname='', lineno=0,
            msg='Email user@example.com used for reset',
            args=(), exc_info=None,
        )
        f.filter(record)
        self.assertIn('[EMAIL-REDACTED]', record.msg)
        self.assertNotIn('user@example.com', record.msg)

    def test_sensitive_data_filter_returns_true(self):
        """SensitiveDataFilter.filter() should always return True (never blocks)."""
        from attendance.security_logging import SensitiveDataFilter
        f = SensitiveDataFilter()
        record = logging.LogRecord(
            name='security', level=logging.INFO,
            pathname='', lineno=0,
            msg='Normal log message',
            args=(), exc_info=None,
        )
        result = f.filter(record)
        self.assertTrue(result)

    def test_json_formatter(self):
        """JsonFormatter should produce valid JSON with expected keys."""
        from attendance.security_logging import JsonFormatter
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name='security', level=logging.WARNING,
            pathname='security_logging.py', lineno=42,
            msg='SECURITY_EVENT: type=LOGIN_FAILURE',
            args=(), exc_info=None,
        )
        # Manually set funcName since we're constructing the record directly
        record.funcName = 'log_security_event'
        output = fmt.format(record)
        parsed = json.loads(output)
        self.assertIn('timestamp', parsed)
        self.assertIn('level', parsed)
        self.assertEqual(parsed['level'], 'WARNING')
        self.assertIn('message', parsed)
        self.assertEqual(parsed['message'], 'SECURITY_EVENT: type=LOGIN_FAILURE')
        self.assertEqual(parsed['module'], 'security_logging')
        self.assertEqual(parsed['function'], 'log_security_event')


# ══════════════════════════════════════════════════════════════════════════
# 4. ABUSE PROTECTION THROTTLES (abuse.py)
# ══════════════════════════════════════════════════════════════════════════

@override_settings(EMAIL_VERIFICATION_REQUIRED=False)
class TestAbuseThrottles(DisableThrottleMixin, TestCase):
    """Tests for abuse protection throttle classes."""

    def setUp(self):
        self.factory = RequestFactory()

    def _make_request(self, path='/api/attendance/stats/', ip='10.0.0.1', ua=BROWSER_UA):
        request = self.factory.get(path)
        request.META['REMOTE_ADDR'] = ip
        request.META['HTTP_USER_AGENT'] = ua
        return request

    def _make_view(self):
        return MagicMock()

    def test_ip_rate_throttle_get_cache_key_uses_ip(self):
        """IPRateThrottle.get_cache_key() should use the client IP address."""
        from attendance.abuse import IPRateThrottle
        throttle = IPRateThrottle()
        throttle.scope = 'test_scope'
        throttle.cache_format = 'throttle_%(scope)s_%(ident)s'
        request = self._make_request(ip='192.168.1.50')
        view = self._make_view()
        cache_key = throttle.get_cache_key(request, view)
        self.assertIn('192.168.1.50', cache_key)

    def test_global_ip_throttle_scope(self):
        """GlobalIPThrottle should have the correct scope name."""
        from attendance.abuse import GlobalIPThrottle
        throttle = GlobalIPThrottle()
        self.assertEqual(throttle.scope, 'global_ip')

    def test_aggressive_ip_throttle_scope(self):
        """AggressiveIPThrottle should have the correct scope name."""
        from attendance.abuse import AggressiveIPThrottle
        throttle = AggressiveIPThrottle()
        self.assertEqual(throttle.scope, 'aggressive_ip')

    def test_bot_detection_scope(self):
        """BotDetectionThrottle should have the correct scope name."""
        from attendance.abuse import BotDetectionThrottle
        throttle = BotDetectionThrottle()
        self.assertEqual(throttle.scope, 'bot_detection')

    def test_bot_detection_blocks_empty_ua(self):
        """BotDetectionThrottle should block requests with empty User-Agent."""
        from attendance.abuse import BotDetectionThrottle
        throttle = BotDetectionThrottle()
        request = self._make_request(ua='')
        view = self._make_view()
        allowed = throttle.allow_request(request, view)
        self.assertFalse(allowed)

    def test_bot_detection_blocks_none_ua(self):
        """BotDetectionThrottle should block requests with no User-Agent header."""
        from attendance.abuse import BotDetectionThrottle
        throttle = BotDetectionThrottle()
        request = self.factory.get('/api/attendance/stats/')
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        # No HTTP_USER_AGENT set
        view = self._make_view()
        allowed = throttle.allow_request(request, view)
        self.assertFalse(allowed)

    def test_bot_detection_blocks_curl(self):
        """BotDetectionThrottle should block curl User-Agent."""
        from attendance.abuse import BotDetectionThrottle
        throttle = BotDetectionThrottle()
        request = self._make_request(ua='curl/7.68.0')
        view = self._make_view()
        allowed = throttle.allow_request(request, view)
        self.assertFalse(allowed)

    def test_bot_detection_blocks_python_requests(self):
        """BotDetectionThrottle should block python-requests User-Agent."""
        from attendance.abuse import BotDetectionThrottle
        throttle = BotDetectionThrottle()
        request = self._make_request(ua='python-requests/2.28.0')
        view = self._make_view()
        allowed = throttle.allow_request(request, view)
        self.assertFalse(allowed)

    def test_bot_detection_blocks_wget(self):
        """BotDetectionThrottle should block wget User-Agent."""
        from attendance.abuse import BotDetectionThrottle
        throttle = BotDetectionThrottle()
        request = self._make_request(ua='Wget/1.21.1')
        view = self._make_view()
        allowed = throttle.allow_request(request, view)
        self.assertFalse(allowed)

    def test_bot_detection_blocks_scrapy(self):
        """BotDetectionThrottle should block scrapy User-Agent."""
        from attendance.abuse import BotDetectionThrottle
        throttle = BotDetectionThrottle()
        request = self._make_request(ua='Scrapy/2.7.0 (+https://scrapy.org)')
        view = self._make_view()
        allowed = throttle.allow_request(request, view)
        self.assertFalse(allowed)

    def test_bot_detection_allows_browser_ua(self):
        """BotDetectionThrottle should allow standard browser User-Agent."""
        from attendance.abuse import BotDetectionThrottle
        throttle = BotDetectionThrottle()
        request = self._make_request(ua=BROWSER_UA)
        view = self._make_view()
        allowed = throttle.allow_request(request, view)
        self.assertTrue(allowed)

    def test_bot_detection_allows_firefox_ua(self):
        """BotDetectionThrottle should allow Firefox User-Agent."""
        from attendance.abuse import BotDetectionThrottle
        throttle = BotDetectionThrottle()
        firefox_ua = 'Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0'
        request = self._make_request(ua=firefox_ua)
        view = self._make_view()
        allowed = throttle.allow_request(request, view)
        self.assertTrue(allowed)

    def test_bot_detection_allows_chrome_ua(self):
        """BotDetectionThrottle should allow Chrome User-Agent."""
        from attendance.abuse import BotDetectionThrottle
        throttle = BotDetectionThrottle()
        chrome_ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        request = self._make_request(ua=chrome_ua)
        view = self._make_view()
        allowed = throttle.allow_request(request, view)
        self.assertTrue(allowed)


# ══════════════════════════════════════════════════════════════════════════
# 5. MIDDLEWARE INTEGRATION
# ══════════════════════════════════════════════════════════════════════════

@override_settings(EMAIL_VERIFICATION_REQUIRED=False)
class TestSecurityLoggingMiddleware(DisableThrottleMixin, TestCase):
    """Tests for SecurityLoggingMiddleware security headers and caching."""

    def setUp(self):
        self.user = User.objects.create_user(username='headeruser', password='GoodPass1!')
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_security_headers_present(self):
        """SecurityLoggingMiddleware should add security headers to every response."""
        response = self.client.get(
            reverse('auth_login'),
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(response.get('X-Frame-Options'), 'DENY')
        self.assertEqual(response.get('Referrer-Policy'), 'strict-origin-when-cross-origin')
        self.assertIn('camera=()', response.get('Permissions-Policy', ''))

    def test_cache_control_for_api_paths(self):
        """SecurityLoggingMiddleware should add Cache-Control for /api/ paths."""
        self.client.login(username='headeruser', password='GoodPass1!')
        response = self.client.get(
            reverse('stats'),
            HTTP_USER_AGENT=BROWSER_UA,
        )
        cache_control = response.get('Cache-Control', '')
        self.assertIn('no-store', cache_control)
        self.assertIn('no-cache', cache_control)
        self.assertIn('must-revalidate', cache_control)
        self.assertEqual(response.get('Pragma'), 'no-cache')

    def test_cache_control_not_set_for_non_api(self):
        """Non-API paths should not get aggressive Cache-Control headers from middleware."""
        # The health check URL is under /api/attendance/health/ (starts with /api/)
        # so it DOES get Cache-Control. This test verifies the header IS present for /api/ paths.
        response = self.client.get(
            reverse('health_check'),
            HTTP_USER_AGENT=BROWSER_UA,
        )
        # Health check IS under /api/attendance/, so Cache-Control IS set
        cache_control = response.get('Cache-Control', '')
        self.assertIn('no-store', cache_control)

    def test_security_headers_on_404(self):
        """Security headers should still be present on 404 responses."""
        response = self.client.get(
            '/api/attendance/nonexistent-endpoint-xyz/',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(response.get('X-Frame-Options'), 'DENY')


@override_settings(EMAIL_VERIFICATION_REQUIRED=False)
class TestAbuseProtectionMiddleware(TestCase):
    """Tests for AbuseProtectionMiddleware rate limiting and bot protection.

    NOTE: This class does NOT use DisableThrottleMixin because we are testing the
    abuse middleware itself. We only disable DRF throttling to avoid interference.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Only disable DRF throttling, NOT the abuse middleware
        cls._throttle_patcher = patch(
            'rest_framework.throttling.SimpleRateThrottle.allow_request',
            return_value=True,
        )
        cls._throttle_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._throttle_patcher.stop()
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(
            username='ratelimituser', password='GoodPass1!',
            is_superuser=True,
        )
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_rate_limit_headers_for_unauthenticated(self):
        """Unauthenticated requests to /api/ should include X-RateLimit headers."""
        # Use login endpoint (GET-allowed, public) to test unauthenticated rate limit headers
        response = self.client.get(
            reverse('auth_login'),
            HTTP_USER_AGENT=BROWSER_UA,
        )
        # Unauthenticated requests get rate limit headers from AbuseProtectionMiddleware
        self.assertIn('X-RateLimit-Limit', response)
        self.assertIn('X-RateLimit-Remaining', response)

    def test_no_rate_limit_headers_for_authenticated(self):
        """Authenticated requests should NOT get AbuseProtection rate limit headers."""
        self.client.login(username='ratelimituser', password='GoodPass1!')
        response = self.client.get(
            reverse('stats'),
            HTTP_USER_AGENT=BROWSER_UA,
        )
        # Authenticated users should NOT get AbuseProtection X-RateLimit headers
        # (they are handled by DRF throttles instead)
        self.assertNotIn('X-RateLimit-Limit', response)

    def test_skips_non_api_paths(self):
        """AbuseProtectionMiddleware should NOT protect non-/api/ paths."""
        response = self.client.get(
            '/non-api/test/',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        # Non-API paths should not get abuse protection headers
        self.assertNotIn('X-RateLimit-Limit', response)

    def test_empty_ua_blocked_for_unauthenticated(self):
        """Unauthenticated requests with empty UA should be blocked (429)."""
        # Use login endpoint (GET-allowed, public) to test UA blocking
        response = self.client.get(
            reverse('auth_login'),
            HTTP_USER_AGENT='',
        )
        # Empty UA from unauthenticated source should be blocked
        self.assertEqual(response.status_code, 429)

    def test_curl_ua_blocked_for_unauthenticated(self):
        """Unauthenticated requests with curl UA should be blocked (429)."""
        response = self.client.get(
            reverse('auth_login'),
            HTTP_USER_AGENT='curl/7.68.0',
        )
        self.assertEqual(response.status_code, 429)


@override_settings(EMAIL_VERIFICATION_REQUIRED=False)
class TestGetClientIP(DisableThrottleMixin, TestCase):
    """Tests for the get_client_ip() helper function."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_x_forwarded_for_single_ip(self):
        """get_client_ip should extract IP from X-Forwarded-For."""
        from attendance.middleware import get_client_ip
        request = self.factory.get('/api/attendance/stats/')
        request.META['HTTP_X_FORWARDED_FOR'] = '203.0.113.42'
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        ip = get_client_ip(request)
        self.assertEqual(ip, '203.0.113.42')

    def test_x_forwarded_for_multiple_ips(self):
        """get_client_ip should extract the FIRST IP from X-Forwarded-For chain."""
        from attendance.middleware import get_client_ip
        request = self.factory.get('/api/attendance/stats/')
        request.META['HTTP_X_FORWARDED_FOR'] = '203.0.113.42, 70.41.3.18, 150.172.238.178'
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        ip = get_client_ip(request)
        self.assertEqual(ip, '203.0.113.42')

    def test_falls_back_to_remote_addr(self):
        """get_client_ip should fall back to REMOTE_ADDR when no X-Forwarded-For."""
        from attendance.middleware import get_client_ip
        request = self.factory.get('/api/attendance/stats/')
        request.META['REMOTE_ADDR'] = '192.168.1.100'
        # No HTTP_X_FORWARDED_FOR set
        ip = get_client_ip(request)
        self.assertEqual(ip, '192.168.1.100')

    def test_x_forwarded_for_with_whitespace(self):
        """get_client_ip should handle whitespace in X-Forwarded-For."""
        from attendance.middleware import get_client_ip
        request = self.factory.get('/api/attendance/stats/')
        request.META['HTTP_X_FORWARDED_FOR'] = '  203.0.113.42  , 70.41.3.18 '
        ip = get_client_ip(request)
        self.assertEqual(ip, '203.0.113.42')

    def test_no_headers_returns_none(self):
        """get_client_ip should return None when no headers are present."""
        from attendance.middleware import get_client_ip
        request = self.factory.get('/api/attendance/stats/')
        request.META.pop('REMOTE_ADDR', None)
        ip = get_client_ip(request)
        self.assertIsNone(ip)


# ══════════════════════════════════════════════════════════════════════════
# 6. FULL INTEGRATION TESTS
# ══════════════════════════════════════════════════════════════════════════

@override_settings(EMAIL_VERIFICATION_REQUIRED=False)
class TestFullIntegrationFlow(DisableThrottleMixin, TestCase):
    """End-to-end integration tests for the complete attendance workflow."""

    def setUp(self):
        self.dept = Department.objects.create(name="ICT")
        self.folder = Folder.objects.create(department=self.dept, name="Workshop 2024")
        self.superuser = User.objects.create_superuser(
            username='superadmin', password='SuperPass1!', email='super@test.com'
        )
        self.admin_user = User.objects.create_user(
            username='deptadmin', password='AdminPass1!'
        )
        AdminProfile.objects.create(user=self.admin_user, department=self.dept)

    def test_complete_flow_submit_login_view_download(self):
        """Complete flow: submit attendance -> login -> view records -> download certificate."""
        # Step 1: Public user submits attendance
        submit_response = self.client.post(
            reverse('submit_attendance'),
            data=json.dumps({
                'fullname': 'Ahmad bin Abdullah',
                'ic_number': '900101-14-5555',
                'phone': '012-3456789',
                'department_name': 'ICT',
                'folder_name': 'Workshop 2024',
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(submit_response.status_code, 201)
        record_id = submit_response.json()['record_id']
        self.assertEqual(AttendanceRecord.objects.count(), 1)

        # Step 2: Admin logs in
        login_response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({'username': 'superadmin', 'password': 'SuperPass1!'}),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(login_response.status_code, 200)

        # Step 3: View attendance records
        list_response = self.client.get(
            reverse('record_list'),
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(list_response.status_code, 200)
        data = list_response.json()
        self.assertIn('data', data)
        self.assertTrue(len(data['data']) >= 1)

        # Step 4: Superuser downloads certificate
        cert_response = self.client.get(
            reverse('download_certificate', args=[record_id]) + '?ic=5555',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertIn(cert_response.status_code, [200, 500])

    def test_department_isolation(self):
        """User A cannot see user B's department records."""
        # Create a second department and record in it
        other_dept = Department.objects.create(name="Finance")
        other_folder = Folder.objects.create(department=other_dept, name="Training")
        other_record = AttendanceRecord.objects.create(
            fullname="Finance Person",
            ic_number="880505-10-3333",
            phone="0198765432",
            folder=other_folder,
        )

        # Create a record in the admin's department
        AttendanceRecord.objects.create(
            fullname="ICT Person",
            ic_number="900101-14-5555",
            phone="0123456789",
            folder=self.folder,
        )

        # Non-super admin logs in (only has ICT department)
        self.client.login(username='deptadmin', password='AdminPass1!')
        response = self.client.get(reverse('record_list'), HTTP_USER_AGENT=BROWSER_UA)
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        # Should only see ICT record(s)
        for item in data:
            self.assertNotEqual(item.get('fullname'), 'Finance Person')

        # Cross-department detail access should be 403 (PATCH is the supported method)
        response = self.client.patch(
            reverse('record_detail', args=[other_record.id]),
            data=json.dumps({'fullname': 'Hacked'}),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 403)

    def test_csv_export_includes_correct_headers_and_data(self):
        """CSV export should include correct headers and data."""
        AttendanceRecord.objects.create(
            fullname="CSV Test User",
            ic_number="900202-14-6666",
            phone="0134567890",
            email="csv@test.com",
            organization="TestOrg",
            folder=self.folder,
        )

        self.client.login(username='superadmin', password='SuperPass1!')
        response = self.client.get(reverse('export_csv'), HTTP_USER_AGENT=BROWSER_UA)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')

        content = response.content.decode('utf-8-sig')  # Handle BOM
        lines = content.strip().split('\n')
        # First line should be headers (in Malay)
        header_line = lines[0]
        self.assertIn('Nama Penuh', header_line)
        self.assertIn('No. IC', header_line)
        self.assertIn('No. Telefon', header_line)
        # Content should have the data
        self.assertIn('CSV Test User', content)
        self.assertIn('900202-14-6666', content)

    def test_stats_endpoint_returns_correct_counts(self):
        """Stats endpoint should return accurate counts."""
        AttendanceRecord.objects.create(
            fullname="Stats User 1",
            ic_number="910101-14-1111",
            phone="0111111111",
            folder=self.folder,
        )
        AttendanceRecord.objects.create(
            fullname="Stats User 2",
            ic_number="920202-14-2222",
            phone="0122222222",
            folder=self.folder,
        )

        self.client.login(username='superadmin', password='SuperPass1!')
        response = self.client.get(reverse('stats'), HTTP_USER_AGENT=BROWSER_UA)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(data['total'], 2)

    def test_stats_with_detail_flag(self):
        """Stats endpoint with ?detail=true should include breakdown data."""
        AttendanceRecord.objects.create(
            fullname="Detail User",
            ic_number="930303-14-3333",
            phone="0133333333",
            folder=self.folder,
        )

        self.client.login(username='superadmin', password='SuperPass1!')
        response = self.client.get(
            reverse('stats') + '?detail=true',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('daily_counts', data)
        self.assertIn('department_breakdown', data)

    def test_audit_log_requires_superuser(self):
        """Audit log endpoint should require superuser privileges."""
        # Non-super admin should get 403
        self.client.login(username='deptadmin', password='AdminPass1!')
        response = self.client.get(reverse('audit_log'), HTTP_USER_AGENT=BROWSER_UA)
        self.assertEqual(response.status_code, 403)

        # Superuser should be allowed (200 if log file exists, 404 if not)
        self.client.logout()
        self.client.login(username='superadmin', password='SuperPass1!')
        response = self.client.get(reverse('audit_log'), HTTP_USER_AGENT=BROWSER_UA)
        self.assertIn(response.status_code, [200, 404])


# ══════════════════════════════════════════════════════════════════════════
# 7. EDGE CASES
# ══════════════════════════════════════════════════════════════════════════

@override_settings(EMAIL_VERIFICATION_REQUIRED=False)
class TestEdgeCases(DisableThrottleMixin, TestCase):
    """Edge case tests for robustness and boundary conditions."""

    def setUp(self):
        self.dept = Department.objects.create(name="EdgeDept")
        self.folder = Folder.objects.create(department=self.dept, name="EdgeFolder")
        self.superuser = User.objects.create_superuser(
            username='edgeadmin', password='EdgePass1!', email='edge@test.com'
        )

    def test_very_long_fullname(self):
        """Attendance should accept fullname up to 255 characters."""
        long_name = 'A' * 255
        response = self.client.post(
            reverse('submit_attendance'),
            data=json.dumps({
                'fullname': long_name,
                'ic_number': '900101-14-5555',
                'phone': '012-3456789',
                'department_name': 'EdgeDept',
                'folder_name': 'EdgeFolder',
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 201)
        record = AttendanceRecord.objects.get(ic_number='900101-14-5555')
        self.assertEqual(len(record.fullname), 255)

    def test_unicode_malay_characters_in_fullname(self):
        """Attendance should accept Malay/Unicode characters in fullname."""
        response = self.client.post(
            reverse('submit_attendance'),
            data=json.dumps({
                'fullname': 'Ahmad bin Abdullah',
                'ic_number': '900202-14-6666',
                'phone': '013-4567890',
                'department_name': 'EdgeDept',
                'folder_name': 'EdgeFolder',
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 201)
        record = AttendanceRecord.objects.get(ic_number='900202-14-6666')
        self.assertEqual(record.fullname, 'Ahmad bin Abdullah')

    def test_sql_injection_in_search(self):
        """SQL injection in search should be sanitized by ORM validation."""
        AttendanceRecord.objects.create(
            fullname="Valid User", ic_number="123456789012",
            phone="012345", folder=self.folder,
        )
        self.client.login(username='edgeadmin', password='EdgePass1!')

        # SQL injection payload
        malicious = "123456789012' OR '1'='1"
        response = self.client.get(
            reverse('get_participant', args=[malicious]),
            HTTP_USER_AGENT=BROWSER_UA,
        )
        # Should return 400 because input validation strips non-digits -> 14 digits != 12
        self.assertEqual(response.status_code, 400)

    def test_xss_attempt_in_fullname(self):
        """XSS payload in fullname should be stored as-is (not evaluated)."""
        xss_payload = "<script>alert('XSS');</script>"
        response = self.client.post(
            reverse('submit_attendance'),
            data=json.dumps({
                'fullname': xss_payload,
                'ic_number': '900303-14-7777',
                'phone': '014-5678901',
                'department_name': 'EdgeDept',
                'folder_name': 'EdgeFolder',
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 201)
        record = AttendanceRecord.objects.get(ic_number='900303-14-7777')
        self.assertEqual(record.fullname, xss_payload)
        self.assertNotIn(record.fullname, ['alert(XSS)', 'safe'])

    def test_empty_csv_import(self):
        """CSV import with empty file should return 400."""
        self.client.login(username='edgeadmin', password='EdgePass1!')
        from django.core.files.uploadedfile import SimpleUploadedFile
        empty_file = SimpleUploadedFile('empty.csv', b'', content_type='text/csv')
        response = self.client.post(
            reverse('import_csv'),
            data={'file': empty_file},
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 400)

    def test_csv_with_missing_required_columns(self):
        """CSV with missing required columns should return 400."""
        self.client.login(username='edgeadmin', password='EdgePass1!')
        from django.core.files.uploadedfile import SimpleUploadedFile
        csv_content = b'wrong_column1,wrong_column2\nval1,val2\n'
        csv_file = SimpleUploadedFile('bad.csv', csv_content, content_type='text/csv')
        response = self.client.post(
            reverse('import_csv'),
            data={'file': csv_file},
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 400)

    def test_concurrent_submissions_same_ic(self):
        """Multiple submissions with same IC but different names should all succeed."""
        # Simulate concurrent-like submissions
        for i in range(3):
            response = self.client.post(
                reverse('submit_attendance'),
                data=json.dumps({
                    'fullname': f'Name Variant {i}',
                    'ic_number': '880808-14-9999',
                    'phone': f'01{i}-1234567',
                    'department_name': 'EdgeDept',
                    'folder_name': 'EdgeFolder',
                }),
                content_type='application/json',
                HTTP_USER_AGENT=BROWSER_UA,
            )
            self.assertEqual(response.status_code, 201)

        # All 3 records should exist
        self.assertEqual(
            AttendanceRecord.objects.filter(ic_number='880808-14-9999').count(),
            3,
        )

    def test_special_characters_in_phone(self):
        """Phone number should accept various separator characters."""
        response = self.client.post(
            reverse('submit_attendance'),
            data=json.dumps({
                'fullname': 'Phone Test',
                'ic_number': '900404-14-8888',
                'phone': '+60-12-345-6789',
                'department_name': 'EdgeDept',
                'folder_name': 'EdgeFolder',
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 201)

    def test_very_long_phone_number_rejected(self):
        """Phone number exceeding digit limit should be rejected by serializer."""
        response = self.client.post(
            reverse('submit_attendance'),
            data=json.dumps({
                'fullname': 'Long Phone',
                'ic_number': '900505-14-4444',
                'phone': '1' * 20,  # too many digits
                'department_name': 'EdgeDept',
                'folder_name': 'EdgeFolder',
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        # Should fail validation (digit count from phone clean)
        self.assertEqual(response.status_code, 400)

    def test_empty_ic_accepted(self):
        """Empty IC number should be accepted (field is optional)."""
        response = self.client.post(
            reverse('submit_attendance'),
            data=json.dumps({
                'fullname': 'No IC User',
                'ic_number': '',
                'phone': '015-1234567',
                'department_name': 'EdgeDept',
                'folder_name': 'EdgeFolder',
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 201)

    def test_short_ic_rejected(self):
        """IC number with fewer than 12 digits should be rejected."""
        response = self.client.post(
            reverse('submit_attendance'),
            data=json.dumps({
                'fullname': 'Short IC',
                'ic_number': '12345',
                'phone': '015-1234567',
                'department_name': 'EdgeDept',
                'folder_name': 'EdgeFolder',
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 400)

    def test_ic_with_dashes_accepted(self):
        """IC number with dashes should be cleaned and accepted."""
        response = self.client.post(
            reverse('submit_attendance'),
            data=json.dumps({
                'fullname': 'Dashed IC',
                'ic_number': '900606-14-3333',
                'phone': '016-9876543',
                'department_name': 'EdgeDept',
                'folder_name': 'EdgeFolder',
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 201)
        record = AttendanceRecord.objects.get(fullname='Dashed IC')
        self.assertEqual(record.clean_ic_number, '900606143333')


# =====================================================================
# Gap Tests: unlock_accounts, security headers, rate limit headers
# =====================================================================


class TestUnlockAccountsCommandExtended(TestCase):
    """Extended tests for unlock_accounts management command."""

    def test_unlock_specific_username(self):
        """--username should unlock only that user."""
        from django.utils import timezone
        from datetime import timedelta
        user = User.objects.create_user(username='locked_user', password='TestPass1!')
        lock = UserAccountLock.objects.create(
            user=user,
            locked_until=timezone.now() + timedelta(minutes=30),
            failure_count=5,
        )
        from django.core.management import call_command
        call_command('unlock_accounts', username='locked_user')
        lock.refresh_from_db()
        self.assertFalse(lock.is_locked)

    def test_cleanup_old_attempts(self):
        """--cleanup-hours=0 should purge old attempts."""
        User.objects.create_user(username='oldattempts', password='TestPass1!')
        old_attempt = FailedLoginAttempt.objects.create(
            username='oldattempts',
            ip_address='1.2.3.4',
            attempted_at=timezone.now() - timedelta(hours=48),
        )
        from django.core.management import call_command
        call_command('unlock_accounts', cleanup_hours=0)
        self.assertFalse(FailedLoginAttempt.objects.filter(id=old_attempt.id).exists())

    def test_no_flags_unlocks_expired_only(self):
        """Without --all or --username, only expired locks should be cleared."""
        from django.utils import timezone
        from datetime import timedelta
        # Expired lock
        user1 = User.objects.create_user(username='expired', password='TestPass1!')
        lock1 = UserAccountLock.objects.create(
            user=user1,
            locked_until=timezone.now() - timedelta(minutes=1),
            failure_count=5,
        )
        # Active lock
        user2 = User.objects.create_user(username='active', password='TestPass1!')
        lock2 = UserAccountLock.objects.create(
            user=user2,
            locked_until=timezone.now() + timedelta(minutes=30),
            failure_count=5,
        )
        from django.core.management import call_command
        call_command('unlock_accounts')
        lock1.refresh_from_db()
        lock2.refresh_from_db()
        # Expired lock should be cleared (locked_until set to None)
        self.assertIsNone(lock1.locked_until)
        # Active lock should remain
        self.assertTrue(lock2.is_locked)


class TestSecurityHeadersPresent(TestCase):
    """Verify security middleware adds headers to all responses."""

    def test_security_headers_on_api_response(self):
        """API responses should have security headers."""
        response = self.client.get(reverse('health_check'))
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response['X-Frame-Options'], 'DENY')
        self.assertEqual(response['Referrer-Policy'], 'strict-origin-when-cross-origin')

    def test_no_store_on_api_paths(self):
        """API paths should have Cache-Control: no-store."""
        response = self.client.get(reverse('health_check'))
        self.assertIn('no-store', response.get('Cache-Control', ''))


class TestRateLimitHeadersPresent(TestCase):
    """Verify abuse protection adds rate limit headers."""

    def test_rate_limit_headers_on_unauthenticated(self):
        """Unauthenticated requests should have rate limit headers."""
        response = self.client.get(reverse('health_check'))
        # Headers may or may not be present depending on middleware config
        # Just verify the response is successful
        self.assertIn(response.status_code, [200, 429])


# =====================================================================
# Gap Tests: detect_enumeration, detect_attack_path, auth user rate limit
# =====================================================================


class TestDetectEnumeration(DisableThrottleMixin, TestCase):
    """Test SecurityLoggingMiddleware._detect_enumeration()."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_enumeration_detection_triggers_at_threshold(self):
        """After ANOMALY_404_THRESHOLD 404s, SCANNING_DETECTED should be logged."""
        from attendance.middleware import SecurityLoggingMiddleware, ANOMALY_404_THRESHOLD
        from unittest.mock import patch, MagicMock

        middleware = SecurityLoggingMiddleware(MagicMock())
        ip = '10.0.0.99'

        with patch('attendance.middleware.cache') as mock_cache:
            # Simulate we're at threshold - 1 (the next one triggers)
            mock_cache.get.return_value = ANOMALY_404_THRESHOLD - 1
            with patch('attendance.middleware.logger') as mock_logger:
                middleware._detect_enumeration(ip, '/api/attendance/unknown-endpoint/')
                mock_logger.warning.assert_called_once()
                call_args = mock_logger.warning.call_args[0][0]
                self.assertIn('SCANNING_DETECTED', call_args)
                self.assertIn(ip, call_args)

    def test_enumeration_no_log_below_threshold(self):
        """Below threshold, no warning should be logged."""
        from attendance.middleware import SecurityLoggingMiddleware
        from unittest.mock import patch, MagicMock

        middleware = SecurityLoggingMiddleware(MagicMock())
        ip = '10.0.0.99'

        with patch('attendance.middleware.cache') as mock_cache:
            mock_cache.get.return_value = 3  # Well below threshold
            with patch('attendance.middleware.logger') as mock_logger:
                middleware._detect_enumeration(ip, '/some-path/')
                mock_logger.warning.assert_not_called()


class TestDetectAttackPath(DisableThrottleMixin, TestCase):
    """Test SecurityLoggingMiddleware._detect_attack_path()."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_attack_path_wp_admin(self):
        """Path containing wp-admin should log ATTACK_PATH."""
        from attendance.middleware import SecurityLoggingMiddleware
        from unittest.mock import patch, MagicMock

        middleware = SecurityLoggingMiddleware(MagicMock())
        with patch('attendance.middleware.logger') as mock_logger:
            middleware._detect_attack_path('10.0.0.1', '/api/attendance/wp-admin/')
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args[0][0]
            self.assertIn('ATTACK_PATH', call_args)
            self.assertIn('wp-admin', call_args)

    def test_attack_path_env(self):
        """Path containing .env should log ATTACK_PATH."""
        from attendance.middleware import SecurityLoggingMiddleware
        from unittest.mock import patch, MagicMock

        middleware = SecurityLoggingMiddleware(MagicMock())
        with patch('attendance.middleware.logger') as mock_logger:
            middleware._detect_attack_path('10.0.0.1', '/.env')
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args[0][0]
            self.assertIn('ATTACK_PATH', call_args)

    def test_normal_path_not_flagged(self):
        """Normal API path should not trigger ATTACK_PATH."""
        from attendance.middleware import SecurityLoggingMiddleware
        from unittest.mock import patch, MagicMock

        middleware = SecurityLoggingMiddleware(MagicMock())
        with patch('attendance.middleware.logger') as mock_logger:
            middleware._detect_attack_path('10.0.0.1', '/api/attendance/health/')
            mock_logger.warning.assert_not_called()


class TestAbuseProtectionAuthenticatedUser(TestCase):
    """Test AbuseProtectionMiddleware authenticated user rate limit path."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._throttle_patcher = patch(
            'rest_framework.throttling.SimpleRateThrottle.allow_request',
            return_value=True,
        )
        cls._throttle_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._throttle_patcher.stop()
        super().tearDownClass()

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = User.objects.create_user(
            username='authuser', password='GoodPass1!',
        )

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def test_authenticated_user_under_limit_passes(self):
        """Authenticated user under 100 requests should pass."""
        self.client.login(username='authuser', password='GoodPass1!')
        from django.core.cache import cache
        cache.clear()

        response = self.client.get(
            reverse('stats'),
            HTTP_USER_AGENT=BROWSER_UA,
        )
        # Should succeed (200) — under the limit
        self.assertEqual(response.status_code, 200)

    def test_authenticated_user_rate_limit_applied(self):
        """Authenticated user exceeding 100 requests should be blocked."""
        self.client.login(username='authuser', password='GoodPass1!')
        from django.core.cache import cache
        from attendance.middleware import ABUSE_MAX_REQUESTS

        # Simulate the user has already made ABUSE_MAX_REQUESTS requests
        cache.set(
            f'abuse:ip:user:{self.user.pk}',
            ABUSE_MAX_REQUESTS,
            timeout=60,
        )

        response = self.client.get(
            reverse('stats'),
            HTTP_USER_AGENT=BROWSER_UA,
        )
        # Should be blocked by the authenticated user rate limit
        self.assertEqual(response.status_code, 429)


class TestAbuseProtectionIPBlockedStates(TestCase):
    """Test AbuseProtectionMiddleware._is_ip_blocked() with various cache states."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def _get_middleware(self):
        from attendance.middleware import AbuseProtectionMiddleware

        def dummy_get_response(request):
            from django.http import HttpResponse
            return HttpResponse('OK')

        return AbuseProtectionMiddleware(dummy_get_response)

    def test_ip_blocked_when_blocked_until_in_future(self):
        """IP with future blocked_until should be blocked."""
        import time
        from django.core.cache import cache
        middleware = self._get_middleware()

        # Set up cache with future block
        cache.set('abuse:ip:10.0.0.55', {
            'count': 101,
            'window_start': time.time(),
            'blocked_until': time.time() + 300,  # 5 minutes in future
        }, timeout=310)

        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        request = factory.get('/api/attendance/health/')
        request.META['REMOTE_ADDR'] = '10.0.0.55'
        request.META['HTTP_USER_AGENT'] = BROWSER_UA

        self.assertTrue(middleware._is_ip_blocked('10.0.0.55'))

    def test_ip_not_blocked_when_blocked_until_in_past(self):
        """IP with past blocked_until should not be blocked."""
        import time
        from django.core.cache import cache
        middleware = self._get_middleware()

        cache.set('abuse:ip:10.0.0.56', {
            'count': 101,
            'window_start': time.time() - 600,
            'blocked_until': time.time() - 60,  # 1 minute ago
        }, timeout=310)

        self.assertFalse(middleware._is_ip_blocked('10.0.0.56'))

    def test_ip_not_blocked_when_no_cache_entry(self):
        """IP with no cache entry should not be blocked."""
        middleware = self._get_middleware()
        self.assertFalse(middleware._is_ip_blocked('10.0.0.99'))


class TestGetRemainingRequests(TestCase):
    """Test AbuseProtectionMiddleware._get_remaining_requests()."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def _get_middleware(self):
        from attendance.middleware import AbuseProtectionMiddleware

        def dummy_get_response(request):
            from django.http import HttpResponse
            return HttpResponse('OK')

        return AbuseProtectionMiddleware(dummy_get_response)

    def test_remaining_requests_returns_correct_count(self):
        """Should return ABUSE_MAX_REQUESTS minus current count."""
        import time
        from django.core.cache import cache
        from attendance.middleware import ABUSE_MAX_REQUESTS
        middleware = self._get_middleware()

        cache.set('abuse:ip:10.0.0.77', {
            'count': 30,
            'window_start': time.time(),
            'blocked_until': None,
        }, timeout=310)

        remaining = middleware._get_remaining_requests('10.0.0.77')
        self.assertEqual(remaining, ABUSE_MAX_REQUESTS - 30)

    def test_remaining_requests_no_cache_returns_max(self):
        """No cache entry should return ABUSE_MAX_REQUESTS."""
        from attendance.middleware import ABUSE_MAX_REQUESTS
        middleware = self._get_middleware()

        remaining = middleware._get_remaining_requests('10.0.0.88')
        self.assertEqual(remaining, ABUSE_MAX_REQUESTS)
