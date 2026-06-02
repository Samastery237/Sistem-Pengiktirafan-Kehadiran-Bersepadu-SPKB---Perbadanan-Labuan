# pyrefly: ignore [missing-import]
from django.contrib import admin
from .models import Department, Folder, AttendanceRecord


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')


@admin.register(Folder)
class FolderAdmin(admin.ModelAdmin):
    list_display = ('name', 'department', 'cert_delay', 'created_at')
    search_fields = ('name', 'department__name')


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('fullname', 'ic_number', 'folder', 'timestamp', 'certificate_generated')
    list_filter = ('folder__department', 'folder', 'certificate_generated', 'timestamp')
    search_fields = ('fullname', 'ic_number', 'email', 'folder__name')
    readonly_fields = ('id', 'timestamp')
