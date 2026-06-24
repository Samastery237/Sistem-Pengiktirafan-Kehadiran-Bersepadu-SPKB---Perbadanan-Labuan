import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.core.management import call_command
from django.contrib.auth.models import User

# Run migrations
print("Running migrations...")
call_command('migrate')

# Create superuser
print("Creating superuser...")
su_username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
su_email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
su_password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

if not User.objects.filter(username=su_username).exists():
    if su_password:
        User.objects.create_superuser(su_username, su_email, su_password)
        print(f"Superuser '{su_username}' created successfully using credentials from .env.")
    else:
        print(f"Warning: DJANGO_SUPERUSER_PASSWORD is not set. Skipping superuser '{su_username}' creation.")
else:
    print(f"Superuser '{su_username}' already exists.")

# Seed departments
from seed_departments import seed
seed()
