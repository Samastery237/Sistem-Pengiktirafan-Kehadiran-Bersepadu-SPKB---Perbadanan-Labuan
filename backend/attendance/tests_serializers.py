"""
Comprehensive TDD tests for AttendanceRecordSerializer.

Tests cover:
- Valid data creation
- IC number validation (format, length, edge cases)
- Phone validation (format, length, edge cases)
- Create logic (department/folder lookup, cert_delay inheritance)
- Read fields serialization
- Partial update (PATCH)
- Required fields validation
- Department/Folder lookup edge cases (case sensitivity, whitespace)
"""

from django.test import TestCase
from attendance.models import AttendanceRecord, Department, Folder
from attendance.serializers import AttendanceRecordSerializer


class AttendanceRecordSerializerValidationTest(TestCase):
    """Test validation logic on AttendanceRecordSerializer fields."""

    def setUp(self):
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General", cert_delay=5000)
        self.valid_payload = {
            'fullname': 'Ahmad bin Ali',
            'ic_number': '123456789012',
            'phone': '0123456789',
            'email': 'ahmad@test.com',
            'organization': 'Org A',
            'department_name': 'IT',
            'folder_name': 'General',
        }

    # ──────────────────────────────────────────────
    # Valid Data Tests
    # ──────────────────────────────────────────────

    def test_valid_full_payload_is_valid(self):
        """A complete valid payload should pass validation."""
        serializer = AttendanceRecordSerializer(data=self.valid_payload)
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")

    def test_valid_payload_creates_record(self):
        """A valid payload should create an AttendanceRecord."""
        serializer = AttendanceRecordSerializer(data=self.valid_payload)
        self.assertTrue(serializer.is_valid())
        record = serializer.save()
        self.assertIsInstance(record, AttendanceRecord)
        self.assertEqual(record.fullname, 'Ahmad bin Ali')
        self.assertEqual(record.ic_number, '123456789012')
        self.assertEqual(record.phone, '0123456789')
        self.assertEqual(record.email, 'ahmad@test.com')
        self.assertEqual(record.organization, 'Org A')

    def test_minimal_valid_payload_with_department_folder(self):
        """fullname + department_name + folder_name are the minimum for create."""
        serializer = AttendanceRecordSerializer(data={
            'fullname': 'Minimal User',
            'department_name': 'IT',
            'folder_name': 'General',
        })
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")

    def test_department_name_required(self):
        """department_name is required (write_only CharField defaults to required=True)."""
        data = {**self.valid_payload}
        del data['department_name']
        serializer = AttendanceRecordSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('department_name', serializer.errors)

    def test_folder_name_required(self):
        """folder_name is required (write_only CharField defaults to required=True)."""
        data = {**self.valid_payload}
        del data['folder_name']
        serializer = AttendanceRecordSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('folder_name', serializer.errors)

    # ──────────────────────────────────────────────
    # IC Number Validation Tests
    # ──────────────────────────────────────────────

    def test_ic_valid_with_dashes(self):
        """IC with dashes like '123456-78-9012' should pass (12 digits)."""
        data = {**self.valid_payload, 'ic_number': '123456-78-9012'}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")

    def test_ic_valid_without_dashes(self):
        """IC without dashes '123456789012' should pass."""
        data = {**self.valid_payload, 'ic_number': '123456789012'}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")

    def test_ic_empty_string_passes(self):
        """Empty IC should pass because allow_blank=True."""
        data = {**self.valid_payload, 'ic_number': ''}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")

    def test_ic_none_fails_requires_blank_not_null(self):
        """None IC fails because allow_blank=True does not imply allow_null."""
        data = {**self.valid_payload, 'ic_number': None}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('ic_number', serializer.errors)

    def test_ic_missing_passes(self):
        """Omitted IC should pass because required=False."""
        data = {**self.valid_payload}
        del data['ic_number']
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")

    def test_ic_too_short_fails(self):
        """IC with fewer than 12 digits should fail."""
        data = {**self.valid_payload, 'ic_number': '12345678901'}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('ic_number', serializer.errors)

    def test_ic_too_short_error_message(self):
        """IC with < 12 digits should mention '12 digit' in error."""
        data = {**self.valid_payload, 'ic_number': '123'}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        error_msg = str(serializer.errors['ic_number'])
        self.assertIn('12', error_msg)

    def test_ic_too_long_fails(self):
        """IC with more than 12 digits should fail."""
        data = {**self.valid_payload, 'ic_number': '1234567890123'}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('ic_number', serializer.errors)

    def test_ic_too_long_error_message(self):
        """IC with > 12 digits should produce an error message."""
        data = {**self.valid_payload, 'ic_number': '1' * 13}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        error_msg = str(serializer.errors['ic_number'])
        self.assertTrue(len(error_msg) > 0)

    def test_ic_letters_only_fails(self):
        """IC with only letters cleans to empty string and fails."""
        data = {**self.valid_payload, 'ic_number': 'abcdefghijkl'}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('ic_number', serializer.errors)

    def test_ic_mixed_with_special_chars_passes(self):
        """IC with mixed dashes and spaces that resolves to 12 digits should pass."""
        data = {**self.valid_payload, 'ic_number': '123 456-789 012'}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")

    def test_validate_ic_number_directly(self):
        """Test validate_ic_number method directly returns original value on valid input."""
        serializer = AttendanceRecordSerializer()
        result = serializer.validate_ic_number('123456-78-9012')
        self.assertEqual(result, '123456-78-9012')

    def test_validate_ic_number_empty_returns_empty(self):
        """validate_ic_number should return empty string for empty input."""
        serializer = AttendanceRecordSerializer()
        result = serializer.validate_ic_number('')
        self.assertEqual(result, '')

    # ──────────────────────────────────────────────
    # Phone Validation Tests
    # ──────────────────────────────────────────────

    def test_phone_valid_10_digits(self):
        """Valid phone '0123456789' (10 digits) should pass."""
        data = {**self.valid_payload, 'phone': '0123456789'}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")

    def test_phone_valid_with_dashes(self):
        """Phone with dashes '012-345-6789' should pass (10 digits)."""
        data = {**self.valid_payload, 'phone': '012-345-6789'}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")

    def test_phone_valid_9_digits(self):
        """Phone with exactly 9 digits should pass (minimum)."""
        data = {**self.valid_payload, 'phone': '123456789'}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")

    def test_phone_valid_15_digits(self):
        """Phone with exactly 15 digits should pass (maximum)."""
        data = {**self.valid_payload, 'phone': '123456789012345'}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")

    def test_phone_empty_passes(self):
        """Empty phone should pass (optional field)."""
        data = {**self.valid_payload, 'phone': ''}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")

    def test_phone_none_passes(self):
        """None phone should pass."""
        data = {**self.valid_payload, 'phone': None}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")

    def test_phone_too_short_fails(self):
        """Phone with fewer than 9 digits should fail."""
        data = {**self.valid_payload, 'phone': '12345678'}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('phone', serializer.errors)

    def test_phone_too_long_fails(self):
        """Phone with more than 15 digits should fail."""
        data = {**self.valid_payload, 'phone': '1234567890123456'}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('phone', serializer.errors)

    def test_phone_letters_only_fails(self):
        """Phone with only letters should fail (cleans to empty, < 9)."""
        data = {**self.valid_payload, 'phone': 'abcdefghij'}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('phone', serializer.errors)

    def test_validate_phone_directly_valid(self):
        """Test validate_phone method directly returns original value on valid input."""
        serializer = AttendanceRecordSerializer()
        result = serializer.validate_phone('012-345-6789')
        self.assertEqual(result, '012-345-6789')

    def test_validate_phone_directly_empty(self):
        """validate_phone should return empty string for empty input."""
        serializer = AttendanceRecordSerializer()
        result = serializer.validate_phone('')
        self.assertEqual(result, '')

    # ──────────────────────────────────────────────
    # Create Logic Tests
    # ──────────────────────────────────────────────

    def test_create_new_department_and_folder(self):
        """Creating a record with new department/folder names should create them."""
        data = {
            **self.valid_payload,
            'department_name': 'New Department',
            'folder_name': 'New Folder',
        }
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        record = serializer.save()

        self.assertTrue(Department.objects.filter(name='New Department').exists())
        self.assertTrue(Folder.objects.filter(name='New Folder').exists())
        self.assertEqual(record.folder.name, 'New Folder')
        self.assertEqual(record.folder.department.name, 'New Department')

    def test_create_reuses_existing_department_and_folder(self):
        """Creating with existing department/folder names should reuse them."""
        data = {
            **self.valid_payload,
            'department_name': 'IT',
            'folder_name': 'General',
        }
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        record = serializer.save()

        self.assertEqual(record.folder, self.folder)
        self.assertEqual(Department.objects.filter(name='IT').count(), 1)

    def test_create_inherits_cert_delay_from_folder(self):
        """Created record should inherit cert_delay from the folder."""
        self.folder.cert_delay = 10000
        self.folder.save()

        serializer = AttendanceRecordSerializer(data=self.valid_payload)
        self.assertTrue(serializer.is_valid())
        record = serializer.save()

        self.assertEqual(record.cert_delay, 10000)

    def test_create_default_department_when_empty(self):
        """Empty department_name should default to 'General Department'."""
        data = {**self.valid_payload, 'department_name': ''}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        record = serializer.save()

        self.assertTrue(Department.objects.filter(name='General Department').exists())
        self.assertEqual(record.folder.department.name, 'General Department')

    def test_create_default_folder_when_empty(self):
        """Empty folder_name should default to 'General Folder'."""
        data = {**self.valid_payload, 'folder_name': ''}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        record = serializer.save()

        self.assertTrue(Folder.objects.filter(name='General Folder').exists())
        self.assertEqual(record.folder.name, 'General Folder')

    def test_whitespace_department_defaults_to_general(self):
        """Whitespace-only department_name strips to '' which defaults to 'General Department'."""
        data = {**self.valid_payload, 'department_name': '   '}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        record = serializer.save()

        # Django CharField strips '   ' to '', then create() defaults to 'General Department'
        self.assertTrue(Department.objects.filter(name='General Department').exists())
        self.assertEqual(record.folder.department.name, 'General Department')

    def test_whitespace_folder_defaults_to_general(self):
        """Whitespace-only folder_name strips to '' which defaults to 'General Folder'."""
        data = {**self.valid_payload, 'folder_name': '   '}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        record = serializer.save()

        # Django CharField strips '   ' to '', then create() defaults to 'General Folder'
        self.assertTrue(Folder.objects.filter(name='General Folder').exists())
        self.assertEqual(record.folder.name, 'General Folder')

    # ──────────────────────────────────────────────
    # Read Fields Tests
    # ──────────────────────────────────────────────

    def test_serialized_output_contains_expected_fields(self):
        """Serialized output should contain all expected read fields."""
        record = AttendanceRecord.objects.create(
            fullname='Read Test',
            ic_number='987654321098',
            phone='0987654321',
            email='read@test.com',
            organization='TestOrg',
            folder=self.folder,
            cert_delay=3000,
        )
        serializer = AttendanceRecordSerializer(record)
        data = serializer.data

        expected_fields = [
            'id', 'ref', 'fullname', 'ic_number', 'phone', 'email',
            'organization', 'timestamp', 'cert_delay', 'certificate_generated', 'folder',
        ]
        for field in expected_fields:
            self.assertIn(field, data, f"Missing field: {field}")

    def test_serialized_output_excludes_write_only_fields(self):
        """Serialized output should NOT contain write_only fields."""
        record = AttendanceRecord.objects.create(
            fullname='WriteOnly Test',
            folder=self.folder,
        )
        serializer = AttendanceRecordSerializer(record)
        data = serializer.data

        self.assertNotIn('department_name', data)
        self.assertNotIn('folder_name', data)

    def test_serialized_folder_is_id(self):
        """The 'folder' field in output should be the folder's ID."""
        record = AttendanceRecord.objects.create(
            fullname='Folder Test',
            folder=self.folder,
        )
        serializer = AttendanceRecordSerializer(record)
        self.assertEqual(serializer.data['folder'], self.folder.id)

    def test_serialized_cert_delay_value(self):
        """cert_delay in output should match the folder's cert_delay."""
        record = AttendanceRecord.objects.create(
            fullname='CertDelay Test',
            folder=self.folder,
            cert_delay=7500,
        )
        serializer = AttendanceRecordSerializer(record)
        self.assertEqual(serializer.data['cert_delay'], 7500)

    # ──────────────────────────────────────────────
    # Partial Update Tests
    # ──────────────────────────────────────────────

    def test_partial_update_fullname(self):
        """PATCH with only fullname should update just that field."""
        record = AttendanceRecord.objects.create(
            fullname='Original Name',
            ic_number='111111111111',
            phone='0111111111',
            folder=self.folder,
        )
        serializer = AttendanceRecordSerializer(record, data={'fullname': 'Updated Name'}, partial=True)
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")
        updated = serializer.save()
        self.assertEqual(updated.fullname, 'Updated Name')
        self.assertEqual(updated.folder, self.folder)  # unchanged

    def test_partial_update_ic_number(self):
        """PATCH with valid IC number should update it."""
        record = AttendanceRecord.objects.create(
            fullname='IC Update Test',
            ic_number='111111111111',
            folder=self.folder,
        )
        serializer = AttendanceRecordSerializer(
            record, data={'ic_number': '999999-99-9999'}, partial=True
        )
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")
        updated = serializer.save()
        self.assertEqual(updated.ic_number, '999999-99-9999')

    def test_partial_update_invalid_ic_rejected(self):
        """PATCH with invalid IC should be rejected."""
        record = AttendanceRecord.objects.create(
            fullname='Invalid IC Test',
            ic_number='111111111111',
            folder=self.folder,
        )
        serializer = AttendanceRecordSerializer(
            record, data={'ic_number': 'abc'}, partial=True
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('ic_number', serializer.errors)

    def test_partial_update_phone(self):
        """PATCH with valid phone should update it."""
        record = AttendanceRecord.objects.create(
            fullname='Phone Update Test',
            phone='0111111111',
            folder=self.folder,
        )
        serializer = AttendanceRecordSerializer(
            record, data={'phone': '019-9876-543'}, partial=True
        )
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")
        updated = serializer.save()
        self.assertEqual(updated.phone, '019-9876-543')

    # ──────────────────────────────────────────────
    # Required Fields Tests
    # ──────────────────────────────────────────────

    def test_fullname_required(self):
        """fullname is required and should fail when missing."""
        data = {**self.valid_payload}
        del data['fullname']
        serializer = AttendanceRecordSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('fullname', serializer.errors)

    def test_fullname_empty_rejected(self):
        """Empty fullname should be rejected."""
        data = {**self.valid_payload, 'fullname': ''}
        serializer = AttendanceRecordSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('fullname', serializer.errors)

    def test_email_optional(self):
        """Email is optional."""
        data = {**self.valid_payload}
        del data['email']
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")

    def test_organization_optional(self):
        """Organization is optional."""
        data = {**self.valid_payload}
        del data['organization']
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")

    def test_ref_optional(self):
        """ref is optional — serializer works whether ref is present or not."""
        data = {**self.valid_payload, 'ref': 'REF-001'}
        # With ref
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")
        # Without ref
        del data['ref']
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid(), f"Errors: {serializer.errors}")

    # ──────────────────────────────────────────────
    # Department/Folder Lookup Edge Cases
    # ──────────────────────────────────────────────

    def test_department_lookup_case_sensitive(self):
        """Department lookup is case-sensitive: 'it' != 'IT'."""
        data = {
            **self.valid_payload,
            'department_name': 'it',  # lowercase, but 'IT' exists
            'folder_name': 'General',
        }
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        serializer.save()

        # get_or_create is case-sensitive, so a new department 'it' is created
        self.assertTrue(Department.objects.filter(name='it').exists())
        self.assertTrue(Department.objects.filter(name='IT').exists())

    def test_folder_lookup_requires_correct_department(self):
        """Folder lookup is scoped to the department."""
        other_dept = Department.objects.create(name="HR")
        Folder.objects.create(department=other_dept, name="General")

        data = {
            **self.valid_payload,
            'department_name': 'HR',
            'folder_name': 'General',
        }
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        record = serializer.save()

        self.assertEqual(record.folder.department.name, 'HR')

    def test_department_name_with_trailing_whitespace(self):
        """Department name with trailing whitespace is stripped by Django CharField."""
        data = {
            **self.valid_payload,
            'department_name': '  IT  ',
            'folder_name': 'General',
        }
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        record = serializer.save()

        # Django CharField strips whitespace by default, so '  IT  ' becomes 'IT'
        # and get_or_create finds the existing 'IT' department.
        self.assertEqual(record.folder.department.name, 'IT')
        self.assertEqual(Department.objects.filter(name='IT').count(), 1)

    def test_multiple_records_same_department_folder(self):
        """Multiple records can share the same department and folder."""
        ser1 = AttendanceRecordSerializer(data=self.valid_payload)
        ser2 = AttendanceRecordSerializer(data={**self.valid_payload, 'fullname': 'Second User'})

        self.assertTrue(ser1.is_valid())
        self.assertTrue(ser2.is_valid())
        rec1 = ser1.save()
        rec2 = ser2.save()

        self.assertEqual(rec1.folder, rec2.folder)
        self.assertEqual(AttendanceRecord.objects.filter(folder=self.folder).count(), 2)

    def test_cert_delay_zero_when_folder_has_no_delay(self):
        """Record should have cert_delay=0 when folder has cert_delay=0."""
        Folder.objects.create(department=self.dept, name="NoDelay", cert_delay=0)
        data = {
            **self.valid_payload,
            'folder_name': 'NoDelay',
        }
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        record = serializer.save()

        self.assertEqual(record.cert_delay, 0)
