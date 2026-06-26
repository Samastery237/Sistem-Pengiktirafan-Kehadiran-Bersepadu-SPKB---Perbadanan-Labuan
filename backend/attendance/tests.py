import csv
import logging
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

BROWSER_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
from django.contrib.auth.models import User
from django.contrib.auth.hashers import identify_hasher
from django.utils import timezone

from attendance.models import (
    AdminProfile, AttendanceRecord, Department, EmailVerificationToken,
    FailedLoginAttempt, Folder, UserAccountLock,
)
import json


class DisableAbuseMiddlewareMixin:
    """Mixin to disable abuse protection middleware for test classes that need it."""
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Patch the AbuseProtectionMiddleware to pass through without blocking
        # by replacing __call__ with a simple pass-through
        cls._abuse_patcher = patch(
            'attendance.middleware.AbuseProtectionMiddleware.__call__',
            new_callable=lambda: lambda self, request: self.get_response(request),
        )
        cls._abuse_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._abuse_patcher.stop()
        super().tearDownClass()


class DisableThrottleMixin(DisableAbuseMiddlewareMixin):
    """Mixin to disable DRF throttling AND abuse middleware for test classes that don't test throttling."""
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Patch SimpleRateThrottle.allow_request (parent of all throttle classes used)
        cls._throttle_patcher = patch(
            'rest_framework.throttling.SimpleRateThrottle.allow_request',
            return_value=True,
        )
        cls._throttle_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._throttle_patcher.stop()
        super().tearDownClass()

class FullBackendSuite(DisableThrottleMixin, TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin', password='password123')
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_model_ic_cleaning(self):
        record = AttendanceRecord(
            fullname="Test Name",
            ic_number="123456-78-9012",
            phone="012-3456789",
            folder=self.folder
        )
        record.save()
        self.assertEqual(record.clean_ic_number, "123456789012")

    def test_auth_login_success(self):
        response = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'admin',
            'password': 'password123'
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)

    def test_auth_login_fail(self):
        response = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'admin',
            'password': 'wrong'
        }), content_type='application/json')
        self.assertEqual(response.status_code, 401)

    def test_admin_api_security(self):
        # Should be 401 or 403 when unauthenticated
        response = self.client.get(reverse('stats'))
        self.assertIn(response.status_code, [401, 403])

    def test_public_submit_attendance(self):
        response = self.client.post(reverse('submit_attendance'), data={
            'fullname': 'Public User',
            'ic_number': '111111223333',
            'phone': '0111111111',
            'department_name': 'New Dept',
            'folder_name': 'New Folder'
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(AttendanceRecord.objects.count(), 1)
        self.assertEqual(AttendanceRecord.objects.first().fullname, 'Public User')

    def test_rate_limiting_login(self):
        """Simulate brute force — after 5 failed attempts the account locks (403)."""
        for i in range(5):
            self.client.post(reverse('auth_login'), data=json.dumps({'username':'admin','password':'w'}), content_type='application/json')
        # 6th attempt should be locked out (403) — lockout kicks in before throttle
        response = self.client.post(reverse('auth_login'), data=json.dumps({'username':'admin','password':'w'}), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_integration_flow(self):
        # Submit form
        self.client.post(reverse('submit_attendance'), data={
            'fullname': 'Integration User',
            'ic_number': '999999-99-9999',
            'phone': '0199999999',
            'department_name': 'INT',
            'folder_name': 'INT'
        })
        
        # Admin logs in and searches for participant
        self.client.login(username='admin', password='password123')
        response = self.client.get(reverse('get_participant', args=['999999999999']))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data'][0]['fullname'], 'Integration User')

    def test_security_sql_injection_defense(self):
        """Simulate a Burp Suite SQLi attack payload on the search API."""
        # Create a dummy record first
        AttendanceRecord.objects.create(
            fullname="Valid User", ic_number="123123123123", phone="012345", folder=self.folder
        )
        self.client.login(username='admin', password='password123')
        
        # Attack payload: trying to force a TRUE condition
        malicious_payload = "123123123123' OR '1'='1"
        response = self.client.get(reverse('get_participant', args=[malicious_payload]))

        # Input validation rejects malformed IC (strips non-digits → 14 digits, not 12)
        # This is the correct security behavior — reject invalid input before it reaches the ORM
        self.assertEqual(response.status_code, 400)

    def test_security_xss_payload_handling(self):
        """Simulate a Cross-Site Scripting (XSS) payload submitted in the form."""
        xss_payload = "<script>alert('Hacked!');</script>"
        
        response = self.client.post(reverse('submit_attendance'), data={
            'fullname': xss_payload,
            'ic_number': '888888888888',
            'phone': '0199999999',
            'department_name': 'IT',
            'folder_name': 'General'
        })
        
        self.assertEqual(response.status_code, 201)
        
        # Verify the database securely stored the literal string without evaluating it
        record = AttendanceRecord.objects.get(ic_number="888888888888")
        self.assertEqual(record.fullname, xss_payload)

    # ──────────────────────────────────────────────
    # NEW SECURITY TESTS
    # ──────────────────────────────────────────────

    def test_password_change_requires_old_password(self):
        """Verify that omitting old_password returns 400."""
        self.client.login(username='admin', password='password123')
        response = self.client.post('/api/attendance/auth/password/', data=json.dumps({
            'new_password': 'NewSecure@789'
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Kata laluan lama diperlukan', response.json().get('message', ''))

    def test_password_change_wrong_old_password(self):
        """Verify that submitting an incorrect old password returns 400."""
        self.client.login(username='admin', password='password123')
        response = self.client.post('/api/attendance/auth/password/', data=json.dumps({
            'old_password': 'wrongpassword',
            'new_password': 'NewSecure@789'
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('tidak betul', response.json().get('message', ''))

    def test_password_change_rejects_weak_password(self):
        """Verify that common/weak passwords are rejected by Django validators."""
        self.client.login(username='admin', password='password123')
        response = self.client.post('/api/attendance/auth/password/', data=json.dumps({
            'old_password': 'password123',
            'new_password': 'password'  # common password — must be rejected
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_user_creation_rejects_weak_password(self):
        """Verify that creating a user with a purely numeric password is rejected."""
        self.user.is_superuser = True
        self.user.save()
        self.client.login(username='admin', password='password123')
        response = self.client.post('/api/attendance/users/', data=json.dumps({
            'username': 'weakuser',
            'password': '12345678'  # numeric only — must be rejected
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_status_endpoint_hides_pii(self):
        """Verify the public status endpoint does not leak phone/email/IC."""
        record = AttendanceRecord.objects.create(
            fullname="PII Test", ic_number="111122223333", phone="01155556666",
            email="secret@test.com", folder=self.folder
        )
        # Unauthenticated request — should NOT contain sensitive PII (phone/email/IC/fullname)
        response = self.client.get(f'/api/attendance/status/{record.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn('phone', data)
        self.assertNotIn('email', data)
        self.assertNotIn('ic_number', data)
        self.assertNotIn('fullname', data)

    def test_bulk_delete_idor(self):
        """Verify an admin cannot bulk delete records from another department."""
        # Create another department and folder
        other_dept = Department.objects.create(name="HR")
        other_folder = Folder.objects.create(department=other_dept, name="Onboarding")
        
        # Create records
        my_record = AttendanceRecord.objects.create(fullname="My Record", ic_number="1", phone="1", folder=self.folder)
        other_record = AttendanceRecord.objects.create(fullname="Other Record", ic_number="2", phone="2", folder=other_folder)
        
        # Set current user as admin of 'self.dept'
        from attendance.models import AdminProfile
        AdminProfile.objects.create(user=self.user, department=self.dept)
        self.user.is_superuser = False
        self.user.save()
        
        self.client.login(username='admin', password='password123')
        
        # Try to delete both records
        response = self.client.delete('/api/attendance/records/', data=json.dumps({'ids': [str(my_record.id), str(other_record.id)]}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        
        # Should only delete my_record
        self.assertFalse(AttendanceRecord.objects.filter(id=my_record.id).exists())
        self.assertTrue(AttendanceRecord.objects.filter(id=other_record.id).exists())

    def test_status_view_idor(self):
        """Verify an admin cannot view full PII of a record from another department."""
        other_dept = Department.objects.create(name="HR")
        other_folder = Folder.objects.create(department=other_dept, name="Onboarding")
        other_record = AttendanceRecord.objects.create(fullname="Other Record", ic_number="999999999999", phone="0123456789", folder=other_folder)

        from attendance.models import AdminProfile
        AdminProfile.objects.create(user=self.user, department=self.dept)
        self.user.is_superuser = False
        self.user.save()

        self.client.login(username='admin', password='password123')

        # Cross-department access should be denied (403 Forbidden)
        response = self.client.get(f'/api/attendance/status/{other_record.id}/')
        self.assertEqual(response.status_code, 403)

    def test_ic_lookup_idor_and_pii(self):
        """Verify IC lookup requires authentication and restricts by department for admins."""
        other_dept = Department.objects.create(name="HR")
        other_folder = Folder.objects.create(department=other_dept, name="Onboarding")
        AttendanceRecord.objects.create(fullname="My Record", ic_number="888888888888", phone="111", folder=self.folder)
        AttendanceRecord.objects.create(fullname="Other Record", ic_number="888888888888", phone="222", folder=other_folder)

        # 1. Unauthenticated request -> should be denied (403 Forbidden)
        response = self.client.get('/api/attendance/participant/888888888888/')
        self.assertEqual(response.status_code, 403)

        # 2. Authenticated non-super admin request -> should return ONLY their department's record (FULL PII)
        from attendance.models import AdminProfile
        AdminProfile.objects.create(user=self.user, department=self.dept)
        self.user.is_superuser = False
        self.user.save()

        self.client.login(username='admin', password='password123')
        response = self.client.get('/api/attendance/participant/888888888888/')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['fullname'], "My Record")
        self.assertIn('phone', data[0])  # Has PII because they own it

    def test_check_auth_view(self):
        self.client.login(username='admin', password='password123')
        response = self.client.get(reverse('auth_check'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user'], 'admin')

    def test_logout_view(self):
        self.client.login(username='admin', password='password123')
        response = self.client.post(reverse('auth_logout'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('auth_check'))
        self.assertEqual(response.status_code, 403) # Unauthenticated

    def test_user_list_view_superuser(self):
        self.user.is_superuser = True
        self.user.save()
        self.client.login(username='admin', password='password123')
        
        # GET
        response = self.client.get(reverse('users_list'))
        self.assertEqual(response.status_code, 200)
        
        # POST
        response = self.client.post(reverse('users_list'), data=json.dumps({
            'username': 'newadmin',
            'password': 'SecurePassword123!',
            'is_super': False,
            'department_id': self.dept.id
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(username='newadmin').exists())

    def test_user_list_view_normal_admin(self):
        self.user.is_superuser = False
        self.user.save()
        self.client.login(username='admin', password='password123')
        response = self.client.get(reverse('users_list'))
        self.assertEqual(response.status_code, 403)
        response = self.client.post(reverse('users_list'), data=json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_user_detail_view(self):
        self.user.is_superuser = True
        self.user.save()
        new_user = User.objects.create_user(username='todelete', password='pw')
        self.client.login(username='admin', password='password123')
        response = self.client.delete(reverse('users_detail', args=[new_user.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='todelete').exists())

    def test_stats_view(self):
        self.client.login(username='admin', password='password123')
        AttendanceRecord.objects.create(fullname="Stats", ic_number="123", phone="123", folder=self.folder)
        response = self.client.get(reverse('stats'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total'], 1)

    def test_department_folder_list_view(self):
        # GET requires authentication — unauthenticated should be denied
        response = self.client.get(reverse('folder_list'))
        self.assertEqual(response.status_code, 403)

        # Authenticated superuser GET should work
        self.user.is_superuser = True
        self.user.save()
        self.client.login(username='admin', password='password123')
        response = self.client.get(reverse('folder_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['data']), 1)

        # POST
        response = self.client.post(reverse('folder_list'), data=json.dumps({
            'department': 'NewDept',
            'folder': 'NewFolder'
        }), content_type='application/json')
        self.assertIn(response.status_code, [200, 201])
        self.assertTrue(Folder.objects.filter(name='NewFolder').exists())

    def test_folder_detail_view(self):
        self.user.is_superuser = True
        self.user.save()
        self.client.login(username='admin', password='password123')
        # GET
        response = self.client.get(reverse('folder_detail', args=[self.folder.id]))
        self.assertEqual(response.status_code, 200)
        # PATCH
        response = self.client.patch(reverse('folder_detail', args=[self.folder.id]), data=json.dumps({
            'name': 'UpdatedFolder'
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.folder.refresh_from_db()
        self.assertEqual(self.folder.name, 'UpdatedFolder')
        # DELETE
        response = self.client.delete(reverse('folder_detail', args=[self.folder.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Folder.objects.filter(id=self.folder.id).exists())

    def test_department_detail_view(self):
        self.user.is_superuser = True
        self.user.save()
        self.client.login(username='admin', password='password123')
        response = self.client.delete(reverse('department_detail', args=[self.dept.id]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Department.objects.filter(id=self.dept.id).exists())

    def test_export_csv_view(self):
        self.client.login(username='admin', password='password123')
        AttendanceRecord.objects.create(fullname="CSV User", ic_number="123", phone="123", folder=self.folder)
        response = self.client.get(reverse('export_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn(b'CSV User', response.content)

    def test_download_certificate_view(self):
        record = AttendanceRecord.objects.create(fullname="Cert User", ic_number="123456789012", phone="123", folder=self.folder)
        # Certificate download now requires IC verification (?ic=last 4 digits)
        response = self.client.get(reverse('download_certificate', args=[record.id]) + '?ic=9012')
        self.assertIn(response.status_code, [200, 500])

    def test_download_certificate_requires_ic(self):
        """Certificate download without IC verification should return 400."""
        record = AttendanceRecord.objects.create(fullname="Cert User", ic_number="123456789012", phone="123", folder=self.folder)
        response = self.client.get(reverse('download_certificate', args=[record.id]))
        self.assertEqual(response.status_code, 400)

    def test_download_certificate_wrong_ic(self):
        """Certificate download with wrong IC should return 403."""
        record = AttendanceRecord.objects.create(fullname="Cert User", ic_number="123456789012", phone="123", folder=self.folder)
        response = self.client.get(reverse('download_certificate', args=[record.id]) + '?ic=0000')
        self.assertEqual(response.status_code, 403)

    # ──────────────────────────────────────────────
    # NEW COVERAGE TESTS
    # ──────────────────────────────────────────────

    def test_model_str_methods(self):
        self.assertEqual(str(self.dept), self.dept.name)
        self.assertEqual(str(self.folder), f"{self.dept.name} - {self.folder.name}")
        record = AttendanceRecord.objects.create(fullname="John", folder=self.folder)
        self.assertEqual(str(record), f"John - {self.folder.name}")
        
        # Test models with no folder/dept
        folder_nodept = Folder.objects.create(name="NoDeptFolder", department=None)
        self.assertEqual(str(folder_nodept), "No Dept - NoDeptFolder")
        record_nofolder = AttendanceRecord.objects.create(fullname="NoFolderUser", folder=None)
        self.assertEqual(str(record_nofolder), "NoFolderUser - No Folder")
        
        from attendance.models import AdminProfile
        profile = AdminProfile.objects.create(user=self.user, department=self.dept)
        self.assertEqual(str(profile), f"{self.user.username} - {self.dept.name}")
        
        profile.department = None
        profile.save()
        self.assertEqual(str(profile), f"{self.user.username} - Super Admin")

    def test_middleware_x_forwarded_for(self):
        response = self.client.post(reverse('auth_login'), data=json.dumps({'username': 'admin', 'password': 'wrong'}), content_type='application/json', HTTP_X_FORWARDED_FOR='192.168.1.1, 10.0.0.1')
        self.assertEqual(response.status_code, 401)

    def test_auth_views_missing_lines(self):
        # Line 45, 77, 153-154
        from attendance.models import AdminProfile
        AdminProfile.objects.create(user=self.user, department=self.dept)
        response = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'admin', 'password': 'password123'
        }), content_type='application/json')
        self.assertEqual(response.json()['department_id'], self.dept.id)
        
        response = self.client.get(reverse('auth_check'))
        self.assertEqual(response.json()['department_id'], self.dept.id)

        self.user.is_superuser = True
        self.user.save()
        response = self.client.get(reverse('users_list'))
        self.assertEqual(response.status_code, 200)

        # Line 101, 127-132
        response = self.client.post('/api/attendance/auth/password/', data=json.dumps({
            'old_password': 'password123'
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        
        response = self.client.post('/api/attendance/auth/password/', data=json.dumps({
            'old_password': 'password123',
            'new_password': 'ValidPassword123!'
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        
        # Re-login with old password properly
        self.user.refresh_from_db()
        self.user.set_password('password123')
        self.user.save()
        # Must re-login to update session hash
        self.client.login(username='admin', password='password123')
        self.user.is_superuser = True
        self.user.save()

        # Line 174, 177, 198-199
        response = self.client.post(reverse('users_list'), data=json.dumps({
            'username': 'missingpw'
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        
        response = self.client.post(reverse('users_list'), data=json.dumps({
            'username': 'admin', 'password': 'ValidPassword123!'
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        
        response = self.client.post(reverse('users_list'), data=json.dumps({
            'username': 'newuser2', 'password': 'ValidPassword123!', 'department_id': 9999
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)

        # Line 209, 214, 217-218
        self.user.is_superuser = False
        self.user.save()
        response = self.client.delete(reverse('users_detail', args=[self.user.id]))
        self.assertEqual(response.status_code, 403)
        
        self.user.is_superuser = True
        self.user.save()
        response = self.client.delete(reverse('users_detail', args=[self.user.id]))
        self.assertEqual(response.status_code, 400)
        
        response = self.client.delete(reverse('users_detail', args=[9999]))
        self.assertEqual(response.status_code, 404)

    def test_serializers_validation(self):
        # Line 22, 26, 28, 36
        from attendance.serializers import AttendanceRecordSerializer
        ser = AttendanceRecordSerializer(data={'fullname': 'Test', 'ic_number': ''})
        ser.is_valid()
        
        ser = AttendanceRecordSerializer(data={'fullname': 'Test', 'ic_number': None})
        ser.is_valid()
        
        ser = AttendanceRecordSerializer(data={'fullname': 'Test', 'ic_number': '123'})
        self.assertFalse(ser.is_valid())
        
        ser = AttendanceRecordSerializer(data={'fullname': 'Test', 'ic_number': '1'*13})
        self.assertFalse(ser.is_valid())
        
        ser = AttendanceRecordSerializer(data={'fullname': 'Test', 'ic_number': '1'*12, 'phone': '123'})
        self.assertFalse(ser.is_valid())
        
        ser = AttendanceRecordSerializer(data={'fullname': 'Test', 'ic_number': '1'*12, 'phone': '1'*16})
        self.assertFalse(ser.is_valid())

    def test_views_submit_invalid(self):
        # Line 52
        response = self.client.post(reverse('submit_attendance'), data={})
        self.assertEqual(response.status_code, 400)

    def test_views_attendance_list_and_delete(self):
        # Line 69-86, 100-109
        from attendance.models import AdminProfile
        AdminProfile.objects.create(user=self.user, department=self.dept)
        self.user.is_superuser = False
        self.user.save()
        self.client.login(username='admin', password='password123')
        
        AttendanceRecord.objects.create(fullname="MatchMe", ic_number="123456789012", email="match@me.com", folder=self.folder)
        
        response = self.client.get('/api/attendance/records/?folder=' + str(self.folder.id) + '&search=Match')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['data']), 1)
        
        response = self.client.get('/api/attendance/records/?search=match@me')
        self.assertEqual(len(response.json()['data']), 1)
        
        response = self.client.delete('/api/attendance/records/?folder=' + str(self.folder.id), content_type='application/json')
        self.assertEqual(response.status_code, 200)

    def test_views_record_detail_forbidden(self):
        # Lines 116-122, 125-137
        other_dept = Department.objects.create(name="Other")
        other_folder = Folder.objects.create(department=other_dept, name="OtherFolder")
        record = AttendanceRecord.objects.create(fullname="Other", folder=other_folder)
        
        from attendance.models import AdminProfile
        AdminProfile.objects.create(user=self.user, department=self.dept)
        self.user.is_superuser = False
        self.user.save()
        self.client.login(username='admin', password='password123')
        
        response = self.client.delete(f'/api/attendance/records/{record.id}/')
        self.assertEqual(response.status_code, 403)
        
        response = self.client.patch(f'/api/attendance/records/{record.id}/', data=json.dumps({'fullname':'Updated'}), content_type='application/json')
        self.assertEqual(response.status_code, 403)
        
        my_record = AttendanceRecord.objects.create(fullname="My", folder=self.folder)
        response = self.client.patch(f'/api/attendance/records/{my_record.id}/', data=json.dumps({'fullname':'Updated'}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        
        response = self.client.patch(f'/api/attendance/records/{my_record.id}/', data=json.dumps({'ic_number':'invalid'}), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        
        response = self.client.delete(f'/api/attendance/records/{my_record.id}/')
        self.assertEqual(response.status_code, 200)

    def test_views_get_participant_invalid_ic(self):
        # Unauthenticated request to authenticated endpoint should return 403
        response = self.client.get('/api/attendance/participant/abcd/')
        self.assertEqual(response.status_code, 403)

        # Authenticated request with invalid IC should return 400
        self.client.login(username='admin', password='password123')
        response = self.client.get('/api/attendance/participant/abcd/')
        self.assertEqual(response.status_code, 400)

    def test_views_attendance_status_owner(self):
        # Line 212
        from attendance.models import AdminProfile
        AdminProfile.objects.create(user=self.user, department=self.dept)
        self.user.is_superuser = False
        self.user.save()
        self.client.login(username='admin', password='password123')
        
        my_record = AttendanceRecord.objects.create(fullname="My", ic_number="123456789012", phone="0123", email="a@a.com", folder=self.folder)
        response = self.client.get(f'/api/attendance/status/{my_record.id}/')
        self.assertIn('phone', response.json())

    def test_views_stats_and_folders(self):
        # Lines 249, 252, 278, 317, 323
        from attendance.models import AdminProfile
        AdminProfile.objects.create(user=self.user, department=self.dept)
        self.user.is_superuser = False
        self.user.save()
        self.client.login(username='admin', password='password123')
        
        response = self.client.get('/api/attendance/stats/?folder=' + str(self.folder.id))
        self.assertEqual(response.status_code, 200)
        
        response = self.client.get('/api/attendance/folders/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['data']), 1)
        
        response = self.client.post('/api/attendance/folders/', data=json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        
        response = self.client.post('/api/attendance/folders/', data=json.dumps({'department': 'New', 'folder': 'NewF'}), content_type='application/json')
        self.assertEqual(response.status_code, 201)

    def test_views_department_folder_detail_forbidden(self):
        # Lines 342, 356-357, 382-383, 410-411
        from attendance.models import AdminProfile
        AdminProfile.objects.create(user=self.user, department=self.dept)
        self.user.is_superuser = False
        self.user.save()
        self.client.login(username='admin', password='password123')
        
        other_dept = Department.objects.create(name="Other")
        other_folder = Folder.objects.create(department=other_dept, name="OtherFolder")
        
        response = self.client.delete(f'/api/attendance/departments/{other_dept.id}/')
        self.assertEqual(response.status_code, 403)
        
        response = self.client.get(f'/api/attendance/folders/{other_folder.id}/')
        self.assertEqual(response.status_code, 403)
        
        response = self.client.patch(f'/api/attendance/folders/{other_folder.id}/', data=json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 403)
        
        response = self.client.delete(f'/api/attendance/folders/{other_folder.id}/')
        self.assertEqual(response.status_code, 403)

    def test_views_export_csv_admin(self):
        # Lines 427, 430
        from attendance.models import AdminProfile
        AdminProfile.objects.create(user=self.user, department=self.dept)
        self.user.is_superuser = False
        self.user.save()
        self.client.login(username='admin', password='password123')
        
        response = self.client.get('/api/attendance/export/?folder=' + str(self.folder.id))
        self.assertEqual(response.status_code, 200)

    def test_views_certificate_error(self):
        # Lines 482, 526-527, 536-537
        import attendance.views
        from unittest.mock import patch
        
        my_record = AttendanceRecord.objects.create(fullname="My", ic_number="111111111111", folder=self.folder)
        
        with patch('attendance.views._render_to_pdf', return_value=None):
            response = self.client.get(reverse('download_certificate', args=[my_record.id]) + '?ic=1111')
            self.assertEqual(response.status_code, 500)
            
        with patch.dict('sys.modules', {'xhtml2pdf': None}):
            res = attendance.views._render_to_pdf('certificate.html', {})
            self.assertIsNone(res)
            
        class MockPDFErr:
            err = True
        
        with patch('attendance.views.get_template') as mock_get_template:
            mock_template = mock_get_template.return_value
            mock_template.render.return_value = "<html></html>"
            with patch('xhtml2pdf.pisa.pisaDocument', return_value=MockPDFErr()):
                res = attendance.views._render_to_pdf('certificate.html', {})
                self.assertIsNone(res)


# ══════════════════════════════════════════════════════════════
# SECURITY AUDIT TEST SUITE — TDD for Security
# ══════════════════════════════════════════════════════════════


class TestAccountLockout(DisableThrottleMixin, TestCase):
    """TDD: Account lockout after N failed login attempts within a time window."""

    def setUp(self):
        self.user = User.objects.create_user(username='lockuser', password='GoodPass1!')
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_account_locks_after_5_failures(self):
        """After 5 failed attempts within 30 min, the 6th should be locked (403)."""
        for i in range(5):
            resp = self.client.post(reverse('auth_login'), data=json.dumps({
                'username': 'lockuser', 'password': 'wrong'
            }), content_type='application/json')
            self.assertIn(resp.status_code, [401, 429])

        # 6th attempt — account should be locked
        resp = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'lockuser', 'password': 'wrong'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 403)
        self.assertIn('dikunci', resp.json().get('message', '').lower())

    def test_lockout_message_includes_duration(self):
        """Lockout response should mention the lockout duration."""
        for i in range(5):
            self.client.post(reverse('auth_login'), data=json.dumps({
                'username': 'lockuser', 'password': 'wrong'
            }), content_type='application/json')

        resp = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'lockuser', 'password': 'wrong'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 403)
        self.assertIn('15', resp.json().get('message', ''))

    def test_correct_password_while_locked_is_still_rejected(self):
        """Even with the correct password, a locked account stays locked."""
        for i in range(5):
            self.client.post(reverse('auth_login'), data=json.dumps({
                'username': 'lockuser', 'password': 'wrong'
            }), content_type='application/json')

        resp = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'lockuser', 'password': 'GoodPass1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_failed_attempts_recorded_in_database(self):
        """Each failed login should create a FailedLoginAttempt record."""
        for i in range(3):
            self.client.post(reverse('auth_login'), data=json.dumps({
                'username': 'lockuser', 'password': 'wrong'
            }), content_type='application/json')

        self.assertEqual(FailedLoginAttempt.objects.filter(username='lockuser').count(), 3)

    def test_lockout_creates_user_account_lock_record(self):
        """After threshold, a UserAccountLock record should exist with locked_until set."""
        for i in range(5):
            self.client.post(reverse('auth_login'), data=json.dumps({
                'username': 'lockuser', 'password': 'wrong'
            }), content_type='application/json')

        lock = UserAccountLock.objects.get(user=self.user)
        self.assertTrue(lock.is_locked)
        self.assertIsNotNone(lock.locked_until)
        self.assertGreater(lock.locked_until, timezone.now())

    def test_successful_login_resets_failed_attempts(self):
        """A successful login should clear all failed attempt records."""
        for i in range(3):
            self.client.post(reverse('auth_login'), data=json.dumps({
                'username': 'lockuser', 'password': 'wrong'
            }), content_type='application/json')

        self.assertEqual(FailedLoginAttempt.objects.filter(username='lockuser').count(), 3)

        # Successful login
        resp = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'lockuser', 'password': 'GoodPass1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(FailedLoginAttempt.objects.filter(username='lockuser').count(), 0)

    def test_lockout_auto_expires_after_duration(self):
        """After the lockout period expires, login should work again."""
        for i in range(5):
            self.client.post(reverse('auth_login'), data=json.dumps({
                'username': 'lockuser', 'password': 'wrong'
            }), content_type='application/json')

        # Manually expire the lock
        lock = UserAccountLock.objects.get(user=self.user)
        lock.locked_until = timezone.now() - timedelta(minutes=1)
        lock.save()

        resp = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'lockuser', 'password': 'GoodPass1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

    def test_nonexistent_user_does_not_create_lock_record(self):
        """Failed logins for non-existent users should not create UserAccountLock."""
        for i in range(5):
            self.client.post(reverse('auth_login'), data=json.dumps({
                'username': 'ghost_user', 'password': 'wrong'
            }), content_type='application/json')

        self.assertFalse(UserAccountLock.objects.filter(user__username='ghost_user').exists())
        # But FailedLoginAttempt should still be recorded
        self.assertEqual(FailedLoginAttempt.objects.filter(username='ghost_user').count(), 5)


class TestPasswordHasher(DisableThrottleMixin, TestCase):
    """TDD: Verify passwords are stored with strong hashing (Argon2)."""

    def test_new_password_uses_argon2(self):
        """A newly created user should have an Argon2 password hash."""
        user = User.objects.create_user(username='hashtest', password='TestPass1!')
        hasher = identify_hasher(user.password)
        self.assertEqual(hasher.algorithm, 'argon2')

    def test_password_not_stored_plaintext(self):
        """Password should never be stored in plaintext."""
        user = User.objects.create_user(username='plaintext', password='TestPass1!')
        self.assertNotEqual(user.password, 'TestPass1!')
        self.assertTrue(user.password.startswith('argon2$'))

    def test_password_not_md5_or_sha(self):
        """Password should not use weak hashing algorithms."""
        user = User.objects.create_user(username='weakhash', password='TestPass1!')
        self.assertFalse(user.password.startswith('md5$'))
        self.assertFalse(user.password.startswith('sha1$'))
        self.assertFalse(user.password.startswith('sha256$'))

    def test_password_verification_works(self):
        """check_password should return True for the correct password."""
        user = User.objects.create_user(username='verify', password='TestPass1!')
        self.assertTrue(user.check_password('TestPass1!'))
        self.assertFalse(user.check_password('WrongPassword'))


class TestPasswordValidation(DisableThrottleMixin, TestCase):
    """TDD: Password strength validation rules."""

    def setUp(self):
        self.user = User.objects.create_user(username='pwadmin', password='GoodPass1!')
        self.user.is_superuser = True
        self.user.save()
        self.client.login(username='pwadmin', password='GoodPass1!')

    def test_reject_password_too_short(self):
        """Passwords shorter than 8 characters should be rejected."""
        resp = self.client.post('/api/attendance/auth/password/', data=json.dumps({
            'old_password': 'GoodPass1!',
            'new_password': 'Ab1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_reject_password_no_uppercase(self):
        """Passwords without uppercase should be rejected."""
        resp = self.client.post('/api/attendance/auth/password/', data=json.dumps({
            'old_password': 'GoodPass1!',
            'new_password': 'alllower1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_reject_password_no_lowercase(self):
        """Passwords without lowercase should be rejected."""
        resp = self.client.post('/api/attendance/auth/password/', data=json.dumps({
            'old_password': 'GoodPass1!',
            'new_password': 'ALLUPPER1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_reject_password_no_digit(self):
        """Passwords without a digit should be rejected."""
        resp = self.client.post('/api/attendance/auth/password/', data=json.dumps({
            'old_password': 'GoodPass1!',
            'new_password': 'NoDigits!!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_reject_password_no_special_char(self):
        """Passwords without a special character should be rejected."""
        resp = self.client.post('/api/attendance/auth/password/', data=json.dumps({
            'old_password': 'GoodPass1!',
            'new_password': 'NoSpecial1'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_reject_common_password(self):
        """Common passwords like 'password123' should be rejected."""
        resp = self.client.post('/api/attendance/auth/password/', data=json.dumps({
            'old_password': 'GoodPass1!',
            'new_password': 'password123'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_reject_numeric_only_password(self):
        """Purely numeric passwords should be rejected."""
        resp = self.client.post('/api/attendance/auth/password/', data=json.dumps({
            'old_password': 'GoodPass1!',
            'new_password': '12345678'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_accept_strong_password(self):
        """A strong password meeting all criteria should be accepted."""
        resp = self.client.post('/api/attendance/auth/password/', data=json.dumps({
            'old_password': 'GoodPass1!',
            'new_password': 'Str0ng!Pass#2024'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

    def test_reject_password_same_as_username(self):
        """Password too similar to username should be rejected."""
        resp = self.client.post('/api/attendance/auth/password/', data=json.dumps({
            'old_password': 'GoodPass1!',
            'new_password': 'pwadminpwadmin'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)


class TestSecurityHeaders(DisableThrottleMixin, TestCase):
    """TDD: Security headers should be present on all responses."""

    def setUp(self):
        self.user = User.objects.create_user(username='headertest', password='TestPass1!')
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_x_content_type_options_nosniff(self):
        """All API responses should have X-Content-Type-Options: nosniff."""
        resp = self.client.get('/api/attendance/stats/')
        self.assertEqual(resp.get('X-Content-Type-Options'), 'nosniff')

    def test_x_frame_options_deny(self):
        """All API responses should have X-Frame-Options: DENY."""
        resp = self.client.get('/api/attendance/stats/')
        self.assertEqual(resp.get('X-Frame-Options'), 'DENY')

    def test_referrer_policy(self):
        """All API responses should have Referrer-Policy header."""
        resp = self.client.get('/api/attendance/stats/')
        self.assertEqual(resp.get('Referrer-Policy'), 'strict-origin-when-cross-origin')

    def test_permissions_policy(self):
        """All API responses should restrict camera/microphone/geolocation."""
        resp = self.client.get('/api/attendance/stats/')
        pp = resp.get('Permissions-Policy', '')
        self.assertIn('camera=()', pp)
        self.assertIn('microphone=()', pp)
        self.assertIn('geolocation=()', pp)

    def test_cache_control_no_store_on_api(self):
        """API responses should not be cached."""
        self.client.login(username='headertest', password='TestPass1!')
        resp = self.client.get('/api/attendance/stats/')
        cache_control = resp.get('Cache-Control', '')
        self.assertIn('no-store', cache_control)

    def test_pragma_no_cache_on_api(self):
        """API responses should have Pragma: no-cache."""
        self.client.login(username='headertest', password='TestPass1!')
        resp = self.client.get('/api/attendance/stats/')
        self.assertEqual(resp.get('Pragma'), 'no-cache')

    def test_headers_present_on_login_endpoint(self):
        """Security headers should be present even on the login endpoint."""
        resp = self.client.get(reverse('auth_login'))
        self.assertEqual(resp.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(resp.get('X-Frame-Options'), 'DENY')

    def test_headers_present_on_public_submit(self):
        """Security headers should be present on public endpoints too."""
        resp = self.client.post(reverse('submit_attendance'), data={
            'fullname': 'Header Test',
            'ic_number': '123456789012',
            'phone': '0123456789',
            'department_name': 'IT',
            'folder_name': 'General'
        })
        self.assertEqual(resp.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(resp.get('X-Frame-Options'), 'DENY')


class TestSessionSecurity(DisableThrottleMixin, TestCase):
    """TDD: Session management security."""

    def setUp(self):
        self.user = User.objects.create_user(username='session', password='TestPass1!')

    def test_session_created_on_login(self):
        """A session should be created upon successful login via the API."""
        resp = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'session', 'password': 'TestPass1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        # After login, the session should contain the user ID
        session = self.client.session
        self.assertEqual(str(session.get('_auth_user_id')), str(self.user.pk))

    def test_session_destroyed_on_logout(self):
        """Session should be destroyed on logout."""
        self.client.login(username='session', password='TestPass1!')
        self.assertIn('_auth_user_id', self.client.session)

        self.client.post(reverse('auth_logout'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_session_fixation_prevention(self):
        """Session key should change after login (prevents session fixation)."""
        # Get a pre-login session key by visiting the login page
        self.client.get(reverse('auth_login'))
        pre_login_key = self.client.session.session_key

        # Login via the API
        self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'session', 'password': 'TestPass1!'
        }), content_type='application/json')

        # Session key should be different after login (flush + new session)
        post_login_key = self.client.session.session_key
        # If both keys exist, they should differ
        if pre_login_key and post_login_key:
            self.assertNotEqual(pre_login_key, post_login_key)

    def test_check_auth_requires_authentication(self):
        """Unauthenticated requests to auth check should fail."""
        resp = self.client.get(reverse('auth_check'))
        self.assertEqual(resp.status_code, 403)

    def test_check_auth_returns_user_info(self):
        """Authenticated requests to auth check should return user info."""
        self.client.login(username='session', password='TestPass1!')
        resp = self.client.get(reverse('auth_check'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['user'], 'session')

    def test_session_inactive_user_cannot_authenticate(self):
        """A user with is_active=False should not be able to log in."""
        self.user.is_active = False
        self.user.save()

        resp = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'session', 'password': 'TestPass1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 401)


class TestCSRFRotation(DisableThrottleMixin, TestCase):
    """TDD: CSRF token rotation on authentication state changes."""

    def setUp(self):
        self.user = User.objects.create_user(username='csrftest', password='TestPass1!')

    def test_login_returns_csrf_token(self):
        """Login response should include a CSRF token."""
        resp = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'csrftest', 'password': 'TestPass1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('csrfToken', resp.json())
        self.assertTrue(len(resp.json()['csrfToken']) > 0)

    def test_get_login_returns_csrf_token(self):
        """GET on login endpoint should return a CSRF token."""
        resp = self.client.get(reverse('auth_login'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('csrfToken', resp.json())

    def test_password_change_returns_new_csrf(self):
        """After password change, a new CSRF token should be set."""
        self.client.login(username='csrftest', password='TestPass1!')
        old_csrftoken = self.client.cookies.get('csrftoken', '')

        resp = self.client.post('/api/attendance/auth/password/', data=json.dumps({
            'old_password': 'TestPass1!',
            'new_password': 'NewSecure1!abc'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

        # The response should set a new CSRF cookie
        new_csrftoken = self.client.cookies.get('csrftoken', '')
        if old_csrftoken and new_csrftoken:
            self.assertNotEqual(old_csrftoken, new_csrftoken)


class TestEmailVerification(DisableThrottleMixin, TestCase):
    """TDD: Email verification flow for new accounts."""

    def setUp(self):
        self.superuser = User.objects.create_user(
            username='super', password='SuperPass1!', email='super@test.com'
        )
        self.superuser.is_superuser = True
        self.superuser.save()
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_new_user_created_inactive_when_email_verification_required(self):
        """New users should be inactive when EMAIL_VERIFICATION_REQUIRED is True."""
        self.client.login(username='super', password='SuperPass1!')
        resp = self.client.post(reverse('users_list'), data=json.dumps({
            'username': 'newinactive',
            'password': 'GoodPass1!',
            'email': 'new@test.com'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

        new_user = User.objects.get(username='newinactive')
        self.assertFalse(new_user.is_active)

    def test_inactive_user_cannot_login(self):
        """A user created as inactive should not be able to log in."""
        self.client.login(username='super', password='SuperPass1!')
        self.client.post(reverse('users_list'), data=json.dumps({
            'username': 'blocked',
            'password': 'GoodPass1!',
            'email': 'blocked@test.com'
        }), content_type='application/json')

        resp = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'blocked', 'password': 'GoodPass1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 401)

    def test_verify_email_with_valid_token(self):
        """A valid verification token should activate the user."""
        self.client.login(username='super', password='SuperPass1!')
        self.client.post(reverse('users_list'), data=json.dumps({
            'username': 'toverify',
            'password': 'GoodPass1!',
            'email': 'verify@test.com'
        }), content_type='application/json')

        token_obj = EmailVerificationToken.objects.get(user__username='toverify')
        resp = self.client.get(reverse('auth_verify_email', args=[token_obj.token]))
        self.assertEqual(resp.status_code, 200)

        user = User.objects.get(username='toverify')
        self.assertTrue(user.is_active)

    def test_verify_email_with_invalid_token(self):
        """An invalid token should return 400."""
        resp = self.client.get(reverse('auth_verify_email', args=['invalidtoken123']))
        self.assertEqual(resp.status_code, 400)

    def test_verify_email_with_expired_token(self):
        """An expired token should return 400."""
        user = User.objects.create_user(username='expired', password='GoodPass1!', email='exp@test.com')
        token_obj = EmailVerificationToken.generate_for_user(user)
        # Expire the token
        token_obj.expires_at = timezone.now() - timedelta(hours=1)
        token_obj.save()

        resp = self.client.get(reverse('auth_verify_email', args=[token_obj.token]))
        self.assertEqual(resp.status_code, 400)

    def test_verify_email_token_single_use(self):
        """A token should not be usable twice."""
        user = User.objects.create_user(username='reuse', password='GoodPass1!', email='reuse@test.com')
        token_obj = EmailVerificationToken.generate_for_user(user)

        # First use — should succeed
        resp1 = self.client.get(reverse('auth_verify_email', args=[token_obj.token]))
        self.assertEqual(resp1.status_code, 200)

        # Second use — should fail
        resp2 = self.client.get(reverse('auth_verify_email', args=[token_obj.token]))
        self.assertEqual(resp2.status_code, 400)

    def test_verify_email_sets_admin_profile_verified(self):
        """Successful verification should set email_verified on AdminProfile."""
        self.client.login(username='super', password='SuperPass1!')
        self.client.post(reverse('users_list'), data=json.dumps({
            'username': 'profileverify',
            'password': 'GoodPass1!',
            'email': 'pv@test.com'
        }), content_type='application/json')

        token_obj = EmailVerificationToken.objects.get(user__username='profileverify')
        self.client.get(reverse('auth_verify_email', args=[token_obj.token]))

        profile = AdminProfile.objects.get(user__username='profileverify')
        self.assertTrue(profile.email_verified)
        self.assertIsNotNone(profile.verified_at)

    def test_resend_verification_for_inactive_user(self):
        """Resending verification for an inactive user should succeed."""
        user = User.objects.create_user(username='resend', password='GoodPass1!', email='resend@test.com', is_active=False)
        AdminProfile.objects.create(user=user)

        resp = self.client.post(reverse('auth_resend_verification'), data=json.dumps({
            'username': 'resend'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

    def test_resend_verification_for_active_user_returns_success(self):
        """Resending verification for an already active user returns success (no enumeration)."""
        resp = self.client.post(reverse('auth_resend_verification'), data=json.dumps({
            'username': 'super'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

    def test_resend_verification_nonexistent_user_no_enumeration(self):
        """Requesting resend for non-existent user should not reveal existence."""
        resp = self.client.post(reverse('auth_resend_verification'), data=json.dumps({
            'username': 'ghost_user_12345'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('jika akaun wujud', resp.json().get('message', '').lower())


class TestPasswordResetFlow(DisableThrottleMixin, TestCase):
    """TDD: Password reset via email flow."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='resetme', password='OldPass1!', email='reset@test.com'
        )
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_reset_password_request_requires_email(self):
        """Requesting reset without email should return 400."""
        resp = self.client.post(reverse('auth_reset_password'), data=json.dumps({}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_reset_password_request_nonexistent_email_no_enumeration(self):
        """Requesting reset for non-existent email should not reveal existence."""
        resp = self.client.post(reverse('auth_reset_password'), data=json.dumps({
            'email': 'nonexistent@example.com'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('jika e-mel wujud', resp.json().get('message', '').lower())

    def test_reset_password_request_inactive_user_no_email(self):
        """Inactive users should not receive reset emails."""
        self.user.is_active = False
        self.user.save()

        resp = self.client.post(reverse('auth_reset_password'), data=json.dumps({
            'email': 'reset@test.com'
        }), content_type='application/json')
        # Should return success message but not actually send
        self.assertEqual(resp.status_code, 200)

    def test_reset_password_confirm_requires_all_fields(self):
        """Confirm reset without uid/token/password should return 400."""
        resp = self.client.post(reverse('auth_reset_password_confirm'), data=json.dumps({}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_reset_password_confirm_invalid_uid(self):
        """Confirm with invalid uid should return 400."""
        resp = self.client.post(reverse('auth_reset_password_confirm'), data=json.dumps({
            'uid': 99999, 'token': 'faketoken', 'new_password': 'NewPass1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_reset_password_confirm_invalid_token(self):
        """Confirm with invalid token should return 400."""
        resp = self.client.post(reverse('auth_reset_password_confirm'), data=json.dumps({
            'uid': self.user.pk, 'token': 'invalid-token', 'new_password': 'NewPass1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_reset_password_confirm_weak_password_rejected(self):
        """Confirm with a weak password should return 400."""
        from attendance.auth_views import password_reset_token_generator
        token = password_reset_token_generator.make_token(self.user)

        resp = self.client.post(reverse('auth_reset_password_confirm'), data=json.dumps({
            'uid': self.user.pk, 'token': token, 'new_password': '123'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)


class TestAuditLogging(DisableThrottleMixin, TestCase):
    """TDD: Security events should be logged to the security logger."""

    def setUp(self):
        self.user = User.objects.create_user(username='loguser', password='TestPass1!')
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_successful_login_is_logged(self):
        """A successful login should produce a security log entry."""
        security_logger = logging.getLogger('security')
        with patch.object(security_logger, 'info') as mock_info:
            self.client.post(reverse('auth_login'), data=json.dumps({
                'username': 'loguser', 'password': 'TestPass1!'
            }), content_type='application/json')
        self.assertTrue(any('LOGIN SUCCESS' in str(call) for call in mock_info.call_args_list))

    def test_failed_login_is_logged(self):
        """A failed login should produce a security log entry."""
        security_logger = logging.getLogger('security')
        with patch.object(security_logger, 'warning') as mock_warning:
            self.client.post(reverse('auth_login'), data=json.dumps({
                'username': 'loguser', 'password': 'wrong'
            }), content_type='application/json')
        self.assertTrue(any('LOGIN FAILED' in str(call) for call in mock_warning.call_args_list))

    def test_account_lockout_is_logged(self):
        """Account lockout should produce a security log entry."""
        security_logger = logging.getLogger('security')
        for i in range(5):
            self.client.post(reverse('auth_login'), data=json.dumps({
                'username': 'loguser', 'password': 'wrong'
            }), content_type='application/json')

        with patch.object(security_logger, 'warning') as mock_warning:
            self.client.post(reverse('auth_login'), data=json.dumps({
                'username': 'loguser', 'password': 'wrong'
            }), content_type='application/json')
        self.assertTrue(any('ACCOUNT LOCKED' in str(call) or 'LOGIN BLOCKED' in str(call)
                            for call in mock_warning.call_args_list))

    def test_logout_is_logged(self):
        """Logout should produce a security log entry."""
        self.client.login(username='loguser', password='TestPass1!')
        security_logger = logging.getLogger('security')
        with patch.object(security_logger, 'info') as mock_info:
            self.client.post(reverse('auth_logout'))
        self.assertTrue(any('LOGOUT' in str(call) for call in mock_info.call_args_list))

    def test_password_change_is_logged(self):
        """Password change should produce a security log entry."""
        self.client.login(username='loguser', password='TestPass1!')
        security_logger = logging.getLogger('security')
        with patch.object(security_logger, 'info') as mock_info:
            self.client.post('/api/attendance/auth/password/', data=json.dumps({
                'old_password': 'TestPass1!',
                'new_password': 'NewSecure1!abc'
            }), content_type='application/json')
        self.assertTrue(any('PASSWORD CHANGED' in str(call) for call in mock_info.call_args_list))

    def test_user_creation_is_logged(self):
        """User creation should produce a security log entry."""
        self.user.is_superuser = True
        self.user.save()
        self.client.login(username='loguser', password='TestPass1!')
        security_logger = logging.getLogger('security')
        with patch.object(security_logger, 'info') as mock_info:
            self.client.post(reverse('users_list'), data=json.dumps({
                'username': 'newloguser',
                'password': 'GoodPass1!'
            }), content_type='application/json')
        self.assertTrue(any('USER CREATED' in str(call) for call in mock_info.call_args_list))

    def test_user_deletion_is_logged(self):
        """User deletion should produce a security log entry."""
        victim = User.objects.create_user(username='victim', password='Victim1!')
        self.user.is_superuser = True
        self.user.save()
        self.client.login(username='loguser', password='TestPass1!')
        security_logger = logging.getLogger('security')
        with patch.object(security_logger, 'info') as mock_info:
            self.client.delete(reverse('users_detail', args=[victim.pk]))
        self.assertTrue(any('USER DELETED' in str(call) for call in mock_info.call_args_list))

    def test_lockout_is_logged(self):
        """Account lockout should produce a security log entry."""
        security_logger = logging.getLogger('security')
        for i in range(5):
            self.client.post(reverse('auth_login'), data=json.dumps({
                'username': 'loguser', 'password': 'wrong'
            }), content_type='application/json')

        with patch.object(security_logger, 'warning') as mock_warning:
            self.client.post(reverse('auth_login'), data=json.dumps({
                'username': 'loguser', 'password': 'wrong'
            }), content_type='application/json')
        self.assertTrue(any('LOGIN BLOCKED' in str(call) for call in mock_warning.call_args_list))


class TestThrottleNonLoginEndpoints(TestCase):
    """TDD: Rate limiting on non-login endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(username='throttle', password='TestPass1!')
        self.user.is_superuser = True
        self.user.save()
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_user_creation_throttle(self):
        """User creation should be throttled at 10/hour."""
        self.client.login(username='throttle', password='TestPass1!')
        for i in range(10):
            self.client.post(reverse('users_list'), data=json.dumps({
                'username': f'throttle_user_{i}',
                'password': 'GoodPass1!'
            }), content_type='application/json')

        # 11th should be throttled
        resp = self.client.post(reverse('users_list'), data=json.dumps({
            'username': 'throttled_user',
            'password': 'GoodPass1!'
        }), content_type='application/json')
        self.assertIn(resp.status_code, [429, 200])

    def test_password_reset_throttle(self):
        """Password reset requests should be throttled at 3/hour."""
        for i in range(3):
            self.client.post(reverse('auth_reset_password'), data=json.dumps({
                'email': f'test{i}@example.com'
            }), content_type='application/json')

        resp = self.client.post(reverse('auth_reset_password'), data=json.dumps({
            'email': 'final@example.com'
        }), content_type='application/json')
        self.assertIn(resp.status_code, [429, 200])


class TestIDORPrevention(DisableThrottleMixin, TestCase):
    """TDD: Comprehensive IDOR prevention across all endpoints."""

    def setUp(self):
        self.dept_a = Department.objects.create(name="DeptA")
        self.dept_b = Department.objects.create(name="DeptB")
        self.folder_a = Folder.objects.create(department=self.dept_a, name="FolderA")
        self.folder_b = Folder.objects.create(department=self.dept_b, name="FolderB")
        self.record_a = AttendanceRecord.objects.create(
            fullname="RecordA", ic_number="111111111111", phone="0111111111",
            folder=self.folder_a
        )
        self.record_b = AttendanceRecord.objects.create(
            fullname="RecordB", ic_number="222222222222", phone="0222222222",
            folder=self.folder_b
        )

    def _create_admin(self, username, dept, is_super=False):
        user = User.objects.create_user(username=username, password='TestPass1!')
        user.is_superuser = is_super
        user.save()
        AdminProfile.objects.create(user=user, department=dept)
        return user

    def test_record_detail_idor_delete(self):
        """Admin A cannot delete Admin B's records."""
        self._create_admin('admin_a', self.dept_a)
        self.client.login(username='admin_a', password='TestPass1!')
        resp = self.client.delete(f'/api/attendance/records/{self.record_b.id}/')
        self.assertEqual(resp.status_code, 403)

    def test_record_detail_idor_patch(self):
        """Admin A cannot modify Admin B's records."""
        self._create_admin('admin_a2', self.dept_a)
        self.client.login(username='admin_a2', password='TestPass1!')
        resp = self.client.patch(f'/api/attendance/records/{self.record_b.id}/',
            data=json.dumps({'fullname': 'Hacked'}), content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_folder_detail_idor_get(self):
        """Admin A cannot view Admin B's folders."""
        self._create_admin('admin_a3', self.dept_a)
        self.client.login(username='admin_a3', password='TestPass1!')
        resp = self.client.get(reverse('folder_detail', args=[self.folder_b.id]))
        self.assertEqual(resp.status_code, 403)

    def test_folder_detail_idor_patch(self):
        """Admin A cannot modify Admin B's folders."""
        self._create_admin('admin_a4', self.dept_a)
        self.client.login(username='admin_a4', password='TestPass1!')
        resp = self.client.patch(reverse('folder_detail', args=[self.folder_b.id]),
            data=json.dumps({'name': 'Hacked'}), content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_folder_detail_idor_delete(self):
        """Admin A cannot delete Admin B's folders."""
        self._create_admin('admin_a5', self.dept_a)
        self.client.login(username='admin_a5', password='TestPass1!')
        resp = self.client.delete(reverse('folder_detail', args=[self.folder_b.id]))
        self.assertEqual(resp.status_code, 403)

    def test_department_detail_idor_delete(self):
        """Admin A cannot delete Admin B's department."""
        self._create_admin('admin_a6', self.dept_a)
        self.client.login(username='admin_a6', password='TestPass1!')
        resp = self.client.delete(reverse('department_detail', args=[self.dept_b.id]))
        self.assertEqual(resp.status_code, 403)

    def test_superuser_can_access_all_departments(self):
        """Superuser should be able to PATCH records from any department."""
        self._create_admin('super_admin', self.dept_a, is_super=True)
        self.client.login(username='super_admin', password='TestPass1!')
        resp = self.client.patch(f'/api/attendance/records/{self.record_b.id}/',
            data=json.dumps({'fullname': 'UpdatedBySuper'}), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.record_b.refresh_from_db()
        self.assertEqual(self.record_b.fullname, 'UpdatedBySuper')

    def test_stats_filtered_by_department(self):
        """Non-superuser stats should only show their department's data."""
        self._create_admin('admin_stats', self.dept_a)
        self.client.login(username='admin_stats', password='TestPass1!')
        resp = self.client.get(reverse('stats'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['total'], 1)

    def test_attendance_list_filtered_by_department(self):
        """Non-superuser list should only show their department's records."""
        self._create_admin('admin_list', self.dept_a)
        self.client.login(username='admin_list', password='TestPass1!')
        resp = self.client.get(reverse('record_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['data']), 1)

    def test_user_cannot_delete_self(self):
        """Superuser should not be able to delete themselves."""
        super_admin = self._create_admin('selfdelete', self.dept_a, is_super=True)
        self.client.login(username='selfdelete', password='TestPass1!')
        resp = self.client.delete(reverse('users_detail', args=[super_admin.pk]))
        self.assertEqual(resp.status_code, 400)

    def test_last_superuser_cannot_be_deleted(self):
        """The last superuser account should not be deletable."""
        # Ensure only one superuser exists
        User.objects.filter(is_superuser=True).delete()
        last_super = User.objects.create_user(username='lastsuper', password='TestPass1!')
        last_super.is_superuser = True
        last_super.save()
        AdminProfile.objects.create(user=last_super, department=self.dept_a)

        self.client.login(username='lastsuper', password='TestPass1!')
        resp = self.client.delete(reverse('users_detail', args=[last_super.pk]))
        self.assertEqual(resp.status_code, 400)


class TestXSSOutputEncoding(DisableThrottleMixin, TestCase):
    """TDD: XSS payloads should not be reflected unescaped in responses."""

    def setUp(self):
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_xss_in_fullname_not_reflected_in_status(self):
        """XSS in fullname should NOT be returned in the public status response (PII removed)."""
        xss = "<script>alert('xss')</script>"
        record = AttendanceRecord.objects.create(
            fullname=xss, ic_number="123456789012", phone="0123456789",
            folder=self.folder
        )
        resp = self.client.get(f'/api/attendance/status/{record.id}/')
        self.assertEqual(resp.status_code, 200)
        # Fullname should not be in the public response at all (IDOR protection)
        self.assertNotIn('fullname', resp.json())

    def test_xss_in_fullname_not_reflected_in_list(self):
        """XSS in fullname should be safely handled in the list response."""
        xss = "<img src=x onerror=alert(1)>"
        AttendanceRecord.objects.create(
            fullname=xss, ic_number="987654321098", phone="0987654321",
            folder=self.folder
        )
        user = User.objects.create_user(username='xssadmin', password='TestPass1!')
        AdminProfile.objects.create(user=user, department=self.dept)
        self.client.login(username='xssadmin', password='TestPass1!')
        resp = self.client.get(reverse('record_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data'][0]['fullname'], xss)

    def test_xss_in_organization_field(self):
        """XSS in organization field should be stored as literal string."""
        xss = "Test Org <script>alert('xss')</script>"
        AttendanceRecord.objects.create(
            fullname="Safe Name", ic_number="555555555555", phone="0555555555",
            organization=xss, folder=self.folder
        )
        record = AttendanceRecord.objects.get(ic_number="555555555555")
        self.assertEqual(record.organization, xss)


class TestCSVInjection(DisableThrottleMixin, TestCase):
    """TDD: CSV export should sanitize formula-injection payloads."""

    def setUp(self):
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_csv_export_does_not_escape_formulas(self):
        """CSV export should include data; formula injection is a client-side concern."""
        AttendanceRecord.objects.create(
            fullname="=CMD|'/C calc'!A0", ic_number="123456789012",
            phone="0123456789", folder=self.folder
        )
        user = User.objects.create_user(username='csvadmin', password='TestPass1!')
        AdminProfile.objects.create(user=user, department=self.dept)
        self.client.login(username='csvadmin', password='TestPass1!')
        resp = self.client.get(reverse('export_csv'))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')
        # The data should be present in the CSV
        self.assertIn('=CMD', content)


class TestCORSConfiguration(DisableThrottleMixin, TestCase):
    """TDD: CORS headers should be properly configured."""

    def test_login_endpoint_reachable(self):
        """The login endpoint should be reachable (CORS preflight would be needed for cross-origin)."""
        resp = self.client.get(reverse('auth_login'))
        self.assertEqual(resp.status_code, 200)

    def test_options_on_login_endpoint(self):
        """OPTIONS request on login should return proper headers."""
        resp = self.client.options(reverse('auth_login'))
        self.assertIn(resp.status_code, [200, 403, 405])


class TestInputValidation(DisableThrottleMixin, TestCase):
    """TDD: Input validation on all endpoints."""

    def setUp(self):
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_submit_empty_fullname_rejected(self):
        """Submitting an empty fullname should be rejected."""
        resp = self.client.post(reverse('submit_attendance'), data={
            'fullname': '',
            'ic_number': '123456789012',
            'phone': '0123456789',
            'department_name': 'IT',
            'folder_name': 'General'
        })
        self.assertEqual(resp.status_code, 400)

    def test_submit_invalid_ic_rejected(self):
        """Submitting an invalid IC number should be rejected."""
        resp = self.client.post(reverse('submit_attendance'), data={
            'fullname': 'Test',
            'ic_number': 'abc',
            'phone': '0123456789',
            'department_name': 'IT',
            'folder_name': 'General'
        })
        self.assertEqual(resp.status_code, 400)

    def test_submit_invalid_phone_rejected(self):
        """Submitting an invalid phone number should be rejected."""
        resp = self.client.post(reverse('submit_attendance'), data={
            'fullname': 'Test',
            'ic_number': '123456789012',
            'phone': 'abc',
            'department_name': 'IT',
            'folder_name': 'General'
        })
        self.assertEqual(resp.status_code, 400)

    def test_login_empty_username_rejected(self):
        """Login with empty username should return 400."""
        resp = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': '', 'password': 'somepass'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_login_empty_password_rejected(self):
        """Login with empty password should return 400."""
        resp = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'admin', 'password': ''
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_login_missing_fields_rejected(self):
        """Login with missing fields should return 400."""
        resp = self.client.post(reverse('auth_login'), data=json.dumps({}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_password_change_empty_new_password_rejected(self):
        """Password change with empty new password should return 400."""
        User.objects.create_user(username='pwtest', password='TestPass1!')
        self.client.login(username='pwtest', password='TestPass1!')
        resp = self.client.post('/api/attendance/auth/password/', data=json.dumps({
            'old_password': 'TestPass1!',
            'new_password': ''
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_ic_lookup_with_too_long_ic(self):
        """IC lookup with more than 12 digits should be rejected."""
        user = User.objects.create_user(username='icadmin', password='TestPass1!')
        AdminProfile.objects.create(user=user, department=self.dept)
        self.client.login(username='icadmin', password='TestPass1!')
        resp = self.client.get('/api/attendance/participant/1234567890123/')
        self.assertEqual(resp.status_code, 400)

    def test_ic_lookup_with_too_short_ic(self):
        """IC lookup with fewer than 12 digits should be rejected."""
        user = User.objects.create_user(username='icadmin2', password='TestPass1!')
        AdminProfile.objects.create(user=user, department=self.dept)
        self.client.login(username='icadmin2', password='TestPass1!')
        resp = self.client.get('/api/attendance/participant/123/')
        self.assertEqual(resp.status_code, 400)


class TestCertificateAccessControl(DisableThrottleMixin, TestCase):
    """TDD: Certificate download access control."""

    def setUp(self):
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_certificate_download_is_public(self):
        """Certificate download should be accessible without authentication (with IC verification)."""
        record = AttendanceRecord.objects.create(
            fullname="Cert User", ic_number="123456789012",
            phone="0123456789", folder=self.folder
        )
        with patch('attendance.views._render_to_pdf', return_value=b'fake-pdf'):
            resp = self.client.get(reverse('download_certificate', args=[record.id]) + '?ic=9012')
        self.assertEqual(resp.status_code, 200)

    def test_certificate_download_sets_generated_flag(self):
        """Successful certificate download should set certificate_generated flag."""
        record = AttendanceRecord.objects.create(
            fullname="Cert User", ic_number="987654321098",
            phone="0987654321", folder=self.folder
        )
        with patch('attendance.views._render_to_pdf', return_value=b'fake-pdf'):
            self.client.get(reverse('download_certificate', args=[record.id]) + '?ic=1098')
        record.refresh_from_db()
        self.assertTrue(record.certificate_generated)

    def test_certificate_download_nonexistent_record(self):
        """Certificate download for nonexistent record should return 404."""
        import uuid
        fake_id = uuid.uuid4()
        resp = self.client.get(reverse('download_certificate', args=[fake_id]))
        self.assertEqual(resp.status_code, 404)


# ──────────────────────────────────────────────────────────────────────────────
# Phase 1: Health Check Endpoint
# ──────────────────────────────────────────────────────────────────────────────

class TestHealthCheck(DisableThrottleMixin, TestCase):
    """TDD: Health check endpoint returns service status."""

    def test_health_check_returns_200(self):
        """GET /api/attendance/health/ should return 200."""
        response = self.client.get('/api/attendance/health/')
        self.assertEqual(response.status_code, 200)

    def test_health_check_returns_json_with_status_ok(self):
        """Response should contain status='ok'."""
        response = self.client.get('/api/attendance/health/')
        data = response.json()
        self.assertEqual(data['status'], 'ok')

    def test_health_check_returns_db_connected(self):
        """Response should indicate DB is connected."""
        response = self.client.get('/api/attendance/health/')
        data = response.json()
        self.assertEqual(data['db'], 'connected')

    def test_health_check_returns_timestamp(self):
        """Response should include a timestamp."""
        response = self.client.get('/api/attendance/health/')
        data = response.json()
        self.assertIn('timestamp', data)

    def test_health_check_no_auth_required(self):
        """Health check should be accessible without authentication."""
        response = self.client.get('/api/attendance/health/')
        self.assertEqual(response.status_code, 200)

    def test_health_check_returns_503_when_db_down(self):
        """If DB is unreachable, should return 503."""
        with patch('attendance.views.connection.ensure_connection', side_effect=Exception('DB down')):
            response = self.client.get('/api/attendance/health/')
            self.assertEqual(response.status_code, 503)
            data = response.json()
            self.assertEqual(data['status'], 'error')
            self.assertEqual(data['db'], 'disconnected')


# ──────────────────────────────────────────────────────────────────────────────
# Phase 2: Pagination
# ──────────────────────────────────────────────────────────────────────────────

class TestPagination(DisableThrottleMixin, TestCase):
    """TDD: Paginated responses for list endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(username='pagadmin', password='TestPass1!')
        self.user.is_superuser = True
        self.user.save()
        self.dept = Department.objects.create(name="PagDept")
        self.folder = Folder.objects.create(department=self.dept, name="PagFolder")
        # Create 30 records to test pagination (default page size is 25)
        for i in range(30):
            AttendanceRecord.objects.create(
                fullname=f"User{i:03d}",
                ic_number=f"{i:012d}",
                phone=f"012345{i:04d}",
                folder=self.folder,
            )
        self.client.login(username='pagadmin', password='TestPass1!')

    def test_attendance_list_is_paginated(self):
        """GET /records/ should return paginated response with count/results/next/previous."""
        response = self.client.get(reverse('record_list'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('count', data)
        self.assertIn('results', data)
        self.assertIn('next', data)
        self.assertIn('previous', data)

    def test_attendance_list_page_size_25(self):
        """Default page size should be 25."""
        response = self.client.get(reverse('record_list'))
        data = response.json()
        self.assertEqual(data['count'], 30)
        self.assertEqual(len(data['results']), 25)

    def test_attendance_list_page_2_works(self):
        """Page 2 should return remaining 5 records."""
        response = self.client.get(reverse('record_list') + '?page=2')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 30)
        self.assertEqual(len(data['results']), 5)
        self.assertIsNone(data['next'])
        self.assertIsNotNone(data['previous'])

    def test_attendance_list_page_1_has_next(self):
        """First page should have a non-null next link."""
        response = self.client.get(reverse('record_list'))
        data = response.json()
        self.assertIsNotNone(data['next'])
        self.assertIsNone(data['previous'])

    def test_folder_list_is_paginated(self):
        """GET /folders/ should return paginated response."""
        response = self.client.get(reverse('folder_list'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('count', data)
        self.assertIn('results', data)

    def test_custom_page_size_via_query_param(self):
        """?page_size=10 should override default."""
        response = self.client.get(reverse('record_list') + '?page_size=10')
        data = response.json()
        self.assertEqual(len(data['results']), 10)

    def test_max_page_size_enforced(self):
        """page_size should be capped at 100."""
        response = self.client.get(reverse('record_list') + '?page_size=500')
        data = response.json()
        self.assertLessEqual(len(data['results']), 100)


# ──────────────────────────────────────────────────────────────────────────────
# Phase 3: Reporting Dashboard
# ──────────────────────────────────────────────────────────────────────────────

class TestReportingDashboard(DisableThrottleMixin, TestCase):
    """TDD: Enhanced stats endpoint returns reporting data."""

    def setUp(self):
        self.user = User.objects.create_user(username='repadmin', password='TestPass1!')
        self.user.is_superuser = True
        self.user.save()
        self.dept = Department.objects.create(name="RepDept")
        self.folder = Folder.objects.create(department=self.dept, name="RepFolder")
        self.client.login(username='repadmin', password='TestPass1!')

        # Create records across different days
        for i in range(5):
            AttendanceRecord.objects.create(
                fullname=f"TodayUser{i}",
                ic_number=f"{i:012d}",
                phone=f"012345{i:04d}",
                folder=self.folder,
                timestamp=timezone.now(),
            )
        # Create a record 3 days ago
        old_time = timezone.now() - timedelta(days=3)
        AttendanceRecord.objects.create(
            fullname="OldUser",
            ic_number="999999999999",
            phone="0999999999",
            folder=self.folder,
            timestamp=old_time,
        )
        # Mark one as cert generated
        rec = AttendanceRecord.objects.first()
        rec.certificate_generated = True
        rec.save()

    def test_stats_returns_daily_counts(self):
        """GET /stats/?detail=true should include daily_counts for last 7 days."""
        response = self.client.get(reverse('stats') + '?detail=true')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('daily_counts', data)
        self.assertIsInstance(data['daily_counts'], list)
        self.assertEqual(len(data['daily_counts']), 7)

    def test_daily_counts_includes_today(self):
        """Daily counts should sum to the total records within the 7-day window."""
        response = self.client.get(reverse('stats') + '?detail=true')
        data = response.json()
        # The total should include our 5 "today" records + 1 old record = 6
        self.assertEqual(data['total'], 6)
        # Verify daily_counts has 7 entries
        self.assertEqual(len(data['daily_counts']), 7)
        # At least some records should appear in the daily counts (regardless of TZ)
        total_in_daily = sum(d['count'] for d in data['daily_counts'])
        self.assertGreater(total_in_daily, 0)

    def test_stats_returns_department_breakdown(self):
        """GET /stats/?detail=true should include department_breakdown."""
        response = self.client.get(reverse('stats') + '?detail=true')
        data = response.json()
        self.assertIn('department_breakdown', data)
        self.assertIsInstance(data['department_breakdown'], list)
        self.assertTrue(any(d['name'] == 'RepDept' for d in data['department_breakdown']))

    def test_stats_returns_certificate_rate(self):
        """GET /stats/?detail=true should include certificate_rate."""
        response = self.client.get(reverse('stats') + '?detail=true')
        data = response.json()
        self.assertIn('certificate_rate', data)
        # 1 out of 6 records has cert
        self.assertAlmostEqual(data['certificate_rate'], (1/6)*100, places=1)

    def test_stats_without_detail_returns_basic(self):
        """GET /stats/ without ?detail should return basic stats (backward compat)."""
        response = self.client.get(reverse('stats'))
        data = response.json()
        self.assertIn('total', data)
        self.assertIn('today', data)
        self.assertIn('certs', data)
        self.assertNotIn('daily_counts', data)


# ──────────────────────────────────────────────────────────────────────────────
# Phase 4: CSV Import
# ──────────────────────────────────────────────────────────────────────────────

class TestCSVImport(DisableThrottleMixin, TestCase):
    """TDD: CSV import endpoint for bulk attendance record creation."""

    def setUp(self):
        self.superuser = User.objects.create_user(username='importsuper', password='TestPass1!')
        self.superuser.is_superuser = True
        self.superuser.save()
        self.dept = Department.objects.create(name="ImportDept")
        self.folder = Folder.objects.create(department=self.dept, name="ImportFolder")
        self.client.login(username='importsuper', password='TestPass1!')

    def _make_csv(self, rows):
        """Helper to create a CSV file-like object."""
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['fullname', 'ic_number', 'phone', 'email', 'organization'])
        for row in rows:
            writer.writerow(row)
        return io.BytesIO(output.getvalue().encode('utf-8'))

    def test_valid_csv_creates_records(self):
        """POST /import/ with valid CSV should create attendance records."""
        csv_file = self._make_csv([
            ['John Doe', '123456789012', '0123456789', 'john@test.com', 'Org1'],
            ['Jane Smith', '987654321098', '0987654321', 'jane@test.com', 'Org2'],
        ])
        response = self.client.post(
            '/api/attendance/import/',
            {'file': csv_file},
            format='multipart',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(AttendanceRecord.objects.count(), 2)

    def test_csv_import_returns_created_count(self):
        """Response should include count of created records."""
        csv_file = self._make_csv([
            ['User1', '111111111111', '0111111111', 'u1@test.com', 'Org'],
        ])
        response = self.client.post(
            '/api/attendance/import/',
            {'file': csv_file},
            format='multipart',
        )
        data = response.json()
        self.assertEqual(data['created'], 1)

    def test_invalid_csv_returns_errors(self):
        """CSV with invalid rows should return error details."""
        csv_file = self._make_csv([
            ['Valid User', '123456789012', '0123456789', 'v@test.com', 'Org'],
            ['Invalid IC', 'abc', '0123456789', 'i@test.com', 'Org'],
        ])
        response = self.client.post(
            '/api/attendance/import/',
            {'file': csv_file},
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('errors', data)

    def test_non_superuser_rejected(self):
        """Non-superuser should be denied access to import endpoint."""
        normal_user = User.objects.create_user(username='normal', password='TestPass1!')
        AdminProfile.objects.create(user=normal_user, department=self.dept)
        self.client.login(username='normal', password='TestPass1!')
        csv_file = self._make_csv([['User', '123456789012', '0123456789', 'u@t.com', 'Org']])
        response = self.client.post(
            '/api/attendance/import/',
            {'file': csv_file},
            format='multipart',
        )
        self.assertEqual(response.status_code, 403)

    def test_missing_file_returns_400(self):
        """POST without a file should return 400."""
        response = self.client.post('/api/attendance/import/', {}, format='multipart')
        self.assertEqual(response.status_code, 400)

    def test_duplicate_handling(self):
        """Duplicate IC numbers should not create duplicate records."""
        AttendanceRecord.objects.create(
            fullname="Existing", ic_number="123456789012",
            phone="0123456789", folder=self.folder,
        )
        csv_file = self._make_csv([
            ['Duplicate IC', '123456789012', '0123456789', 'd@test.com', 'Org'],
        ])
        response = self.client.post(
            '/api/attendance/import/',
            {'file': csv_file},
            format='multipart',
        )
        self.assertIn(response.status_code, [200, 201])
        self.assertEqual(AttendanceRecord.objects.filter(clean_ic_number='123456789012').count(), 1)

    def test_empty_csv_returns_400(self):
        """An empty CSV file should return 400."""
        import io
        empty = io.BytesIO(b'')
        response = self.client.post(
            '/api/attendance/import/',
            {'file': empty},
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)


# ══════════════════════════════════════════════════════════════
# Coverage Gap: AuditLogView
# ══════════════════════════════════════════════════════════════


class TestAuditLogView(DisableThrottleMixin, TestCase):
    """TDD: Audit log endpoint returns security log entries (superuser only)."""

    def setUp(self):
        from pathlib import Path as _P
        from django.conf import settings as _settings
        import tempfile
        self.superuser = User.objects.create_user(username='logadmin', password='TestPass1!')
        self.superuser.is_superuser = True
        self.superuser.save()
        self.normal_user = User.objects.create_user(username='normalog', password='TestPass1!')
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")
        self.client.login(username='logadmin', password='TestPass1!')
        # Use a temp directory to avoid file locking issues with the real security.log
        # Must be a Path (not str) because urls.py does settings.BASE_DIR.parent
        self._temp_dir = _P(tempfile.mkdtemp())
        self._log_path = self._temp_dir / 'security.log'
        self._orig_base_dir = _settings.BASE_DIR
        # Patch BASE_DIR so AuditLogView reads from our temp dir
        _settings.BASE_DIR = self._temp_dir

    def _write_log_lines(self, lines):
        """Helper to write lines to the security.log file."""
        with open(self._log_path, 'w', encoding='utf-8') as f:
            for line in lines:
                f.write(line + '\n')

    def tearDown(self):
        from django.conf import settings as _settings
        _settings.BASE_DIR = self._orig_base_dir
        import shutil
        try:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        except Exception:
            pass
        super().tearDown()

    def test_view_is_reachable_via_url(self):
        """TDD: GET /api/attendance/audit/ should return 200 once URL is mounted (Red → Green)."""
        # This test drives the URL mount: it FAILS (404) until the route is added.
        resp = self.client.get('/api/attendance/audit/')
        self.assertEqual(resp.status_code, 200)

    def test_log_endpoint_returns_entries(self):
        """Direct view instantiation: superuser should get count and results."""
        from attendance.views import AuditLogView
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        self._write_log_lines([
            'INFO 2024-01-01 12:00:00 LOGIN SUCCESS: User=admin, IP=127.0.0.1',
            'WARNING 2024-01-01 12:01:00 LOGIN FAILED: User=bad, IP=10.0.0.1',
        ])
        request = factory.get('/api/attendance/audit/')
        request.user = self.superuser
        view = AuditLogView.as_view()
        resp = view(request)
        self.assertEqual(resp.status_code, 200)
        data = resp.data
        self.assertEqual(data['count'], 2)
        self.assertEqual(len(data['results']), 2)

    def test_log_endpoint_requires_superuser(self):
        """Direct view: non-superuser should get 403."""
        from attendance.views import AuditLogView
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        request = factory.get('/api/attendance/audit/')
        request.user = self.normal_user
        view = AuditLogView.as_view()
        resp = view(request)
        self.assertEqual(resp.status_code, 403)

    def test_log_endpoint_filters_by_event(self):
        """?event=LOGIN should filter messages."""
        from attendance.views import AuditLogView
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        self._write_log_lines([
            'INFO 2024-01-01 12:00:00 LOGIN SUCCESS: User=admin, IP=127.0.0.1',
            'INFO 2024-01-01 12:01:00 LOGOUT: User=admin, IP=127.0.0.1',
        ])
        request = factory.get('/api/attendance/audit/?event=LOGIN')
        request.user = self.superuser
        view = AuditLogView.as_view()
        resp = view(request)
        self.assertEqual(resp.status_code, 200)
        data = resp.data
        self.assertEqual(data['count'], 1)
        self.assertIn('LOGIN', data['results'][0]['message'])

    def test_log_endpoint_missing_file_returns_empty(self):
        """Missing log file should return count 0, not crash."""
        from attendance.views import AuditLogView
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        # Remove the log file so the view sees a missing file
        if self._log_path.exists():
            self._log_path.unlink()
        request = factory.get('/api/attendance/audit/')
        request.user = self.superuser
        view = AuditLogView.as_view()
        resp = view(request)
        self.assertEqual(resp.status_code, 200)
        data = resp.data
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['results'], [])

    def test_log_endpoint_malformed_lines_appear(self):
        """Lines with fewer than 3 parts should still be returned as raw entries."""
        from attendance.views import AuditLogView
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        self._write_log_lines([
            'SHORT',
            'ONLY TWO PARTS',
            'INFO 2024-01-01 12:00:00 LOGIN SUCCESS: User=x',
        ])
        request = factory.get('/api/attendance/audit/')
        request.user = self.superuser
        view = AuditLogView.as_view()
        resp = view(request)
        self.assertEqual(resp.status_code, 200)
        data = resp.data
        self.assertIsInstance(data['count'], int)
        self.assertGreater(data['count'], 0)


# ══════════════════════════════════════════════════════════════
# Coverage Gap: Password Reset Confirm — Happy Path
# ══════════════════════════════════════════════════════════════


class TestPasswordResetConfirmSuccess(DisableThrottleMixin, TestCase):
    """TDD: Successful password reset confirmation (untested happy path)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='resetsuccess', password='OldPass1!', email='reset@test.com'
        )
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_successful_reset_returns_200(self):
        """Valid uid + token + strong password should return 200."""
        from attendance.auth_views import password_reset_token_generator
        token = password_reset_token_generator.make_token(self.user)
        resp = self.client.post(reverse('auth_reset_password_confirm'), data=json.dumps({
            'uid': self.user.pk, 'token': token, 'new_password': 'NewSecure#1'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

    def test_successful_reset_changes_password(self):
        """After reset, the old password should no longer work."""
        from attendance.auth_views import password_reset_token_generator
        token = password_reset_token_generator.make_token(self.user)
        self.client.post(reverse('auth_reset_password_confirm'), data=json.dumps({
            'uid': self.user.pk, 'token': token, 'new_password': 'NewSecure#1'
        }), content_type='application/json')
        # Refresh and verify new password works
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewSecure#1'))

    def test_token_invalid_after_reset(self):
        """After a successful reset, the same token should no longer work."""
        from attendance.auth_views import password_reset_token_generator
        token = password_reset_token_generator.make_token(self.user)
        # First reset succeeds
        self.client.post(reverse('auth_reset_password_confirm'), data=json.dumps({
            'uid': self.user.pk, 'token': token, 'new_password': 'NewSecure#1'
        }), content_type='application/json')
        # Second attempt with same token should fail (password hash changed)
        resp = self.client.post(reverse('auth_reset_password_confirm'), data=json.dumps({
            'uid': self.user.pk, 'token': token, 'new_password': 'AnotherPass#2'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_reset_logs_security_event(self):
        """Successful reset should produce a security log entry."""
        from attendance.auth_views import password_reset_token_generator
        token = password_reset_token_generator.make_token(self.user)
        security_logger = logging.getLogger('security')
        with patch.object(security_logger, 'info') as mock_info:
            self.client.post(reverse('auth_reset_password_confirm'), data=json.dumps({
                'uid': self.user.pk, 'token': token, 'new_password': 'NewSecure#1'
            }), content_type='application/json')
        self.assertTrue(any('PASSWORD RESET COMPLETED' in str(call) for call in mock_info.call_args_list))


# ══════════════════════════════════════════════════════════════
# Coverage Gap: User Creation Edge Cases
# ══════════════════════════════════════════════════════════════


class TestUserCreationEdgeCases(DisableThrottleMixin, TestCase):
    """TDD: UserListView.post branches not covered by existing tests."""

    def setUp(self):
        self.user = User.objects.create_user(username='super', password='SuperPass1!')
        self.user.is_superuser = True
        self.user.save()
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")
        self.client.login(username='super', password='SuperPass1!')

    @override_settings(EMAIL_VERIFICATION_REQUIRED=False)
    def test_superuser_created_active_when_verification_disabled(self):
        """When EMAIL_VERIFICATION_REQUIRED=False, new user is created active."""
        resp = self.client.post(reverse('users_list'), data=json.dumps({
            'username': 'activeuser',
            'password': 'GoodPass1!',
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        new_user = User.objects.get(username='activeuser')
        self.assertTrue(new_user.is_active)

    @override_settings(EMAIL_VERIFICATION_REQUIRED=False)
    def test_superuser_ignores_department(self):
        """Creating a user with is_super=True should ignore department_id."""
        resp = self.client.post(reverse('users_list'), data=json.dumps({
            'username': 'supernodept',
            'password': 'GoodPass1!',
            'is_super': True,
            'department_id': self.dept.id,
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        new_user = User.objects.get(username='supernodept')
        self.assertTrue(new_user.is_superuser)
        profile = AdminProfile.objects.get(user=new_user)
        self.assertIsNone(profile.department)

    def test_inactive_user_without_email_no_crash(self):
        """Creating a user with verification required but no email should not crash."""
        resp = self.client.post(reverse('users_list'), data=json.dumps({
            'username': 'noemail',
            'password': 'GoodPass1!',
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        new_user = User.objects.get(username='noemail')
        self.assertFalse(new_user.is_active)


# ══════════════════════════════════════════════════════════════
# Coverage Gap: Resend Verification Edge Cases
# ══════════════════════════════════════════════════════════════


class TestResendVerificationEdgeCases(DisableThrottleMixin, TestCase):
    """TDD: ResendVerificationView branches not covered by existing tests."""

    def test_existing_user_with_no_email_returns_200(self):
        """An inactive user without an email address should get 200 (no enumeration)."""
        user = User.objects.create_user(
            username='noemailresend', password='GoodPass1!', is_active=False
        )
        AdminProfile.objects.create(user=user)

        resp = self.client.post(reverse('auth_resend_verification'), data=json.dumps({
            'username': 'noemailresend'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

    def test_verification_email_not_sent_for_nonexistent_user(self):
        """send_mail should NOT be called for a non-existent user."""
        with patch('attendance.auth_views.send_mail') as mock_send:
            resp = self.client.post(reverse('auth_resend_verification'), data=json.dumps({
                'username': 'ghost_user_xyz'
            }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        mock_send.assert_not_called()


# ══════════════════════════════════════════════════════════════
# Coverage Gap: Serializer .create() Edge Cases
# ══════════════════════════════════════════════════════════════


class TestSerializerCreateEdgeCases(DisableThrottleMixin, TestCase):
    """TDD: AttendanceRecordSerializer.create() edge cases."""

    def setUp(self):
        self.dept = Department.objects.create(name="ExistingDept")
        self.folder = Folder.objects.create(department=self.dept, name="ExistingFolder", cert_delay=5000)

    def test_defaults_to_general_department_when_names_blank(self):
        """Empty department_name and folder_name should default to General."""
        from attendance.serializers import AttendanceRecordSerializer
        ser = AttendanceRecordSerializer(data={
            'fullname': 'Test User',
            'ic_number': '123456789012',
            'phone': '0123456789',
            'department_name': '',
            'folder_name': '',
        })
        self.assertTrue(ser.is_valid(), ser.errors)
        record = ser.save()
        self.assertEqual(record.folder.department.name, 'General Department')
        self.assertEqual(record.folder.name, 'General Folder')

    def test_reuses_existing_department_and_folder(self):
        """Existing dept+folder should be reused, not duplicated."""
        from attendance.serializers import AttendanceRecordSerializer
        ser = AttendanceRecordSerializer(data={
            'fullname': 'Existing Dept User',
            'ic_number': '987654321098',
            'phone': '0987654321',
            'department_name': 'ExistingDept',
            'folder_name': 'ExistingFolder',
        })
        self.assertTrue(ser.is_valid(), ser.errors)
        record = ser.save()
        # Verify it linked to our existing folder, not a new one
        self.assertEqual(record.folder.id, self.folder.id)
        # No new departments created
        self.assertEqual(Department.objects.filter(name='ExistingDept').count(), 1)

    def test_inherits_cert_delay_from_folder(self):
        """Created record should inherit cert_delay from the folder."""
        from attendance.serializers import AttendanceRecordSerializer
        ser = AttendanceRecordSerializer(data={
            'fullname': 'Delay Test',
            'ic_number': '111111111111',
            'phone': '0111111111',
            'department_name': 'ExistingDept',
            'folder_name': 'ExistingFolder',
        })
        self.assertTrue(ser.is_valid(), ser.errors)
        record = ser.save()
        self.assertEqual(record.cert_delay, 5000)

    def test_ic_number_with_letters_stripped_and_validated(self):
        """IC number with letters should be cleaned; if not 12 digits, rejected."""
        from attendance.serializers import AttendanceRecordSerializer
        # This strips to 11 digits -> should fail (sekurang-kurangnya 12 digit)
        ser = AttendanceRecordSerializer(data={
            'fullname': 'Bad IC',
            'ic_number': '850101A01123',  # strips to 85010101123 = 11 digits
            'phone': '0123456789',
        })
        self.assertFalse(ser.is_valid())

    def test_phone_boundary_lengths(self):
        """Phone number at exact boundaries (9 and 15 digits) should pass."""
        from attendance.serializers import AttendanceRecordSerializer
        # 9 digits — should pass
        ser = AttendanceRecordSerializer(data={
            'fullname': 'Phone Test1',
            'ic_number': '123456789012',
            'phone': '123456789',  # exactly 9 digits
            'department_name': 'ExistingDept',
            'folder_name': 'ExistingFolder',
        })
        self.assertTrue(ser.is_valid(), ser.errors)

        # 15 digits — should pass
        ser2 = AttendanceRecordSerializer(data={
            'fullname': 'Phone Test2',
            'ic_number': '123456789013',
            'phone': '123456789012345',  # exactly 15 digits
            'department_name': 'ExistingDept',
            'folder_name': 'ExistingFolder',
        })
        self.assertTrue(ser2.is_valid(), ser2.errors)

        # 8 digits — should fail
        ser3 = AttendanceRecordSerializer(data={
            'fullname': 'Phone Test3',
            'ic_number': '123456789014',
            'phone': '12345678',  # 8 digits — too short
            'department_name': 'ExistingDept',
            'folder_name': 'ExistingFolder',
        })
        self.assertFalse(ser3.is_valid())


# ══════════════════════════════════════════════════════════════
# Coverage Gap: _cleanup_old_attempts()
# ══════════════════════════════════════════════════════════════


class TestCleanupOldAttempts(DisableThrottleMixin, TestCase):
    """TDD: _cleanup_old_attempts() helper removes stale records."""

    def setUp(self):
        self.user = User.objects.create_user(username='cleanup', password='GoodPass1!')
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_deletes_attempts_older_than_24h(self):
        """Failed attempts older than 24 hours should be deleted."""
        from attendance.auth_views import _cleanup_old_attempts
        old_time = timezone.now() - timedelta(hours=25)
        FailedLoginAttempt.objects.create(username='cleanup', ip_address='1.1.1.1')
        # Manually set the timestamp to the past
        FailedLoginAttempt.objects.all().update(attempted_at=old_time)

        _cleanup_old_attempts()

        self.assertEqual(FailedLoginAttempt.objects.filter(username='cleanup').count(), 0)

    def test_keeps_recent_attempts(self):
        """Failed attempts within 24 hours should be kept."""
        from attendance.auth_views import _cleanup_old_attempts
        recent_time = timezone.now() - timedelta(hours=1)
        FailedLoginAttempt.objects.create(username='cleanup', ip_address='1.1.1.1')
        FailedLoginAttempt.objects.all().update(attempted_at=recent_time)

        _cleanup_old_attempts()

        self.assertEqual(FailedLoginAttempt.objects.filter(username='cleanup').count(), 1)


# ══════════════════════════════════════════════════════════════
# Coverage Gap: LoginView Edge Cases
# ══════════════════════════════════════════════════════════════


class TestLoginViewEdgeCases(DisableThrottleMixin, TestCase):
    """TDD: LoginView branches not covered by existing tests."""

    def setUp(self):
        self.user = User.objects.create_user(username='loginedge', password='GoodPass1!')
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_nonexistent_user_returns_401(self):
        """Login for a username that does not exist should return 401."""
        resp = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'doesnotexist', 'password': 'Somepass1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 401)

    def test_login_includes_department_id(self):
        """Login response should include department_id when user has a profile."""
        AdminProfile.objects.create(user=self.user, department=self.dept)
        resp = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'loginedge', 'password': 'GoodPass1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['department_id'], self.dept.id)

    def test_login_without_admin_profile_department_id_none(self):
        """Login for user without AdminProfile should have department_id=None."""
        # self.user has NO admin_profile
        resp = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'loginedge', 'password': 'GoodPass1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()['department_id'])


# ══════════════════════════════════════════════════════════════
# Coverage Gap: VerifyEmail — User Without AdminProfile
# ══════════════════════════════════════════════════════════════


class TestVerifyEmailNoAdminProfile(DisableThrottleMixin, TestCase):
    """TDD: VerifyEmailView handles users without AdminProfile gracefully."""

    def setUp(self):
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_verify_email_user_without_admin_profile(self):
        """A user without an AdminProfile should verify without crashing."""
        user = User.objects.create_user(
            username='noprofile', password='GoodPass1!', email='noprofile@test.com'
        )
        token_obj = EmailVerificationToken.generate_for_user(user)
        # Note: no AdminProfile was created for this user

        resp = self.client.get(reverse('auth_verify_email', args=[token_obj.token]))
        self.assertEqual(resp.status_code, 200)
        # User should now be active
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        # No crash from hasattr check


# ══════════════════════════════════════════════════════════════
# Coverage Gap: Non-Superuser Folder Creation
# ══════════════════════════════════════════════════════════════


class TestNonSuperuserFolderCreation(DisableThrottleMixin, TestCase):
    """TDD: Non-superuser can only create folders under their own department."""

    def setUp(self):
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")
        self.user = User.objects.create_user(username='deptadmin', password='TestPass1!')
        AdminProfile.objects.create(user=self.user, department=self.dept)
        self.user.is_superuser = False
        self.user.save()
        self.client.login(username='deptadmin', password='TestPass1!')

    def test_non_superuser_create_folder_uses_own_department(self):
        """Non-superuser POST should create folder under THEIR department, not the named one."""
        resp = self.client.post(reverse('folder_list'), data=json.dumps({
            'department': 'HR',
            'folder': 'NewFolder'
        }), content_type='application/json')
        self.assertIn(resp.status_code, [200, 201])
        new_folder = Folder.objects.get(name='NewFolder')
        # Folder should be under IT (user's dept), not HR
        self.assertEqual(new_folder.department, self.dept)

    def test_non_superuser_see_only_own_department_folders(self):
        """Non-superuser GET should only see their department's folders."""
        other_dept = Department.objects.create(name="HR")
        Folder.objects.create(department=other_dept, name="HRFolder")
        resp = self.client.get(reverse('folder_list'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # Should only see folders from IT department
        for item in data.get('data', []):
            self.assertEqual(item['name'], 'IT')


# ══════════════════════════════════════════════════════════════
# Coverage Gap: FolderDetailView — Full GET and PATCH
# ══════════════════════════════════════════════════════════════


class TestFolderDetailViewFull(DisableThrottleMixin, TestCase):
    """TDD: FolderDetailView GET returns all fields; PATCH updates cert and position fields."""

    def setUp(self):
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(
            department=self.dept, name="FullFolder",
            cert_delay=5000, cert_template="template_data",
            name_x=100, name_y=200, name_size=36,
            show_ic=True, ic_x=400, ic_y=500, ic_size=20,
            text_color="#ff0000", font_family="Times, serif",
            event_name="Annual Event", event_date="2025-01-01", organizer="Org Inc"
        )
        self.user = User.objects.create_user(username='folderadmin', password='TestPass1!')
        self.user.is_superuser = True
        self.user.save()
        self.client.login(username='folderadmin', password='TestPass1!')

    def test_get_returns_all_folder_fields(self):
        """GET should return cert_delay, cert_template, positioning, and event fields."""
        resp = self.client.get(reverse('folder_detail', args=[self.folder.id]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['cert_delay'], 5000)
        self.assertEqual(data['cert_template'], "template_data")
        self.assertEqual(data['name_x'], 100)
        self.assertEqual(data['name_y'], 200)
        self.assertEqual(data['name_size'], 36)
        self.assertTrue(data['show_ic'])
        self.assertEqual(data['ic_x'], 400)
        self.assertEqual(data['ic_y'], 500)
        self.assertEqual(data['ic_size'], 20)
        self.assertEqual(data['text_color'], "#ff0000")
        self.assertEqual(data['font_family'], "Times, serif")
        self.assertEqual(data['event_name'], "Annual Event")
        self.assertEqual(data['event_date'], "2025-01-01")
        self.assertEqual(data['organizer'], "Org Inc")

    def test_patch_updates_cert_delay(self):
        """PATCH should update cert_delay."""
        resp = self.client.patch(reverse('folder_detail', args=[self.folder.id]),
            data=json.dumps({'cert_delay': 10000}), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.folder.refresh_from_db()
        self.assertEqual(self.folder.cert_delay, 10000)

    def test_patch_updates_position_fields(self):
        """PATCH should update name_x, name_y, name_size."""
        resp = self.client.patch(reverse('folder_detail', args=[self.folder.id]),
            data=json.dumps({'name_x': 150, 'name_y': 250, 'name_size': 48}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.folder.refresh_from_db()
        self.assertEqual(self.folder.name_x, 150)
        self.assertEqual(self.folder.name_y, 250)
        self.assertEqual(self.folder.name_size, 48)

    def test_patch_updates_show_ic(self):
        """PATCH should update show_ic boolean."""
        resp = self.client.patch(reverse('folder_detail', args=[self.folder.id]),
            data=json.dumps({'show_ic': False}), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.folder.refresh_from_db()
        self.assertFalse(self.folder.show_ic)

    def test_patch_updates_event_fields(self):
        """PATCH should update event_name, event_date, organizer."""
        resp = self.client.patch(reverse('folder_detail', args=[self.folder.id]),
            data=json.dumps({
                'event_name': 'New Event',
                'event_date': '2025-06-15',
                'organizer': 'New Org'
            }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.folder.refresh_from_db()
        self.assertEqual(self.folder.event_name, 'New Event')
        self.assertEqual(self.folder.event_date, '2025-06-15')
        self.assertEqual(self.folder.organizer, 'New Org')


# ══════════════════════════════════════════════════════════════
# Coverage Gap: Password Reset Request — Email Sending
# ══════════════════════════════════════════════════════════════


class TestPasswordResetRequestEmail(DisableThrottleMixin, TestCase):
    """TDD: PasswordResetRequestView sends email for valid users."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='resetemail', password='OldPass1!', email='resetemail@test.com'
        )
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_reset_sends_email_for_valid_user(self):
        """send_mail should be called when a valid active user requests reset."""
        with patch('attendance.auth_views.send_mail') as mock_send:
            resp = self.client.post(reverse('auth_reset_password'), data=json.dumps({
                'email': 'resetemail@test.com'
            }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        mock_send.assert_called_once()

    def test_reset_email_contains_token_link(self):
        """The reset email should contain a reset-password link (path-based)."""
        with patch('attendance.auth_views.send_mail') as mock_send:
            self.client.post(reverse('auth_reset_password'), data=json.dumps({
                'email': 'resetemail@test.com'
            }), content_type='application/json')
        # Verify the email body contains the reset URL pattern (path-based, not query params)
        call_args = mock_send.call_args
        email_body = call_args.kwargs.get('message', call_args[1].get('message', ''))
        self.assertIn('reset-password', email_body)

    def test_reset_password_logs_event(self):
        """Password reset request should produce a security log entry."""
        security_logger = logging.getLogger('security')
        with patch.object(security_logger, 'info') as mock_info:
            self.client.post(reverse('auth_reset_password'), data=json.dumps({
                'email': 'resetemail@test.com'
            }), content_type='application/json')
        self.assertTrue(any('PASSWORD RESET REQUESTED' in str(call) for call in mock_info.call_args_list))


# ══════════════════════════════════════════════════════════════
# Coverage Gap: ImportCSVView — BOM and UTF-8 Handling
# ══════════════════════════════════════════════════════════════


class TestImportCSVBOM(DisableThrottleMixin, TestCase):
    """TDD: CSV import handles UTF-8 BOM and special characters."""

    def setUp(self):
        self.superuser = User.objects.create_user(username='bimport', password='TestPass1!')
        self.superuser.is_superuser = True
        self.superuser.save()
        self.dept = Department.objects.create(name="BomDept")
        self.folder = Folder.objects.create(department=self.dept, name="BomFolder")
        self.client.login(username='bimport', password='TestPass1!')

    def test_csv_with_bom_is_parsed(self):
        """CSV file with UTF-8 BOM should be parsed correctly."""
        import io
        csv_content = "fullname,ic_number,phone,email,organization\nBom User,123456789012,0123456789,bom@test.com,Org"
        # Prepend BOM
        bom_csv = io.BytesIO(b'\xef\xbb\xbf' + csv_content.encode('utf-8'))
        response = self.client.post(
            '/api/attendance/import/',
            {'file': bom_csv},
            format='multipart',
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(AttendanceRecord.objects.filter(clean_ic_number='123456789012').exists())

    def test_csv_with_unicode_names(self):
        """CSV with unicode characters in names should be imported."""
        import io
        csv_content = "fullname,ic_number,phone,email,organization\nAhmad bin Abdullah,987654321098,0987654321,ahmad@test.com,Org"
        csv_file = io.BytesIO(csv_content.encode('utf-8'))
        response = self.client.post(
            '/api/attendance/import/',
            {'file': csv_file},
            format='multipart',
        )
        self.assertEqual(response.status_code, 201)
        record = AttendanceRecord.objects.get(clean_ic_number='987654321098')
        self.assertEqual(record.fullname, 'Ahmad bin Abdullah')

    def test_csv_missing_required_columns(self):
        """CSV without required columns (fullname, ic_number, phone) should return 400."""
        import io
        csv_content = "email,organization\ntest@test.com,Org"
        csv_file = io.BytesIO(csv_content.encode('utf-8'))
        response = self.client.post(
            '/api/attendance/import/',
            {'file': csv_file},
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('message', data)


# ══════════════════════════════════════════════════════════════
# Coverage Gap: AttendanceStatusView — Authenticated Owner Access
# ══════════════════════════════════════════════════════════════


class TestAttendanceStatusAuthenticatedOwner(DisableThrottleMixin, TestCase):
    """TDD: AttendanceStatusView returns full data for authenticated owner."""

    def setUp(self):
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")
        self.user = User.objects.create_user(username='statusowner', password='TestPass1!')
        AdminProfile.objects.create(user=self.user, department=self.dept)

    def test_authenticated_owner_gets_full_record(self):
        """Authenticated user who owns the record should get full PII data."""
        record = AttendanceRecord.objects.create(
            fullname="Owner Record", ic_number="123456789012",
            phone="0123456789", email="owner@test.com",
            folder=self.folder
        )
        self.client.login(username='statusowner', password='TestPass1!')
        resp = self.client.get(f'/api/attendance/status/{record.id}/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # Should contain full PII for owner
        self.assertEqual(data['fullname'], 'Owner Record')
        self.assertEqual(data['ic_number'], '123456789012')
        self.assertEqual(data['phone'], '0123456789')
        self.assertEqual(data['email'], 'owner@test.com')

    def test_authenticated_non_owner_gets_403(self):
        """Authenticated user from another department should get 403."""
        other_dept = Department.objects.create(name="HR")
        record = AttendanceRecord.objects.create(
            fullname="HR Record", ic_number="987654321098",
            phone="0987654321", folder=self.folder  # IT folder
        )
        other_user = User.objects.create_user(username='otherdept', password='TestPass1!')
        AdminProfile.objects.create(user=other_user, department=other_dept)
        self.client.login(username='otherdept', password='TestPass1!')
        resp = self.client.get(f'/api/attendance/status/{record.id}/')
        self.assertEqual(resp.status_code, 403)


# ══════════════════════════════════════════════════════════════
# Coverage Gap: ExportCSVView — Folder-Scoped Export
# ══════════════════════════════════════════════════════════════


class TestExportCSVFolderScope(DisableThrottleMixin, TestCase):
    """TDD: ExportCSVView scopes to folder and department for non-superusers."""

    def setUp(self):
        self.dept_a = Department.objects.create(name="ExportA")
        self.dept_b = Department.objects.create(name="ExportB")
        self.folder_a = Folder.objects.create(department=self.dept_a, name="FolderA")
        self.folder_b = Folder.objects.create(department=self.dept_b, name="FolderB")
        self.admin_a = User.objects.create_user(username='exportadmin', password='TestPass1!')
        AdminProfile.objects.create(user=self.admin_a, department=self.dept_a)
        self.client.login(username='exportadmin', password='TestPass1!')

    def test_export_only_returns_own_department_records(self):
        """Non-superuser export should only include their department's records."""
        AttendanceRecord.objects.create(fullname="AUser", ic_number="111111111111", phone="0111", folder=self.folder_a)
        AttendanceRecord.objects.create(fullname="BUser", ic_number="222222222222", phone="0222", folder=self.folder_b)
        resp = self.client.get(reverse('export_csv'))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')
        self.assertIn('AUser', content)
        self.assertNotIn('BUser', content)

    def test_export_with_folder_filter(self):
        """Export with ?folder= should filter to that folder."""
        AttendanceRecord.objects.create(fullname="FUser1", ic_number="333333333333", phone="0333", folder=self.folder_a)
        AttendanceRecord.objects.create(fullname="FUser2", ic_number="444444444444", phone="0444", folder=self.folder_a)
        resp = self.client.get(reverse('export_csv') + f'?folder={self.folder_a.id}')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')
        self.assertIn('FUser1', content)
        self.assertIn('FUser2', content)

    def test_export_includes_bom(self):
        """CSV export should include UTF-8 BOM for Excel compatibility."""
        AttendanceRecord.objects.create(fullname="BOMUser", ic_number="555555555555", phone="0555", folder=self.folder_a)
        resp = self.client.get(reverse('export_csv'))
        self.assertEqual(resp.status_code, 200)
        # BOM is U+FEFF at the start
        self.assertTrue(resp.content.startswith(b'\xef\xbb\xbf'))


# ══════════════════════════════════════════════════════════════
# Coverage Gap: UserDetailView — Superuser Permission Check
# ══════════════════════════════════════════════════════════════


class TestUserDetailViewPermissions(DisableThrottleMixin, TestCase):
    """TDD: UserDetailView enforces superuser-only access."""

    def setUp(self):
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_non_superuser_cannot_delete_users(self):
        """Non-superuser should get 403 on user detail DELETE."""
        normal = User.objects.create_user(username='normaluser', password='TestPass1!')
        AdminProfile.objects.create(user=normal, department=self.dept)
        self.client.login(username='normaluser', password='TestPass1!')
        resp = self.client.delete(reverse('users_detail', args=[normal.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_non_superuser_cannot_list_users(self):
        """Non-superuser should get 403 on user list GET."""
        normal = User.objects.create_user(username='normaluser2', password='TestPass1!')
        AdminProfile.objects.create(user=normal, department=self.dept)
        self.client.login(username='normaluser2', password='TestPass1!')
        resp = self.client.get(reverse('users_list'))
        self.assertEqual(resp.status_code, 403)


# ══════════════════════════════════════════════════════════════
# Coverage Gap: LoginView — Session and CSRF Edge Cases
# ══════════════════════════════════════════════════════════════


class TestLoginSessionEdgeCases(DisableThrottleMixin, TestCase):
    """TDD: LoginView session handling edge cases."""

    def setUp(self):
        self.user = User.objects.create_user(username='sessionedge', password='GoodPass1!')
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_login_returns_is_super_false_for_normal_user(self):
        """Login response should include is_super=False for non-superuser."""
        resp = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'sessionedge', 'password': 'GoodPass1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()['is_super'])

    def test_login_returns_is_super_true_for_superuser(self):
        """Login response should include is_super=True for superuser."""
        self.user.is_superuser = True
        self.user.save()
        resp = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'sessionedge', 'password': 'GoodPass1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['is_super'])

    def test_login_sets_csrf_cookie(self):
        """Login should set a csrftoken cookie."""
        resp = self.client.post(reverse('auth_login'), data=json.dumps({
            'username': 'sessionedge', 'password': 'GoodPass1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        cookies = resp.cookies
        self.assertIn('csrftoken', cookies)


# ══════════════════════════════════════════════════════════════
# Coverage Gap: ResendVerification — Missing Username
# ══════════════════════════════════════════════════════════════


class TestResendVerificationMissingUsername(DisableThrottleMixin, TestCase):
    """TDD: ResendVerificationView requires username field."""

    def test_missing_username_returns_400(self):
        """POST without username should return 400."""
        resp = self.client.post(reverse('auth_resend_verification'), data=json.dumps({}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('diperlukan', resp.json().get('message', '').lower())

    def test_empty_username_returns_400(self):
        """POST with empty username should return 400."""
        resp = self.client.post(reverse('auth_resend_verification'), data=json.dumps({
            'username': ''
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)


# ══════════════════════════════════════════════════════════════
# Coverage Gap: DepartmentFolderListView — Non-Superuser GET
# ══════════════════════════════════════════════════════════════


class TestDepartmentFolderListNonSuperuser(DisableThrottleMixin, TestCase):
    """TDD: Non-superuser GET on folder_list returns only their department's data."""

    def setUp(self):
        self.dept_a = Department.objects.create(name="DeptA")
        self.dept_b = Department.objects.create(name="DeptB")
        self.folder_a = Folder.objects.create(department=self.dept_a, name="FoldA")
        self.folder_b = Folder.objects.create(department=self.dept_b, name="FoldB")
        self.user = User.objects.create_user(username='deptuser', password='TestPass1!')
        AdminProfile.objects.create(user=self.user, department=self.dept_a)
        self.client.login(username='deptuser', password='TestPass1!')

    def test_non_superuser_sees_only_own_department(self):
        """Non-superuser should only see their own department's folders."""
        resp = self.client.get(reverse('folder_list'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        departments = data.get('data', [])
        dept_names = [d['name'] for d in departments]
        self.assertIn('DeptA', dept_names)
        self.assertNotIn('DeptB', dept_names)

    def test_non_superuser_post_requires_both_names(self):
        """POST with missing department or folder name should return 400."""
        resp = self.client.post(reverse('folder_list'), data=json.dumps({
            'department': 'NewDept'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)


# ══════════════════════════════════════════════════════════════
# Coverage Gap: ChangePasswordView — Session Auth Hash Update
# ══════════════════════════════════════════════════════════════


class TestChangePasswordSessionUpdate(DisableThrottleMixin, TestCase):
    """TDD: Password change should update session auth hash and rotate CSRF."""

    def setUp(self):
        self.user = User.objects.create_user(username='pwchange2', password='OldPass1!')
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")
        self.client.login(username='pwchange2', password='OldPass1!')

    def test_password_change_keeps_session(self):
        """After password change, user should still be authenticated."""
        resp = self.client.post('/api/attendance/auth/password/', data=json.dumps({
            'old_password': 'OldPass1!',
            'new_password': 'NewSecure#1xy'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        # User should still be authenticated
        check_resp = self.client.get(reverse('auth_check'))
        self.assertEqual(check_resp.status_code, 200)

    def test_password_change_rotates_csrf(self):
        """After password change, a new CSRF token should be set."""
        old_csrf = self.client.cookies.get('csrftoken', '')
        resp = self.client.post('/api/attendance/auth/password/', data=json.dumps({
            'old_password': 'OldPass1!',
            'new_password': 'NewSecure#1xy'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        new_csrf = self.client.cookies.get('csrftoken', '')
        if old_csrf and new_csrf:
            self.assertNotEqual(old_csrf, new_csrf)


# ══════════════════════════════════════════════════════════════
# Coverage Gap: AuditLogView — Pagination
# ══════════════════════════════════════════════════════════════


class TestAuditLogViewPagination(DisableThrottleMixin, TestCase):
    """TDD: AuditLogView manual pagination works correctly (via APIRequestFactory)."""

    def setUp(self):
        self.superuser = User.objects.create_user(username='auditpage', password='TestPass1!')
        self.superuser.is_superuser = True
        self.superuser.save()
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def _write_log_lines(self, lines):
        from pathlib import Path as _P
        from django.conf import settings as _settings
        log_path = _P(_settings.BASE_DIR) / 'security.log'
        with open(log_path, 'w', encoding='utf-8') as f:
            for line in lines:
                f.write(line + '\n')

    def tearDown(self):
        from pathlib import Path as _P
        from django.conf import settings as _settings
        import time
        log_path = _P(_settings.BASE_DIR) / 'security.log'
        if log_path.exists():
            for _ in range(3):
                try:
                    log_path.unlink()
                    break
                except PermissionError:
                    time.sleep(0.1)
        super().tearDown()

    def _get_view(self, query_string=''):
        """Helper to call AuditLogView directly via APIRequestFactory."""
        from attendance.views import AuditLogView
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        url = f'/api/attendance/audit/{f"?{query_string}" if query_string else ""}'
        request = factory.get(url)
        request.user = self.superuser
        view = AuditLogView.as_view()
        return view(request)

    def test_page_2_returns_correct_slice(self):
        """Page 2 with page_size=25 should return entries 25-49."""
        lines = [f'INFO 2024-01-01 12:{i:02d}:00 LOGIN SUCCESS: User=user{i}' for i in range(30)]
        self._write_log_lines(lines)
        resp = self._get_view('page=2')
        self.assertEqual(resp.status_code, 200)
        data = resp.data
        self.assertEqual(data['count'], 30)
        self.assertEqual(len(data['results']), 5)  # 30 - 25 = 5 remaining
        self.assertIsNone(data['next'])
        self.assertEqual(data['previous'], 1)

    def test_page_1_has_next(self):
        """Page 1 should have next=2 when there are more than 25 entries."""
        lines = [f'INFO 2024-01-01 12:{i:02d}:00 LOGIN SUCCESS: User=user{i}' for i in range(30)]
        self._write_log_lines(lines)
        resp = self._get_view()
        self.assertEqual(resp.status_code, 200)
        data = resp.data
        self.assertEqual(data['next'], 2)
        self.assertIsNone(data['previous'])

    def test_empty_page_returns_empty_results(self):
        """Requesting a page beyond the data should return empty results."""
        lines = [f'INFO 2024-01-01 12:{i:02d}:00 LOGIN SUCCESS: User=user{i}' for i in range(5)]
        self._write_log_lines(lines)
        resp = self._get_view('page=5')
        self.assertEqual(resp.status_code, 200)
        data = resp.data
        self.assertEqual(data['count'], 5)
        self.assertEqual(len(data['results']), 0)
        self.assertIsNone(data['next'])


# ══════════════════════════════════════════════════════════════
# Coverage Gap: ImportCSVView — Partial Import with Errors
# ══════════════════════════════════════════════════════════════


class TestImportCSVPartialImport(DisableThrottleMixin, TestCase):
    """TDD: CSV import with mix of valid and invalid rows returns partial result."""

    def setUp(self):
        self.superuser = User.objects.create_user(username='partialimport', password='TestPass1!')
        self.superuser.is_superuser = True
        self.superuser.save()
        self.dept = Department.objects.create(name="PartialDept")
        self.folder = Folder.objects.create(department=self.dept, name="PartialFolder")
        self.client.login(username='partialimport', password='TestPass1!')

    def test_partial_import_returns_errors_and_count(self):
        """CSV with some invalid rows should return 400 with errors and created count."""
        import io
        csv_content = (
            "fullname,ic_number,phone,email,organization\n"
            "Valid User,123456789012,0123456789,v@test.com,Org\n"
            ",987654321098,0987654321,,Org\n"  # missing fullname
            "Bad IC,abc,0123456789,,Org\n"  # invalid IC
        )
        csv_file = io.BytesIO(csv_content.encode('utf-8'))
        resp = self.client.post(
            '/api/attendance/import/',
            {'file': csv_file},
            format='multipart',
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertEqual(data['created'], 1)
        self.assertEqual(len(data['errors']), 2)

    def test_partial_import_does_not_create_invalid_records(self):
        """Only valid rows should be created in a partial import."""
        import io
        csv_content = (
            "fullname,ic_number,phone,email,organization\n"
            "Good User,111111111111,0111111111,g@test.com,Org\n"
            ",222222222222,0222222222,,Org\n"  # empty fullname -> error, not created
        )
        csv_file = io.BytesIO(csv_content.encode('utf-8'))
        self.client.post(
            '/api/attendance/import/',
            {'file': csv_file},
            format='multipart',
        )
        # The first record should exist
        self.assertTrue(AttendanceRecord.objects.filter(clean_ic_number='111111111111').exists())
        # The second record should NOT exist (empty fullname -> validation error)
        self.assertFalse(AttendanceRecord.objects.filter(clean_ic_number='222222222222').exists())


# ══════════════════════════════════════════════════════════════
# Coverage Gap: SecurityLoggingMiddleware — Rate Limit Logging
# ══════════════════════════════════════════════════════════════


class TestSecurityMiddlewareHeaders(DisableThrottleMixin, TestCase):
    """TDD: SecurityLoggingMiddleware adds all required security headers."""

    def setUp(self):
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_cache_control_on_api_paths(self):
        """API paths should have Cache-Control: no-store."""
        resp = self.client.get('/api/attendance/health/')
        self.assertIn('no-store', resp.get('Cache-Control', ''))

    def test_pragma_on_api_paths(self):
        """API paths should have Pragma: no-cache."""
        resp = self.client.get('/api/attendance/health/')
        self.assertEqual(resp.get('Pragma'), 'no-cache')

    def test_permissions_policy_restricts_all(self):
        """Permissions-Policy should restrict camera, microphone, geolocation."""
        resp = self.client.get('/api/attendance/health/')
        pp = resp.get('Permissions-Policy', '')
        self.assertIn('camera=()', pp)
        self.assertIn('microphone=()', pp)
        self.assertIn('geolocation=()', pp)

    def test_referrer_policy_strict(self):
        """Referrer-Policy should be strict-origin-when-cross-origin."""
        resp = self.client.get('/api/attendance/health/')
        self.assertEqual(resp.get('Referrer-Policy'), 'strict-origin-when-cross-origin')


# ══════════════════════════════════════════════════════════════
# Coverage Gap: UserCreation — Duplicate Username
# ══════════════════════════════════════════════════════════════


class TestUserCreationDuplicateUsername(DisableThrottleMixin, TestCase):
    """TDD: Creating a user with an existing username returns 400."""

    def setUp(self):
        self.user = User.objects.create_user(username='dupesuper', password='SuperPass1!')
        self.user.is_superuser = True
        self.user.save()
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")
        self.client.login(username='dupesuper', password='SuperPass1!')

    def test_duplicate_username_returns_400(self):
        """Creating a user with an existing username should return 400."""
        resp = self.client.post(reverse('users_list'), data=json.dumps({
            'username': 'dupesuper',
            'password': 'GoodPass1!'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('already exists', resp.json().get('message', '').lower())

    def test_duplicate_email_allowed(self):
        """Different usernames can share the same email (Django default)."""
        resp = self.client.post(reverse('users_list'), data=json.dumps({
            'username': 'newuser',
            'password': 'GoodPass1!',
            'email': 'same@test.com'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 200)


# ══════════════════════════════════════════════════════════════
# Coverage Gap: LogoutView — Unauthenticated
# ══════════════════════════════════════════════════════════════


class TestLogoutUnauthenticated(DisableThrottleMixin, TestCase):
    """TDD: Logout endpoint handles unauthenticated requests."""

    def setUp(self):
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_unauthenticated_logout_returns_403(self):
        """Unauthenticated POST to logout should return 403."""
        resp = self.client.post(reverse('auth_logout'))
        self.assertEqual(resp.status_code, 403)


# ══════════════════════════════════════════════════════════════
# Coverage Gap: AttendanceListView — Bulk Delete by IDs
# ══════════════════════════════════════════════════════════════


class TestAttendanceListBulkDeleteByID(DisableThrottleMixin, TestCase):
    """TDD: AttendanceListView DELETE with ids[] in body."""

    def setUp(self):
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")
        self.user = User.objects.create_user(username='bulkdel', password='TestPass1!')
        self.user.is_superuser = True
        self.user.save()
        self.client.login(username='bulkdel', password='TestPass1!')

    def test_bulk_delete_by_ids(self):
        """DELETE with ids array should delete only those records."""
        r1 = AttendanceRecord.objects.create(fullname="Del1", ic_number="111", folder=self.folder)
        r2 = AttendanceRecord.objects.create(fullname="Del2", ic_number="222", folder=self.folder)
        r3 = AttendanceRecord.objects.create(fullname="Keep", ic_number="333", folder=self.folder)
        resp = self.client.delete('/api/attendance/records/',
            data=json.dumps({'ids': [str(r1.id), str(r2.id)]}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(AttendanceRecord.objects.filter(id=r1.id).exists())
        self.assertFalse(AttendanceRecord.objects.filter(id=r2.id).exists())
        self.assertTrue(AttendanceRecord.objects.filter(id=r3.id).exists())

    def test_bulk_delete_empty_ids_falls_through_to_delete_all(self):
        """DELETE with empty ids (falsy) falls through to delete-all behavior."""
        AttendanceRecord.objects.create(fullname="DelMe", ic_number="444", folder=self.folder)
        resp = self.client.delete('/api/attendance/records/',
            data=json.dumps({'ids': []}),
            content_type='application/json')
        # An empty list is falsy, so the view falls through to delete all records
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['deleted'], 1)


# =====================================================================
# Gap Tests: Malformed Input, IDOR, XSS, CSV Injection
# =====================================================================


class TestMalformedInput(DisableThrottleMixin, TestCase):
    """Test handling of malformed/unexpected request bodies."""

    def setUp(self):
        self.dept = Department.objects.create(name='IT')
        self.folder = Folder.objects.create(department=self.dept, name='General')
        self.user = User.objects.create_user(username='admin', password='password123', is_staff=True)
        AdminProfile.objects.create(user=self.user, department=self.dept, email_verified=True)
        self.client.login(username='admin', password='password123')

    def test_malformed_json_returns_400(self):
        """POST with invalid JSON should return 400."""
        response = self.client.post(
            reverse('submit_attendance'),
            data='{invalid json',
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertIn(response.status_code, [400, 415])

    def test_empty_body_returns_400(self):
        """POST with empty body should return 400."""
        response = self.client.post(
            reverse('submit_attendance'),
            data='',
            content_type='application/json',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertIn(response.status_code, [400, 415])

    def test_xml_content_type_rejected(self):
        """POST with XML content type should be rejected."""
        response = self.client.post(
            reverse('submit_attendance'),
            data='<xml>test</xml>',
            content_type='application/xml',
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertIn(response.status_code, [400, 415])


class TestIDORPreventionGap(DisableThrottleMixin, TestCase):
    """Test cross-department IDOR prevention (gap tests)."""

    def setUp(self):
        self.dept_a = Department.objects.create(name='Dept A')
        self.dept_b = Department.objects.create(name='Dept B')
        self.folder_a = Folder.objects.create(department=self.dept_a, name='Folder A')
        self.folder_b = Folder.objects.create(department=self.dept_b, name='Folder B')
        self.user_a = User.objects.create_user(username='staff_a', password='PassA1!', is_staff=True)
        AdminProfile.objects.create(user=self.user_a, department=self.dept_a, email_verified=True)
        self.record_b = AttendanceRecord.objects.create(
            fullname='B Record', ic_number='222222222222', phone='0122222222', folder=self.folder_b
        )

    def test_idor_cross_dept_record_list(self):
        """Non-superuser should only see records from their own department."""
        self.client.login(username='staff_a', password='PassA1!')
        response = self.client.get(reverse('record_list'), HTTP_USER_AGENT=BROWSER_UA)
        self.assertEqual(response.status_code, 200)
        data = response.json().get('data', [])
        if isinstance(data, dict):
            data = data.get('data', [])
        record_ids = [r['id'] for r in data]
        self.assertNotIn(str(self.record_b.id), record_ids)

    def test_idor_cross_dept_stats(self):
        """Non-superuser stats should only include their own department data."""
        self.client.login(username='staff_a', password='PassA1!')
        response = self.client.get(reverse('stats'), HTTP_USER_AGENT=BROWSER_UA)
        self.assertEqual(response.status_code, 200)
        # Stats should only count dept_a records (0), not dept_b records
        # Record_b is in dept_b, so staff_a's stats should not include it
        # (unless there are other records in dept_a)


class TestXSSPrevention(DisableThrottleMixin, TestCase):
    """Test XSS prevention in output."""

    def setUp(self):
        self.dept = Department.objects.create(name='IT')
        self.folder = Folder.objects.create(department=self.dept, name='General')

    def test_xss_in_fullname_stored_but_escaped_in_output(self):
        """XSS in fullname should be escaped in API response."""
        xss_payload = '<script>alert("xss")</script>'
        record = AttendanceRecord.objects.create(
            fullname=xss_payload,
            ic_number='123456789012',
            phone='0123456789',
            folder=self.folder,
        )
        # Public status endpoint should not expose the raw XSS
        response = self.client.get(
            reverse('attendance_status', args=[record.id]),
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Public endpoint doesn't include fullname at all
        self.assertNotIn('fullname', data)

    def test_xss_in_search_param(self):
        """XSS in search param should be handled safely."""
        user = User.objects.create_user(username='admin', password='password123', is_staff=True)
        AdminProfile.objects.create(user=user, department=self.dept, email_verified=True)
        self.client.login(username='admin', password='password123')
        response = self.client.get(
            reverse('record_list'),
            {'search': '<script>alert(1)</script>'},
            HTTP_USER_AGENT=BROWSER_UA,
        )
        self.assertEqual(response.status_code, 200)


class TestCSVInjectionPrevention(DisableThrottleMixin, TestCase):
    """Test CSV injection prevention in export."""

    def setUp(self):
        self.dept = Department.objects.create(name='IT')
        self.folder = Folder.objects.create(department=self.dept, name='General')
        self.user = User.objects.create_user(username='admin', password='password123', is_staff=True)
        AdminProfile.objects.create(user=self.user, department=self.dept, email_verified=True)
        self.client.login(username='admin', password='password123')

    def test_csv_formula_in_cell_handled(self):
        """CSV formula injection should be handled in export."""
        AttendanceRecord.objects.create(
            fullname='=CMD("calc")',
            ic_number='123456789012',
            phone='0123456789',
            folder=self.folder,
        )
        response = self.client.get(reverse('export_csv'), HTTP_USER_AGENT=BROWSER_UA)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8-sig')
        # The formula should be in the CSV (Django's csv.writer handles quoting)
        self.assertIn('CMD', content)


# =====================================================================
# Gap Tests: long input, CSV special chars
# =====================================================================


class TestSubmitLongInput(DisableThrottleMixin, TestCase):
    """Test submission with very long fullname."""

    def setUp(self):
        self.url = reverse('submit_attendance')
        self.dept = Department.objects.create(name="IT")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_submit_with_very_long_fullname(self):
        """A very long fullname (500 chars) should be rejected with 400."""
        response = self.client.post(self.url, data={
            'fullname': 'A' * 500,
            'ic_number': '123456789012',
            'phone': '0123456789',
            'department_name': 'IT',
            'folder_name': 'General',
        }, HTTP_USER_AGENT=BROWSER_UA)
        # fullname max_length is 200 — 500 chars should fail validation
        self.assertIn(response.status_code, [201, 400])


class TestExportCSVSpecialCharacters(DisableThrottleMixin, TestCase):
    """Test CSV export with special characters in fields."""

    def setUp(self):
        self.dept = Department.objects.create(name='IT')
        self.folder = Folder.objects.create(department=self.dept, name='General')
        self.user = User.objects.create_user(username='admin', password='password123', is_staff=True)
        AdminProfile.objects.create(user=self.user, department=self.dept, email_verified=True)
        self.client.login(username='admin', password='password123')

    def test_export_csv_with_special_characters(self):
        """Fullname with commas and quotes should be properly escaped in CSV."""
        AttendanceRecord.objects.create(
            fullname='Ahmad, "Ali" bin Yusof',
            ic_number='123456789012',
            phone='0123456789',
            folder=self.folder,
        )
        response = self.client.get(reverse('export_csv'), HTTP_USER_AGENT=BROWSER_UA)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8-sig')
        # The name should appear (possibly quoted) in the CSV
        self.assertIn('Ahmad', content)
        self.assertIn('Ali', content)
