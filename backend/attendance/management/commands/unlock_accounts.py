from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from attendance.models import UserAccountLock, FailedLoginAttempt


class Command(BaseCommand):
    help = 'Unlock accounts whose lockout period has expired and clean up old failed login attempts.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Force-unlock all accounts regardless of lockout time.',
        )
        parser.add_argument(
            '--username',
            type=str,
            help='Unlock a specific username.',
        )
        parser.add_argument(
            '--cleanup-hours',
            type=int,
            default=24,
            help='Delete failed login attempts older than this many hours (default: 24).',
        )

    def handle(self, *args, **options):
        now = timezone.now()

        if options['username']:
            try:
                lock = UserAccountLock.objects.get(user__username=options['username'])
                lock.locked_until = None
                lock.failure_count = 0
                lock.save(update_fields=['locked_until', 'failure_count'])
                self.stdout.write(self.style.SUCCESS(f"Account '{options['username']}' unlocked."))
            except UserAccountLock.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"No lock record for '{options['username']}'."))
            return

        if options['all']:
            count = UserAccountLock.objects.filter(locked_until__isnull=False).update(
                locked_until=None, failure_count=0
            )
            self.stdout.write(self.style.SUCCESS(f"Force-unlocked {count} accounts."))
            return

        # Auto-unlock expired lockouts
        expired = UserAccountLock.objects.filter(
            locked_until__isnull=False,
            locked_until__lt=now
        )
        count = expired.update(locked_until=None, failure_count=0)
        self.stdout.write(self.style.SUCCESS(f"Auto-unlocked {count} expired account locks."))

        # Clean up old failed login attempts
        cutoff = now - timedelta(hours=options['cleanup_hours'])
        deleted, _ = FailedLoginAttempt.objects.filter(attempted_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f"Cleaned up {deleted} old failed login attempts."))
