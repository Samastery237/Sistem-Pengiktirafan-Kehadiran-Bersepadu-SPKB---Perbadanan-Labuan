"""
Shared test fixtures and constants for SPKB test suite.

These fixtures are available to all test files when running with pytest.
For Django TestCase-based tests, the helper functions in factories.py
can be called directly in setUp().
"""
import pytest
from django.contrib.auth.models import User

from attendance.models import (
    AdminProfile, Department, Folder,
)

BROWSER_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
STRONG_PASSWORD = 'Str0ng!Pass#2024'


@pytest.fixture
def department(db):
    """Create a test department."""
    return Department.objects.create(name='Test Department')


@pytest.fixture
def folder(db, department):
    """Create a test folder linked to the department fixture."""
    return Folder.objects.create(
        name='Test Folder',
        department=department,
        cert_delay=0,
    )


@pytest.fixture
def admin_user(db, department):
    """Create a staff admin user with verified email."""
    user = User.objects.create_user(username='admin1', password='AdminPass1!')
    AdminProfile.objects.create(user=user, department=department, email_verified=True)
    return user


@pytest.fixture
def superuser(db):
    """Create a superuser."""
    return User.objects.create_superuser(
        username='super1', password='SuperPass1!', email='super@test.com'
    )


@pytest.fixture
def authenticated_client(client, admin_user):
    """Return a Django test client logged in as admin_user."""
    client.login(username='admin1', password='AdminPass1!')
    return client


@pytest.fixture
def superuser_client(client, superuser):
    """Return a Django test client logged in as superuser."""
    client.login(username='super1', password='SuperPass1!')
    return client
