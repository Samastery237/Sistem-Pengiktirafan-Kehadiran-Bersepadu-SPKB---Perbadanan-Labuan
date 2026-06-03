from django.db import models
from django.utils import timezone
import uuid
import re
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
    ic_number = models.CharField(max_length=50)
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

    def __str__(self):
        return f"{self.user.username} - {self.department.name if self.department else 'Super Admin'}"
