from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.middleware.csrf import get_token
from rest_framework import status, views
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated

from rest_framework.permissions import AllowAny, IsAuthenticated

from rest_framework.throttling import AnonRateThrottle

class LoginThrottle(AnonRateThrottle):
    scope = 'login'

class LoginView(views.APIView):
    """POST: Authenticate user and create session."""
    authentication_classes = [] # Disable session auth (and thus CSRF validation) for the login endpoint itself
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            # We return the CSRF token in the response data as a convenience
            # so the frontend can easily grab it, though it's also set in a cookie.
            csrf_token = get_token(request)
            
            # Get admin role
            is_super = user.is_superuser
            department_id = None
            if hasattr(user, 'admin_profile') and user.admin_profile.department:
                department_id = user.admin_profile.department.id

            return Response({
                'status': 'success', 
                'csrfToken': csrf_token,
                'is_super': is_super,
                'department_id': department_id
            })
        else:
            return Response(
                {'status': 'error', 'message': 'Kata laluan atau ID pengguna salah.'},
                status=status.HTTP_401_UNAUTHORIZED
            )

class LogoutView(views.APIView):
    """POST: End user session."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({'status': 'success'})

class CheckAuthView(views.APIView):
    """GET: Verify current session is active."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        is_super = user.is_superuser
        department_id = None
        if hasattr(user, 'admin_profile') and user.admin_profile.department:
            department_id = user.admin_profile.department.id
            
        return Response({
            'status': 'success', 
            'user': user.username,
            'is_super': is_super,
            'department_id': department_id
        })

class ChangePasswordView(views.APIView):
    """POST: Change the current user's password."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        new_password = request.data.get('new_password')
        if not new_password or len(new_password) < 6:
            return Response(
                {'status': 'error', 'message': 'Kata laluan terlalu pendek.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = request.user
        user.set_password(new_password)
        user.save()
        # Keep user logged in after password change
        login(request, user)
        return Response({'status': 'success'})

class UserListView(views.APIView):
    """
    GET: List all users (admin accounts) and their assigned departments.
    POST: Create a new admin account assigned to a department.
    Super Admins only.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_superuser:
            return Response({'status': 'error', 'message': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        
        users = User.objects.all().select_related('admin_profile__department')
        data = []
        for u in users:
            dept_name = None
            dept_id = None
            if hasattr(u, 'admin_profile') and u.admin_profile.department:
                dept_name = u.admin_profile.department.name
                dept_id = u.admin_profile.department.id
            data.append({
                'id': u.id,
                'username': u.username,
                'is_super': u.is_superuser,
                'department_id': dept_id,
                'department_name': dept_name
            })
        return Response({'status': 'success', 'data': data})

    def post(self, request):
        if not request.user.is_superuser:
            return Response({'status': 'error', 'message': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
            
        username = request.data.get('username')
        password = request.data.get('password')
        department_id = request.data.get('department_id')
        is_super = str(request.data.get('is_super')).lower() == 'true'
        
        if not username or not password:
            return Response({'status': 'error', 'message': 'Username and password are required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        if User.objects.filter(username=username).exists():
            return Response({'status': 'error', 'message': 'Username already exists.'}, status=status.HTTP_400_BAD_REQUEST)
            
        user = User.objects.create_user(username=username, password=password)
        user.is_staff = True
        user.is_superuser = is_super
        user.save()
        
        from .models import Department, AdminProfile
        if department_id and not is_super:
            try:
                dept = Department.objects.get(id=department_id)
                AdminProfile.objects.create(user=user, department=dept)
            except Department.DoesNotExist:
                pass
                
        return Response({'status': 'success', 'message': 'User created'})

class UserDetailView(views.APIView):
    """DELETE: Delete an admin user. Super Admins only."""
    permission_classes = [IsAuthenticated]

    def delete(self, request, user_id):
        if not request.user.is_superuser:
            return Response({'status': 'error', 'message': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
            
        try:
            user_to_delete = User.objects.get(id=user_id)
            if user_to_delete.id == request.user.id:
                return Response({'status': 'error', 'message': 'Cannot delete yourself.'}, status=status.HTTP_400_BAD_REQUEST)
            user_to_delete.delete()
            return Response({'status': 'success'})
        except User.DoesNotExist:
            return Response({'status': 'error', 'message': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
