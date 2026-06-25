"""
Comprehensive TDD tests for the SPKB attendance system models.

Tests cover: Department, Folder, AttendanceRecord, AdminProfile,
FailedLoginAttempt, UserAccountLock, AbuseRequestLog, EmailVerificationToken.
"""

from datetime import timedelta

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import IntegrityError

from attendance.models import (
    Department, Folder, AttendanceRecord, AdminProfile,
    FailedLoginAttempt, UserAccountLock, AbuseRequestLog,
    EmailVerificationToken,
)


BROWSER_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'


# =====================================================================
# Department Model Tests
# =====================================================================

class DepartmentModelTest(TestCase):
    """Tests for the Department model."""

    def test_create_department_with_name(self):
        """Department can be created with a name."""
        dept = Department.objects.create(name="IT")
        self.assertEqual(dept.name, "IT")

    def test_str_representation(self):
        """str() returns the department name."""
        dept = Department.objects.create(name="Finance")
        self.assertEqual(str(dept), "Finance")

    def test_name_is_unique(self):
        """Two departments cannot share the same name."""
        Department.objects.create(name="UniqueDept")
        with self.assertRaises(IntegrityError):
            Department.objects.create(name="UniqueDept")

    def test_created_at_auto_set(self):
        """created_at is automatically set on creation."""
        dept = Department.objects.create(name="AutoDate")
        self.assertIsNotNone(dept.created_at)

    def test_created_at_is_current_time(self):
        """created_at is approximately the current time."""
        before = timezone.now()
        dept = Department.objects.create(name="TimeCheck")
        after = timezone.now()
        self.assertGreaterEqual(dept.created_at, before)
        self.assertLessEqual(dept.created_at, after)

    def test_name_max_length_255(self):
        """Department name accepts up to 255 characters."""
        long_name = "A" * 255
        dept = Department.objects.create(name=long_name)
        self.assertEqual(dept.name, long_name)

    def test_name_exceeding_max_length_truncated_or_accepted(self):
        """Department name exceeding 255 chars may be truncated by SQLite."""
        # SQLite does not enforce VARCHAR length constraints; the database
        # silently truncates. We verify the model accepts the value without
        # crashing (the real enforcement would be at the DB backend level).
        long_name = "A" * 256
        dept = Department(name=long_name)
        dept.save()
        # The name was saved (possibly truncated depending on backend)
        self.assertIsNotNone(dept.pk)

    def test_multiple_departments_can_exist(self):
        """Multiple departments with different names can be created."""
        Department.objects.create(name="Dept1")
        Department.objects.create(name="Dept2")
        Department.objects.create(name="Dept3")
        self.assertEqual(Department.objects.count(), 3)

    def test_department_has_folders_related_name(self):
        """Department can access related folders via 'folders' related name."""
        dept = Department.objects.create(name="RelatedDept")
        folder = Folder.objects.create(department=dept, name="TestFolder")
        self.assertIn(folder, dept.folders.all())

    def test_department_with_empty_name_allowed(self):
        """Department with empty string name is allowed (no blank=False)."""
        dept = Department.objects.create(name="")
        self.assertEqual(dept.name, "")


# =====================================================================
# Folder Model Tests
# =====================================================================

class FolderModelTest(TestCase):
    """Tests for the Folder model."""

    def setUp(self):
        self.dept = Department.objects.create(name="TestDept")

    def test_create_folder_with_department(self):
        """Folder can be created with a department."""
        folder = Folder.objects.create(department=self.dept, name="General")
        self.assertEqual(folder.department, self.dept)
        self.assertEqual(folder.name, "General")

    def test_str_representation_with_department(self):
        """str() returns 'DepartmentName - FolderName'."""
        folder = Folder.objects.create(department=self.dept, name="General")
        self.assertEqual(str(folder), "TestDept - General")

    def test_str_representation_without_department(self):
        """str() returns 'No Dept - FolderName' when department is None."""
        folder = Folder.objects.create(department=None, name="NoDeptFolder")
        self.assertEqual(str(folder), "No Dept - NoDeptFolder")

    def test_unique_together_department_name(self):
        """Two folders in the same department cannot share the same name."""
        Folder.objects.create(department=self.dept, name="UniqueFolder")
        with self.assertRaises(IntegrityError):
            Folder.objects.create(department=self.dept, name="UniqueFolder")

    def test_same_name_different_departments_allowed(self):
        """Same folder name is allowed across different departments."""
        other_dept = Department.objects.create(name="OtherDept")
        Folder.objects.create(department=self.dept, name="SharedName")
        Folder.objects.create(department=other_dept, name="SharedName")
        self.assertEqual(Folder.objects.filter(name="SharedName").count(), 2)

    def test_cert_delay_default_is_zero(self):
        """cert_delay defaults to 0."""
        folder = Folder.objects.create(department=self.dept, name="DelayCheck")
        self.assertEqual(folder.cert_delay, 0)

    def test_cert_template_nullable(self):
        """cert_template can be null."""
        folder = Folder.objects.create(department=self.dept, name="NullCert")
        self.assertIsNone(folder.cert_template)

    def test_cert_template_blank_allowed(self):
        """cert_template can be blank string."""
        folder = Folder.objects.create(department=self.dept, name="BlankCert", cert_template="")
        self.assertEqual(folder.cert_template, "")

    def test_positioning_defaults(self):
        """Name and IC positioning fields have correct defaults."""
        folder = Folder.objects.create(department=self.dept, name="Defaults")
        self.assertEqual(folder.name_x, 50)
        self.assertEqual(folder.name_y, 45)
        self.assertEqual(folder.name_size, 48)
        self.assertEqual(folder.ic_x, 50)
        self.assertEqual(folder.ic_y, 53)
        self.assertEqual(folder.ic_size, 24)

    def test_show_ic_default_true(self):
        """show_ic defaults to True."""
        folder = Folder.objects.create(department=self.dept, name="ShowIC")
        self.assertTrue(folder.show_ic)

    def test_text_color_default(self):
        """text_color defaults to '#000000'."""
        folder = Folder.objects.create(department=self.dept, name="ColorCheck")
        self.assertEqual(folder.text_color, "#000000")

    def test_font_family_default(self):
        """font_family defaults to 'Arial, sans-serif'."""
        folder = Folder.objects.create(department=self.dept, name="FontCheck")
        self.assertEqual(folder.font_family, "Arial, sans-serif")

    def test_event_name_nullable(self):
        """event_name can be null."""
        folder = Folder.objects.create(department=self.dept, name="EventCheck")
        self.assertIsNone(folder.event_name)

    def test_event_date_nullable(self):
        """event_date can be null."""
        folder = Folder.objects.create(department=self.dept, name="DateCheck")
        self.assertIsNone(folder.event_date)

    def test_organizer_default(self):
        """organizer defaults to 'Perbadanan Labuan'."""
        folder = Folder.objects.create(department=self.dept, name="OrgCheck")
        self.assertEqual(folder.organizer, "Perbadanan Labuan")

    def test_created_at_auto_set(self):
        """created_at is automatically set on creation."""
        folder = Folder.objects.create(department=self.dept, name="CreatedCheck")
        self.assertIsNotNone(folder.created_at)

    def test_custom_positioning_values(self):
        """Custom positioning values are stored correctly."""
        folder = Folder.objects.create(
            department=self.dept, name="CustomPos",
            name_x=100, name_y=200, name_size=36,
            ic_x=150, ic_y=250, ic_size=20,
        )
        self.assertEqual(folder.name_x, 100)
        self.assertEqual(folder.name_y, 200)
        self.assertEqual(folder.name_size, 36)
        self.assertEqual(folder.ic_x, 150)
        self.assertEqual(folder.ic_y, 250)
        self.assertEqual(folder.ic_size, 20)

    def test_custom_event_fields(self):
        """Custom event fields are stored correctly."""
        folder = Folder.objects.create(
            department=self.dept, name="EventFolder",
            event_name="Annual Dinner",
            event_date="2025-12-25",
            organizer="PL Events Committee",
        )
        self.assertEqual(folder.event_name, "Annual Dinner")
        self.assertEqual(folder.event_date, "2025-12-25")
        self.assertEqual(folder.organizer, "PL Events Committee")

    def test_folder_has_attendances_related_name(self):
        """Folder can access related attendance records via 'attendances'."""
        folder = Folder.objects.create(department=self.dept, name="AttendanceCheck")
        record = AttendanceRecord.objects.create(
            fullname="Test User", folder=folder
        )
        self.assertIn(record, folder.attendances.all())

    def test_cert_delay_custom_value(self):
        """Custom cert_delay value is stored correctly."""
        folder = Folder.objects.create(
            department=self.dept, name="CustomDelay", cert_delay=5000
        )
        self.assertEqual(folder.cert_delay, 5000)

    def test_text_color_custom_value(self):
        """Custom text_color value is stored correctly."""
        folder = Folder.objects.create(
            department=self.dept, name="CustomColor", text_color="#ff0000"
        )
        self.assertEqual(folder.text_color, "#ff0000")

    def test_font_family_custom_value(self):
        """Custom font_family value is stored correctly."""
        folder = Folder.objects.create(
            department=self.dept, name="CustomFont", font_family="Times, serif"
        )
        self.assertEqual(folder.font_family, "Times, serif")


# =====================================================================
# AttendanceRecord Model Tests
# =====================================================================

class AttendanceRecordModelTest(TestCase):
    """Tests for the AttendanceRecord model."""

    def setUp(self):
        self.dept = Department.objects.create(name="TestDept")
        self.folder = Folder.objects.create(department=self.dept, name="General")

    def test_create_record_with_required_fields(self):
        """Record can be created with fullname and folder."""
        record = AttendanceRecord.objects.create(
            fullname="John Doe", folder=self.folder
        )
        self.assertEqual(record.fullname, "John Doe")
        self.assertEqual(record.folder, self.folder)

    def test_uuid_primary_key(self):
        """id is a UUID field set automatically."""
        record = AttendanceRecord.objects.create(
            fullname="UUID Test", folder=self.folder
        )
        self.assertIsNotNone(record.id)
        import uuid
        self.assertIsInstance(record.id, uuid.UUID)

    def test_uuid_is_unique(self):
        """Each record gets a unique UUID."""
        r1 = AttendanceRecord.objects.create(fullname="R1", folder=self.folder)
        r2 = AttendanceRecord.objects.create(fullname="R2", folder=self.folder)
        self.assertNotEqual(r1.id, r2.id)

    def test_str_representation(self):
        """str() returns 'Fullname - FolderName'."""
        record = AttendanceRecord.objects.create(
            fullname="Jane Doe", folder=self.folder
        )
        self.assertEqual(str(record), "Jane Doe - General")

    def test_str_representation_no_folder(self):
        """str() returns 'Fullname - No Folder' when folder is None."""
        record = AttendanceRecord.objects.create(
            fullname="No Folder User", folder=None
        )
        self.assertEqual(str(record), "No Folder User - No Folder")

    def test_ref_optional(self):
        """ref field is optional."""
        record = AttendanceRecord.objects.create(
            fullname="Ref Test", folder=self.folder
        )
        self.assertIsNone(record.ref)

    def test_ref_can_be_set(self):
        """ref field can be set to a string value."""
        record = AttendanceRecord.objects.create(
            fullname="Ref Set", folder=self.folder, ref="REF-001"
        )
        self.assertEqual(record.ref, "REF-001")

    def test_ic_number_optional(self):
        """ic_number field is optional."""
        record = AttendanceRecord.objects.create(
            fullname="No IC", folder=self.folder
        )
        self.assertEqual(record.ic_number, "")

    def test_save_cleans_ic_number_with_dashes(self):
        """save() strips dashes from ic_number into clean_ic_number."""
        record = AttendanceRecord(
            fullname="Dash IC",
            ic_number="123456-78-9012",
            folder=self.folder,
        )
        record.save()
        self.assertEqual(record.clean_ic_number, "123456789012")

    def test_save_cleans_ic_number_no_dashes(self):
        """save() preserves digits-only ic_number in clean_ic_number."""
        record = AttendanceRecord(
            fullname="Clean IC",
            ic_number="123456789012",
            folder=self.folder,
        )
        record.save()
        self.assertEqual(record.clean_ic_number, "123456789012")

    def test_save_cleans_ic_number_empty_string(self):
        """save() with empty ic_number leaves clean_ic_number as None (default)."""
        record = AttendanceRecord(
            fullname="Empty IC",
            ic_number="",
            folder=self.folder,
        )
        record.save()
        # Empty string is falsy, so save() skips cleaning; clean_ic_number stays None
        self.assertIsNone(record.clean_ic_number)

    def test_save_cleans_ic_number_with_spaces(self):
        """save() strips spaces from ic_number."""
        record = AttendanceRecord(
            fullname="Space IC",
            ic_number="123 456 789 012",
            folder=self.folder,
        )
        record.save()
        self.assertEqual(record.clean_ic_number, "123456789012")

    def test_save_cleans_ic_number_with_letters(self):
        """save() strips non-digit characters from ic_number."""
        record = AttendanceRecord(
            fullname="Alpha IC",
            ic_number="123456A78B9012",
            folder=self.folder,
        )
        record.save()
        self.assertEqual(record.clean_ic_number, "123456789012")

    def test_save_cleans_ic_number_mixed_special_chars(self):
        """save() strips all non-digit characters including mixed special chars."""
        record = AttendanceRecord(
            fullname="Special IC",
            ic_number="12-34.56_78+9012",
            folder=self.folder,
        )
        record.save()
        self.assertEqual(record.clean_ic_number, "123456789012")

    def test_phone_optional(self):
        """phone field is optional."""
        record = AttendanceRecord.objects.create(
            fullname="No Phone", folder=self.folder
        )
        self.assertIsNone(record.phone)

    def test_email_optional(self):
        """email field is optional."""
        record = AttendanceRecord.objects.create(
            fullname="No Email", folder=self.folder
        )
        self.assertIsNone(record.email)

    def test_organization_optional(self):
        """organization field is optional."""
        record = AttendanceRecord.objects.create(
            fullname="No Org", folder=self.folder
        )
        self.assertIsNone(record.organization)

    def test_timestamp_default_is_now(self):
        """timestamp defaults to approximately the current time."""
        before = timezone.now()
        record = AttendanceRecord.objects.create(
            fullname="Time Test", folder=self.folder
        )
        after = timezone.now()
        self.assertGreaterEqual(record.timestamp, before)
        self.assertLessEqual(record.timestamp, after)

    def test_cert_delay_default_is_zero(self):
        """cert_delay defaults to 0."""
        record = AttendanceRecord.objects.create(
            fullname="Delay Test", folder=self.folder
        )
        self.assertEqual(record.cert_delay, 0)

    def test_certificate_generated_default_false(self):
        """certificate_generated defaults to False."""
        record = AttendanceRecord.objects.create(
            fullname="Cert Flag", folder=self.folder
        )
        self.assertFalse(record.certificate_generated)

    def test_clean_ic_number_nullable(self):
        """clean_ic_number can be null."""
        record = AttendanceRecord.objects.create(
            fullname="Null Clean", folder=self.folder
        )
        self.assertIsNone(record.clean_ic_number)

    def test_clean_ic_number_indexed(self):
        """clean_ic_number has a database index for fast lookups."""
        # Verify by checking the field definition
        field = AttendanceRecord._meta.get_field('clean_ic_number')
        self.assertTrue(field.db_index)

    def test_timestamp_indexed(self):
        """timestamp has a database index for fast lookups."""
        field = AttendanceRecord._meta.get_field('timestamp')
        self.assertTrue(field.db_index)

    def test_fullname_max_length_255(self):
        """fullname accepts up to 255 characters."""
        long_name = "A" * 255
        record = AttendanceRecord.objects.create(
            fullname=long_name, folder=self.folder
        )
        self.assertEqual(record.fullname, long_name)

    def test_fullname_stores_empty_string(self):
        """fullname is a CharField (blank=False by default), but Django allows empty string on save."""
        # Django CharField with blank=False validates at form level, not model save().
        # An empty fullname can be saved; validation happens in the serializer.
        record = AttendanceRecord(fullname="", folder=self.folder)
        record.save()
        self.assertEqual(record.fullname, "")

    def test_folder_cascade_delete(self):
        """Deleting a folder cascades to its attendance records."""
        record = AttendanceRecord.objects.create(
            fullname="Cascade Test", folder=self.folder
        )
        self.folder.delete()
        self.assertFalse(AttendanceRecord.objects.filter(id=record.id).exists())

    def test_save_persists_clean_ic_number_to_db(self):
        """clean_ic_number is persisted correctly after reload from DB."""
        record = AttendanceRecord(
            fullname="Persist IC",
            ic_number="987654-32-1098",
            folder=self.folder,
        )
        record.save()
        record.refresh_from_db()
        self.assertEqual(record.clean_ic_number, "987654321098")

    def test_save_does_not_clean_when_ic_number_falsy(self):
        """save() does not overwrite clean_ic_number when ic_number is falsy."""
        record = AttendanceRecord(
            fullname="Existing Clean",
            ic_number="",
            folder=self.folder,
        )
        record.save()
        # Since ic_number is falsy (empty string), clean_ic_number stays as default (None)
        self.assertIsNone(record.clean_ic_number)


# =====================================================================
# AdminProfile Model Tests
# =====================================================================

class AdminProfileModelTest(TestCase):
    """Tests for the AdminProfile model."""

    def setUp(self):
        self.user = User.objects.create_user(username='admin', password='TestPass1!')
        self.dept = Department.objects.create(name="AdminDept")

    def test_create_admin_profile(self):
        """AdminProfile can be created with user and department."""
        profile = AdminProfile.objects.create(user=self.user, department=self.dept)
        self.assertEqual(profile.user, self.user)
        self.assertEqual(profile.department, self.dept)

    def test_str_representation_with_department(self):
        """str() returns 'username - department_name'."""
        profile = AdminProfile.objects.create(user=self.user, department=self.dept)
        self.assertEqual(str(profile), "admin - AdminDept")

    def test_str_representation_without_department(self):
        """str() returns 'username - Super Admin' when department is None."""
        profile = AdminProfile.objects.create(user=self.user, department=None)
        self.assertEqual(str(profile), "admin - Super Admin")

    def test_user_one_to_one_relationship(self):
        """A user can only have one AdminProfile."""
        AdminProfile.objects.create(user=self.user, department=self.dept)
        with self.assertRaises(IntegrityError):
            AdminProfile.objects.create(user=self.user, department=self.dept)

    def test_email_verified_default_false(self):
        """email_verified defaults to False."""
        profile = AdminProfile.objects.create(user=self.user, department=self.dept)
        self.assertFalse(profile.email_verified)

    def test_verified_at_nullable(self):
        """verified_at can be null."""
        profile = AdminProfile.objects.create(user=self.user, department=self.dept)
        self.assertIsNone(profile.verified_at)

    def test_verified_at_can_be_set(self):
        """verified_at can be set to a datetime."""
        now = timezone.now()
        profile = AdminProfile.objects.create(
            user=self.user, department=self.dept,
            email_verified=True, verified_at=now
        )
        self.assertTrue(profile.email_verified)
        self.assertEqual(profile.verified_at, now)

    def test_department_nullable(self):
        """department field can be null."""
        profile = AdminProfile.objects.create(user=self.user, department=None)
        self.assertIsNone(profile.department)

    def test_department_set_null_on_delete(self):
        """When department is deleted, profile.department is set to NULL."""
        profile = AdminProfile.objects.create(user=self.user, department=self.dept)
        self.dept.delete()
        profile.refresh_from_db()
        self.assertIsNone(profile.department)

    def test_user_cascade_delete(self):
        """Deleting a user deletes the AdminProfile."""
        profile = AdminProfile.objects.create(user=self.user, department=self.dept)
        self.user.delete()
        self.assertFalse(AdminProfile.objects.filter(id=profile.id).exists())

    def test_admin_profile_related_name(self):
        """User can access profile via 'admin_profile' related name."""
        profile = AdminProfile.objects.create(user=self.user, department=self.dept)
        self.assertEqual(self.user.admin_profile, profile)

    def test_email_verified_can_be_set_true(self):
        """email_verified can be set to True."""
        profile = AdminProfile.objects.create(
            user=self.user, department=self.dept, email_verified=True
        )
        self.assertTrue(profile.email_verified)


# =====================================================================
# FailedLoginAttempt Model Tests
# =====================================================================

class FailedLoginAttemptModelTest(TestCase):
    """Tests for the FailedLoginAttempt model."""

    def test_create_failed_attempt(self):
        """FailedLoginAttempt can be created with username and ip."""
        attempt = FailedLoginAttempt.objects.create(
            username="testuser", ip_address="192.168.1.1"
        )
        self.assertEqual(attempt.username, "testuser")
        self.assertEqual(attempt.ip_address, "192.168.1.1")

    def test_str_representation(self):
        """str() includes username, ip_address, and attempted_at."""
        attempt = FailedLoginAttempt.objects.create(
            username="struser", ip_address="10.0.0.1"
        )
        result = str(attempt)
        self.assertIn("struser", result)
        self.assertIn("10.0.0.1", result)

    def test_attempted_at_auto_set(self):
        """attempted_at is automatically set on creation."""
        attempt = FailedLoginAttempt.objects.create(
            username="autotime", ip_address="10.0.0.1"
        )
        self.assertIsNotNone(attempt.attempted_at)

    def test_ordering_by_attempted_at_desc(self):
        """Default ordering is by attempted_at descending (newest first)."""
        attempt1 = FailedLoginAttempt.objects.create(
            username="user1", ip_address="10.0.0.1"
        )
        attempt2 = FailedLoginAttempt.objects.create(
            username="user2", ip_address="10.0.0.2"
        )
        attempts = list(FailedLoginAttempt.objects.all())
        self.assertEqual(attempts[0], attempt2)
        self.assertEqual(attempts[1], attempt1)

    def test_username_indexed(self):
        """username has a database index."""
        field = FailedLoginAttempt._meta.get_field('username')
        self.assertTrue(field.db_index)

    def test_ip_address_indexed(self):
        """ip_address has a database index."""
        field = FailedLoginAttempt._meta.get_field('ip_address')
        self.assertTrue(field.db_index)

    def test_multiple_attempts_same_user(self):
        """Multiple failed attempts for the same user can be recorded."""
        for i in range(5):
            FailedLoginAttempt.objects.create(
                username="repeat", ip_address="10.0.0.1"
            )
        self.assertEqual(
            FailedLoginAttempt.objects.filter(username="repeat").count(), 5
        )

    def test_ipv6_address_supported(self):
        """IPv6 addresses are supported."""
        attempt = FailedLoginAttempt.objects.create(
            username="ipv6user", ip_address="::1"
        )
        self.assertEqual(attempt.ip_address, "::1")

    def test_verbose_name(self):
        """Model has correct verbose name and plural."""
        self.assertEqual(FailedLoginAttempt._meta.verbose_name, 'Failed Login Attempt')
        self.assertEqual(FailedLoginAttempt._meta.verbose_name_plural, 'Failed Login Attempts')


# =====================================================================
# UserAccountLock Model Tests
# =====================================================================

class UserAccountLockModelTest(TestCase):
    """Tests for the UserAccountLock model."""

    def setUp(self):
        self.user = User.objects.create_user(username='lockuser', password='TestPass1!')

    def test_create_account_lock(self):
        """UserAccountLock can be created for a user."""
        lock = UserAccountLock.objects.create(user=self.user)
        self.assertEqual(lock.user, self.user)

    def test_user_one_to_one_relationship(self):
        """A user can only have one UserAccountLock."""
        UserAccountLock.objects.create(user=self.user)
        with self.assertRaises(IntegrityError):
            UserAccountLock.objects.create(user=self.user)

    def test_str_representation(self):
        """str() includes username and locked_until."""
        lock = UserAccountLock.objects.create(user=self.user)
        result = str(lock)
        self.assertIn("lockuser", result)

    def test_locked_until_nullable(self):
        """locked_until can be null."""
        lock = UserAccountLock.objects.create(user=self.user)
        self.assertIsNone(lock.locked_until)

    def test_failure_count_default_zero(self):
        """failure_count defaults to 0."""
        lock = UserAccountLock.objects.create(user=self.user)
        self.assertEqual(lock.failure_count, 0)

    def test_last_failure_at_nullable(self):
        """last_failure_at can be null."""
        lock = UserAccountLock.objects.create(user=self.user)
        self.assertIsNone(lock.last_failure_at)

    def test_is_locked_false_when_locked_until_none(self):
        """is_locked returns False when locked_until is None."""
        lock = UserAccountLock.objects.create(user=self.user, locked_until=None)
        self.assertFalse(lock.is_locked)

    def test_is_locked_true_when_locked_until_in_future(self):
        """is_locked returns True when locked_until is in the future."""
        future = timezone.now() + timedelta(minutes=15)
        lock = UserAccountLock.objects.create(user=self.user, locked_until=future)
        self.assertTrue(lock.is_locked)

    def test_is_locked_false_when_locked_until_in_past(self):
        """is_locked returns False when locked_until is in the past (expired)."""
        past = timezone.now() - timedelta(minutes=1)
        lock = UserAccountLock.objects.create(user=self.user, locked_until=past)
        self.assertFalse(lock.is_locked)

    def test_is_locked_false_when_locked_until_exactly_now(self):
        """is_locked returns False when locked_until is exactly now (boundary)."""
        # locked_until == now means now < locked_until is False
        now = timezone.now()
        lock = UserAccountLock.objects.create(user=self.user, locked_until=now)
        # timezone.now() in property will be slightly after, so not locked
        self.assertFalse(lock.is_locked)

    def test_is_locked_true_long_future(self):
        """is_locked returns True for a lock far in the future."""
        far_future = timezone.now() + timedelta(days=365)
        lock = UserAccountLock.objects.create(user=self.user, locked_until=far_future)
        self.assertTrue(lock.is_locked)

    def test_user_cascade_delete(self):
        """Deleting a user deletes the UserAccountLock."""
        lock = UserAccountLock.objects.create(user=self.user)
        self.user.delete()
        self.assertFalse(UserAccountLock.objects.filter(id=lock.id).exists())

    def test_account_lock_related_name(self):
        """User can access lock via 'account_lock' related name."""
        lock = UserAccountLock.objects.create(user=self.user)
        self.assertEqual(self.user.account_lock, lock)

    def test_verbose_name(self):
        """Model has correct verbose name and plural."""
        self.assertEqual(UserAccountLock._meta.verbose_name, 'User Account Lock')
        self.assertEqual(UserAccountLock._meta.verbose_name_plural, 'User Account Locks')

    def test_failure_count_can_be_incremented(self):
        """failure_count can be incremented."""
        lock = UserAccountLock.objects.create(user=self.user)
        lock.failure_count += 1
        lock.save()
        lock.refresh_from_db()
        self.assertEqual(lock.failure_count, 1)

    def test_last_failure_at_can_be_set(self):
        """last_failure_at can be set to a datetime."""
        now = timezone.now()
        lock = UserAccountLock.objects.create(user=self.user, last_failure_at=now)
        self.assertEqual(lock.last_failure_at, now)


# =====================================================================
# AbuseRequestLog Model Tests
# =====================================================================

class AbuseRequestLogModelTest(TestCase):
    """Tests for the AbuseRequestLog model."""

    def test_create_abuse_log(self):
        """AbuseRequestLog can be created with ip_address."""
        log = AbuseRequestLog.objects.create(ip_address="192.168.1.1")
        self.assertEqual(log.ip_address, "192.168.1.1")

    def test_str_representation(self):
        """str() includes ip_address, request_count, and is_blocked."""
        log = AbuseRequestLog.objects.create(
            ip_address="10.0.0.1", request_count=5, is_blocked=True
        )
        result = str(log)
        self.assertIn("10.0.0.1", result)
        self.assertIn("5", result)
        self.assertIn("True", result)

    def test_window_start_default(self):
        """window_start defaults to approximately current time."""
        before = timezone.now()
        log = AbuseRequestLog.objects.create(ip_address="10.0.0.1")
        after = timezone.now()
        self.assertGreaterEqual(log.window_start, before)
        self.assertLessEqual(log.window_start, after)

    def test_request_count_default_one(self):
        """request_count defaults to 1."""
        log = AbuseRequestLog.objects.create(ip_address="10.0.0.1")
        self.assertEqual(log.request_count, 1)

    def test_is_blocked_default_false(self):
        """is_blocked defaults to False."""
        log = AbuseRequestLog.objects.create(ip_address="10.0.0.1")
        self.assertFalse(log.is_blocked)

    def test_blocked_until_nullable(self):
        """blocked_until can be null."""
        log = AbuseRequestLog.objects.create(ip_address="10.0.0.1")
        self.assertIsNone(log.blocked_until)

    def test_last_request_path_default_empty(self):
        """last_request_path defaults to empty string."""
        log = AbuseRequestLog.objects.create(ip_address="10.0.0.1")
        self.assertEqual(log.last_request_path, "")

    def test_user_agent_nullable(self):
        """user_agent can be null."""
        log = AbuseRequestLog.objects.create(ip_address="10.0.0.1")
        self.assertIsNone(log.user_agent)

    def test_user_agent_can_be_set(self):
        """user_agent can be set to a string value."""
        log = AbuseRequestLog.objects.create(
            ip_address="10.0.0.1", user_agent=BROWSER_UA
        )
        self.assertEqual(log.user_agent, BROWSER_UA)

    def test_ordering_by_window_start_desc(self):
        """Default ordering is by window_start descending (newest first)."""
        log1 = AbuseRequestLog.objects.create(ip_address="10.0.0.1")
        log2 = AbuseRequestLog.objects.create(ip_address="10.0.0.2")
        logs = list(AbuseRequestLog.objects.all())
        self.assertEqual(logs[0], log2)
        self.assertEqual(logs[1], log1)

    def test_ip_address_indexed(self):
        """ip_address has a database index."""
        field = AbuseRequestLog._meta.get_field('ip_address')
        self.assertTrue(field.db_index)

    def test_request_count_can_be_incremented(self):
        """request_count can be incremented."""
        log = AbuseRequestLog.objects.create(ip_address="10.0.0.1")
        log.request_count += 10
        log.save()
        log.refresh_from_db()
        self.assertEqual(log.request_count, 11)

    def test_is_blocked_can_be_set_true(self):
        """is_blocked can be set to True."""
        log = AbuseRequestLog.objects.create(
            ip_address="10.0.0.1", is_blocked=True
        )
        self.assertTrue(log.is_blocked)

    def test_blocked_until_can_be_set(self):
        """blocked_until can be set to a datetime."""
        future = timezone.now() + timedelta(hours=1)
        log = AbuseRequestLog.objects.create(
            ip_address="10.0.0.1", blocked_until=future
        )
        self.assertEqual(log.blocked_until, future)

    def test_last_request_path_can_be_set(self):
        """last_request_path can be set to a path string."""
        log = AbuseRequestLog.objects.create(
            ip_address="10.0.0.1", last_request_path="/api/attendance/stats/"
        )
        self.assertEqual(log.last_request_path, "/api/attendance/stats/")

    def test_verbose_name(self):
        """Model has correct verbose name and plural."""
        self.assertEqual(AbuseRequestLog._meta.verbose_name, 'Abuse Request Log')
        self.assertEqual(AbuseRequestLog._meta.verbose_name_plural, 'Abuse Request Logs')


# =====================================================================
# EmailVerificationToken Model Tests
# =====================================================================

class EmailVerificationTokenModelTest(TestCase):
    """Tests for the EmailVerificationToken model."""

    def setUp(self):
        self.user = User.objects.create_user(username='verifyuser', password='TestPass1!')

    def test_create_token(self):
        """EmailVerificationToken can be created with user and expires_at."""
        expires = timezone.now() + timedelta(hours=24)
        token = EmailVerificationToken.objects.create(
            user=self.user, token="abc123", expires_at=expires
        )
        self.assertEqual(token.user, self.user)
        self.assertEqual(token.token, "abc123")
        self.assertEqual(token.expires_at, expires)

    def test_str_representation(self):
        """str() includes username and is_used status."""
        expires = timezone.now() + timedelta(hours=24)
        token = EmailVerificationToken.objects.create(
            user=self.user, token="strtest", expires_at=expires
        )
        result = str(token)
        self.assertIn("verifyuser", result)
        self.assertIn("False", result)

    def test_token_unique(self):
        """Two tokens cannot share the same token string."""
        expires = timezone.now() + timedelta(hours=24)
        EmailVerificationToken.objects.create(
            user=self.user, token="unique_token", expires_at=expires
        )
        other_user = User.objects.create_user(username='other', password='TestPass1!')
        with self.assertRaises(IntegrityError):
            EmailVerificationToken.objects.create(
                user=other_user, token="unique_token", expires_at=expires
            )

    def test_token_indexed(self):
        """token has a database index."""
        field = EmailVerificationToken._meta.get_field('token')
        self.assertTrue(field.db_index)

    def test_created_at_auto_set(self):
        """created_at is automatically set on creation."""
        expires = timezone.now() + timedelta(hours=24)
        token = EmailVerificationToken.objects.create(
            user=self.user, token="autocreate", expires_at=expires
        )
        self.assertIsNotNone(token.created_at)

    def test_is_used_default_false(self):
        """is_used defaults to False."""
        expires = timezone.now() + timedelta(hours=24)
        token = EmailVerificationToken.objects.create(
            user=self.user, token="usedtest", expires_at=expires
        )
        self.assertFalse(token.is_used)

    def test_is_expired_false_when_expires_at_in_future(self):
        """is_expired returns False when expires_at is in the future."""
        future = timezone.now() + timedelta(hours=1)
        token = EmailVerificationToken(
            user=self.user, token="notexpired", expires_at=future
        )
        self.assertFalse(token.is_expired)

    def test_is_expired_true_when_expires_at_in_past(self):
        """is_expired returns True when expires_at is in the past."""
        past = timezone.now() - timedelta(hours=1)
        token = EmailVerificationToken(
            user=self.user, token="isexpired", expires_at=past
        )
        self.assertTrue(token.is_expired)

    def test_is_valid_true_for_fresh_token(self):
        """is_valid returns True for a fresh (unused, non-expired) token."""
        future = timezone.now() + timedelta(hours=24)
        token = EmailVerificationToken(
            user=self.user, token="validfresh", expires_at=future
        )
        self.assertTrue(token.is_valid)

    def test_is_valid_false_for_used_token(self):
        """is_valid returns False for a used token."""
        future = timezone.now() + timedelta(hours=24)
        token = EmailVerificationToken(
            user=self.user, token="usedinvalid", expires_at=future, is_used=True
        )
        self.assertFalse(token.is_valid)

    def test_is_valid_false_for_expired_token(self):
        """is_valid returns False for an expired token."""
        past = timezone.now() - timedelta(hours=1)
        token = EmailVerificationToken(
            user=self.user, token="expiredinvalid", expires_at=past
        )
        self.assertFalse(token.is_valid)

    def test_is_valid_false_for_used_and_expired_token(self):
        """is_valid returns False for a token that is both used and expired."""
        past = timezone.now() - timedelta(hours=1)
        token = EmailVerificationToken(
            user=self.user, token="bothexpired", expires_at=past, is_used=True
        )
        self.assertFalse(token.is_valid)

    def test_ordering_by_created_at_desc(self):
        """Default ordering is by created_at descending (newest first)."""
        expires = timezone.now() + timedelta(hours=24)
        t1 = EmailVerificationToken.objects.create(
            user=self.user, token="order1", expires_at=expires
        )
        t2 = EmailVerificationToken.objects.create(
            user=self.user, token="order2", expires_at=expires
        )
        tokens = list(EmailVerificationToken.objects.filter(user=self.user))
        self.assertEqual(tokens[0], t2)
        self.assertEqual(tokens[1], t1)

    def test_generate_for_user_creates_token(self):
        """generate_for_user creates a new token for the user."""
        token = EmailVerificationToken.generate_for_user(self.user)
        self.assertIsNotNone(token)
        self.assertEqual(token.user, self.user)
        self.assertFalse(token.is_used)
        self.assertFalse(token.is_expired)

    def test_generate_for_user_token_is_64_chars_hex(self):
        """generate_for_user creates a 64-character hex token."""
        token = EmailVerificationToken.generate_for_user(self.user)
        self.assertEqual(len(token.token), 64)
        self.assertTrue(all(c in '0123456789abcdef' for c in token.token))

    def test_generate_for_user_expires_in_24_hours_by_default(self):
        """generate_for_user sets expires_at to ~24 hours from now."""
        before = timezone.now() + timedelta(hours=24)
        token = EmailVerificationToken.generate_for_user(self.user)
        after = timezone.now() + timedelta(hours=24)
        self.assertGreaterEqual(token.expires_at, before - timedelta(seconds=1))
        self.assertLessEqual(token.expires_at, after + timedelta(seconds=1))

    def test_generate_for_user_custom_expiry_hours(self):
        """generate_for_user respects custom expiry_hours parameter."""
        before = timezone.now() + timedelta(hours=48)
        token = EmailVerificationToken.generate_for_user(self.user, expiry_hours=48)
        after = timezone.now() + timedelta(hours=48)
        self.assertGreaterEqual(token.expires_at, before - timedelta(seconds=1))
        self.assertLessEqual(token.expires_at, after + timedelta(seconds=1))

    def test_generate_for_user_invalidates_previous_tokens(self):
        """generate_for_user marks all previous tokens for the user as used."""
        t1 = EmailVerificationToken.generate_for_user(self.user)
        t2 = EmailVerificationToken.generate_for_user(self.user)
        t1.refresh_from_db()
        self.assertTrue(t1.is_used)
        self.assertFalse(t2.is_used)

    def test_generate_for_user_invalidates_all_previous_not_just_latest(self):
        """generate_for_user invalidates ALL previous tokens, not just the latest."""
        t1 = EmailVerificationToken.generate_for_user(self.user)
        t2 = EmailVerificationToken.generate_for_user(self.user)
        t3 = EmailVerificationToken.generate_for_user(self.user)
        t1.refresh_from_db()
        t2.refresh_from_db()
        self.assertTrue(t1.is_used)
        self.assertTrue(t2.is_used)
        self.assertFalse(t3.is_used)

    def test_generate_for_user_does_not_affect_other_users_tokens(self):
        """generate_for_user only invalidates tokens for the target user."""
        other_user = User.objects.create_user(username='otherverify', password='TestPass1!')
        other_token = EmailVerificationToken.generate_for_user(other_user)
        EmailVerificationToken.generate_for_user(self.user)
        other_token.refresh_from_db()
        self.assertFalse(other_token.is_used)

    def test_generate_for_user_returns_persisted_token(self):
        """generate_for_user returns a token that is persisted in the database."""
        token = EmailVerificationToken.generate_for_user(self.user)
        self.assertTrue(
            EmailVerificationToken.objects.filter(
                token=token.token, user=self.user
            ).exists()
        )

    def test_user_fk_cascade_delete(self):
        """Deleting a user deletes their EmailVerificationTokens."""
        expires = timezone.now() + timedelta(hours=24)
        EmailVerificationToken.objects.create(
            user=self.user, token="cascade", expires_at=expires
        )
        self.user.delete()
        self.assertFalse(
            EmailVerificationToken.objects.filter(token="cascade").exists()
        )

    def test_user_related_name(self):
        """User can access tokens via 'email_verification_tokens' related name."""
        expires = timezone.now() + timedelta(hours=24)
        token = EmailVerificationToken.objects.create(
            user=self.user, token="related", expires_at=expires
        )
        self.assertIn(token, self.user.email_verification_tokens.all())

    def test_token_uniqueness_enforced_in_db(self):
        """Token uniqueness is enforced at the database level."""
        expires = timezone.now() + timedelta(hours=24)
        EmailVerificationToken.objects.create(
            user=self.user, token="dbunique", expires_at=expires
        )
        other_user = User.objects.create_user(username='other2', password='TestPass1!')
        with self.assertRaises(IntegrityError):
            EmailVerificationToken.objects.create(
                user=other_user, token="dbunique", expires_at=expires
            )
