import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth.models import User

def create_default_admin():
    username = 'admin'
    password = 'Admin123!'
    if not User.objects.filter(username=username).exists():
        User.objects.create_superuser(username, '', password)
        print(f"Superuser '{username}' created successfully.")
    else:
        print(f"Superuser '{username}' already exists.")

if __name__ == '__main__':
    create_default_admin()
