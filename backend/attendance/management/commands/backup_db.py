import os
import shutil
from datetime import datetime
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Backup the database to a timestamped file.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            default='backups',
            help='Directory to store backups (default: backups/).',
        )

    def handle(self, *args, **options):
        db_settings = settings.DATABASES['default']
        engine = db_settings['ENGINE'].split('.')[-1]

        if engine == 'sqlite3':
            db_path = db_settings['NAME']
            if not os.path.exists(db_path):
                self.stdout.write(self.style.ERROR(f'Database file not found: {db_path}'))
                return
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_dir = options['output_dir']
            os.makedirs(output_dir, exist_ok=True)
            backup_path = os.path.join(output_dir, f'spkb_backup_{timestamp}.sqlite3')
            shutil.copy2(db_path, backup_path)
            self.stdout.write(self.style.SUCCESS(f'Backup created: {backup_path}'))
            self.stdout.write(f'  Size: {os.path.getsize(backup_path) / 1024:.1f} KB')

        elif engine == 'postgresql':
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_dir = options['output_dir']
            os.makedirs(output_dir, exist_ok=True)
            backup_path = os.path.join(output_dir, f'spkb_backup_{timestamp}.sql')
            db_name = db_settings['NAME']
            db_user = db_settings.get('USER', '')
            db_host = db_settings.get('HOST', 'localhost')
            cmd = f'pg_dump --dbname={db_name} --username={db_user} --host={db_host} --no-password --file={backup_path}'
            self.stdout.write(f'Running: pg_dump (database: {db_name})')
            exit_code = os.system(cmd)
            if exit_code == 0:
                self.stdout.write(self.style.SUCCESS(f'Backup created: {backup_path}'))
            else:
                self.stdout.write(self.style.ERROR('pg_dump failed. Is PostgreSQL installed and PGPASSWORD set?'))
        else:
            self.stdout.write(self.style.WARNING(f'Unsupported database engine: {engine}'))
