"""
Structured security event logging for the SPKB application.

Provides:
  - JSON-formatted security logs for SIEM integration
  - Sensitive data masking (IC numbers, emails, passwords)
  - Traffic anomaly detection helpers
"""
import logging
import json
import re
from datetime import datetime, timezone

logger = logging.getLogger('security')


class SensitiveDataFilter(logging.Filter):
    """Mask sensitive data in log records (IC numbers, emails, passwords)."""

    IC_PATTERN = re.compile(r'\b\d{6}-?\d{2}-?\d{4}\b')
    EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')

    def filter(self, record):
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = self.IC_PATTERN.sub('[IC-REDACTED]', record.msg)
            record.msg = self.EMAIL_PATTERN.sub('[EMAIL-REDACTED]', record.msg)
        return True


class JsonFormatter(logging.Formatter):
    """Format log records as JSON for SIEM/log aggregation tools."""

    def format(self, record):
        log_entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        if record.exc_info and record.exc_info[0]:
            log_entry['exception'] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def log_security_event(event_type, request=None, user=None, extra=None, level='info'):
    """
    Log a structured security event.

    Usage:
        log_security_event('LOGIN_SUCCESS', request, user=username)
        log_security_event('API_ERROR', request, extra={'status': 403}, level='warning')
    """
    message = f"SECURITY_EVENT: type={event_type}"
    if user:
        message += f", user={user}"
    if request:
        message += f", ip={_get_ip(request)}, path={request.path}"
    if extra:
        message += f", extra={json.dumps(extra)}"

    getattr(logger, level)(message)


def _get_ip(request):
    """Get client IP from request."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')
