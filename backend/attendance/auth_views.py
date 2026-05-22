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
            return Response({'status': 'success', 'csrfToken': csrf_token})
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
        return Response({'status': 'success', 'user': request.user.username})

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
