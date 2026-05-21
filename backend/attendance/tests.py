from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.utils import timezone
from datetime import timedelta
import json
from .models import Program, AttendanceRecord
from .serializers import AttendanceRecordSerializer


class ProgramModelTest(TestCase):
    """Test cases for Program model"""

    def setUp(self):
        self.program = Program.objects.create(
            name="Test Program",
            cert_delay=300000  # 5 minutes
        )

    def test_program_creation(self):
        """Test that a program can be created"""
        self.assertEqual(self.program.name, "Test Program")
        self.assertEqual(self.program.cert_delay, 300000)
        self.assertTrue(self.program.created_at)

    def test_program_str(self):
        """Test string representation of Program"""
        self.assertEqual(str(self.program), "Test Program")

    def test_program_default_cert_delay(self):
        """Test default certificate delay"""
        program = Program.objects.create(name="Default Program")
        self.assertEqual(program.cert_delay, 120000)  # Default from model


class AttendanceRecordModelTest(TestCase):
    """Test cases for AttendanceRecord model"""

    def setUp(self):
        self.program = Program.objects.create(name="Test Program")
        self.record = AttendanceRecord.objects.create(
            fullname="Test User",
            ic_number="123456789012",
            program=self.program,
            ref="REF123",
            phone="0123456789",
            email="test@example.com",
            organization="Test Org"
        )

    def test_attendance_record_creation(self):
        """Test that an attendance record can be created"""
        self.assertEqual(self.record.fullname, "Test User")
        self.assertEqual(self.record.ic_number, "123456789012")
        self.assertEqual(self.record.program, self.program)
        self.assertEqual(self.record.ref, "REF123")
        self.assertEqual(self.record.phone, "0123456789")
        self.assertEqual(self.record.email, "test@example.com")
        self.assertEqual(self.record.organization, "Test Org")
        self.assertFalse(self.record.certificate_generated)  # Default
        self.assertEqual(self.record.cert_delay, 120000)  # Inherited from program
        self.assertTrue(self.record.timestamp)
        self.assertTrue(self.record.id)  # UUID should be set

    def test_attendance_record_str(self):
        """Test string representation of AttendanceRecord"""
        expected = f"{self.record.fullname} - {self.record.program.name}"
        self.assertEqual(str(self.record), expected)

    def test_attendance_record_defaults(self):
        """Test default values"""
        record = AttendanceRecord.objects.create(
            fullname="Default User",
            ic_number="987654321098",
            program=self.program
        )
        self.assertIsNone(record.ref)
        self.assertIsNone(record.phone)
        self.assertIsNone(record.email)
        self.assertIsNone(record.organization)
        self.assertFalse(record.certificate_generated)
        self.assertEqual(record.cert_delay, 120000)


class SerializerTest(TestCase):
    """Test cases for serializers"""

    def setUp(self):
        self.program = Program.objects.create(name="Test Program", cert_delay=180000)
        self.valid_data = {
            'fullname': 'Test User',
            'ic_number': '123456789012',
            'program_name': 'Test Program',
            'ref': 'REF123',
            'phone': '0123456789',
            'email': 'test@example.com',
            'organization': 'Test Org'
        }

    def test_attendance_record_serializer_valid(self):
        """Test serializer with valid data"""
        serializer = AttendanceRecordSerializer(data=self.valid_data)
        self.assertTrue(serializer.is_valid())
        record = serializer.save()
        self.assertEqual(record.fullname, 'Test User')
        self.assertEqual(record.program.name, 'Test Program')
        self.assertEqual(record.cert_delay, 180000)  # From program

    def test_attendance_record_serializer_invalid_missing_fields(self):
        """Test serializer with missing required fields"""
        invalid_data = self.valid_data.copy()
        del invalid_data['fullname']
        serializer = AttendanceRecordSerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('fullname', serializer.errors)

    def test_attendance_record_serializer_program_name_handling(self):
        """Test that program_name is handled correctly"""
        data = self.valid_data.copy()
        data['program_name'] = 'New Program'
        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        record = serializer.save()
        self.assertEqual(record.program.name, 'New Program')
        # Should create new program
        self.assertTrue(Program.objects.filter(name='New Program').exists())

    def test_attendance_record_serializer_read_only_fields(self):
        """Test that read-only fields cannot be overridden"""
        data = self.valid_data.copy()
        data['id'] = '00000000-0000-0000-0000-000000000001'
        data['timestamp'] = '2023-01-01T00:00:00Z'
        data['certificate_generated'] = True
        data['program'] = 999
        data['cert_delay'] = 999999

        serializer = AttendanceRecordSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        record = serializer.save()
        # These should not be set from input
        self.assertNotEqual(str(record.id), '00000000-0000-0000-0000-000000000001')
        self.assertIsNotNone(record.timestamp)  # Should be auto-set
        self.assertFalse(record.certificate_generated)  # Default False
        self.assertNotEqual(record.program_id, 999)
        self.assertNotEqual(record.cert_delay, 999999)


class APITestCaseBase(APITestCase):
    """Base class for API tests"""

    def setUp(self):
        self.client = APIClient()
        self.program = Program.objects.create(name="Test Program", cert_delay=60000)
        self.program2 = Program.objects.create(name="Another Program", cert_delay=120000)


class SubmitAttendanceViewTest(APITestCaseBase):
    """Test cases for SubmitAttendanceView"""

    def test_submit_attendance_success(self):
        """Test successful attendance submission"""
        url = reverse('submit_attendance')  # Assuming this is the URL name
        data = {
            'fullname': 'John Doe',
            'ic_number': '987654321098',
            'program_name': 'Test Program',
            'ref': 'REF456',
            'phone': '0198765432',
            'email': 'john@example.com',
            'organization': 'Test Company'
        }

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['message'], 'Attendance recorded successfully')
        self.assertIn('record_id', response.data)
        self.assertIn('data', response.data)

        # Check that record was created
        record = AttendanceRecord.objects.get(id=response.data['record_id'])
        self.assertEqual(record.fullname, 'John Doe')
        self.assertEqual(record.ic_number, '987654321098')
        self.assertEqual(record.program.name, 'Test Program')

    def test_submit_attendance_missing_required_fields(self):
        """Test submission with missing required fields"""
        url = reverse('submit_attendance')
        data = {
            'ic_number': '123456789012'
            # Missing fullname and program_name
        }

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertIn('errors', response.data)

    def test_submit_attendance_empty_program_name(self):
        """Test submission with empty program name defaults to 'General Attendance'"""
        url = reverse('submit_attendance')
        data = {
            'fullname': 'Jane Doe',
            'ic_number': '111111111111',
            'program_name': '',  # Empty program name
        }

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        record = AttendanceRecord.objects.get(id=response.data['record_id'])
        self.assertEqual(record.program.name, 'General Attendance')

    def test_submit_attendance_pl_program_name(self):
        """Test submission with 'PL' program name defaults to 'General Attendance'"""
        url = reverse('submit_attendance')
        data = {
            'fullname': 'PL User',
            'ic_number': '222222222222',
            'program_name': 'PL',
        }

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        record = AttendanceRecord.objects.get(id=response.data['record_id'])
        self.assertEqual(record.program.name, 'General Attendance')


class RecordListViewTest(APITestCaseBase):
    """Test cases for RecordListView"""

    def setUp(self):
        super().setUp()
        # Create test records
        AttendanceRecord.objects.create(
            fullname='Alice Smith',
            ic_number='111111111111',
            program=self.program
        )
        AttendanceRecord.objects.create(
            fullname='Bob Johnson',
            ic_number='222222222222',
            program=self.program2
        )
        AttendanceRecord.objects.create(
            fullname='Charlie Brown',
            ic_number='333333333333',
            program=self.program,
            organization='Test Org'
        )

    def test_record_list_get_all(self):
        """Test getting all records"""
        url = reverse('record_list')  # Assuming this is the URL name
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(len(response.data['data']), 3)

    def test_record_list_filter_by_program(self):
        """Test filtering records by program"""
        url = reverse('record_list')
        response = self.client.get(url, {'program': self.program.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 2)  # Alice and Charlie

        # Check that all records belong to the correct program
        for record in response.data['data']:
            self.assertEqual(record['program_name'], self.program.name)

    def test_record_list_search(self):
        """Test searching records"""
        url = reverse('record_list')
        response = self.client.get(url, {'search': 'alice'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['fullname'], 'Alice Smith')

        # Test case insensitive search
        response = self.client.get(url, {'search': 'ALICE'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 1)

        # Test search on IC
        response = self.client.get(url, {'search': '222222'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['fullname'], 'Bob Johnson')

        # Test search on organization
        response = self.client.get(url, {'search': 'Test Org'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['organization'], 'Test Org')

    def test_record_list_delete_all(self):
        """Test deleting all records"""
        url = reverse('record_list')
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['deleted'], 3)

        # Verify records are deleted
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_record_list_delete_by_program(self):
        """Test deleting records filtered by program"""
        url = reverse('record_list')
        # Pass program ID as query parameter in URL for DELETE request
        response = self.client.delete(f"{url}?program={self.program.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['deleted'], 2)  # Alice and Charlie

        # Verify only Bob's record remains
        self.assertEqual(AttendanceRecord.objects.count(), 1)
        remaining_record = AttendanceRecord.objects.first()
        self.assertEqual(remaining_record.fullname, 'Bob Johnson')
        self.assertEqual(remaining_record.program, self.program2)

    def test_record_list_delete_by_ids(self):
        """Test deleting specific records by ID list"""
        url = reverse('record_list')
        # Get all records to extract IDs
        records = AttendanceRecord.objects.all()
        id1 = str(records[0].id)
        id2 = str(records[1].id)
        
        # Send DELETE request with JSON payload containing 'ids'
        response = self.client.delete(url, data={'ids': [id1, id2]}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['deleted'], 2)

        # Verify only 1 record remains
        self.assertEqual(AttendanceRecord.objects.count(), 1)


class RecordDetailViewTest(APITestCaseBase):
    """Test cases for RecordDetailView"""

    def setUp(self):
        super().setUp()
        self.record = AttendanceRecord.objects.create(
            fullname='Test Record',
            ic_number='999999999999',
            program=self.program
        )

    def test_record_detail_delete_success(self):
        """Test successful deletion of a record"""
        url = reverse('record_detail', kwargs={'record_id': self.record.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')

        # Verify record is deleted
        self.assertFalse(AttendanceRecord.objects.filter(id=self.record.id).exists())

    def test_record_detail_patch_success(self):
        """Test successful update of a record"""
        url = reverse('record_detail', kwargs={'record_id': self.record.id})
        data = {
            'fullname': 'Updated Name',
            'ic_number': '123123123123',
            'phone': '0199999999',
            'email': 'updated@example.com',
            'organization': 'Updated Org'
        }
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        
        # Verify database was updated
        self.record.refresh_from_db()
        self.assertEqual(self.record.fullname, 'Updated Name')
        self.assertEqual(self.record.ic_number, '123123123123')
        self.assertEqual(self.record.phone, '0199999999')
        self.assertEqual(self.record.email, 'updated@example.com')
        self.assertEqual(self.record.organization, 'Updated Org')

    def test_record_detail_delete_not_found(self):
        """Test deletion of non-existent record"""
        import uuid
        fake_id = uuid.uuid4()
        url = reverse('record_detail', kwargs={'record_id': fake_id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class GetParticipantByICViewTest(APITestCaseBase):
    """Test cases for GetParticipantByICView"""

    def setUp(self):
        super().setUp()
        # Create records with same IC but different formats
        self.record1 = AttendanceRecord.objects.create(
            fullname='User One',
            ic_number='123-456-789-012',  # With dashes
            program=self.program
        )
        self.record2 = AttendanceRecord.objects.create(
            fullname='User Two',
            ic_number='123456789012',  # Without dashes
            program=self.program2
        )
        # Make record2 more recent
        self.record2.timestamp = timezone.now() - timedelta(hours=1)
        self.record2.save()

    def test_get_participant_by_ic_exact_match(self):
        """Test getting participant by exact IC match"""
        url = reverse('get_participant', kwargs={'ic_number': '123-456-789-012'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['fullname'], 'User One')

    def test_get_participant_by_ic_digits_only_match(self):
        """Test getting participant by digits-only IC match"""
        url = reverse('get_participant', kwargs={'ic_number': '123456789012'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        # Should return the most recent record (record2)
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['fullname'], 'User Two')

    def test_get_participant_by_ic_invalid(self):
        """Test getting participant with invalid IC"""
        url = reverse('get_participant', kwargs={'ic_number': 'abc!'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertEqual(response.data['message'], 'Invalid IC')

    def test_get_participant_by_ic_not_found(self):
        """Test getting participant with non-existent IC"""
        url = reverse('get_participant', kwargs={'ic_number': '000000000000'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['status'], 'error')
        self.assertEqual(response.data['message'], 'Not found')


class AttendanceStatusViewTest(APITestCaseBase):
    """Test cases for AttendanceStatusView"""

    def setUp(self):
        super().setUp()
        self.record = AttendanceRecord.objects.create(
            fullname='Status Test User',
            ic_number='555555555555',
            program=self.program,
            certificate_generated=True
        )

    def test_attendance_status_success(self):
        """Test getting attendance status"""
        url = reverse('attendance_status', kwargs={'record_id': self.record.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return serialized record data
        self.assertEqual(response.data['fullname'], 'Status Test User')
        self.assertEqual(response.data['ic_number'], '555555555555')
        self.assertTrue(response.data['certificate_generated'])

    def test_attendance_status_not_found(self):
        """Test getting status of non-existent record"""
        import uuid
        fake_id = uuid.uuid4()
        url = reverse('attendance_status', kwargs={'record_id': fake_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class StatsViewTest(APITestCaseBase):
    """Test cases for StatsView"""

    def setUp(self):
        super().setUp()
        # Create some test records
        AttendanceRecord.objects.create(
            fullname='Stats User 1',
            ic_number='111111111111',
            program=self.program,
            certificate_generated=True
        )
        AttendanceRecord.objects.create(
            fullname='Stats User 2',
            ic_number='222222222222',
            program=self.program,
            certificate_generated=False
        )
        AttendanceRecord.objects.create(
            fullname='Stats User 3',
            ic_number='333333333333',
            program=self.program2,
            certificate_generated=True
        )

    def test_stats_overall(self):
        """Test overall statistics"""
        url = reverse('stats')  # Assuming this is the URL name
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total'], 3)
        self.assertEqual(response.data['certs'], 2)  # Two with certificates
        # Today count depends on when the test runs, but should be >= 0
        self.assertGreaterEqual(response.data['today'], 0)

    def test_stats_filtered_by_program(self):
        """Test statistics filtered by program"""
        url = reverse('stats')
        response = self.client.get(url, {'program': self.program.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total'], 2)  # Only stats user 1 and 2
        self.assertEqual(response.data['certs'], 1)  # Only stats user 1 has certificate


class ProgramListViewTest(APITestCaseBase):
    """Test cases for ProgramListView"""

    def test_program_list_get(self):
        """Test getting list of programs"""
        url = reverse('program_list')  # Assuming this is the URL name
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(len(response.data['data']), 2)

        # Check program data structure
        program_data = response.data['data'][0]
        self.assertIn('id', program_data)
        self.assertIn('name', program_data)
        self.assertIn('cert_delay', program_data)
        self.assertIn('count', program_data)

    def test_program_list_post_success(self):
        """Test creating a new program"""
        url = reverse('program_list')
        data = {'name': 'New Program'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'success')
        self.assertTrue(response.data['created'])  # Should be newly created
        self.assertEqual(response.data['name'], 'New Program')
        self.assertEqual(response.data['cert_delay'], 120000)  # Default

    def test_program_list_post_existing(self):
        """Test creating a program that already exists"""
        url = reverse('program_list')
        data = {'name': 'Test Program'}  # Already exists
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertFalse(response.data['created'])  # Should not be newly created
        self.assertEqual(response.data['name'], 'Test Program')

    def test_program_list_post_missing_name(self):
        """Test creating program without name"""
        url = reverse('program_list')
        data = {}  # Missing name
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')
        self.assertEqual(response.data['message'], 'Program name is required')


class ProgramDetailViewTest(APITestCaseBase):
    """Test cases for ProgramDetailView"""

    def setUp(self):
        super().setUp()
        # Add some attendance records to test count
        AttendanceRecord.objects.create(
            fullname='Prog User 1',
            ic_number='444444444444',
            program=self.program
        )
        AttendanceRecord.objects.create(
            fullname='Prog User 2',
            ic_number='555555555555',
            program=self.program
        )

    def test_program_detail_get(self):
        """Test getting program details"""
        url = reverse('program_detail', kwargs={'program_id': self.program.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['id'], self.program.id)
        self.assertEqual(response.data['name'], self.program.name)
        self.assertEqual(response.data['cert_delay'], self.program.cert_delay)

    def test_program_detail_patch(self):
        """Test updating program details"""
        url = reverse('program_detail', kwargs={'program_id': self.program.id})
        data = {
            'name': 'Updated Program Name',
            'cert_delay': 180000
        }
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        self.assertEqual(response.data['name'], 'Updated Program Name')
        self.assertEqual(response.data['cert_delay'], 180000)

        # Verify the program was actually updated
        self.program.refresh_from_db()
        self.assertEqual(self.program.name, 'Updated Program Name')
        self.assertEqual(self.program.cert_delay, 180000)

    def test_program_detail_delete(self):
        """Test deleting a program"""
        url = reverse('program_detail', kwargs={'program_id': self.program.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')

        # Verify program and its attendance records are deleted
        self.assertFalse(Program.objects.filter(id=self.program.id).exists())
        self.assertEqual(AttendanceRecord.objects.filter(program=self.program).count(), 0)

    def test_program_detail_get_not_found(self):
        """Test getting details of non-existent program"""
        fake_id = 99999  # Non-existent integer ID
        url = reverse('program_detail', kwargs={'program_id': fake_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ExportCSVViewTest(APITestCaseBase):
    """Test cases for ExportCSVView"""

    def setUp(self):
        super().setUp()
        AttendanceRecord.objects.create(
            fullname='CSV User',
            ic_number='999999999999',
            program=self.program,
            ref='CSVREF',
            phone='0123456789',
            email='csv@example.com',
            organization='CSV Org'
        )

    def test_export_csv(self):
        """Test CSV export"""
        url = reverse('export_csv')  # Assuming this is the URL name
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment; filename=', response['Content-Disposition'])

        # Check that content contains expected data
        content = response.content.decode('utf-8-sig')  # Remove BOM
        lines = content.strip().split('\n')
        self.assertGreaterEqual(len(lines), 2)  # Header + at least one data row
        self.assertIn('Ref', lines[0])  # Header
        self.assertIn('CSV User', lines[1])  # Data
        self.assertIn('CSVREF', lines[1])
        self.assertIn('CSV Org', lines[1])


# Note: DownloadCertificateView test would require mocking PDF generation
# Since it depends on xhtml2pdf which may not be installed in test environment
# We'll test that the view handles the case gracefully when PDF generation fails

class DownloadCertificateViewTest(APITestCaseBase):
    """Test cases for DownloadCertificateView"""

    def setUp(self):
        super().setUp()
        self.record = AttendanceRecord.objects.create(
            fullname='Certificate User',
            ic_number='888888888888',
            program=self.program
        )

    def test_download_certificate_success(self):
        """Test successful certificate download"""
        url = reverse('download_certificate', kwargs={'record_id': self.record.id})
        response = self.client.get(url)
        # Should either succeed (if xhtml2pdf is installed) or gracefully fail
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR])

        if response.status_code == status.HTTP_200_OK:
            self.assertEqual(response['Content-Type'], 'application/pdf')
            self.assertIn('attachment; filename=', response['Content-Disposition'])
            # Check that certificate_generated was set to True
            self.record.refresh_from_db()
            self.assertTrue(self.record.certificate_generated)
        else:
            # Should return error message about missing dependency
            self.assertEqual(response.data['status'], 'error')
            self.assertIn('PDF generation failed', response.data['message'])
            self.assertIn('xhtml2pdf', response.data['message'])

    def test_download_certificate_not_found(self):
        """Test downloading certificate for non-existent record"""
        import uuid
        fake_id = uuid.uuid4()
        url = reverse('download_certificate', kwargs={'record_id': fake_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)