from rest_framework import serializers
from .models import Department, Folder, AttendanceRecord


class AttendanceRecordSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(write_only=True, allow_blank=True)
    folder_name = serializers.CharField(write_only=True, allow_blank=True)

    class Meta:
        model = AttendanceRecord
        fields = [
            'id', 'ref', 'department_name', 'folder_name', 'fullname', 'ic_number',
            'phone', 'email', 'organization', 'timestamp',
            'cert_delay', 'certificate_generated', 'folder',
        ]
        read_only_fields = ['id', 'timestamp', 'certificate_generated', 'folder', 'cert_delay']

    def create(self, validated_data):
        department_name = validated_data.pop('department_name', 'General Department')
        folder_name = validated_data.pop('folder_name', 'General Folder')
        
        if not department_name: department_name = 'General Department'
        if not folder_name: folder_name = 'General Folder'

        department, _ = Department.objects.get_or_create(name=department_name)
        folder, _ = Folder.objects.get_or_create(department=department, name=folder_name)
        
        validated_data['folder'] = folder

        # Inherit the cert_delay from the Folder (set by admin)
        validated_data['cert_delay'] = folder.cert_delay

        return super().create(validated_data)
