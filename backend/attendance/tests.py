from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from attendance.models import Department, Folder, AttendanceRecord
import json

class FullBackendSuite(TestCase):
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
        """Simulate brute force to test the 5/minute throttle on login."""
        for i in range(5):
            self.client.post(reverse('auth_login'), data=json.dumps({'username':'admin','password':'w'}), content_type='application/json')
        # 6th attempt should be throttled (429)
        response = self.client.post(reverse('auth_login'), data=json.dumps({'username':'admin','password':'w'}), content_type='application/json')
        self.assertEqual(response.status_code, 429)

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
        
        # If the backend is vulnerable to SQLi, it might return all records.
        # Since Django ORM is secure, it will safely parameterize the string and find 0 matches, returning 404.
        self.assertEqual(response.status_code, 404)

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

