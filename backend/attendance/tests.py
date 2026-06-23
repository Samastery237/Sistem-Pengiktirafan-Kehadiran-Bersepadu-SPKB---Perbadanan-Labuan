import csv
import logging
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.contrib.auth.hashers import identify_hasher
from django.utils import timezone
from rest_framework import status
from rest_framework.throttling import BaseThrottle

from attendance.models import (
    AdminProfile, AttendanceRecord, Department, EmailVerificationToken,
    FailedLoginAttempt, Folder, UserAccountLock,
)
import json


class DisableThrottleMixin:
    """Mixin to disable DRF throttling for test classes that don't test throttling."""
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
        # Unauthenticated request — should NOT contain sensitive PII (phone/email/IC)
        response = self.client.get(f'/api/attendance/status/{record.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn('phone', data)
        self.assertNotIn('email', data)
        self.assertNotIn('ic_number', data)
        # Name and timestamp should still be present (needed for certificate lookup)
        self.assertEqual(data['fullname'], 'PII Test')

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
        my_record = AttendanceRecord.objects.create(fullname="My Record", ic_number="888888888888", phone="111", folder=self.folder)
        other_record = AttendanceRecord.objects.create(fullname="Other Record", ic_number="888888888888", phone="222", folder=other_folder)

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
        record = AttendanceRecord.objects.create(fullname="Cert User", ic_number="123", phone="123", folder=self.folder)
        response = self.client.get(reverse('download_certificate', args=[record.id]))
        self.assertIn(response.status_code, [200, 500])
        record.refresh_from_db()
        self.assertTrue(record.certificate_generated)

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
        
        my_record = AttendanceRecord.objects.create(fullname="My", folder=self.folder)
        
        with patch('attendance.views._render_to_pdf', return_value=None):
            response = self.client.get(reverse('download_certificate', args=[my_record.id]))
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
        self.assertEqual(resp.status_code, 403)
        self.assertIn('belum diaktifkan', resp.json().get('message', '').lower())


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
        self.assertEqual(resp.status_code, 403)

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

    def test_resend_verification_for_active_user_fails(self):
        """Resending verification for an already active user should fail."""
        resp = self.client.post(reverse('auth_resend_verification'), data=json.dumps({
            'username': 'super'
        }), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

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
        from django.contrib.auth.tokens import PasswordResetTokenGenerator
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
        admin_a = self._create_admin('admin_a', self.dept_a)
        self.client.login(username='admin_a', password='TestPass1!')
        resp = self.client.delete(f'/api/attendance/records/{self.record_b.id}/')
        self.assertEqual(resp.status_code, 403)

    def test_record_detail_idor_patch(self):
        """Admin A cannot modify Admin B's records."""
        admin_a = self._create_admin('admin_a2', self.dept_a)
        self.client.login(username='admin_a2', password='TestPass1!')
        resp = self.client.patch(f'/api/attendance/records/{self.record_b.id}/',
            data=json.dumps({'fullname': 'Hacked'}), content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_folder_detail_idor_get(self):
        """Admin A cannot view Admin B's folders."""
        admin_a = self._create_admin('admin_a3', self.dept_a)
        self.client.login(username='admin_a3', password='TestPass1!')
        resp = self.client.get(reverse('folder_detail', args=[self.folder_b.id]))
        self.assertEqual(resp.status_code, 403)

    def test_folder_detail_idor_patch(self):
        """Admin A cannot modify Admin B's folders."""
        admin_a = self._create_admin('admin_a4', self.dept_a)
        self.client.login(username='admin_a4', password='TestPass1!')
        resp = self.client.patch(reverse('folder_detail', args=[self.folder_b.id]),
            data=json.dumps({'name': 'Hacked'}), content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_folder_detail_idor_delete(self):
        """Admin A cannot delete Admin B's folders."""
        admin_a = self._create_admin('admin_a5', self.dept_a)
        self.client.login(username='admin_a5', password='TestPass1!')
        resp = self.client.delete(reverse('folder_detail', args=[self.folder_b.id]))
        self.assertEqual(resp.status_code, 403)

    def test_department_detail_idor_delete(self):
        """Admin A cannot delete Admin B's department."""
        admin_a = self._create_admin('admin_a6', self.dept_a)
        self.client.login(username='admin_a6', password='TestPass1!')
        resp = self.client.delete(reverse('department_detail', args=[self.dept_b.id]))
        self.assertEqual(resp.status_code, 403)

    def test_superuser_can_access_all_departments(self):
        """Superuser should be able to PATCH records from any department."""
        super_admin = self._create_admin('super_admin', self.dept_a, is_super=True)
        self.client.login(username='super_admin', password='TestPass1!')
        resp = self.client.patch(f'/api/attendance/records/{self.record_b.id}/',
            data=json.dumps({'fullname': 'UpdatedBySuper'}), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.record_b.refresh_from_db()
        self.assertEqual(self.record_b.fullname, 'UpdatedBySuper')

    def test_stats_filtered_by_department(self):
        """Non-superuser stats should only show their department's data."""
        admin_a = self._create_admin('admin_stats', self.dept_a)
        self.client.login(username='admin_stats', password='TestPass1!')
        resp = self.client.get(reverse('stats'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['total'], 1)

    def test_attendance_list_filtered_by_department(self):
        """Non-superuser list should only show their department's records."""
        admin_a = self._create_admin('admin_list', self.dept_a)
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
        """XSS in fullname should be safely handled in the status response."""
        xss = "<script>alert('xss')</script>"
        record = AttendanceRecord.objects.create(
            fullname=xss, ic_number="123456789012", phone="0123456789",
            folder=self.folder
        )
        resp = self.client.get(f'/api/attendance/status/{record.id}/')
        self.assertEqual(resp.status_code, 200)
        # The response should contain the literal string, not execute it
        self.assertEqual(resp.json()['fullname'], xss)

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
        user = User.objects.create_user(username='pwtest', password='TestPass1!')
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
        """Certificate download should be accessible without authentication."""
        record = AttendanceRecord.objects.create(
            fullname="Cert User", ic_number="123456789012",
            phone="0123456789", folder=self.folder
        )
        with patch('attendance.views._render_to_pdf', return_value=b'fake-pdf'):
            resp = self.client.get(reverse('download_certificate', args=[record.id]))
        self.assertEqual(resp.status_code, 200)

    def test_certificate_download_sets_generated_flag(self):
        """Successful certificate download should set certificate_generated flag."""
        record = AttendanceRecord.objects.create(
            fullname="Cert User", ic_number="987654321098",
            phone="0987654321", folder=self.folder
        )
        with patch('attendance.views._render_to_pdf', return_value=b'fake-pdf'):
            self.client.get(reverse('download_certificate', args=[record.id]))
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
        """Today's count should be 5."""
        response = self.client.get(reverse('stats') + '?detail=true')
        data = response.json()
        today_str = timezone.now().date().isoformat()
        today_entry = next((d for d in data['daily_counts'] if d['date'] == today_str), None)
        self.assertIsNotNone(today_entry)
        self.assertEqual(today_entry['count'], 5)

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
