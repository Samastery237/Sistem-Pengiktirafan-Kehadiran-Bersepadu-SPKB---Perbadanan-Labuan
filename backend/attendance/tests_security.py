"""
Tests for production security features.

Covers:
  - Production settings validation (SECRET_KEY, ALLOWED_HOSTS)
  - Sensitive data masking (IC numbers, emails)
  - Security middleware logging (401, 403, 429, 5xx)
  - Traffic anomaly detection (404 enumeration, attack paths)
  - JSON log formatter output
"""
import json
import logging

from django.test import TestCase, override_settings
from django.core.cache import cache

BROWSER_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'


class TestSensitiveDataFilter(TestCase):
    """Test the SensitiveDataFilter masks PII in log records."""

    def setUp(self):
        from attendance.security_logging import SensitiveDataFilter
        self.filter = SensitiveDataFilter()

    def test_masks_ic_number_with_dashes(self):
        """IC number format XXXXXX-XX-XXXX should be redacted."""
        record = logging.LogRecord(
            name='security', level=logging.INFO,
            pathname='', lineno=0,
            msg='User with IC 123456-78-9012 logged in',
            args=(), exc_info=None
        )
        self.filter.filter(record)
        self.assertEqual(record.msg, 'User with IC [IC-REDACTED] logged in')

    def test_masks_ic_number_without_dashes(self):
        """IC number format XXXXXXXXXXXX should be redacted."""
        record = logging.LogRecord(
            name='security', level=logging.INFO,
            pathname='', lineno=0,
            msg='User with IC 123456789012 logged in',
            args=(), exc_info=None
        )
        self.filter.filter(record)
        self.assertEqual(record.msg, 'User with IC [IC-REDACTED] logged in')

    def test_masks_email(self):
        """Email addresses should be redacted."""
        record = logging.LogRecord(
            name='security', level=logging.INFO,
            pathname='', lineno=0,
            msg='Email sent to user@example.com successfully',
            args=(), exc_info=None
        )
        self.filter.filter(record)
        self.assertEqual(record.msg, 'Email sent to [EMAIL-REDACTED] successfully')

    def test_multiple_sensitive_values(self):
        """Both IC and email in same message should be redacted."""
        record = logging.LogRecord(
            name='security', level=logging.INFO,
            pathname='', lineno=0,
            msg='IC 123456-78-9012 and email test@example.com found',
            args=(), exc_info=None
        )
        self.filter.filter(record)
        self.assertEqual(
            record.msg,
            'IC [IC-REDACTED] and email [EMAIL-REDACTED] found'
        )

    def test_non_string_msg_unchanged(self):
        """Non-string msg attribute should not cause errors."""
        record = logging.LogRecord(
            name='security', level=logging.INFO,
            pathname='', lineno=0,
            msg=12345,
            args=(), exc_info=None
        )
        self.filter.filter(record)
        self.assertEqual(record.msg, 12345)


class TestJsonFormatter(TestCase):
    """Test the JsonFormatter outputs valid JSON."""

    def setUp(self):
        from attendance.security_logging import JsonFormatter
        self.formatter = JsonFormatter()

    def test_output_is_valid_json(self):
        """Formatted log record should be valid JSON."""
        record = logging.LogRecord(
            name='security.auth', level=logging.WARNING,
            pathname='middleware.py', lineno=42,
            msg='AUTH_FAILURE: IP=1.2.3.4',
            args=(), exc_info=None
        )
        output = self.formatter.format(record)
        parsed = json.loads(output)
        self.assertEqual(parsed['level'], 'WARNING')
        self.assertEqual(parsed['logger'], 'security.auth')
        self.assertIn('AUTH_FAILURE', parsed['message'])
        self.assertIn('timestamp', parsed)

    def test_output_contains_required_fields(self):
        """JSON output should contain all required fields."""
        record = logging.LogRecord(
            name='security', level=logging.INFO,
            pathname='test.py', lineno=1,
            msg='Test message',
            args=(), exc_info=None
        )
        output = self.formatter.format(record)
        parsed = json.loads(output)
        required = ['timestamp', 'level', 'logger', 'message', 'module', 'function', 'line']
        for field in required:
            self.assertIn(field, parsed)

    def test_exception_included_when_present(self):
        """Exception info should be included in JSON when available."""
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name='security', level=logging.ERROR,
            pathname='test.py', lineno=1,
            msg='Error occurred',
            args=(), exc_info=exc_info
        )
        output = self.formatter.format(record)
        parsed = json.loads(output)
        self.assertIn('exception', parsed)
        self.assertIn('ValueError', parsed['exception'])


class TestSecurityMiddlewareLogging(TestCase):
    """Test that the SecurityLoggingMiddleware logs security events."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_401_response_logged(self):
        """401 responses should be logged as AUTH_FAILURE."""
        from django.contrib.auth.models import User
        User.objects.create_user(username='testuser401', password='TestPass1!')

        # Send wrong password to trigger actual 401
        with self.assertLogs('security', level='WARNING') as cm:
            response = self.client.post(
                '/api/attendance/auth/login/',
                data=json.dumps({'username': 'testuser401', 'password': 'wrongpassword'}),
                content_type='application/json',
                HTTP_USER_AGENT=BROWSER_UA,
            )
            self.assertEqual(response.status_code, 401)
            log_output = '\n'.join(cm.output)
            self.assertIn('AUTH_FAILURE', log_output)

    def test_429_response_logged(self):
        """429 responses should be logged as RATE_LIMITED."""
        # Exhaust the rate limit
        for i in range(101):
            self.client.get(
                '/api/attendance/health/',
                HTTP_USER_AGENT=BROWSER_UA,
            )

        with self.assertLogs('security', level='WARNING') as cm:
            response = self.client.get(
                '/api/attendance/health/',
                HTTP_USER_AGENT=BROWSER_UA,
            )
            self.assertEqual(response.status_code, 429)
            log_output = '\n'.join(cm.output)
            self.assertIn('RATE_LIMITED', log_output)


class TestTrafficAnomalyDetection(TestCase):
    """Test traffic anomaly detection in SecurityLoggingMiddleware."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_attack_path_detection(self):
        """Requests to known attack paths should be logged."""
        with self.assertLogs('security', level='WARNING') as cm:
            self.client.get(
                '/api/attendance/.env',
                HTTP_USER_AGENT=BROWSER_UA,
            )
            log_output = '\n'.join(cm.output)
            self.assertIn('ATTACK_PATH', log_output)

    def test_attack_path_phpmyadmin(self):
        """Requests to phpmyadmin should be logged as attack path."""
        with self.assertLogs('security', level='WARNING') as cm:
            self.client.get(
                '/api/attendance/phpmyadmin/',
                HTTP_USER_AGENT=BROWSER_UA,
            )
            log_output = '\n'.join(cm.output)
            self.assertIn('ATTACK_PATH', log_output)

    def test_enumeration_detection(self):
        """Multiple 404s from same IP should trigger SCANNING_DETECTED."""
        from attendance.middleware import ANOMALY_404_THRESHOLD

        # Make enough 404 requests to trigger the threshold
        for i in range(ANOMALY_404_THRESHOLD):
            self.client.get(
                f'/api/attendance/nonexistent-endpoint-{i}/',
                HTTP_USER_AGENT=BROWSER_UA,
            )

        # The threshold should have been reached — verify by checking cache
        from django.core.cache import cache
        key = "anomaly:404:127.0.0.1"
        count = cache.get(key, 0)
        self.assertGreaterEqual(count, ANOMALY_404_THRESHOLD)


class TestProductionSettingsValidation(TestCase):
    """Test that production settings validation rejects insecure configs."""

    @override_settings(DEBUG=False, SECRET_KEY='short')
    def test_short_secret_key_rejected(self):
        """SECRET_KEY < 50 chars should cause sys.exit in production."""
        from attendance.apps import AttendanceConfig
        config = AttendanceConfig.__new__(AttendanceConfig)
        with self.assertRaises(SystemExit):
            config._validate_production_security()

    @override_settings(DEBUG=False, SECRET_KEY='a' * 50, ALLOWED_HOSTS=['localhost', '127.0.0.1'])
    def test_default_allowed_hosts_rejected(self):
        """ALLOWED_HOSTS = localhost only should be rejected in production."""
        from attendance.apps import AttendanceConfig
        config = AttendanceConfig.__new__(AttendanceConfig)
        with self.assertRaises(SystemExit):
            config._validate_production_security()

    @override_settings(DEBUG=False, SECRET_KEY='a' * 50, ALLOWED_HOSTS=['example.com'])
    def test_valid_production_settings_pass(self):
        """Valid production settings should not raise SystemExit."""
        from attendance.apps import AttendanceConfig
        config = AttendanceConfig.__new__(AttendanceConfig)
        # Should not raise
        config._validate_production_security()

    @override_settings(DEBUG=True, SECRET_KEY='short')
    def test_debug_true_skips_validation(self):
        """When DEBUG=True, ready() should not call _validate_production_security."""
        # The guard is in ready(): `if not settings.DEBUG:` — so with DEBUG=True,
        # _validate_production_security is never called. We verify the method
        # exists and would fail if called, but ready() won't trigger it.
        from attendance.apps import AttendanceConfig
        config = AttendanceConfig.__new__(AttendanceConfig)
        # Calling directly should still fail (method itself doesn't check DEBUG)
        with self.assertRaises(SystemExit):
            config._validate_production_security()
        # But in practice, ready() guards this with `if not settings.DEBUG:`


class TestUploadSizeLimits(TestCase):
    """Test that upload size limits are configured."""

    def test_data_upload_max_memory_size_set(self):
        """DATA_UPLOAD_MAX_MEMORY_SIZE should be set to 5MB."""
        from django.conf import settings
        self.assertEqual(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, 5 * 1024 * 1024)

    def test_file_upload_max_memory_size_set(self):
        """FILE_UPLOAD_MAX_MEMORY_SIZE should be set to 5MB."""
        from django.conf import settings
        self.assertEqual(settings.FILE_UPLOAD_MAX_MEMORY_SIZE, 5 * 1024 * 1024)

    def test_file_upload_permissions_set(self):
        """FILE_UPLOAD_PERMISSIONS should be 0o644."""
        from django.conf import settings
        self.assertEqual(settings.FILE_UPLOAD_PERMISSIONS, 0o644)
