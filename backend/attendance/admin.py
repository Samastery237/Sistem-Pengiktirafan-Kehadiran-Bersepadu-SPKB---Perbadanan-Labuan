# pyrefly: ignore [missing-import]
from django.contrib import admin
from .models import Program, AttendanceRecord


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ('name', 'cert_delay', 'created_at')
    search_fields = ('name',)


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('fullname', 'ic_number', 'program', 'organization', 'timestamp', 'certificate_generated')
    list_filter = ('program', 'organization', 'certificate_generated', 'timestamp')
    search_fields = ('fullname', 'ic_number', 'email')
    readonly_fields = ('id', 'timestamp')
