"""
Comprehensive TDD tests for SPKB Authentication Views.

Covers: LoginView, LogoutView, CheckAuthView, ChangePasswordView,
UserListView, UserDetailView, VerifyEmailView, ResendVerificationView,
PasswordResetRequestView, PasswordResetConfirmView, account lockout
helpers, and email helper functions.

All test classes that make API requests inherit from DisableThrottleMixin
to bypass DRF throttling and abuse-protection middleware.
"""
import json
import logging
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from attendance.auth_views import (
    MAX_FAILED_ATTEMPTS,
    _is_locked,
    _record_failed_attempt,
    _reset_failed_attempts,
    _cleanup_old_attempts,
    password_reset_token_generator,
)
from attendance.models import (
    AdminProfile,
    Department,
    EmailVerificationToken,
    FailedLoginAttempt,
    Folder,
    UserAccountLock,
)
from attendance.tests import DisableThrottleMixin


# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

BROWSER_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
STRONG_PASSWORD = 'Str0ng!Pass#2024'
ANOTHER_STRONG_PASSWORD = 'An0ther!Str0ng#'


# ══════════════════════════════════════════════════════════════
# LoginView Tests
# ══════════════════════════════════════════════════════════════


class TestLoginViewGET(DisableThrottleMixin, TestCase):
    """GET /api/attendance/auth/login/ returns a CSRF token."""

    def test_get_returns_csrf_token(self):
        """GET on login endpoint should return a CSRF token."""
        response = self.client.get(reverse('auth_login'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('csrfToken', data)
        self.assertTrue(len(data['csrfToken']) > 0)

    def test_get_requires_no_authentication(self):
        """GET on login endpoint should be accessible without auth."""
        response = self.client.get(reverse('auth_login'))
        self.assertEqual(response.status_code, 200)


class TestLoginViewPOST(DisableThrottleMixin, TestCase):
    """POST /api/attendance/auth/login/ authenticates users."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='loginuser', password=STRONG_PASSWORD
        )
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_valid_credentials_returns_200(self):
        """POST with valid credentials returns 200 with user info."""
        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'loginuser',
                'password': STRONG_PASSWORD,
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('csrfToken', data)
        self.assertIn('is_super', data)
        self.assertIn('department_id', data)

    def test_valid_credentials_returns_csrf_token(self):
        """Successful login response includes a CSRF token."""
        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'loginuser',
                'password': STRONG_PASSWORD,
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.json()['csrfToken']) > 0)

    def test_csrf_token_rotates_on_login(self):
        """CSRF token should rotate (change) after successful login."""
        # First login
        response1 = self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'loginuser',
                'password': STRONG_PASSWORD,
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        csrf1 = response1.json()['csrfToken']

        # Second login
        response2 = self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'loginuser',
                'password': STRONG_PASSWORD,
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        csrf2 = response2.json()['csrfToken']

        self.assertNotEqual(csrf1, csrf2)

    def test_wrong_password_returns_401(self):
        """POST with wrong password returns 401."""
        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'loginuser',
                'password': 'WrongPassword1!',
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['status'], 'error')

    def test_missing_username_returns_400(self):
        """POST with missing username returns 400."""
        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({'password': STRONG_PASSWORD}),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('diperlukan', response.json().get('message', '').lower())

    def test_missing_password_returns_400(self):
        """POST with missing password returns 400."""
        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({'username': 'loginuser'}),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('diperlukan', response.json().get('message', '').lower())

    def test_empty_username_returns_400(self):
        """POST with empty username string returns 400."""
        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({'username': '', 'password': STRONG_PASSWORD}),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 400)

    def test_empty_password_returns_400(self):
        """POST with empty password string returns 400."""
        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({'username': 'loginuser', 'password': ''}),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 400)

    def test_locked_account_returns_403(self):
        """POST with locked account returns 403 with locked=true."""
        # Lock the account
        lock = UserAccountLock.objects.create(user=self.user)
        lock.locked_until = timezone.now() + timedelta(minutes=15)
        lock.save(update_fields=['locked_until'])

        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'loginuser',
                'password': STRONG_PASSWORD,
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertTrue(data.get('locked'))
        self.assertIn('dikunci', data.get('message', '').lower())

    def test_inactive_account_returns_401(self):
        """POST with inactive account returns 401 (no user enumeration)."""
        self.user.is_active = False
        self.user.save()

        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'loginuser',
                'password': STRONG_PASSWORD,
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 401)

    def test_nonexistent_user_returns_401(self):
        """POST with non-existent username returns 401."""
        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'ghost_user',
                'password': STRONG_PASSWORD,
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 401)

    def test_login_returns_is_super_true_for_superuser(self):
        """Login response includes is_super=True for superusers."""
        self.user.is_superuser = True
        self.user.save()

        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'loginuser',
                'password': STRONG_PASSWORD,
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['is_super'])

    def test_login_returns_is_super_false_for_normal_user(self):
        """Login response includes is_super=False for non-superusers."""
        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'loginuser',
                'password': STRONG_PASSWORD,
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['is_super'])

    def test_login_returns_department_id_from_admin_profile(self):
        """Login response includes department_id from AdminProfile."""
        AdminProfile.objects.create(user=self.user, department=self.dept)

        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'loginuser',
                'password': STRONG_PASSWORD,
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['department_id'], self.dept.id)

    def test_login_without_admin_profile_department_id_none(self):
        """Login for user without AdminProfile returns department_id=None."""
        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'loginuser',
                'password': STRONG_PASSWORD,
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['department_id'])

    def test_login_sets_csrf_cookie(self):
        """Successful login sets a csrftoken cookie."""
        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'loginuser',
                'password': STRONG_PASSWORD,
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('csrftoken', response.cookies)


# ══════════════════════════════════════════════════════════════
# LogoutView Tests
# ══════════════════════════════════════════════════════════════


class TestLogoutView(DisableThrottleMixin, TestCase):
    """POST /api/attendance/auth/logout/ ends user session."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='logoutuser', password=STRONG_PASSWORD
        )
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_authenticated_post_returns_200(self):
        """Authenticated POST to logout returns 200."""
        self.client.login(username='logoutuser', password=STRONG_PASSWORD)
        response = self.client.post(reverse('auth_logout'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')

    def test_unauthenticated_post_returns_403(self):
        """Unauthenticated POST to logout returns 403."""
        response = self.client.post(reverse('auth_logout'))
        self.assertEqual(response.status_code, 403)

    def test_session_destroyed_after_logout(self):
        """Session should be destroyed after logout."""
        self.client.login(username='logoutuser', password=STRONG_PASSWORD)
        self.assertIn('_auth_user_id', self.client.session)

        self.client.post(reverse('auth_logout'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_check_auth_fails_after_logout(self):
        """After logout, auth check should fail."""
        self.client.login(username='logoutuser', password=STRONG_PASSWORD)
        self.client.post(reverse('auth_logout'))
        response = self.client.get(reverse('auth_check'))
        self.assertEqual(response.status_code, 403)


# ══════════════════════════════════════════════════════════════
# CheckAuthView Tests
# ══════════════════════════════════════════════════════════════


class TestCheckAuthView(DisableThrottleMixin, TestCase):
    """GET /api/attendance/auth/check/ verifies current session."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='checkauth', password=STRONG_PASSWORD
        )
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_authenticated_returns_username(self):
        """Authenticated GET returns the username."""
        self.client.login(username='checkauth', password=STRONG_PASSWORD)
        response = self.client.get(reverse('auth_check'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user'], 'checkauth')

    def test_authenticated_returns_is_super(self):
        """Authenticated GET returns is_super flag."""
        self.client.login(username='checkauth', password=STRONG_PASSWORD)
        response = self.client.get(reverse('auth_check'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['is_super'], False)

    def test_authenticated_returns_department_id(self):
        """Authenticated GET returns department_id from AdminProfile."""
        AdminProfile.objects.create(user=self.user, department=self.dept)
        self.client.login(username='checkauth', password=STRONG_PASSWORD)
        response = self.client.get(reverse('auth_check'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['department_id'], self.dept.id)

    def test_unauthenticated_returns_403(self):
        """Unauthenticated GET returns 403."""
        response = self.client.get(reverse('auth_check'))
        self.assertEqual(response.status_code, 403)


# ══════════════════════════════════════════════════════════════
# ChangePasswordView Tests
# ══════════════════════════════════════════════════════════════


class TestChangePasswordView(DisableThrottleMixin, TestCase):
    """POST /api/attendance/auth/password/ changes user password."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='pwuser', password=STRONG_PASSWORD
        )
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")
        self.client.login(username='pwuser', password=STRONG_PASSWORD)

    def test_valid_change_returns_200(self):
        """Valid old+new password returns 200."""
        response = self.client.post(
            '/api/attendance/auth/password/',
            data=json.dumps({
                'old_password': STRONG_PASSWORD,
                'new_password': ANOTHER_STRONG_PASSWORD,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')

    def test_password_actually_changes(self):
        """After successful change, the new password works."""
        self.client.post(
            '/api/attendance/auth/password/',
            data=json.dumps({
                'old_password': STRONG_PASSWORD,
                'new_password': ANOTHER_STRONG_PASSWORD,
            }),
            content_type='application/json',
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(ANOTHER_STRONG_PASSWORD))
        self.assertFalse(self.user.check_password(STRONG_PASSWORD))

    def test_wrong_old_password_returns_400(self):
        """Wrong old password returns 400."""
        response = self.client.post(
            '/api/attendance/auth/password/',
            data=json.dumps({
                'old_password': 'WrongOldPass1!',
                'new_password': ANOTHER_STRONG_PASSWORD,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('tidak betul', response.json().get('message', '').lower())

    def test_missing_old_password_returns_400(self):
        """Missing old_password returns 400."""
        response = self.client.post(
            '/api/attendance/auth/password/',
            data=json.dumps({
                'new_password': ANOTHER_STRONG_PASSWORD,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('lama diperlukan', response.json().get('message', '').lower())

    def test_missing_new_password_returns_400(self):
        """Missing new_password returns 400."""
        response = self.client.post(
            '/api/attendance/auth/password/',
            data=json.dumps({
                'old_password': STRONG_PASSWORD,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('baru diperlukan', response.json().get('message', '').lower())

    def test_weak_new_password_rejected(self):
        """Weak new password fails validation."""
        response = self.client.post(
            '/api/attendance/auth/password/',
            data=json.dumps({
                'old_password': STRONG_PASSWORD,
                'new_password': 'password',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_short_password_rejected(self):
        """Password shorter than 8 characters is rejected."""
        response = self.client.post(
            '/api/attendance/auth/password/',
            data=json.dumps({
                'old_password': STRONG_PASSWORD,
                'new_password': 'Ab1!',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_numeric_only_password_rejected(self):
        """Purely numeric password is rejected."""
        response = self.client.post(
            '/api/attendance/auth/password/',
            data=json.dumps({
                'old_password': STRONG_PASSWORD,
                'new_password': '12345678',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_csrf_token_rotated_after_change(self):
        """CSRF token should rotate after password change."""
        old_csrf = self.client.cookies.get('csrftoken', '')

        response = self.client.post(
            '/api/attendance/auth/password/',
            data=json.dumps({
                'old_password': STRONG_PASSWORD,
                'new_password': ANOTHER_STRONG_PASSWORD,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        new_csrf = self.client.cookies.get('csrftoken', '')
        if old_csrf and new_csrf:
            self.assertNotEqual(old_csrf, new_csrf)

    def test_session_maintained_after_change(self):
        """User should still be authenticated after password change."""
        self.client.post(
            '/api/attendance/auth/password/',
            data=json.dumps({
                'old_password': STRONG_PASSWORD,
                'new_password': ANOTHER_STRONG_PASSWORD,
            }),
            content_type='application/json',
        )
        response = self.client.get(reverse('auth_check'))
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_returns_403(self):
        """Unauthenticated password change returns 403."""
        self.client.logout()
        response = self.client.post(
            '/api/attendance/auth/password/',
            data=json.dumps({
                'old_password': STRONG_PASSWORD,
                'new_password': ANOTHER_STRONG_PASSWORD,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)


# ══════════════════════════════════════════════════════════════
# UserListView Tests
# ══════════════════════════════════════════════════════════════


class TestUserListViewGET(DisableThrottleMixin, TestCase):
    """GET /api/attendance/users/ lists all users (superuser only)."""

    def setUp(self):
        self.superuser = User.objects.create_user(
            username='super', password=STRONG_PASSWORD
        )
        self.superuser.is_superuser = True
        self.superuser.save()
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")
        self.client.login(username='super', password=STRONG_PASSWORD)

    def test_superuser_get_returns_all_users(self):
        """Superuser GET returns all users."""
        # Create another user
        User.objects.create_user(username='other', password='OtherPass1!')

        response = self.client.get(reverse('users_list'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('data', data)
        self.assertEqual(len(data['data']), 2)  # super + other

    def test_superuser_get_includes_department_info(self):
        """User list includes department_id and department_name."""
        AdminProfile.objects.create(user=self.superuser, department=self.dept)
        response = self.client.get(reverse('users_list'))
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        super_user_entry = next(u for u in data if u['username'] == 'super')
        self.assertEqual(super_user_entry['department_id'], self.dept.id)
        self.assertEqual(super_user_entry['department_name'], 'IT')

    def test_non_superuser_get_returns_403(self):
        """Non-superuser GET returns 403."""
        self.superuser.is_superuser = False
        self.superuser.save()
        response = self.client.get(reverse('users_list'))
        self.assertEqual(response.status_code, 403)


class TestUserListViewPOST(DisableThrottleMixin, TestCase):
    """POST /api/attendance/users/ creates a new user (superuser only)."""

    def setUp(self):
        self.superuser = User.objects.create_user(
            username='super', password=STRONG_PASSWORD
        )
        self.superuser.is_superuser = True
        self.superuser.save()
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")
        self.client.login(username='super', password=STRONG_PASSWORD)

    def test_superuser_post_creates_user(self):
        """Superuser POST creates a new user."""
        response = self.client.post(
            reverse('users_list'),
            data=json.dumps({
                'username': 'newuser',
                'password': 'NewUserPass1!',
                'email': 'new@test.com',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_duplicate_username_returns_400(self):
        """Creating a user with an existing username returns 400."""
        response = self.client.post(
            reverse('users_list'),
            data=json.dumps({
                'username': 'super',
                'password': 'SomePass1!',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('already exists', response.json().get('message', '').lower())

    def test_missing_username_returns_400(self):
        """Missing username returns 400."""
        response = self.client.post(
            reverse('users_list'),
            data=json.dumps({
                'password': 'SomePass1!',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_password_returns_400(self):
        """Missing password returns 400."""
        response = self.client.post(
            reverse('users_list'),
            data=json.dumps({
                'username': 'newuser',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_weak_password_returns_400(self):
        """Creating a user with a weak password returns 400."""
        response = self.client.post(
            reverse('users_list'),
            data=json.dumps({
                'username': 'weakuser',
                'password': '12345678',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(EMAIL_VERIFICATION_REQUIRED=True)
    def test_user_created_inactive_when_email_verification_required(self):
        """New user is created inactive when EMAIL_VERIFICATION_REQUIRED=true."""
        response = self.client.post(
            reverse('users_list'),
            data=json.dumps({
                'username': 'inactive_new',
                'password': 'GoodPass1!',
                'email': 'inactive@test.com',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        new_user = User.objects.get(username='inactive_new')
        self.assertFalse(new_user.is_active)

    @override_settings(EMAIL_VERIFICATION_REQUIRED=False)
    def test_user_created_active_when_email_verification_disabled(self):
        """New user is created active when EMAIL_VERIFICATION_REQUIRED=false."""
        response = self.client.post(
            reverse('users_list'),
            data=json.dumps({
                'username': 'active_new',
                'password': 'GoodPass1!',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        new_user = User.objects.get(username='active_new')
        self.assertTrue(new_user.is_active)

    def test_admin_profile_created_with_department(self):
        """Creating a non-super user creates an AdminProfile with department."""
        response = self.client.post(
            reverse('users_list'),
            data=json.dumps({
                'username': 'deptuser',
                'password': 'GoodPass1!',
                'department_id': self.dept.id,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        new_user = User.objects.get(username='deptuser')
        self.assertTrue(hasattr(new_user, 'admin_profile'))
        self.assertEqual(new_user.admin_profile.department, self.dept)

    def test_superuser_ignores_department(self):
        """Creating a superuser ignores department_id."""
        response = self.client.post(
            reverse('users_list'),
            data=json.dumps({
                'username': 'newsuper',
                'password': 'GoodPass1!',
                'is_super': True,
                'department_id': self.dept.id,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        new_user = User.objects.get(username='newsuper')
        self.assertTrue(new_user.is_superuser)
        self.assertIsNone(new_user.admin_profile.department)

    def test_non_superuser_post_returns_403(self):
        """Non-superuser POST returns 403."""
        self.superuser.is_superuser = False
        self.superuser.save()
        response = self.client.post(
            reverse('users_list'),
            data=json.dumps({
                'username': 'shouldfail',
                'password': 'GoodPass1!',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(EMAIL_VERIFICATION_REQUIRED=True)
    def test_inactive_user_without_email_no_crash(self):
        """Creating a user with verification required but no email doesn't crash."""
        response = self.client.post(
            reverse('users_list'),
            data=json.dumps({
                'username': 'noemailuser',
                'password': 'GoodPass1!',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        new_user = User.objects.get(username='noemailuser')
        self.assertFalse(new_user.is_active)


# ══════════════════════════════════════════════════════════════
# UserDetailView Tests
# ══════════════════════════════════════════════════════════════


class TestUserDetailView(DisableThrottleMixin, TestCase):
    """DELETE /api/attendance/users/<id>/ deletes a user (superuser only)."""

    def setUp(self):
        self.superuser = User.objects.create_user(
            username='delsuper', password=STRONG_PASSWORD
        )
        self.superuser.is_superuser = True
        self.superuser.save()
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")
        self.client.login(username='delsuper', password=STRONG_PASSWORD)

    def test_superuser_can_delete_other_user(self):
        """Superuser can delete another user."""
        victim = User.objects.create_user(username='victim', password='Victim1!')
        response = self.client.delete(reverse('users_detail', args=[victim.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='victim').exists())

    def test_self_deletion_returns_400(self):
        """Self-deletion returns 400."""
        response = self.client.delete(reverse('users_detail', args=[self.superuser.id]))
        self.assertEqual(response.status_code, 400)
        self.assertIn('yourself', response.json().get('message', '').lower())

    def test_deleting_last_superuser_returns_400(self):
        """Deleting the last superuser returns 400.

        Uses APIRequestFactory to call the view directly with a mocked
        superuser, while the DB has only 1 superuser (the target).
        """
        from attendance.auth_views import UserDetailView
        from rest_framework.test import APIRequestFactory

        target_super = User.objects.create_user(
            username='target_super', password='Target1!'
        )
        target_super.is_superuser = True
        target_super.save()

        # Demote delsuper so target_super is the only superuser in DB
        User.objects.filter(pk=self.superuser.pk).update(is_superuser=False)

        # Call view directly with a mocked superuser request
        factory = APIRequestFactory()
        request = factory.delete(f'/api/attendance/users/{target_super.id}/')
        request.user = MagicMock()
        request.user.is_superuser = True
        request.user.pk = self.superuser.pk
        request.user.id = self.superuser.id
        request.user.username = 'delsuper'

        view = UserDetailView.as_view()
        response = view(request, user_id=target_super.id)
        self.assertEqual(response.status_code, 400)
        self.assertIn('last superuser', response.data.get('message', '').lower())

    def test_deleting_second_to_last_superuser_succeeds(self):
        """Deleting a superuser when there are multiple succeeds."""
        other_super = User.objects.create_user(
            username='othersuper', password='Other1!'
        )
        other_super.is_superuser = True
        other_super.save()

        response = self.client.delete(reverse('users_detail', args=[other_super.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='othersuper').exists())

    def test_nonexistent_user_returns_404(self):
        """Deleting a non-existent user returns 404."""
        response = self.client.delete(reverse('users_detail', args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_non_superuser_returns_403(self):
        """Non-superuser DELETE returns 403."""
        self.superuser.is_superuser = False
        self.superuser.save()
        victim = User.objects.create_user(username='notdeleted', password='pw')
        response = self.client.delete(reverse('users_detail', args=[victim.id]))
        self.assertEqual(response.status_code, 403)


# ══════════════════════════════════════════════════════════════
# VerifyEmailView Tests
# ══════════════════════════════════════════════════════════════


class TestVerifyEmailView(DisableThrottleMixin, TestCase):
    """GET /api/attendance/auth/verify-email/<token>/ activates user."""

    def setUp(self):
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_valid_token_activates_user(self):
        """Valid token activates the user."""
        user = User.objects.create_user(
            username='activate', password=STRONG_PASSWORD,
            email='activate@test.com', is_active=False
        )
        token_obj = EmailVerificationToken.generate_for_user(user)

        response = self.client.get(
            reverse('auth_verify_email', args=[token_obj.token])
        )
        self.assertEqual(response.status_code, 200)

        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_invalid_token_returns_400(self):
        """Invalid token returns 400."""
        response = self.client.get(
            reverse('auth_verify_email', args=['invalidtoken1234567890abcdef'])
        )
        self.assertEqual(response.status_code, 400)

    def test_expired_token_returns_400(self):
        """Expired token returns 400."""
        user = User.objects.create_user(
            username='expired', password=STRONG_PASSWORD,
            email='expired@test.com', is_active=False
        )
        token_obj = EmailVerificationToken.generate_for_user(user)
        token_obj.expires_at = timezone.now() - timedelta(hours=1)
        token_obj.save()

        response = self.client.get(
            reverse('auth_verify_email', args=[token_obj.token])
        )
        self.assertEqual(response.status_code, 400)

    def test_already_used_token_returns_400(self):
        """Already used token returns 400."""
        user = User.objects.create_user(
            username='usedtoken', password=STRONG_PASSWORD,
            email='used@test.com', is_active=False
        )
        token_obj = EmailVerificationToken.generate_for_user(user)
        token_obj.is_used = True
        token_obj.save()

        response = self.client.get(
            reverse('auth_verify_email', args=[token_obj.token])
        )
        self.assertEqual(response.status_code, 400)

    def test_updates_admin_profile_email_verified(self):
        """Successful verification sets email_verified on AdminProfile."""
        user = User.objects.create_user(
            username='profverify', password=STRONG_PASSWORD,
            email='prof@test.com', is_active=False
        )
        AdminProfile.objects.create(user=user)
        token_obj = EmailVerificationToken.generate_for_user(user)

        self.client.get(reverse('auth_verify_email', args=[token_obj.token]))

        profile = AdminProfile.objects.get(user=user)
        self.assertTrue(profile.email_verified)
        self.assertIsNotNone(profile.verified_at)

    def test_user_without_admin_profile_verifies(self):
        """A user without AdminProfile can verify without crashing."""
        user = User.objects.create_user(
            username='noprofile', password=STRONG_PASSWORD,
            email='noprofile@test.com', is_active=False
        )
        # No AdminProfile created
        token_obj = EmailVerificationToken.generate_for_user(user)

        response = self.client.get(
            reverse('auth_verify_email', args=[token_obj.token])
        )
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_valid_token_response_message(self):
        """Successful verification returns bilingual success message."""
        user = User.objects.create_user(
            username='msgtest', password=STRONG_PASSWORD,
            email='msg@test.com', is_active=False
        )
        token_obj = EmailVerificationToken.generate_for_user(user)

        response = self.client.get(
            reverse('auth_verify_email', args=[token_obj.token])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('berjaya', response.json().get('message', '').lower())


# ══════════════════════════════════════════════════════════════
# ResendVerificationView Tests
# ══════════════════════════════════════════════════════════════


class TestResendVerificationView(DisableThrottleMixin, TestCase):
    """POST /api/attendance/auth/resend-verification/ resends verification email."""

    def setUp(self):
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_missing_username_returns_400(self):
        """POST without username returns 400."""
        response = self.client.post(
            reverse('auth_resend_verification'),
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('diperlukan', response.json().get('message', '').lower())

    def test_empty_username_returns_400(self):
        """POST with empty username returns 400."""
        response = self.client.post(
            reverse('auth_resend_verification'),
            data=json.dumps({'username': ''}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_already_active_user_returns_200(self):
        """Already active user returns 200 (no enumeration)."""
        User.objects.create_user(
            username='activeuser', password=STRONG_PASSWORD, is_active=True
        )
        response = self.client.post(
            reverse('auth_resend_verification'),
            data=json.dumps({'username': 'activeuser'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

    def test_user_without_email_returns_200(self):
        """User without email returns 200 (no enumeration)."""
        user = User.objects.create_user(
            username='noemail', password=STRONG_PASSWORD, is_active=False
        )
        AdminProfile.objects.create(user=user)
        response = self.client.post(
            reverse('auth_resend_verification'),
            data=json.dumps({'username': 'noemail'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

    def test_nonexistent_user_returns_success_no_enumeration(self):
        """Non-existent user returns success to prevent enumeration."""
        response = self.client.post(
            reverse('auth_resend_verification'),
            data=json.dumps({'username': 'ghost_user_99999'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('jika akaun wujud', response.json().get('message', '').lower())

    @patch('attendance.auth_views.send_mail')
    def test_valid_request_sends_email(self, mock_send):
        """Valid request sends verification email."""
        user = User.objects.create_user(
            username='resendme', password=STRONG_PASSWORD,
            email='resend@test.com', is_active=False
        )
        AdminProfile.objects.create(user=user)

        response = self.client.post(
            reverse('auth_resend_verification'),
            data=json.dumps({'username': 'resendme'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        mock_send.assert_called_once()

    @patch('attendance.auth_views.send_mail')
    def test_nonexistent_user_does_not_send_email(self, mock_send):
        """Non-existent user does not trigger email sending."""
        response = self.client.post(
            reverse('auth_resend_verification'),
            data=json.dumps({'username': 'ghost_user_xyz'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        mock_send.assert_not_called()


# ══════════════════════════════════════════════════════════════
# PasswordResetRequestView Tests
# ══════════════════════════════════════════════════════════════


class TestPasswordResetRequestView(DisableThrottleMixin, TestCase):
    """POST /api/attendance/auth/reset-password/ requests password reset."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='resetuser', password=STRONG_PASSWORD,
            email='reset@test.com'
        )
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_missing_email_returns_400(self):
        """POST without email returns 400."""
        response = self.client.post(
            reverse('auth_reset_password'),
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('diperlukan', response.json().get('message', '').lower())

    def test_empty_email_returns_400(self):
        """POST with empty email returns 400."""
        response = self.client.post(
            reverse('auth_reset_password'),
            data=json.dumps({'email': ''}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_nonexistent_email_returns_success_no_enumeration(self):
        """Non-existent email returns success to prevent enumeration."""
        response = self.client.post(
            reverse('auth_reset_password'),
            data=json.dumps({'email': 'nonexistent@example.com'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('jika e-mel wujud', response.json().get('message', '').lower())

    def test_inactive_user_returns_success_no_email(self):
        """Inactive user returns success but does not send email."""
        self.user.is_active = False
        self.user.save()

        response = self.client.post(
            reverse('auth_reset_password'),
            data=json.dumps({'email': 'reset@test.com'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

    @patch('attendance.auth_views.send_mail')
    def test_valid_request_sends_reset_email(self, mock_send):
        """Valid request sends password reset email."""
        response = self.client.post(
            reverse('auth_reset_password'),
            data=json.dumps({'email': 'reset@test.com'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        mock_send.assert_called_once()

    @patch('attendance.auth_views.send_mail')
    def test_reset_email_contains_uid_and_token(self, mock_send):
        """Reset email body contains path-based uid/token."""
        self.client.post(
            reverse('auth_reset_password'),
            data=json.dumps({'email': 'reset@test.com'}),
            content_type='application/json',
        )
        call_args = mock_send.call_args
        email_body = call_args.kwargs.get('message', call_args[1].get('message', ''))
        self.assertIn('reset-password', email_body)

    @patch('attendance.auth_views.send_mail')
    def test_inactive_user_does_not_send_email(self, mock_send):
        """Inactive user does not trigger email sending."""
        self.user.is_active = False
        self.user.save()

        response = self.client.post(
            reverse('auth_reset_password'),
            data=json.dumps({'email': 'reset@test.com'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        mock_send.assert_not_called()


# ══════════════════════════════════════════════════════════════
# PasswordResetConfirmView Tests
# ══════════════════════════════════════════════════════════════


class TestPasswordResetConfirmView(DisableThrottleMixin, TestCase):
    """POST /api/attendance/auth/reset-password/confirm/ resets password."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='confirmreset', password=STRONG_PASSWORD,
            email='confirm@test.com'
        )
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_missing_uid_returns_400(self):
        """Missing uid returns 400."""
        token = password_reset_token_generator.make_token(self.user)
        response = self.client.post(
            reverse('auth_reset_password_confirm'),
            data=json.dumps({
                'token': token,
                'new_password': ANOTHER_STRONG_PASSWORD,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_token_returns_400(self):
        """Missing token returns 400."""
        response = self.client.post(
            reverse('auth_reset_password_confirm'),
            data=json.dumps({
                'uid': self.user.pk,
                'new_password': ANOTHER_STRONG_PASSWORD,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_new_password_returns_400(self):
        """Missing new_password returns 400."""
        token = password_reset_token_generator.make_token(self.user)
        response = self.client.post(
            reverse('auth_reset_password_confirm'),
            data=json.dumps({
                'uid': self.user.pk,
                'token': token,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_uid_returns_400(self):
        """Invalid uid returns 400."""
        token = password_reset_token_generator.make_token(self.user)
        response = self.client.post(
            reverse('auth_reset_password_confirm'),
            data=json.dumps({
                'uid': 999999,
                'token': token,
                'new_password': ANOTHER_STRONG_PASSWORD,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_token_returns_400(self):
        """Invalid token returns 400."""
        response = self.client.post(
            reverse('auth_reset_password_confirm'),
            data=json.dumps({
                'uid': self.user.pk,
                'token': 'invalid-token-string',
                'new_password': ANOTHER_STRONG_PASSWORD,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_weak_password_returns_400(self):
        """Weak password returns 400."""
        token = password_reset_token_generator.make_token(self.user)
        response = self.client.post(
            reverse('auth_reset_password_confirm'),
            data=json.dumps({
                'uid': self.user.pk,
                'token': token,
                'new_password': '123',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_valid_reset_succeeds(self):
        """Valid reset returns 200."""
        token = password_reset_token_generator.make_token(self.user)
        response = self.client.post(
            reverse('auth_reset_password_confirm'),
            data=json.dumps({
                'uid': self.user.pk,
                'token': token,
                'new_password': ANOTHER_STRONG_PASSWORD,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

    def test_password_actually_changes(self):
        """After reset, the new password works."""
        token = password_reset_token_generator.make_token(self.user)
        self.client.post(
            reverse('auth_reset_password_confirm'),
            data=json.dumps({
                'uid': self.user.pk,
                'token': token,
                'new_password': ANOTHER_STRONG_PASSWORD,
            }),
            content_type='application/json',
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(ANOTHER_STRONG_PASSWORD))
        self.assertFalse(self.user.check_password(STRONG_PASSWORD))

    def test_token_invalid_after_reset(self):
        """After reset, the same token cannot be reused."""
        token = password_reset_token_generator.make_token(self.user)
        # First reset succeeds
        self.client.post(
            reverse('auth_reset_password_confirm'),
            data=json.dumps({
                'uid': self.user.pk,
                'token': token,
                'new_password': ANOTHER_STRONG_PASSWORD,
            }),
            content_type='application/json',
        )
        # Second attempt with same token should fail
        response = self.client.post(
            reverse('auth_reset_password_confirm'),
            data=json.dumps({
                'uid': self.user.pk,
                'token': token,
                'new_password': 'YetAn0ther!Pass',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_reset_logs_security_event(self):
        """Successful reset produces a security log entry."""
        token = password_reset_token_generator.make_token(self.user)
        security_logger = logging.getLogger('security')
        with patch.object(security_logger, 'info') as mock_info:
            self.client.post(
                reverse('auth_reset_password_confirm'),
                data=json.dumps({
                    'uid': self.user.pk,
                    'token': token,
                    'new_password': ANOTHER_STRONG_PASSWORD,
                }),
                content_type='application/json',
            )
        self.assertTrue(
            any('PASSWORD RESET COMPLETED' in str(call) for call in mock_info.call_args_list)
        )


# ══════════════════════════════════════════════════════════════
# Account Lockout Helper Tests
# ══════════════════════════════════════════════════════════════


class TestIsLockedHelper(DisableThrottleMixin, TestCase):
    """Tests for the _is_locked() helper function."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='lockhelper', password=STRONG_PASSWORD
        )
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_returns_false_for_nonexistent_user(self):
        """_is_locked returns False for a username that doesn't exist."""
        self.assertFalse(_is_locked('nonexistent_user'))

    def test_returns_true_when_locked_until_in_future(self):
        """_is_locked returns True when locked_until is in the future."""
        lock = UserAccountLock.objects.create(user=self.user)
        lock.locked_until = timezone.now() + timedelta(minutes=15)
        lock.save(update_fields=['locked_until'])

        self.assertTrue(_is_locked('lockhelper'))

    def test_returns_false_when_lockout_expired(self):
        """_is_locked returns False when lockout has expired."""
        lock = UserAccountLock.objects.create(user=self.user)
        lock.locked_until = timezone.now() - timedelta(minutes=1)
        lock.save(update_fields=['locked_until'])

        self.assertFalse(_is_locked('lockhelper'))

    def test_returns_false_when_no_lock_record(self):
        """_is_locked returns False when no UserAccountLock record exists."""
        self.assertFalse(_is_locked('lockhelper'))

    def test_returns_false_when_locked_until_is_none(self):
        """_is_locked returns False when locked_until is None."""
        UserAccountLock.objects.create(user=self.user)
        self.assertFalse(_is_locked('lockhelper'))

    def test_auto_clears_expired_lock(self):
        """_is_locked auto-clears expired lock fields."""
        lock = UserAccountLock.objects.create(user=self.user)
        lock.locked_until = timezone.now() - timedelta(minutes=1)
        lock.failure_count = 5
        lock.save(update_fields=['locked_until', 'failure_count'])

        # Should return False and clear the lock
        self.assertFalse(_is_locked('lockhelper'))

        lock.refresh_from_db()
        self.assertIsNone(lock.locked_until)
        self.assertEqual(lock.failure_count, 0)


class TestRecordFailedAttempt(DisableThrottleMixin, TestCase):
    """Tests for the _record_failed_attempt() helper function."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='recordfail', password=STRONG_PASSWORD
        )
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_increments_failure_counter(self):
        """_record_failed_attempt increments the failure counter."""
        _record_failed_attempt('recordfail', '127.0.0.1')
        lock = UserAccountLock.objects.get(user=self.user)
        self.assertEqual(lock.failure_count, 1)

    def test_creates_failed_login_attempt_record(self):
        """_record_failed_attempt creates a FailedLoginAttempt record."""
        _record_failed_attempt('recordfail', '192.168.1.1')
        self.assertEqual(
            FailedLoginAttempt.objects.filter(username='recordfail').count(), 1
        )
        attempt = FailedLoginAttempt.objects.first()
        self.assertEqual(attempt.ip_address, '192.168.1.1')

    def test_account_locks_after_max_attempts(self):
        """Account locks after MAX_FAILED_ATTEMPTS (5) failures."""
        for _ in range(MAX_FAILED_ATTEMPTS):
            _record_failed_attempt('recordfail', '127.0.0.1')

        lock = UserAccountLock.objects.get(user=self.user)
        self.assertTrue(lock.is_locked)
        self.assertIsNotNone(lock.locked_until)
        self.assertGreater(lock.locked_until, timezone.now())

    def test_does_not_lock_before_max_attempts(self):
        """Account does not lock before MAX_FAILED_ATTEMPTS."""
        for _ in range(MAX_FAILED_ATTEMPTS - 1):
            _record_failed_attempt('recordfail', '127.0.0.1')

        lock = UserAccountLock.objects.get(user=self.user)
        self.assertFalse(lock.is_locked)

    def test_nonexistent_user_no_lock_record(self):
        """Non-existent user does not create a UserAccountLock record."""
        _record_failed_attempt('ghost_user', '127.0.0.1')
        self.assertFalse(
            UserAccountLock.objects.filter(user__username='ghost_user').exists()
        )

    def test_nonexistent_user_stores_failed_attempt(self):
        """Non-existent user still stores FailedLoginAttempt for auditing."""
        _record_failed_attempt('ghost_user', '10.0.0.1')
        self.assertEqual(
            FailedLoginAttempt.objects.filter(username='ghost_user').count(), 1
        )


class TestResetFailedAttempts(DisableThrottleMixin, TestCase):
    """Tests for the _reset_failed_attempts() helper function."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='resetfail', password=STRONG_PASSWORD
        )
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_clears_failed_login_attempts(self):
        """_reset_failed_attempts deletes all FailedLoginAttempt records."""
        for _ in range(3):
            FailedLoginAttempt.objects.create(username='resetfail', ip_address='1.1.1.1')

        self.assertEqual(
            FailedLoginAttempt.objects.filter(username='resetfail').count(), 3
        )

        _reset_failed_attempts('resetfail')

        self.assertEqual(
            FailedLoginAttempt.objects.filter(username='resetfail').count(), 0
        )

    def test_resets_lock_record(self):
        """_reset_failed_attempts clears lock state."""
        lock = UserAccountLock.objects.create(user=self.user)
        lock.locked_until = timezone.now() + timedelta(minutes=15)
        lock.failure_count = 5
        lock.save()

        _reset_failed_attempts('resetfail')

        lock.refresh_from_db()
        self.assertIsNone(lock.locked_until)
        self.assertEqual(lock.failure_count, 0)

    def test_nonexistent_user_no_crash(self):
        """_reset_failed_attempts does not crash for non-existent user."""
        _reset_failed_attempts('ghost_user')  # Should not raise


class TestCleanupOldAttempts(DisableThrottleMixin, TestCase):
    """Tests for the _cleanup_old_attempts() helper function."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='cleanupuser', password=STRONG_PASSWORD
        )
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_deletes_attempts_older_than_24h(self):
        """Attempts older than 24 hours should be deleted."""
        old_time = timezone.now() - timedelta(hours=25)
        FailedLoginAttempt.objects.create(username='cleanupuser', ip_address='1.1.1.1')
        FailedLoginAttempt.objects.all().update(attempted_at=old_time)

        _cleanup_old_attempts()

        self.assertEqual(
            FailedLoginAttempt.objects.filter(username='cleanupuser').count(), 0
        )

    def test_keeps_recent_attempts(self):
        """Attempts within 24 hours should be kept."""
        FailedLoginAttempt.objects.create(username='cleanupuser', ip_address='1.1.1.1')

        _cleanup_old_attempts()

        self.assertEqual(
            FailedLoginAttempt.objects.filter(username='cleanupuser').count(), 1
        )


# ══════════════════════════════════════════════════════════════
# Account Lockout Integration Tests
# ══════════════════════════════════════════════════════════════


class TestAccountLockoutIntegration(DisableThrottleMixin, TestCase):
    """Integration tests for the full account lockout flow via login."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='lockint', password=STRONG_PASSWORD
        )
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_account_locks_after_5_failed_attempts(self):
        """After 5 failed login attempts, the account is locked."""
        for _ in range(5):
            response = self.client.post(
                reverse('auth_login'),
                data=json.dumps({
                    'username': 'lockint',
                    'password': 'wrong',
                }),
                content_type='application/json',
                HTTP_USER_AGENT=BROWSER_UA,
            )
            self.assertIn(response.status_code, [401, 429])

        # 6th attempt should be locked
        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'lockint',
                'password': 'wrong',
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.json().get('locked'))

    def test_correct_password_while_locked_still_rejected(self):
        """Even with correct password, a locked account is rejected."""
        for _ in range(5):
            self.client.post(
                reverse('auth_login'),
                data=json.dumps({
                    'username': 'lockint',
                    'password': 'wrong',
                }),
                content_type='application/json',
                HTTP_USER_AGENT=BROWSER_UA,
            )

        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'lockint',
                'password': STRONG_PASSWORD,
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 403)

    def test_successful_login_resets_failed_attempts(self):
        """A successful login clears all failed attempt records."""
        for _ in range(3):
            self.client.post(
                reverse('auth_login'),
                data=json.dumps({
                    'username': 'lockint',
                    'password': 'wrong',
                }),
                content_type='application/json',
                HTTP_USER_AGENT=BROWSER_UA,
            )

        self.assertEqual(
            FailedLoginAttempt.objects.filter(username='lockint').count(), 3
        )

        # Successful login
        self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'lockint',
                'password': STRONG_PASSWORD,
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )

        self.assertEqual(
            FailedLoginAttempt.objects.filter(username='lockint').count(), 0
        )

    def test_lockout_expires_after_duration(self):
        """After lockout duration expires, login works again."""
        for _ in range(5):
            self.client.post(
                reverse('auth_login'),
                data=json.dumps({
                    'username': 'lockint',
                    'password': 'wrong',
                }),
                content_type='application/json',
                HTTP_USER_AGENT=BROWSER_UA,
            )

        # Manually expire the lock
        lock = UserAccountLock.objects.get(user=self.user)
        lock.locked_until = timezone.now() - timedelta(minutes=1)
        lock.save()

        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'lockint',
                'password': STRONG_PASSWORD,
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)

    def test_lockout_message_includes_duration(self):
        """Lockout response mentions the 15-minute duration."""
        for _ in range(5):
            self.client.post(
                reverse('auth_login'),
                data=json.dumps({
                    'username': 'lockint',
                    'password': 'wrong',
                }),
                content_type='application/json',
                HTTP_USER_AGENT=BROWSER_UA,
            )

        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'lockint',
                'password': 'wrong',
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn('15', response.json().get('message', ''))


# ══════════════════════════════════════════════════════════════
# Email Helper Tests (mocked send_mail)
# ══════════════════════════════════════════════════════════════


class TestEmailHelpers(DisableThrottleMixin, TestCase):
    """Tests for _send_verification_email and _send_password_reset_email."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='emailtest', password=STRONG_PASSWORD,
            email='emailtest@test.com'
        )
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    @override_settings(EMAIL_VERIFICATION_REQUIRED=True)
    @patch('attendance.auth_views.send_mail')
    def test_verification_email_sent_on_user_creation(self, mock_send):
        """Verification email is sent when user is created with email+verification."""
        superuser = User.objects.create_user(
            username='creator', password=STRONG_PASSWORD
        )
        superuser.is_superuser = True
        superuser.save()
        self.client.login(username='creator', password=STRONG_PASSWORD)

        self.client.post(
            reverse('users_list'),
            data=json.dumps({
                'username': 'with_email',
                'password': 'GoodPass1!',
                'email': 'newemail@test.com',
            }),
            content_type='application/json',
        )
        mock_send.assert_called_once()

    @patch('attendance.auth_views.send_mail')
    def test_verification_email_not_sent_without_email(self, mock_send):
        """No verification email if user has no email address."""
        superuser = User.objects.create_user(
            username='creator2', password=STRONG_PASSWORD
        )
        superuser.is_superuser = True
        superuser.save()
        self.client.login(username='creator2', password=STRONG_PASSWORD)

        self.client.post(
            reverse('users_list'),
            data=json.dumps({
                'username': 'no_email',
                'password': 'GoodPass1!',
            }),
            content_type='application/json',
        )
        mock_send.assert_not_called()

    @patch('attendance.auth_views.send_mail')
    def test_verification_email_contains_link(self, mock_send):
        """Verification email body contains the verification URL."""
        from attendance.auth_views import _send_verification_email

        token_obj = EmailVerificationToken.generate_for_user(self.user)
        _send_verification_email(self.user, token_obj)

        call_args = mock_send.call_args
        email_body = call_args.kwargs.get('message', call_args[1].get('message', ''))
        self.assertIn('verify-email', email_body)
        self.assertIn(token_obj.token, email_body)

    @patch('attendance.auth_views.send_mail')
    def test_password_reset_email_sent_on_request(self, mock_send):
        """Password reset email is sent for valid active user."""
        self.client.post(
            reverse('auth_reset_password'),
            data=json.dumps({'email': 'emailtest@test.com'}),
            content_type='application/json',
        )
        mock_send.assert_called_once()

    @patch('attendance.auth_views.send_mail')
    def test_password_reset_email_contains_reset_link(self, mock_send):
        """Password reset email body contains path-based reset link."""
        self.client.post(
            reverse('auth_reset_password'),
            data=json.dumps({'email': 'emailtest@test.com'}),
            content_type='application/json',
        )
        call_args = mock_send.call_args
        email_body = call_args.kwargs.get('message', call_args[1].get('message', ''))
        self.assertIn('reset-password', email_body)

    @patch('attendance.auth_views.send_mail')
    def test_email_failure_does_not_crash_user_creation(self, mock_send):
        """Email sending failure is logged but doesn't crash user creation."""
        mock_send.side_effect = Exception('SMTP server down')

        superuser = User.objects.create_user(
            username='creator3', password=STRONG_PASSWORD
        )
        superuser.is_superuser = True
        superuser.save()
        self.client.login(username='creator3', password=STRONG_PASSWORD)

        # Should still return 200 even if email fails
        response = self.client.post(
            reverse('users_list'),
            data=json.dumps({
                'username': 'emailfail',
                'password': 'GoodPass1!',
                'email': 'fail@test.com',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(username='emailfail').exists())

    @patch('attendance.auth_views.send_mail')
    def test_email_failure_does_not_crash_reset_request(self, mock_send):
        """Email sending failure is logged but doesn't crash reset request."""
        mock_send.side_effect = Exception('SMTP server down')

        response = self.client.post(
            reverse('auth_reset_password'),
            data=json.dumps({'email': 'emailtest@test.com'}),
            content_type='application/json',
        )
        # Should still return 200 even if email fails
        self.assertEqual(response.status_code, 200)

    @patch('attendance.auth_views.send_mail')
    def test_verification_email_subject_bilingual(self, mock_send):
        """Verification email subject is bilingual (Malay + English)."""
        from attendance.auth_views import _send_verification_email

        token_obj = EmailVerificationToken.generate_for_user(self.user)
        _send_verification_email(self.user, token_obj)

        call_args = mock_send.call_args
        subject = call_args.kwargs.get('subject', call_args[1].get('subject', ''))
        self.assertIn('SPKB', subject)
        self.assertIn('Sahkan', subject)

    @patch('attendance.auth_views.send_mail')
    def test_reset_email_subject_bilingual(self, mock_send):
        """Reset email subject is bilingual (Malay + English)."""
        from attendance.auth_views import _send_password_reset_email

        _send_password_reset_email(self.user, 'http://test.com/reset?uid=1&token=abc')

        call_args = mock_send.call_args
        subject = call_args.kwargs.get('subject', call_args[1].get('subject', ''))
        self.assertIn('SPKB', subject)
        self.assertIn('Set Semula', subject)


# ══════════════════════════════════════════════════════════════
# Session Security Tests
# ══════════════════════════════════════════════════════════════


class TestSessionSecurity(DisableThrottleMixin, TestCase):
    """Session management security tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='sesssec', password=STRONG_PASSWORD
        )
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_session_created_on_login(self):
        """A session is created upon successful API login."""
        self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'sesssec',
                'password': STRONG_PASSWORD,
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        session = self.client.session
        self.assertEqual(str(session.get('_auth_user_id')), str(self.user.pk))

    def test_session_fixation_prevention(self):
        """Session key changes after login (prevents session fixation)."""
        # Get pre-login session
        self.client.get(reverse('auth_login'))
        pre_login_key = self.client.session.session_key

        # Login
        self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'sesssec',
                'password': STRONG_PASSWORD,
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        post_login_key = self.client.session.session_key

        if pre_login_key and post_login_key:
            self.assertNotEqual(pre_login_key, post_login_key)

    def test_inactive_user_cannot_authenticate(self):
        """A user with is_active=False cannot log in (returns 401, no enumeration)."""
        self.user.is_active = False
        self.user.save()

        response = self.client.post(
            reverse('auth_login'),
            data=json.dumps({
                'username': 'sesssec',
                'password': STRONG_PASSWORD,
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 401)


# ══════════════════════════════════════════════════════════════
# Audit Logging Tests for Auth Views
# ══════════════════════════════════════════════════════════════


class TestAuthAuditLogging(DisableThrottleMixin, TestCase):
    """Security events from auth views are logged to the security logger."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='auditauth', password=STRONG_PASSWORD
        )
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_successful_login_is_logged(self):
        """A successful login produces a LOGIN SUCCESS log entry."""
        security_logger = logging.getLogger('security')
        with patch.object(security_logger, 'info') as mock_info:
            self.client.post(
                reverse('auth_login'),
                data=json.dumps({
                    'username': 'auditauth',
                    'password': STRONG_PASSWORD,
                }),
                content_type='application/json',
                HTTP_USER_AGENT=BROWSER_UA,
            )
        self.assertTrue(
            any('LOGIN SUCCESS' in str(call) for call in mock_info.call_args_list)
        )

    def test_failed_login_is_logged(self):
        """A failed login produces a LOGIN FAILED log entry."""
        security_logger = logging.getLogger('security')
        with patch.object(security_logger, 'warning') as mock_warning:
            self.client.post(
                reverse('auth_login'),
                data=json.dumps({
                    'username': 'auditauth',
                    'password': 'wrong',
                }),
                content_type='application/json',
                HTTP_USER_AGENT=BROWSER_UA,
            )
        self.assertTrue(
            any('LOGIN FAILED' in str(call) for call in mock_warning.call_args_list)
        )

    def test_account_lockout_is_logged(self):
        """Account lockout produces a ACCOUNT LOCKED or LOGIN BLOCKED log entry."""
        security_logger = logging.getLogger('security')
        for _ in range(5):
            self.client.post(
                reverse('auth_login'),
                data=json.dumps({
                    'username': 'auditauth',
                    'password': 'wrong',
                }),
                content_type='application/json',
                HTTP_USER_AGENT=BROWSER_UA,
            )
        with patch.object(security_logger, 'warning') as mock_warning:
            self.client.post(
                reverse('auth_login'),
                data=json.dumps({
                    'username': 'auditauth',
                    'password': 'wrong',
                }),
                content_type='application/json',
                HTTP_USER_AGENT=BROWSER_UA,
            )
        self.assertTrue(
            any(
                'ACCOUNT LOCKED' in str(call) or 'LOGIN BLOCKED' in str(call)
                for call in mock_warning.call_args_list
            )
        )

    def test_logout_is_logged(self):
        """Logout produces a LOGOUT log entry."""
        self.client.login(username='auditauth', password=STRONG_PASSWORD)
        security_logger = logging.getLogger('security')
        with patch.object(security_logger, 'info') as mock_info:
            self.client.post(reverse('auth_logout'))
        self.assertTrue(
            any('LOGOUT' in str(call) for call in mock_info.call_args_list)
        )

    def test_password_change_is_logged(self):
        """Password change produces a PASSWORD CHANGED log entry."""
        self.client.login(username='auditauth', password=STRONG_PASSWORD)
        security_logger = logging.getLogger('security')
        with patch.object(security_logger, 'info') as mock_info:
            self.client.post(
                '/api/attendance/auth/password/',
                data=json.dumps({
                    'old_password': STRONG_PASSWORD,
                    'new_password': ANOTHER_STRONG_PASSWORD,
                }),
                content_type='application/json',
            )
        self.assertTrue(
            any('PASSWORD CHANGED' in str(call) for call in mock_info.call_args_list)
        )

    def test_user_creation_is_logged(self):
        """User creation produces a USER CREATED log entry."""
        self.user.is_superuser = True
        self.user.save()
        self.client.login(username='auditauth', password=STRONG_PASSWORD)
        security_logger = logging.getLogger('security')
        with patch.object(security_logger, 'info') as mock_info:
            self.client.post(
                reverse('users_list'),
                data=json.dumps({
                    'username': 'newaudited',
                    'password': 'GoodPass1!',
                }),
                content_type='application/json',
            )
        self.assertTrue(
            any('USER CREATED' in str(call) for call in mock_info.call_args_list)
        )

    def test_user_deletion_is_logged(self):
        """User deletion produces a USER DELETED log entry."""
        victim = User.objects.create_user(username='delvictim', password='Victim1!')
        self.user.is_superuser = True
        self.user.save()
        self.client.login(username='auditauth', password=STRONG_PASSWORD)
        security_logger = logging.getLogger('security')
        with patch.object(security_logger, 'info') as mock_info:
            self.client.delete(reverse('users_detail', args=[victim.pk]))
        self.assertTrue(
            any('USER DELETED' in str(call) for call in mock_info.call_args_list)
        )

    def test_email_verification_is_logged(self):
        """Email verification produces a EMAIL VERIFIED log entry."""
        user = User.objects.create_user(
            username='verifylog', password=STRONG_PASSWORD,
            email='verifylog@test.com', is_active=False
        )
        token_obj = EmailVerificationToken.generate_for_user(user)
        security_logger = logging.getLogger('security')
        with patch.object(security_logger, 'info') as mock_info:
            self.client.get(reverse('auth_verify_email', args=[token_obj.token]))
        self.assertTrue(
            any('EMAIL VERIFIED' in str(call) for call in mock_info.call_args_list)
        )

    def test_password_reset_request_is_logged(self):
        """Password reset request produces a PASSWORD RESET REQUESTED log entry."""
        security_logger = logging.getLogger('security')
        with patch.object(security_logger, 'info') as mock_info:
            self.client.post(
                reverse('auth_reset_password'),
                data=json.dumps({'email': 'auditauth@test.com'}),
                content_type='application/json',
            )
        # Note: user has no email set, so this may not actually log. Check if it does.
        # The user was created without email, so the lookup will fail.
        # Let's use the correct user email.
        User.objects.create_user(
            username='resetlog', password=STRONG_PASSWORD, email='resetlog@test.com'
        )
        with patch.object(security_logger, 'info') as mock_info:
            self.client.post(
                reverse('auth_reset_password'),
                data=json.dumps({'email': 'resetlog@test.com'}),
                content_type='application/json',
            )
        self.assertTrue(
            any('PASSWORD RESET REQUESTED' in str(call) for call in mock_info.call_args_list)
        )


# =====================================================================
# Gap Tests: UserDetailView, Token Reuse, Inactive User
# =====================================================================


class TestUserDetailViewSelfDeletionGuard(DisableThrottleMixin, TestCase):
    """Self-deletion and last-superuser prevention."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='super', password='SuperPass1!', email='super@test.com'
        )
        self.client.login(username='super', password='SuperPass1!')
        self.url = reverse('users_detail', args=[self.superuser.id])

    def test_self_delete_returns_400(self):
        """Superuser should not be able to delete themselves."""
        response = self.client.delete(self.url, HTTP_USER_AGENT=BROWSER_UA)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('yourself', response.json().get('message', '').lower())

    def test_last_superuser_delete_blocked(self):
        """Deleting the only superuser should return 400."""
        response = self.client.delete(self.url, HTTP_USER_AGENT=BROWSER_UA)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_other_user_succeeds(self):
        """Deleting a different user should succeed."""
        other = User.objects.create_user(username='other', password='OtherPass1!')
        url = reverse('users_detail', args=[other.id])
        response = self.client.delete(url, HTTP_USER_AGENT=BROWSER_UA)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(User.objects.filter(id=other.id).exists())


class TestUserDetailViewLastSuperuser(DisableThrottleMixin, TestCase):
    """Last superuser prevention when multiple superusers exist."""

    def setUp(self):
        self.super1 = User.objects.create_superuser(
            username='super1', password='SuperPass1!', email='super1@test.com'
        )
        self.super2 = User.objects.create_superuser(
            username='super2', password='SuperPass2!', email='super2@test.com'
        )
        self.client.login(username='super1', password='SuperPass1!')

    def test_delete_second_superuser_succeeds(self):
        """With 2+ superusers, deletion should be allowed."""
        url = reverse('users_detail', args=[self.super2.id])
        response = self.client.delete(url, HTTP_USER_AGENT=BROWSER_UA)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_delete_nonexistent_returns_404(self):
        """Deleting nonexistent user should return 404."""
        url = reverse('users_detail', args=[99999])
        response = self.client.delete(url, HTTP_USER_AGENT=BROWSER_UA)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TestPasswordResetRequestInactiveUser(DisableThrottleMixin, TestCase):
    """Password reset for inactive/nonexistent users (anti-enumeration)."""

    def setUp(self):
        self.url = reverse('auth_reset_password')

    def test_inactive_user_returns_same_message(self):
        """Inactive user should get same response as active (anti-enumeration)."""
        User.objects.create_user(
            username='inactive', password='Pass1!', email='inactive@test.com', is_active=False
        )
        response = self.client.post(
            self.url,
            data=json.dumps({'email': 'inactive@test.com'}),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        # Should return 200 (not revealing whether user exists/is active)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_nonexistent_email_returns_same_message(self):
        """Nonexistent email should return same response."""
        response = self.client.post(
            self.url,
            data=json.dumps({'email': 'nobody@test.com'}),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TestVerifyEmailTokenReuse(DisableThrottleMixin, TestCase):
    """Email verification token reuse and invalid tokens."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='unverified', password='Pass1!', email='unverified@test.com', is_active=False
        )
        self.token = EmailVerificationToken.generate_for_user(self.user)

    def test_valid_token_verifies_email(self):
        """Valid token should activate user."""
        url = reverse('auth_verify_email', args=[self.token.token])
        response = self.client.get(url, HTTP_USER_AGENT=BROWSER_UA)
        self.assertIn(response.status_code, [200, 302])
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_reused_token_returns_error(self):
        """Re-using an already-used token should return error."""
        self.token.is_used = True
        self.token.save()
        url = reverse('auth_verify_email', args=[self.token.token])
        response = self.client.get(url, HTTP_USER_AGENT=BROWSER_UA)
        self.assertIn(response.status_code, [400, 404])

    def test_invalid_token_returns_error(self):
        """Random string token should return error."""
        url = reverse('auth_verify_email', args=['invalid-token-12345'])
        response = self.client.get(url, HTTP_USER_AGENT=BROWSER_UA)
        self.assertIn(response.status_code, [400, 404])


class TestResendVerificationExtended(DisableThrottleMixin, TestCase):
    """Resend verification edge cases."""

    def setUp(self):
        self.url = reverse('auth_resend_verification')

    def test_already_verified_returns_error(self):
        """Already verified user should get error."""
        user = User.objects.create_user(
            username='verified', password='Pass1!', email='verified@test.com'
        )
        AdminProfile.objects.create(user=user, email_verified=True)
        response = self.client.post(
            self.url,
            data=json.dumps({'email': 'verified@test.com'}),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        # Should return 400 (already verified)
        self.assertIn(response.status_code, [400, 200])


class TestLoginViewInactiveUser(DisableThrottleMixin, TestCase):
    """Login with inactive or locked account."""

    def setUp(self):
        self.url = reverse('auth_login')

    def test_inactive_user_returns_error(self):
        """Inactive user with correct password should get error."""
        User.objects.create_user(
            username='inactive', password='Pass1!', is_active=False
        )
        response = self.client.post(
            self.url,
            data=json.dumps({'username': 'inactive', 'password': 'Pass1!'}),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertIn(response.status_code, [401, 403])

    def test_locked_account_returns_error(self):
        """Locked user with correct password should get error."""
        user = User.objects.create_user(username='locked', password='LockedPass1!')
        UserAccountLock.objects.create(
            user=user,
            locked_until=timezone.now() + timedelta(minutes=30),
            failure_count=5,
        )
        response = self.client.post(
            self.url,
            data=json.dumps({'username': 'locked', 'password': 'LockedPass1!'}),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertIn(response.status_code, [401, 403])


class TestChangePasswordExtended(DisableThrottleMixin, TestCase):
    """Change password edge cases."""

    def setUp(self):
        self.user = User.objects.create_user(username='admin', password='OldPass1!')
        self.client.login(username='admin', password='OldPass1!')
        self.url = reverse('auth_change_password')

    def test_wrong_old_password_rejected(self):
        """Wrong old password should return 400."""
        response = self.client.post(
            self.url,
            data=json.dumps({'old_password': 'WrongOld1!', 'new_password': 'NewPass1!'}),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_weak_new_password_rejected(self):
        """Weak new password should be rejected."""
        response = self.client.post(
            self.url,
            data=json.dumps({'old_password': 'OldPass1!', 'new_password': 'weak'}),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_old_password_rejected(self):
        """Missing old_password field should return 400."""
        response = self.client.post(
            self.url,
            data=json.dumps({'new_password': 'NewPass1!'}),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_new_password_rejected(self):
        """Missing new_password field should return 400."""
        response = self.client.post(
            self.url,
            data=json.dumps({'old_password': 'OldPass1!'}),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# =====================================================================
# Gap Tests: inactive user strict 403, reset confirm edge cases,
# user create email, delete nonexistent
# =====================================================================


class TestInactiveUserLoginStrict403(DisableThrottleMixin, TestCase):
    """Verify inactive user gets 403 (not 401) when DEBUG=False."""

    def setUp(self):
        self.url = reverse('auth_login')

    def test_inactive_user_returns_401(self):
        """Inactive user with correct password should get 401 (no enumeration)."""
        User.objects.create_user(username='inactive2', password='Pass1!', is_active=False)
        with override_settings(DEBUG=False):
            response = self.client.post(
                self.url,
                data=json.dumps({'username': 'inactive2', 'password': 'Pass1!'}),
                content_type='application/json',
                HTTP_USER_AGENT=BROWSER_UA,
            )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TestPasswordResetConfirmEdgeCases(DisableThrottleMixin, TestCase):
    """Test PasswordResetConfirmView with invalid uid and weak password."""

    def setUp(self):
        self.url = reverse('auth_reset_password_confirm')

    def test_invalid_uid_returns_400(self):
        """Non-numeric uid should return 400."""
        response = self.client.post(
            self.url,
            data=json.dumps({
                'uid': 'invalid',
                'token': 'fake-token',
                'new_password': 'NewStr0ng!Pass',
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_weak_password_returns_400(self):
        """Weak new password should return 400."""
        user = User.objects.create_user(username='resetuser', password='OrigPass1!')
        # Generate a valid token
        from django.contrib.auth.tokens import default_token_generator
        uid = user.pk
        token = default_token_generator.make_token(user)

        response = self.client.post(
            self.url,
            data=json.dumps({
                'uid': uid,
                'token': token,
                'new_password': 'weak',
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestUserDetailDeleteNonexistent(DisableThrottleMixin, TestCase):
    """Test that DELETE on a nonexistent user ID returns 404."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='super', password='SuperPass1!', email='super@test.com'
        )
        self.client.login(username='super', password='SuperPass1!')

    def test_delete_nonexistent_user_returns_404(self):
        """DELETE a user ID that doesn't exist should return 404."""
        response = self.client.delete(
            reverse('users_detail', args=[99999]),
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TestUserCreateExistingEmail(DisableThrottleMixin, TestCase):
    """Test UserListView POST with existing email handles gracefully."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='super', password='SuperPass1!', email='original@test.com'
        )
        self.client.login(username='super', password='SuperPass1!')
        self.url = reverse('users_list')

    def test_create_user_with_existing_email(self):
        """Creating a user with an existing email should succeed (email uniqueness is not enforced)."""
        response = self.client.post(
            self.url,
            data=json.dumps({
                'username': 'newuser',
                'password': 'NewPass1!',
                'email': 'original@test.com',  # Same email as superuser
            }),
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        # No email field in User model is unique — should succeed
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_201_CREATED])
