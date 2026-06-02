import os
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth.models import User
from django.conf import settings
from django.core.cache import cache
from pathlib import Path

class SecurityFeaturesTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.login_url = reverse('auth_login')
        self.user = User.objects.create_user(username='admin', password='StrongPassword123!')
        self.base_dir = settings.BASE_DIR

    def tearDown(self):
        cache.clear()

    # 1. Privacy policy if you collect user data
    def test_privacy_consent_required_in_frontend(self):
        """Test that the frontend form requires explicit consent (terms-agree checkbox)."""
        form_html_path = self.base_dir.parent / 'frontend' / 'form.html'
        if form_html_path.exists():
            with open(form_html_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn('id="terms"', content)
            self.assertIn('Saya bersetuju', content)

    # 2. Know where user data is stored
    def test_database_is_local(self):
        """Ensure data is stored locally in SQLite and not sent to 3rd party BaaS."""
        db_engine = settings.DATABASES['default']['ENGINE']
        self.assertEqual(db_engine, 'django.db.backends.sqlite3')

    # 3. Check security headers
    def test_http_security_headers(self):
        """Test that critical HTTP security headers are present in API responses."""
        response = self.client.get(reverse('folder_list'))
        self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(response.headers.get('X-Frame-Options'), 'DENY')

    # 4. Scan against OWASP basics (SQLi)
    def test_sql_injection_protection(self):
        """Ensure the ORM sanitizes SQL injection payloads instead of crashing."""
        self.client.force_authenticate(user=self.user)
        # Attempt SQL injection on folder list endpoint
        payload = {"name": "test'); DROP TABLE attendance_folder;--"}
        response = self.client.post(reverse('folder_list'), payload, format='json')
        # The serializer should safely reject it (or accept it as literal string), but NEVER 500
        self.assertNotEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    # 5. Make sure .env values are not leaking
    def test_env_file_not_tracked(self):
        """Check that .env is safely ignored in .gitignore to prevent secrets leak."""
        gitignore_path = self.base_dir.parent / '.gitignore'
        if gitignore_path.exists():
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn('.env', content.split('\n'))

    # 6. Check API responses for sensitive data
    def test_api_responses_no_sensitive_data(self):
        """Test that user passwords and sensitive fields are not leaked in API responses."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse('auth_check'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = str(response.data).lower()
        self.assertNotIn('password', data)
        self.assertNotIn('hash', data)

    # 8. Never expose API keys in frontend code
    def test_no_api_keys_in_frontend_js(self):
        """Ensure frontend JS files rely on sessions and don't contain hardcoded API keys."""
        js_dir = self.base_dir.parent / 'frontend' / 'js'
        if js_dir.exists():
            for js_file in js_dir.glob('*.js'):
                with open(js_file, 'r', encoding='utf-8') as f:
                    content = f.read().lower()
                self.assertNotIn('bearer ', content)
                self.assertNotIn('api_key', content)
                self.assertNotIn('jwt', content)

    # 10. Add rate limits before someone burns your API bill
    def test_brute_force_login_protection(self):
        """Test that the API blocks brute-force login attempts (returns 429 Too Many Requests)."""
        for _ in range(5):
            response = self.client.post(self.login_url, {'username': 'admin', 'password': 'wrongpassword'})
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.post(self.login_url, {'username': 'admin', 'password': 'wrongpassword'})
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn('Request was throttled', str(response.data.get('detail', '')))
