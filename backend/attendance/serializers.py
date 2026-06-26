import base64
from io import BytesIO
from PIL import Image
from rest_framework import serializers
from .models import Department, Folder, AttendanceRecord


def validate_cert_template(value):
    if not value:
        return value
    try:
        decoded = base64.b64decode(value, validate=True)
        if len(decoded) > 5 * 1024 * 1024:
            raise serializers.ValidationError("Saiz imej sijil mesti kurang daripada 5MB.")
        Image.open(BytesIO(decoded)).verify()
    except (ValueError, base64.binascii.Error):
        raise serializers.ValidationError("Data imej sijil tidak sah (bukan Base64 yang valid).")
    except Exception:
        raise serializers.ValidationError(
            "Imej sijil tidak sah. Hanya PNG, JPEG, GIF, atau WebP dibenarkan."
        )
    return value


class FolderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Folder
        fields = [
            'id', 'name', 'cert_delay', 'cert_template', 'name_x', 'name_y', 'name_size',
            'show_ic', 'ic_x', 'ic_y', 'ic_size', 'text_color', 'font_family',
            'event_name', 'event_date', 'organizer', 'department',
        ]
        read_only_fields = ['id', 'department']
        extra_kwargs = {
            'cert_template': {'required': False, 'allow_blank': True, 'validators': [validate_cert_template]},
            'cert_delay': {'required': False},
            'name_x': {'required': False},
            'name_y': {'required': False},
            'name_size': {'required': False},
            'show_ic': {'required': False},
            'ic_x': {'required': False},
            'ic_y': {'required': False},
            'ic_size': {'required': False},
            'text_color': {'required': False},
            'font_family': {'required': False},
            'event_name': {'required': False, 'allow_blank': True},
            'event_date': {'required': False, 'allow_blank': True},
            'organizer': {'required': False, 'allow_blank': True},
        }


class AttendanceRecordSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(write_only=True, allow_blank=True)
    folder_name = serializers.CharField(write_only=True, allow_blank=True)

    ic_number = serializers.CharField(allow_blank=True, required=False)

    class Meta:
        model = AttendanceRecord
        fields = [
            'id', 'ref', 'department_name', 'folder_name', 'fullname', 'ic_number',
            'phone', 'email', 'organization', 'timestamp',
            'cert_delay', 'certificate_generated', 'folder',
        ]
        read_only_fields = ['id', 'timestamp', 'certificate_generated', 'folder', 'cert_delay']

    def validate_ic_number(self, value):
        if not value:
            return ""
        import re
        clean_val = re.sub(r'\D', '', value)
        if len(clean_val) < 12:
            raise serializers.ValidationError("Nombor IC mestilah sekurang-kurangnya 12 digit tanpa tanda sengkang (-).")
        if len(clean_val) > 12:
            raise serializers.ValidationError("Nombor IC tidak sah.")
        return value
        
    def validate_phone(self, value):
        import re
        if value:
            clean_val = re.sub(r'\D', '', value)
            if len(clean_val) < 9 or len(clean_val) > 15:
                raise serializers.ValidationError("Sila masukkan nombor telefon yang sah.")
        return value

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
