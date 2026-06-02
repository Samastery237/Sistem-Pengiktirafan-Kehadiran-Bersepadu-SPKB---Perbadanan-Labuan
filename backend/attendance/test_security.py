from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth.models import User
import time

from django.core.cache import cache

class SecurityFeaturesTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.login_url = reverse('auth_login')
        self.user = User.objects.create_user(username='admin', password='StrongPassword123!')

    def tearDown(self):
        cache.clear()

    def test_brute_force_login_protection(self):
        """
        Test that the API blocks brute-force login attempts (returns 429 Too Many Requests).
        Our custom LoginThrottle allows 5 requests per minute.
        """
        # Make 5 failed attempts (the limit)
        for _ in range(5):
            response = self.client.post(self.login_url, {'username': 'admin', 'password': 'wrongpassword'})
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # The 6th attempt should be throttled
        response = self.client.post(self.login_url, {'username': 'admin', 'password': 'wrongpassword'})
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn('Request was throttled', str(response.data.get('detail', '')))

    def test_http_security_headers(self):
        """
        Test that critical HTTP security headers are present in API responses.
        This ensures SECURE_BROWSER_XSS_FILTER and SECURE_CONTENT_TYPE_NOSNIFF are active.
        """
        response = self.client.get(reverse('folder_list'))
        
        # Verify X-Content-Type-Options: nosniff
        self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')
        
        # Verify X-Frame-Options: DENY (prevents clickjacking)
        self.assertEqual(response.headers.get('X-Frame-Options'), 'DENY')
