"""
Seed test data for E2E tests and manual testing.

Creates:
  - Departments (IT, HR, Finance)
  - Folders (Programs under each department)
  - Admin users (admin, superadmin)
  - Sample attendance records

Usage:
    python manage.py seed_test_data
    python manage.py seed_test_data --records 50
    python manage.py seed_test_data --clear
"""
import random
import string

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from attendance.models import (
    Department, Folder, AttendanceRecord, AdminProfile,
)


class Command(BaseCommand):
    help = 'Seed test data for E2E tests and development.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--records',
            type=int,
            default=20,
            help='Number of attendance records to create (default: 20).',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing seed data before creating new data.',
        )

    def handle(self, *args, **options):
        num_records = options['records']

        if options['clear']:
            self.stdout.write('Clearing existing seed data...')
            # Delete in reverse FK order
            AttendanceRecord.objects.filter(
                fullname__startswith='Seed '
            ).delete()
            AdminProfile.objects.filter(
                user__username__in=['admin', 'superadmin', 'e2e_tester']
            ).delete()
            User.objects.filter(
                username__in=['admin', 'superadmin', 'e2e_tester']
            ).delete()
            Folder.objects.filter(
                name__startswith='Seed '
            ).delete()
            Department.objects.filter(
                name__startswith='Seed '
            ).delete()
            self.stdout.write(self.style.SUCCESS('Seed data cleared.'))

        self.stdout.write('Seeding test data...')

        # --- Departments ---
        dept_names = ['Seed IT', 'Seed HR', 'Seed Finance']
        departments = []
        for name in dept_names:
            dept, _ = Department.objects.get_or_create(name=name)
            departments.append(dept)
        self.stdout.write(f'  Created {len(departments)} departments.')

        # --- Folders ---
        folders = []
        folder_data = [
            ('Seed IT', 'Seed Program A'),
            ('Seed IT', 'Seed Program B'),
            ('Seed HR', 'Seed Induksi 2026'),
            ('Seed Finance', 'Seed Kewangan Q1'),
        ]
        for dept_name, folder_name in folder_data:
            dept = Department.objects.get(name=dept_name)
            folder, _ = Folder.objects.get_or_create(
                department=dept,
                name=folder_name,
                defaults={'cert_delay': 0},
            )
            folders.append(folder)
        self.stdout.write(f'  Created {len(folders)} folders.')

        # --- Admin Users ---
        # Regular admin
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={'is_staff': True},
        )
        if created:
            admin_user.set_password('admin123')
            admin_user.save()
        AdminProfile.objects.get_or_create(
            user=admin_user,
            defaults={
                'department': departments[0],
                'email_verified': True,
            },
        )

        # Superuser
        super_user, created = User.objects.get_or_create(
            username='superadmin',
            defaults={'is_staff': True, 'is_superuser': True},
        )
        if created:
            super_user.set_password('admin123')
            super_user.save()
        AdminProfile.objects.get_or_create(
            user=super_user,
            defaults={
                'department': departments[0],
                'email_verified': True,
            },
        )

        # E2E tester (non-super admin)
        e2e_user, created = User.objects.get_or_create(
            username='e2e_tester',
            defaults={'is_staff': True},
        )
        if created:
            e2e_user.set_password('TestPass1!')
            e2e_user.save()
        AdminProfile.objects.get_or_create(
            user=e2e_user,
            defaults={
                'department': departments[1],
                'email_verified': True,
            },
        )

        self.stdout.write('  Created admin users (admin/admin123, superadmin/admin123, e2e_tester/TestPass1!).')

        # --- Attendance Records ---
        organizations = [
            'Jabatan Hal Ehwal Korporat',
            'Jabatan Kewangan',
            'Jabatan Teknologi Maklumat',
            'Jabatan Sumber Manusia',
            'Jabatan Operasi',
        ]

        first_names = ['Ahmad', 'Siti', 'Mohd', 'Nur', 'Ali', 'Fatimah', 'Hassan', 'Zainab', 'Ismail', 'Aisyah']
        last_names = ['Ali', 'Ahmad', 'Hassan', 'Ismail', 'Yusof', 'Rahman', 'Osman', 'Kassim', 'Hussein', 'Zakaria']

        records_created = 0
        for i in range(num_records):
            folder = random.choice(folders)
            fullname = f'Seed {random.choice(first_names)} {random.choice(last_names)}'
            ic_number = ''.join(random.choices(string.digits, k=12))
            phone = '01' + ''.join(random.choices(string.digits, k=8))
            org = random.choice(organizations)

            # Spread records over the last 30 days
            days_ago = random.randint(0, 30)
            timestamp = timezone.now() - timedelta(days=days_ago)

            AttendanceRecord.objects.create(
                fullname=fullname,
                ic_number=ic_number,
                phone=phone,
                organization=org,
                folder=folder,
                timestamp=timestamp,
            )
            records_created += 1

        self.stdout.write(f'  Created {records_created} attendance records.')
        self.stdout.write(self.style.SUCCESS('Seeding complete!'))
        self.stdout.write('')
        self.stdout.write('Login credentials:')
        self.stdout.write('  admin / admin123       (regular admin, Seed IT dept)')
        self.stdout.write('  superadmin / admin123   (superuser)')
        self.stdout.write('  e2e_tester / TestPass1! (regular admin, Seed HR dept)')
