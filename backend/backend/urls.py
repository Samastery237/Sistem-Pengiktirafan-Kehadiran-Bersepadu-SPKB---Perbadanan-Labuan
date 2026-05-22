"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.http import FileResponse
import os

FRONTEND_DIR = os.path.join(settings.BASE_DIR.parent, 'frontend')

def serve_frontend(request, filename='index.html'):
    filepath = os.path.join(FRONTEND_DIR, filename)
    if os.path.isfile(filepath):
        content_type = 'text/html'
        if filename.endswith('.css'): content_type = 'text/css'
        elif filename.endswith('.js'): content_type = 'application/javascript'
        return FileResponse(open(filepath, 'rb'), content_type=content_type)
    from django.http import Http404
    raise Http404

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/attendance/', include('attendance.urls')),

    # Serve frontend static files
    path('', serve_frontend, name='home'),
    path('index.html', serve_frontend, {'filename': 'index.html'}),
    path('form.html', serve_frontend, {'filename': 'form.html'}),
    path('admin.html', serve_frontend, {'filename': 'admin.html'}),
    path('success.html', serve_frontend, {'filename': 'success.html'}),
    path('css/<path:filename>', lambda r, filename: serve_frontend(r, f'css/{filename}')),
    path('js/<path:filename>', lambda r, filename: serve_frontend(r, f'js/{filename}')),
]
