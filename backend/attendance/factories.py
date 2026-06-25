"""
Test data factories for SPKB.

These helper functions create common test data objects.
They can be called from Django TestCase setUp() methods.
"""
import json
import csv
import io

from django.contrib.auth.models import User

from attendance.models import (
    AdminProfile, AttendanceRecord, Department, Folder,
)


BROWSER_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
STRONG_PASSWORD = 'Str0ng!Pass#2024'


def create_department(name='Test Department'):
    """Create and return a Department."""
    return Department.objects.create(name=name)


def create_folder(department, name='General', cert_delay=0, cert_template=None):
    """Create and return a Folder linked to the given department."""
    return Folder.objects.create(
        department=department,
        name=name,
        cert_delay=cert_delay,
        cert_template=cert_template,
    )


def create_attendance(folder, full_name='Test User', ic_number='123456789012',
                      phone='0123456789', email=None, organization=None):
    """Create and return an AttendanceRecord."""
    return AttendanceRecord.objects.create(
        full_name=full_name,
        ic_number=ic_number,
        phone=phone,
        email=email,
        organization=organization,
        folder=folder,
    )


def create_admin_user(username='admin1', password='AdminPass1!', department=None,
                      email_verified=True):
    """Create a staff user with an AdminProfile."""
    user = User.objects.create_user(username=username, password=password, is_staff=True)
    if department:
        AdminProfile.objects.create(
            user=user, department=department, email_verified=email_verified
        )
    return user


def create_superuser(username='super1', password='SuperPass1!'):
    """Create and return a superuser."""
    return User.objects.create_superuser(
        username=username, password=password, email=f'{username}@test.com'
    )


def auth_client(client, username='admin1', password='AdminPass1!'):
    """Log in the test client and return it."""
    client.login(username=username, password=password)
    return client


def post_json(client, url, data):
    """POST JSON data to the given URL."""
    return client.post(url, data=json.dumps(data), content_type='application/json')


def patch_json(client, url, data):
    """PATCH JSON data to the given URL."""
    return client.patch(url, data=json.dumps(data), content_type='application/json')


def make_csv_bytes(rows, header=None):
    """
    Generate a BytesIO CSV file for upload tests.

    Args:
        rows: list of lists, each inner list is a row of values
        header: optional list of column names (default: fullname, ic_number, phone, email, organization)

    Returns:
        BytesIO object containing the CSV data
    """
    if header is None:
        header = ['fullname', 'ic_number', 'phone', 'email', 'organization']
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return io.BytesIO(output.getvalue().encode('utf-8-sig'))  # UTF-8 BOM


def make_attendance_csv(count=5, folder=None):
    """
    Generate a BytesIO CSV with attendance data for import tests.

    Returns:
        BytesIO with header row + count data rows
    """
    rows = []
    for i in range(count):
        rows.append([
            f'Test User {i}',
            f'{100000000000 + i}',
            f'012{i:07d}',
            f'user{i}@test.com',
            f'Org {i}',
        ])
    return make_csv_bytes(rows)
