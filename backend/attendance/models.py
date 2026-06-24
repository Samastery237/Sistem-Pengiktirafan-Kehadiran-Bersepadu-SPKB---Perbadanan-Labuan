from datetime import timedelta
from django.db import models
from django.utils import timezone
import uuid
import re
import secrets
from django.contrib.auth.models import User


class Department(models.Model):
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class Folder(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='folders', null=True)
    name = models.CharField(max_length=255)
    cert_delay = models.IntegerField(
        default=0,
        help_text="Certificate delay in milliseconds. 0 = no delay."
    )
    cert_template = models.TextField(blank=True, null=True, help_text="Base64 encoded certificate background image")
    name_x = models.FloatField(default=50)
    name_y = models.FloatField(default=45)
    name_size = models.FloatField(default=48)
    show_ic = models.BooleanField(default=True)
    ic_x = models.FloatField(default=50)
    ic_y = models.FloatField(default=53)
    ic_size = models.FloatField(default=24)
    text_color = models.CharField(max_length=20, default="#000000")
    font_family = models.CharField(max_length=100, default="Arial, sans-serif")
    event_name = models.CharField(max_length=255, blank=True, null=True)
    event_date = models.CharField(max_length=255, blank=True, null=True)
    organizer = models.CharField(max_length=255, default="Perbadanan Labuan")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('department', 'name')
        
    def __str__(self):
        return f"{self.department.name if self.department else 'No Dept'} - {self.name}"

class AttendanceRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ref = models.CharField(max_length=100, blank=True, null=True)
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, related_name='attendances', null=True)
    fullname = models.CharField(max_length=255)
    ic_number = models.CharField(max_length=50, blank=True)
    clean_ic_number = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    organization = models.CharField(max_length=255, blank=True, null=True) # Participant's organization/department
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    cert_delay = models.IntegerField(default=0, help_text="Delay in milliseconds")
    certificate_generated = models.BooleanField(default=False)
    
    def save(self, *args, **kwargs):
        if self.ic_number:
            self.clean_ic_number = re.sub(r'\D', '', self.ic_number)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.fullname} - {self.folder.name if self.folder else 'No Folder'}"

class AdminProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    email_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.department.name if self.department else 'Super Admin'}"


class FailedLoginAttempt(models.Model):
    """Tracks failed login attempts for account lockout."""
    username = models.CharField(max_length=150, db_index=True)
    ip_address = models.GenericIPAddressField(db_index=True)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-attempted_at']
        verbose_name = 'Failed Login Attempt'
        verbose_name_plural = 'Failed Login Attempts'

    def __str__(self):
        return f"{self.username} from {self.ip_address} at {self.attempted_at}"


class UserAccountLock(models.Model):
    """Tracks account lockout state per user."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='account_lock')
    locked_until = models.DateTimeField(null=True, blank=True)
    failure_count = models.IntegerField(default=0)
    last_failure_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'User Account Lock'
        verbose_name_plural = 'User Account Locks'

    def __str__(self):
        return f"{self.user.username} locked until {self.locked_until}"

    @property
    def is_locked(self):
        if self.locked_until is None:
            return False
        return timezone.now() < self.locked_until


class AbuseRequestLog(models.Model):
    """Tracks IP-level request counts for abuse detection and rate limiting."""
    ip_address = models.GenericIPAddressField(db_index=True)
    window_start = models.DateTimeField(default=timezone.now)
    request_count = models.IntegerField(default=1)
    is_blocked = models.BooleanField(default=False)
    blocked_until = models.DateTimeField(null=True, blank=True)
    last_request_path = models.CharField(max_length=500, blank=True)
    user_agent = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-window_start']
        verbose_name = 'Abuse Request Log'
        verbose_name_plural = 'Abuse Request Logs'

    def __str__(self):
        return f"{self.ip_address} ({self.request_count} reqs, blocked={self.is_blocked})"


class EmailVerificationToken(models.Model):
    """Token for verifying new user email addresses."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_verification_tokens')
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Verification for {self.user.username} (used={self.is_used})"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.is_used and not self.is_expired

    @classmethod
    def generate_for_user(cls, user, expiry_hours=24):
        """Generate a new verification token for a user. Invalidates previous tokens."""
        # Invalidate any existing tokens
        cls.objects.filter(user=user).update(is_used=True)
        token = secrets.token_hex(32)
        expires_at = timezone.now() + timedelta(hours=expiry_hours)
        return cls.objects.create(user=user, token=token, expires_at=expires_at)
