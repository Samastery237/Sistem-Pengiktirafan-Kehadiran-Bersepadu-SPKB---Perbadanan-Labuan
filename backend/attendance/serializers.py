from rest_framework import serializers
from .models import Program, AttendanceRecord


class AttendanceRecordSerializer(serializers.ModelSerializer):
    program_name = serializers.CharField(write_only=True, allow_blank=True)

    class Meta:
        model = AttendanceRecord
        fields = [
            'id', 'ref', 'program_name', 'fullname', 'ic_number',
            'phone', 'email', 'organization', 'timestamp',
            'cert_delay', 'certificate_generated', 'program',
        ]
        read_only_fields = ['id', 'timestamp', 'certificate_generated', 'program', 'cert_delay']

    def create(self, validated_data):
        program_name = validated_data.pop('program_name', 'General Attendance')
        if not program_name or program_name.lower() == 'pl':
            program_name = 'General Attendance'

        program, _ = Program.objects.get_or_create(name=program_name)
        validated_data['program'] = program

        # Inherit the cert_delay from the Program (set by admin)
        # This ensures all devices see the same countdown timer
        validated_data['cert_delay'] = program.cert_delay

        return super().create(validated_data)
