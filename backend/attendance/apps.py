from django.apps import AppConfig


class AttendanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'attendance'

    def ready(self):
        from django.conf import settings
        if not settings.DEBUG:
            self._validate_production_security()

    def _validate_production_security(self):
        from django.conf import settings
        import sys
        errors = []
        if len(settings.SECRET_KEY) < 50:
            errors.append(f'SECRET_KEY too short: {len(settings.SECRET_KEY)} chars (min 50)')
        if not settings.ALLOWED_HOSTS or settings.ALLOWED_HOSTS == ['localhost', '127.0.0.1']:
            errors.append('ALLOWED_HOSTS not configured for production')
        if errors:
            for e in errors:
                print(f'SECURITY ERROR: {e}', file=sys.stderr)
            sys.exit(1)
