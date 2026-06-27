from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db.models import F
from django.middleware.csrf import get_token, rotate_token
from django.utils import timezone
from rest_framework import status, views
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

import logging
from .abuse import GlobalIPThrottle
from .middleware import get_client_ip
from .models import AdminProfile, Department, EmailVerificationToken, FailedLoginAttempt, UserAccountLock

logger = logging.getLogger('security')


# ──────────────────────────────────────────────
# Throttle classes
# ──────────────────────────────────────────────

class LoginThrottle(AnonRateThrottle):
    scope = 'login'
    
    def allow_request(self, request, view):
        from django.conf import settings
        if settings.DEBUG:
            return True
        return super().allow_request(request, view)

class UserCreationThrottle(UserRateThrottle):
    scope = 'create_user'

class PasswordResetThrottle(AnonRateThrottle):
    scope = 'password_reset'


# ──────────────────────────────────────────────
# Account lockout helpers
# ──────────────────────────────────────────────

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15
ATTEMPT_WINDOW_MINUTES = 30


def _get_lockout(username):
    """Get or create the UserAccountLock for a given username."""
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return None
    lock, _ = UserAccountLock.objects.get_or_create(user=user)
    return lock


def _is_locked(username):
    """Check if the account for the given username is currently locked."""
    lock = _get_lockout(username)
    if lock is None:
        return False
    if lock.is_locked:
        return True
    # Auto-unlock if the lockout period has expired
    if lock.locked_until and timezone.now() >= lock.locked_until:
        lock.locked_until = None
        lock.failure_count = 0
        lock.save(update_fields=['locked_until', 'failure_count'])
    return False


def _record_failed_attempt(username, ip):
    """Record a failed login attempt and lock the account if threshold is exceeded."""
    # Store the attempt for auditing
    FailedLoginAttempt.objects.create(username=username, ip_address=ip)

    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return  # Don't create lock records for non-existent users

    lock, _ = UserAccountLock.objects.get_or_create(user=user)

    window_start = timezone.now() - timedelta(minutes=ATTEMPT_WINDOW_MINUTES)
    recent_attempts = FailedLoginAttempt.objects.filter(
        username=username,
        attempted_at__gte=window_start
    ).count()

    UserAccountLock.objects.filter(user=user).update(
        failure_count=F('failure_count') + 1,
        last_failure_at=timezone.now(),
        locked_until=timezone.now() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
        if recent_attempts >= MAX_FAILED_ATTEMPTS
        else None,
    )

    if recent_attempts >= MAX_FAILED_ATTEMPTS:
        logger.warning(
            f"ACCOUNT LOCKED: User={username}, IP={ip}, "
            f"Failures={recent_attempts}, LockedUntil={timezone.now() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)}"
        )


def _reset_failed_attempts(username):
    """Reset failed login attempts on successful login."""
    FailedLoginAttempt.objects.filter(username=username).delete()
    try:
        user = User.objects.get(username=username)
        UserAccountLock.objects.filter(user=user).update(
            failure_count=0, locked_until=None, last_failure_at=None
        )
    except User.DoesNotExist:
        pass


def _cleanup_old_attempts():
    """Remove failed login attempts older than 24 hours."""
    cutoff = timezone.now() - timedelta(hours=24)
    FailedLoginAttempt.objects.filter(attempted_at__lt=cutoff).delete()


# ──────────────────────────────────────────────
# Email helpers
# ──────────────────────────────────────────────

def _send_verification_email(user, token_obj):
    """Send email verification link to the user."""
    verification_url = f"{getattr(settings, 'SITE_URL', 'http://localhost:8000')}/api/attendance/auth/verify-email/{token_obj.token}/"
    subject = 'SPKB — Sahkan E-mel Anda / Verify Your Email'
    message = (
        f"Selamat sejahtera {user.username},\n\n"
        f"Sila klik pautan berikut untuk mengesahkan alamat e-mel anda:\n"
        f"{verification_url}\n\n"
        f"Pautan ini akan luput dalam 24 jam.\n\n"
        f"Jika anda tidak meminta ini, abaikan e-mel ini.\n\n"
        f"— Sistem Pengiktirafan Kehadiran Bersepadu (SPKB)\n"
        f"  Perbadanan Labuan"
    )
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=None,  # Uses DEFAULT_FROM_EMAIL
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info(f"VERIFICATION EMAIL SENT: User={user.username}, Email={user.email}")
    except Exception as e:
        logger.error(f"VERIFICATION EMAIL FAILED: User={user.username}, Error={e}")


def _send_password_reset_email(user, reset_url):
    """Send password reset link to the user."""
    subject = 'SPKB — Set Semula Kata Laluan / Reset Password'
    message = (
        f"Selamat sejahtera {user.username},\n\n"
        f"Klik pautan berikut untuk menetapkan semula kata laluan anda:\n"
        f"{reset_url}\n\n"
        f"Pautan ini akan luput dalam 1 jam.\n\n"
        f"Jika anda tidak meminta ini, abaikan e-mel ini dan kata laluan anda "
        f"tidak akan berubah.\n\n"
        f"— Sistem Pengiktirafan Kehadiran Bersepadu (SPKB)\n"
        f"  Perbadanan Labuan"
    )
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=None,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info(f"PASSWORD RESET EMAIL SENT: User={user.username}, Email={user.email}")
    except Exception as e:
        logger.error(f"PASSWORD RESET EMAIL FAILED: User={user.username}, Error={e}")


# ──────────────────────────────────────────────
# Views
# ──────────────────────────────────────────────

class LoginView(views.APIView):
    """GET: Return a CSRF token. POST: Authenticate user and create session."""
    authentication_classes = []  # Allow unauthenticated access
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle, GlobalIPThrottle]

    def get(self, request):
        """Return a fresh CSRF token for the login form."""
        csrf_token = get_token(request)
        return Response({'status': 'success', 'csrfToken': csrf_token})

    def post(self, request):
        username = (request.data.get('username') or '').strip()
        password = request.data.get('password', '')

        if not username or not password:
            return Response(
                {'status': 'error', 'message': 'ID pengguna dan kata laluan diperlukan.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        ip = get_client_ip(request)

        # Check account lockout before attempting authentication
        if _is_locked(username):
            logger.warning(f"LOGIN BLOCKED (Account Locked): User={username}, IP={ip}")
            return Response(
                {
                    'status': 'error',
                    'message': f'Akaun dikunci akibat terlalu banyak cubaan. '
                               f'Sila cuba lagi dalam {LOCKOUT_DURATION_MINUTES} minit.',
                    'locked': True,
                },
                status=status.HTTP_403_FORBIDDEN
            )

        user = authenticate(request, username=username, password=password)

        if user is not None:
            # Prevent session fixation: flush any existing session before login
            request.session.flush()
            login(request, user)

            # Reset failed login attempts on success
            _reset_failed_attempts(username)

            logger.info(f"LOGIN SUCCESS: User={username}, IP={ip}")
            # Rotate CSRF token on login (prevents session fixation)
            rotate_token(request)
            csrf_token = get_token(request)

            is_super = user.is_superuser
            department_id = None
            if hasattr(user, 'admin_profile') and user.admin_profile.department:
                department_id = user.admin_profile.department.id

            response = Response({
                'status': 'success',
                'csrfToken': csrf_token,
                'is_super': is_super,
                'department_id': department_id,
            })
            # Explicitly set the new CSRF cookie so the browser picks it up
            response.set_cookie(
                'csrftoken',
                csrf_token,
                max_age=31449600,
                path='/',
                secure=not settings.DEBUG,
                httponly=False,
                samesite='Lax',
            )
            return response
        else:
            # Record failed attempt and potentially lock account
            _record_failed_attempt(username, ip)
            logger.warning(f"LOGIN FAILED: AttemptedUser={username}, IP={ip}")

            # Periodic cleanup of old attempt records
            _cleanup_old_attempts()

            return Response(
                {'status': 'error', 'message': 'Kata laluan atau ID pengguna salah.'},
                status=status.HTTP_401_UNAUTHORIZED
            )


class LogoutView(views.APIView):
    """POST: End user session."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        username = request.user.username
        ip = get_client_ip(request)
        logout(request)
        logger.info(f"LOGOUT: User={username}, IP={ip}")
        return Response({'status': 'success'})


class CheckAuthView(views.APIView):
    """GET: Verify current session is active."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        is_super = user.is_superuser
        department_id = None
        if hasattr(user, 'admin_profile') and user.admin_profile.department:
            department_id = user.admin_profile.department.id

        return Response({
            'status': 'success',
            'user': user.username,
            'is_super': is_super,
            'department_id': department_id,
        })


class ChangePasswordView(views.APIView):
    """POST: Change the current user's password. Requires old_password verification."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [PasswordResetThrottle]

    def post(self, request):
        old_password = request.data.get('old_password', '')
        new_password = request.data.get('new_password', '')

        if not old_password:
            return Response(
                {'status': 'error', 'message': 'Kata laluan lama diperlukan.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not new_password:
            return Response(
                {'status': 'error', 'message': 'Kata laluan baru diperlukan.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = request.user
        ip = get_client_ip(request)

        if not user.check_password(old_password):
            logger.warning(f"PASSWORD CHANGE FAILED (Wrong old password): User={user.username}, IP={ip}")
            return Response(
                {'status': 'error', 'message': 'Kata laluan lama tidak betul.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            validate_password(new_password, user=user)
        except ValidationError as e:
            logger.warning(f"PASSWORD CHANGE FAILED (Validation error): User={user.username}, IP={ip}")
            return Response(
                {'status': 'error', 'message': ' '.join(e.messages)},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save()
        logger.info(f"PASSWORD CHANGED SUCCESSFULLY: User={user.username}, IP={ip}")
        update_session_auth_hash(request, user)
        # Rotate CSRF token after password change to prevent token mismatch
        rotate_token(request)
        new_csrf = get_token(request)
        response = Response({'status': 'success'})
        response.set_cookie(
            'csrftoken',
            new_csrf,
            max_age=31449600,
            path='/',
            secure=not settings.DEBUG,
            httponly=False,
            samesite='Lax',
        )
        return response


class UserListView(views.APIView):
    """
    GET: List all users (admin accounts) and their assigned departments.
    POST: Create a new admin account assigned to a department.
    Super Admins only.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserCreationThrottle]

    def get(self, request):
        if not request.user.is_superuser:
            return Response({'status': 'error', 'message': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        users = User.objects.all().select_related('admin_profile__department')
        data = []
        for u in users:
            dept_name = None
            dept_id = None
            if hasattr(u, 'admin_profile') and u.admin_profile.department:
                dept_name = u.admin_profile.department.name
                dept_id = u.admin_profile.department.id
            data.append({
                'id': u.id,
                'username': u.username,
                'is_super': u.is_superuser,
                'department_id': dept_id,
                'department_name': dept_name,
                'email_verified': hasattr(u, 'admin_profile') and u.admin_profile.email_verified,
            })
        return Response({'status': 'success', 'data': data})

    def post(self, request):
        if not request.user.is_superuser:
            return Response({'status': 'error', 'message': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        username = (request.data.get('username') or '').strip()
        password = request.data.get('password', '')
        email = (request.data.get('email') or '').strip()
        department_id = request.data.get('department_id')
        is_super = str(request.data.get('is_super')).lower() == 'true'

        if not username or not password:
            return Response(
                {'status': 'error', 'message': 'Username and password are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if User.objects.filter(username=username).exists():
            return Response(
                {'status': 'error', 'message': 'Username already exists.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            validate_password(password)
        except ValidationError as e:
            return Response(
                {'status': 'error', 'message': ' '.join(e.messages)},
                status=status.HTTP_400_BAD_REQUEST
            )

        ip = get_client_ip(request)

        # Create user as inactive until email is verified
        user = User.objects.create_user(username=username, password=password, email=email)
        user.is_staff = True
        user.is_superuser = is_super
        if settings.EMAIL_VERIFICATION_REQUIRED:
            user.is_active = False
        user.save()

        # Create admin profile
        dept = None
        if department_id and not is_super:
            try:
                dept = Department.objects.get(id=department_id)
            except Department.DoesNotExist:
                pass
        AdminProfile.objects.create(user=user, department=dept)

        # Send email verification if required
        if settings.EMAIL_VERIFICATION_REQUIRED and email:
            token_obj = EmailVerificationToken.generate_for_user(user)
            _send_verification_email(user, token_obj)

        logger.info(
            f"USER CREATED: Creator={request.user.username}, "
            f"NewUser={username}, IP={ip}, "
            f"Department={dept.name if dept else 'None'}, "
            f"IsSuper={is_super}"
        )

        return Response({'status': 'success', 'message': 'User created'})


class UserDetailView(views.APIView):
    """PATCH: Reset password for an admin user. DELETE: Delete an admin user. Super Admins only."""
    permission_classes = [IsAuthenticated]

    def patch(self, request, user_id):
        if not request.user.is_superuser:
            return Response({'status': 'error', 'message': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        new_password = request.data.get('password')
        if not new_password:
            return Response(
                {'status': 'error', 'message': 'Kata laluan diperlukan.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from django.contrib.auth.password_validation import validate_password
            validate_password(new_password)
        except Exception as e:
            return Response(
                {'status': 'error', 'message': ' '.join(e.messages if hasattr(e, 'messages') else [str(e)])},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {'status': 'error', 'message': 'User not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        user.set_password(new_password)
        user.save(update_fields=['password'])

        ip = get_client_ip(request)
        logger.info(
            f"PASSWORD RESET: Admin={request.user.username}, "
            f"TargetUser={user.username}, IP={ip}"
        )
        return Response({'status': 'success', 'message': 'Kata laluan berjaya ditetapkan semula.'})

    def delete(self, request, user_id):
        if not request.user.is_superuser:
            return Response({'status': 'error', 'message': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        ip = get_client_ip(request)

        try:
            user_to_delete = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {'status': 'error', 'message': 'User not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Prevent self-deletion
        if user_to_delete.id == request.user.id:
            return Response(
                {'status': 'error', 'message': 'Cannot delete yourself.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Prevent deletion of the last superuser (lockout prevention)
        if user_to_delete.is_superuser:
            superuser_count = User.objects.filter(is_superuser=True).count()
            if superuser_count <= 1:
                return Response(
                    {'status': 'error', 'message': 'Cannot delete the last superuser account.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        deleted_username = user_to_delete.username
        user_to_delete.delete()
        logger.info(
            f"USER DELETED: Deleter={request.user.username}, "
            f"DeletedUser={deleted_username}, IP={ip}"
        )
        return Response({'status': 'success'})


# ──────────────────────────────────────────────
# Email Verification
# ──────────────────────────────────────────────

class VerifyEmailView(views.APIView):
    """GET: Verify email using token sent via email."""
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [GlobalIPThrottle]

    def get(self, request, token):
        try:
            token_obj = EmailVerificationToken.objects.select_related('user').get(token=token)
        except EmailVerificationToken.DoesNotExist:
            return Response(
                {'status': 'error', 'message': 'Pautan pengesahan tidak sah atau telah luput.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not token_obj.is_valid:
            return Response(
                {'status': 'error', 'message': 'Pautan pengesahan telah luput atau telah digunakan.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = token_obj.user
        user.is_active = True
        user.save(update_fields=['is_active'])

        token_obj.is_used = True
        token_obj.save(update_fields=['is_used'])

        # Update admin profile
        if hasattr(user, 'admin_profile'):
            user.admin_profile.email_verified = True
            user.admin_profile.verified_at = timezone.now()
            user.admin_profile.save(update_fields=['email_verified', 'verified_at'])

        logger.info(f"EMAIL VERIFIED: User={user.username}")
        return Response({
            'status': 'success',
            'message': 'E-mel berjaya disahkan. Anda boleh log masuk sekarang.'
        })


class ResendVerificationView(views.APIView):
    """POST: Resend verification email."""
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle]

    def post(self, request):
        username = (request.data.get('username') or '').strip()
        if not username:
            return Response(
                {'status': 'error', 'message': 'Username diperlukan.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return Response({'status': 'success', 'message': 'Jika akaun wujud, e-mel pengesahan akan dihantar.'})

        if user.is_active or not user.email:
            return Response({'status': 'success', 'message': 'Jika akaun wujud, e-mel pengesahan akan dihantar.'})

        token_obj = EmailVerificationToken.generate_for_user(user)
        _send_verification_email(user, token_obj)

        logger.info(f"VERIFICATION EMAIL RESENT: User={username}")
        return Response({'status': 'success', 'message': 'Jika akaun wujud, e-mel pengesahan akan dihantar.'})


# ──────────────────────────────────────────────
# Password Reset
# ──────────────────────────────────────────────

class _PasswordResetTokenGenerator(PasswordResetTokenGenerator):
    """Custom token generator that includes user's password hash for invalidation on password change."""
    def _make_hash_value(self, user, timestamp):
        return (
            str(user.pk) + str(timestamp) +
            str(user.password) +
            str(user.last_login or '')
        )

password_reset_token_generator = _PasswordResetTokenGenerator()


class PasswordResetRequestView(views.APIView):
    """POST: Request a password reset email."""
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle]

    def post(self, request):
        email = (request.data.get('email') or '').strip()
        if not email:
            return Response(
                {'status': 'error', 'message': 'Alamat e-mel diperlukan.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Don't reveal whether the email exists
            return Response({
                'status': 'success',
                'message': 'Jika e-mel wujud dalam sistem, pautan set semula akan dihantar.'
            })

        if not user.is_active:
            return Response({
                'status': 'success',
                'message': 'Jika e-mel wujud dalam sistem, pautan set semula akan dihantar.'
            })

        # Generate a secure token
        token = password_reset_token_generator.make_token(user)
        uid = user.pk
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        uidb64 = urlsafe_base64_encode(force_bytes(uid))
        reset_url = f"{getattr(settings, 'SITE_URL', 'http://localhost:8000')}/reset-password/{uidb64}/{token}/"

        _send_password_reset_email(user, reset_url)
        logger.info(f"PASSWORD RESET REQUESTED: User={user.username}, Email={email}")

        return Response({
            'status': 'success',
            'message': 'Jika e-mel wujud dalam sistem, pautan set semula akan dihantar.'
        })


class PasswordResetConfirmView(views.APIView):
    """POST: Confirm password reset with token and set new password."""
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [GlobalIPThrottle]

    def post(self, request):
        uid = request.data.get('uid')
        token = request.data.get('token')
        new_password = request.data.get('new_password')

        if not uid or not token or not new_password:
            return Response(
                {'status': 'error', 'message': 'Token, ID pengguna, dan kata laluan baru diperlukan.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError, TypeError):
            return Response(
                {'status': 'error', 'message': 'Pautan set semula tidak sah.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not password_reset_token_generator.check_token(user, token):
            return Response(
                {'status': 'error', 'message': 'Pautan set semula tidak sah atau telah luput.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            validate_password(new_password, user=user)
        except ValidationError as e:
            return Response(
                {'status': 'error', 'message': ' '.join(e.messages)},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save()

        from django.contrib.sessions.models import Session
        Session.objects.filter(
            expire_date__gte=timezone.now(),
            session_data__contains=str(user.pk)
        ).delete()

        logger.info(f"PASSWORD RESET COMPLETED: User={user.username}")
        return Response({
            'status': 'success',
            'message': 'Kata laluan berjaya ditetapkan semula. Sila log masuk dengan kata laluan baru.'
        })
