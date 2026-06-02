import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth.models import User

def update_admin():
    username = 'admin'
    password = 'Admin123!'
    user, created = User.objects.get_or_create(username=username)
    user.set_password(password)
    user.is_superuser = True
    user.is_staff = True
    user.save()
    print(f"Password for '{username}' updated successfully.")

if __name__ == '__main__':
    update_admin()
