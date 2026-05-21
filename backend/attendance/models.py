from django.db import models
from django.utils import timezone
import uuid

class Program(models.Model):
    name = models.CharField(max_length=255, unique=True)
    cert_delay = models.IntegerField(
        default=120000,
        help_text="Certificate delay in milliseconds. 120000 = 2 minutes."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class AttendanceRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ref = models.CharField(max_length=100, blank=True, null=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name='attendances')
    fullname = models.CharField(max_length=255)
    ic_number = models.CharField(max_length=50)
    phone = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    organization = models.CharField(max_length=255, blank=True, null=True)
    timestamp = models.DateTimeField(default=timezone.now)
    cert_delay = models.IntegerField(default=120000, help_text="Delay in milliseconds")
    certificate_generated = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.fullname} - {self.program.name}"
