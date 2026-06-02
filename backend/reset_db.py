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
print("Creating superuser 'admin'...")
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print("Superuser created successfully.")
else:
    print("Superuser already exists.")

# Seed departments
from seed_departments import seed
seed()
