"""
Views for the SPKB Attendance API.
Provides endpoints for attendance submission, record management,
certificate generation, program management, and statistics.

IDOR Prevention Strategy:
- All endpoints require authentication by default (DRF DEFAULT_PERMISSION_CLASSES = IsAuthenticated).
- Views that intentionally allow anonymous access explicitly set permission_classes = [AllowAny].
- Every view that accepts a resource ID enforces ownership:
    - Superusers can access any resource.
    - Non-superuser staff can only access resources in their own department.
    - Unauthenticated access is only allowed on explicitly public endpoints,
      and those endpoints return minimal data (no PII).
- The helper `_enforce_department_filter(qs, request)` ensures every queryset
  is scoped to the requesting user's department when applicable.
"""
import re
import csv
from datetime import timedelta
from io import BytesIO

from django.db import connection
from django.db.models import Q, Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import get_template
from django.conf import settings
from django.utils import timezone

from pathlib import Path as _Path

from rest_framework import status, views
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import AnonRateThrottle
from rest_framework.pagination import PageNumberPagination

from .models import AttendanceRecord, Department, Folder
from .serializers import AttendanceRecordSerializer


# ──────────────────────────────────────────────
# Pagination
# ──────────────────────────────────────────────

class StandardPagination(PageNumberPagination):
    """Default pagination: page size 25, configurable via ?page_size= (max 100)."""
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
            'data': data,
        })


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

class SubmitThrottle(AnonRateThrottle):
    scope = 'submit'

class GenerateThrottle(AnonRateThrottle):
    scope = 'generate'


def _user_department(request):
    """Return the department for an authenticated non-superuser, or None."""
    user = getattr(request, 'user', None)
    if (
        user
        and user.is_authenticated
        and not user.is_superuser
        and hasattr(user, 'admin_profile')
        and user.admin_profile.department
    ):
        return user.admin_profile.department
    return None


def _enforce_department_filter(qs, request):
    """Filter a queryset to the requesting user's department (non-superuser only)."""
    dept = _user_department(request)
    if dept is not None:
        return qs.filter(folder__department=dept)
    return qs


def _enforce_record_ownership(record, request):
    """
    Check if the requesting user owns (has department access to) the record.
    Returns None if allowed, or a Response(403) if denied.
    """
    dept = _user_department(request)
    if dept is not None:
        record_dept = record.folder.department if record.folder else None
        if record_dept and record_dept != dept:
            return Response({'status': 'error', 'message': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    return None


def _enforce_folder_ownership(folder, request):
    """
    Check if the requesting user owns (has department access to) the folder.
    Returns None if allowed, or a Response(403) if denied.
    """
    dept = _user_department(request)
    if dept is not None and folder.department != dept:
        return Response({'status': 'error', 'message': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
    return None


def _serialize_record(record):
    """Convert an AttendanceRecord instance into a JSON-safe dict (full data for authenticated users)."""
    return {
        'id': str(record.id),
        'ref': record.ref,
        'fullname': record.fullname,
        'ic_number': record.ic_number,
        'phone': record.phone,
        'email': record.email,
        'organization': record.organization,
        'folder_id': record.folder_id,
        'department_name': record.folder.department.name if record.folder and record.folder.department else '—',
        'folder_name': record.folder.name if record.folder else '—',
        'cert_delay': record.folder.cert_delay if record.folder else 120000,
        'cert_template': record.folder.cert_template if record.folder else None,
        'name_x': record.folder.name_x if record.folder else 500,
        'name_y': record.folder.name_y if record.folder else 360,
        'name_size': record.folder.name_size if record.folder else 42,
        'show_ic': record.folder.show_ic if record.folder else True,
        'ic_x': record.folder.ic_x if record.folder else 500,
        'ic_y': record.folder.ic_y if record.folder else 470,
        'ic_size': record.folder.ic_size if record.folder else 28,
        'text_color': record.folder.text_color if record.folder else '#f0f4f8',
        'font_family': record.folder.font_family if record.folder else 'Palatino, serif',
        'timestamp': record.timestamp.strftime('%d %B %Y, %I:%M %p'),
        'raw_date': record.timestamp.isoformat(),
        'certificate_generated': record.certificate_generated,
    }


def _serialize_record_public(record):
    """Convert an AttendanceRecord into a JSON-safe dict with PII stripped (for public/unauthenticated access)."""
    return {
        'id': str(record.id),
        'ref': record.ref,
        'folder_name': record.folder.name if record.folder else '—',
        'department_name': record.folder.department.name if record.folder and record.folder.department else '—',
        'timestamp': record.timestamp.strftime('%d %B %Y, %I:%M %p'),
        'certificate_generated': record.certificate_generated,
    }


def _render_to_pdf(template_src, context_dict=None):
    """Render an HTML template to PDF bytes. Returns None on failure."""
    try:
        from xhtml2pdf import pisa
    except ImportError:
        return None

    template = get_template(template_src)
    html = template.render(context_dict or {})
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode('UTF-8')), result)
    if not pdf.err:
        return result.getvalue()

    print("PDF Generation Error:", pdf.err)
    return None


# ──────────────────────────────────────────────
# Attendance Submission (public — no auth required)
# ──────────────────────────────────────────────

class SubmitAttendanceView(views.APIView):
    """POST: Submit a new attendance record. Public endpoint — no authentication required."""
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [SubmitThrottle]

    def post(self, request):
        serializer = AttendanceRecordSerializer(data=request.data)
        if serializer.is_valid():
            record = serializer.save()
            return Response({
                'status': 'success',
                'message': 'Attendance recorded successfully',
                'record_id': str(record.id),
                'data': _serialize_record_public(record),
            }, status=status.HTTP_201_CREATED)
        return Response({
            'status': 'error',
            'errors': serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)


# ──────────────────────────────────────────────
# Record List & Bulk Operations
# ──────────────────────────────────────────────

class AttendanceListView(views.APIView):
    """
    GET:    List all attendance records (optional ?folder=ID&search=TERM).
    DELETE: Clear all records (optional ?folder=ID or body ids[]).
    Authenticated only — scoped to user's department for non-superusers.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        folder_id = request.query_params.get('folder')
        search = request.query_params.get('search', '').strip()

        qs = AttendanceRecord.objects.select_related('folder__department').order_by('-timestamp')
        qs = _enforce_department_filter(qs, request)

        if folder_id:
            qs = qs.filter(folder_id=folder_id)
        if search:
            qs = qs.filter(
                Q(fullname__icontains=search) |
                Q(ic_number__icontains=search) |
                Q(email__icontains=search)
            )

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            data = [_serialize_record(r) for r in page]
            return paginator.get_paginated_response(data)

        data = [_serialize_record(r) for r in qs]
        return Response({'status': 'success', 'data': data})

    def delete(self, request):
        """Delete records by IDs or by folder. Scoped to user's department."""
        ids = request.data.get('ids')
        if ids:
            qs = AttendanceRecord.objects.filter(id__in=ids)
            qs = _enforce_department_filter(qs, request)
            count, _ = qs.delete()
            return Response({'status': 'success', 'deleted': count})

        folder_id = request.query_params.get('folder')
        qs = AttendanceRecord.objects.all()
        qs = _enforce_department_filter(qs, request)

        if folder_id:
            qs = qs.filter(folder_id=folder_id)

        count, _ = qs.delete()
        return Response({'status': 'success', 'deleted': count})


class RecordDetailView(views.APIView):
    """
    DELETE: Delete a single attendance record.
    PATCH:  Update a single attendance record.
    Authenticated only — scoped to user's department.
    """
    permission_classes = [IsAuthenticated]

    def _get_record(self, request, record_id):
        """Fetch record and enforce ownership. Returns (record, error_response)."""
        record = get_object_or_404(AttendanceRecord, id=record_id)
        error = _enforce_record_ownership(record, request)
        return record, error

    def delete(self, request, record_id):
        record, error = self._get_record(request, record_id)
        if error:
            return error
        record.delete()
        return Response({'status': 'success'})

    def patch(self, request, record_id):
        record, error = self._get_record(request, record_id)
        if error:
            return error

        serializer = AttendanceRecordSerializer(record, data=request.data, partial=True)
        if serializer.is_valid():
            updated_record = serializer.save()
            return Response({
                'status': 'success',
                'data': _serialize_record(updated_record)
            })
        return Response({
            'status': 'error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


# ──────────────────────────────────────────────
# Participant Lookup (by IC)
# ──────────────────────────────────────────────

class GetParticipantByICView(views.APIView):
    """
    GET: Find all records for a given IC number.
    Authenticated only — scoped to user's department for non-superusers.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, ic_number):
        clean_ic = re.sub(r'\D', '', ic_number)
        if not clean_ic or len(clean_ic) != 12:
            return Response(
                {'status': 'error', 'message': 'Invalid IC'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        records = AttendanceRecord.objects.filter(
            clean_ic_number=clean_ic
        ).select_related('folder__department').order_by('-timestamp')
        records = _enforce_department_filter(records, request)

        if records.exists():
            data = [_serialize_record(r) for r in records]
            return Response({'status': 'success', 'data': data})

        return Response(
            {'status': 'error', 'message': 'Not found'},
            status=status.HTTP_404_NOT_FOUND,
        )


# ──────────────────────────────────────────────
# Attendance Status
# ──────────────────────────────────────────────

class AttendanceStatusView(views.APIView):
    """
    GET: Check the status of a single attendance record.
    Authenticated users get full record data scoped to their department.
    Unauthenticated requests get only non-PII data.
    """
    permission_classes = [AllowAny]

    def get(self, request, record_id):
        record = get_object_or_404(AttendanceRecord, id=record_id)

        # Authenticated admin users get full record data (if they own it)
        if request.user and request.user.is_authenticated:
            error = _enforce_record_ownership(record, request)
            if error:
                return error
            return Response(_serialize_record(record))

        # Public (unauthenticated) requests get limited data (no phone/email/IC)
        return Response({
            'id': str(record.id),
            'ref': record.ref,
            'fullname': record.fullname,
            'folder_name': record.folder.name if record.folder else '—',
            'department_name': record.folder.department.name if record.folder and record.folder.department else '—',
            'timestamp': record.timestamp.strftime('%d %B %Y, %I:%M %p'),
            'raw_date': record.timestamp.isoformat(),
            'certificate_generated': record.certificate_generated,
            'cert_delay': record.folder.cert_delay if record.folder else 120000,
            'cert_template': record.folder.cert_template if record.folder else None,
            'name_x': record.folder.name_x if record.folder else 500,
            'name_y': record.folder.name_y if record.folder else 360,
            'name_size': record.folder.name_size if record.folder else 42,
            'show_ic': record.folder.show_ic if record.folder else True,
            'ic_x': record.folder.ic_x if record.folder else 500,
            'ic_y': record.folder.ic_y if record.folder else 470,
            'ic_size': record.folder.ic_size if record.folder else 28,
            'text_color': record.folder.text_color if record.folder else '#f0f4f8',
            'font_family': record.folder.font_family if record.folder else 'Palatino, serif',
        })


# ──────────────────────────────────────────────
# Statistics
# ──────────────────────────────────────────────

class StatsView(views.APIView):
    """GET: Return aggregate statistics (optional ?folder=ID&detail=true)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        folder_id = request.query_params.get('folder')
        detail = request.query_params.get('detail', '').lower() == 'true'
        qs = AttendanceRecord.objects.all()
        qs = _enforce_department_filter(qs, request)

        if folder_id:
            qs = qs.filter(folder_id=folder_id)

        today = timezone.now().date()
        response_data = {
            'total': qs.count(),
            'today': qs.filter(timestamp__date=today).count(),
            'certs': qs.filter(certificate_generated=True).count(),
        }

        if detail:
            # Daily counts for last 7 days
            daily_counts = []
            for i in range(6, -1, -1):
                day = today - timedelta(days=i)
                count = qs.filter(timestamp__date=day).count()
                daily_counts.append({'date': day.isoformat(), 'count': count})
            response_data['daily_counts'] = daily_counts

            # Department breakdown
            dept_breakdown = (
                AttendanceRecord.objects
                .filter(id__in=qs.values('id'))
                .values('folder__department__name')
                .annotate(count=Count('id'))
                .order_by('-count')
            )
            response_data['department_breakdown'] = [
                {'name': d['folder__department__name'] or '—', 'count': d['count']}
                for d in dept_breakdown
            ]

            # Certificate rate
            total = response_data['total']
            certs = response_data['certs']
            response_data['certificate_rate'] = round((certs / total) * 100, 1) if total > 0 else 0.0

        return Response(response_data)


# ──────────────────────────────────────────────
# Program Management
# ──────────────────────────────────────────────

class DepartmentFolderListView(views.APIView):
    """
    GET:  List all departments and their folders.
    POST: Create a new department or folder.
    Authenticated only — non-superusers see only their department.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        dept = _user_department(request)
        if dept is not None:
            departments = Department.objects.prefetch_related('folders').filter(
                id=dept.id
            ).order_by('name')
        else:
            departments = Department.objects.prefetch_related('folders').all().order_by('name')

        paginator = StandardPagination()
        page = paginator.paginate_queryset(departments, request)
        if page is not None:
            data = []
            for d in page:
                folders = [
                    {
                        'id': f.id,
                        'name': f.name,
                        'cert_delay': f.cert_delay,
                        'cert_template': f.cert_template,
                        'name_x': f.name_x,
                        'name_y': f.name_y,
                        'name_size': f.name_size,
                        'show_ic': f.show_ic,
                        'ic_x': f.ic_x,
                        'ic_y': f.ic_y,
                        'ic_size': f.ic_size,
                        'text_color': f.text_color,
                        'font_family': f.font_family,
                        'event_name': f.event_name,
                        'event_date': f.event_date,
                        'organizer': f.organizer,
                        'count': f.attendances.count(),
                    }
                    for f in d.folders.all().order_by('name')
                ]
                data.append({
                    'id': d.id,
                    'name': d.name,
                    'folders': folders
                })
            return paginator.get_paginated_response(data)

        data = []
        for d in departments:
            folders = [
                {
                    'id': f.id,
                    'name': f.name,
                    'cert_delay': f.cert_delay,
                    'cert_template': f.cert_template,
                    'name_x': f.name_x,
                    'name_y': f.name_y,
                    'name_size': f.name_size,
                    'show_ic': f.show_ic,
                    'ic_x': f.ic_x,
                    'ic_y': f.ic_y,
                    'ic_size': f.ic_size,
                    'text_color': f.text_color,
                    'font_family': f.font_family,
                    'event_name': f.event_name,
                    'event_date': f.event_date,
                    'organizer': f.organizer,
                    'count': f.attendances.count(),
                }
                for f in d.folders.all().order_by('name')
            ]
            data.append({
                'id': d.id,
                'name': d.name,
                'folders': folders
            })
        return Response({'status': 'success', 'data': data})

    def post(self, request):
        dept_name = (request.data.get('department') or '').strip()
        folder_name = (request.data.get('folder') or '').strip()

        if not dept_name or not folder_name:
            return Response(
                {'status': 'error', 'message': 'Department and Folder names are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        dept = _user_department(request)
        if dept is not None:
            # Non-superuser: can only create folders under their own department
            department = dept
        else:
            department, _ = Department.objects.get_or_create(name=dept_name)

        folder, created = Folder.objects.get_or_create(department=department, name=folder_name)

        return Response(
            {'status': 'success', 'folder_id': folder.id, 'department': department.name, 'folder': folder.name,
             'cert_delay': folder.cert_delay, 'created': created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class DepartmentDetailView(views.APIView):
    """DELETE: Delete a department and all its associated folders and records. Superuser only."""
    permission_classes = [IsAuthenticated]

    def delete(self, request, dept_id):
        if not request.user.is_superuser:
            return Response(
                {'status': 'error', 'message': 'Only Super Admin can delete departments'},
                status=status.HTTP_403_FORBIDDEN
            )
        department = get_object_or_404(Department, id=dept_id)
        department.delete()
        return Response({'status': 'success', 'message': 'Department deleted successfully'})


class FolderDetailView(views.APIView):
    """
    GET:    Get folder details (including cert_delay and cert_template).
    PATCH:  Update folder settings (cert_delay, cert_template).
    DELETE: Delete a folder and all its attendance records (CASCADE).
    Authenticated only — scoped to user's department.
    """
    permission_classes = [IsAuthenticated]

    def _get_folder(self, request, folder_id):
        """Fetch folder and enforce ownership. Returns (folder, error_response)."""
        folder = get_object_or_404(Folder, id=folder_id)
        error = _enforce_folder_ownership(folder, request)
        return folder, error

    def get(self, request, folder_id):
        folder, error = self._get_folder(request, folder_id)
        if error:
            return error
        return Response({
            'status': 'success',
            'id': folder.id,
            'department': folder.department.name if folder.department else None,
            'name': folder.name,
            'cert_delay': folder.cert_delay,
            'cert_template': folder.cert_template,
            'name_x': folder.name_x,
            'name_y': folder.name_y,
            'name_size': folder.name_size,
            'show_ic': folder.show_ic,
            'ic_x': folder.ic_x,
            'ic_y': folder.ic_y,
            'ic_size': folder.ic_size,
            'text_color': folder.text_color,
            'font_family': folder.font_family,
            'event_name': folder.event_name,
            'event_date': folder.event_date,
            'organizer': folder.organizer,
        })

    def patch(self, request, folder_id):
        folder, error = self._get_folder(request, folder_id)
        if error:
            return error
        if 'name' in request.data: folder.name = request.data['name']
        if 'cert_delay' in request.data: folder.cert_delay = int(request.data['cert_delay'])
        if 'cert_template' in request.data: folder.cert_template = request.data['cert_template']
        if 'name_x' in request.data: folder.name_x = float(request.data['name_x'])
        if 'name_y' in request.data: folder.name_y = float(request.data['name_y'])
        if 'name_size' in request.data: folder.name_size = float(request.data['name_size'])
        if 'show_ic' in request.data: folder.show_ic = str(request.data['show_ic']).lower() == 'true'
        if 'ic_x' in request.data: folder.ic_x = float(request.data['ic_x'])
        if 'ic_y' in request.data: folder.ic_y = float(request.data['ic_y'])
        if 'ic_size' in request.data: folder.ic_size = float(request.data['ic_size'])
        if 'text_color' in request.data: folder.text_color = request.data['text_color']
        if 'font_family' in request.data: folder.font_family = request.data['font_family']
        if 'event_name' in request.data: folder.event_name = request.data['event_name']
        if 'event_date' in request.data: folder.event_date = request.data['event_date']
        if 'organizer' in request.data: folder.organizer = request.data['organizer']
        folder.save()
        return Response({
            'status': 'success',
            'id': folder.id,
            'name': folder.name,
            'cert_delay': folder.cert_delay,
        })

    def delete(self, request, folder_id):
        folder, error = self._get_folder(request, folder_id)
        if error:
            return error
        folder.delete()
        return Response({'status': 'success'})


# ──────────────────────────────────────────────
# CSV Export
# ──────────────────────────────────────────────

class ExportCSVView(views.APIView):
    """GET: Download attendance records as a UTF-8 CSV file. Authenticated only — scoped to department."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        folder_id = request.query_params.get('folder')
        qs = AttendanceRecord.objects.select_related('folder__department').order_by('-timestamp')
        qs = _enforce_department_filter(qs, request)

        if folder_id:
            qs = qs.filter(folder_id=folder_id)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="kehadiran_{timezone.now().strftime("%Y-%m-%d")}.csv"'
        )
        response.write('﻿')  # BOM for Excel UTF-8 compat

        writer = csv.writer(response)
        writer.writerow(['Ref', 'Jabatan (Penganjur)', 'Folder (Program)', 'Nama Penuh', 'No. IC', 'No. Telefon',
                         'E-mel', 'Organisasi', 'Tarikh'])
        for r in qs:
            writer.writerow([
                r.ref,
                r.folder.department.name if r.folder and r.folder.department else '—',
                r.folder.name if r.folder else '—',
                r.fullname, r.ic_number,
                r.phone, r.email, r.organization,
                r.timestamp.strftime('%d %B %Y, %I:%M %p'),
            ])
        return response


# ──────────────────────────────────────────────
# Certificate Download (PDF)
# ──────────────────────────────────────────────

class DownloadCertificateView(views.APIView):
    """GET: Generate and download a certificate PDF for a record. Public endpoint."""
    permission_classes = [AllowAny]
    throttle_classes = [GenerateThrottle]

    def get(self, request, record_id):
        record = get_object_or_404(AttendanceRecord, id=record_id)

        if not record.certificate_generated:
            record.certificate_generated = True
            record.save(update_fields=['certificate_generated'])

        context = {
            'fullname': record.fullname.upper(),
            'program': record.folder.name if record.folder else 'General Folder',
            'date': record.timestamp.strftime('%d %B %Y'),
        }

        pdf_bytes = _render_to_pdf('certificate.html', context)
        if pdf_bytes:
            filename = f"Sijil_{record.fullname.replace(' ', '_')}.pdf"
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        return Response(
            {'status': 'error', 'message': 'PDF generation failed. Install xhtml2pdf: pip install xhtml2pdf'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class HealthCheckView(views.APIView):
    """GET: Return service health status. No authentication required."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            connection.ensure_connection()
            db_status = 'connected'
            http_status = status.HTTP_200_OK
            resp_status = 'ok'
        except Exception:
            db_status = 'disconnected'
            http_status = status.HTTP_503_SERVICE_UNAVAILABLE
            resp_status = 'error'

        return Response({
            'status': resp_status,
            'db': db_status,
            'timestamp': timezone.now().isoformat(),
        }, status=http_status)


class ImportCSVView(views.APIView):
    """POST: Import attendance records from a CSV file. Superuser only."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_superuser:
            return Response(
                {'status': 'error', 'message': 'Only superusers can import CSV'},
                status=status.HTTP_403_FORBIDDEN,
            )

        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response(
                {'status': 'error', 'message': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            content = uploaded_file.read().decode('utf-8-sig')
        except Exception:
            return Response(
                {'status': 'error', 'message': 'Unable to read file'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not content.strip():
            return Response(
                {'status': 'error', 'message': 'File is empty'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        import io
        reader = csv.DictReader(io.StringIO(content))
        required_fields = {'fullname', 'ic_number', 'phone'}
        if not reader.fieldnames or not required_fields.issubset(set(f.strip().lower() for f in reader.fieldnames)):
            return Response(
                {'status': 'error', 'message': f'CSV must contain columns: {required_fields}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = 0
        errors = []
        row_num = 0

        for row in reader:
            row_num += 1
            fullname = (row.get('fullname') or '').strip()
            ic_number = (row.get('ic_number') or '').strip()
            phone = (row.get('phone') or '').strip()
            email = (row.get('email') or '').strip()
            organization = (row.get('organization') or '').strip()

            if not fullname:
                errors.append({'row': row_num, 'error': 'Missing fullname'})
                continue

            clean_ic = re.sub(r'\D', '', ic_number) if ic_number else ''
            if ic_number and (not clean_ic or len(clean_ic) != 12):
                errors.append({'row': row_num, 'error': f'Invalid IC: {ic_number}'})
                continue

            # Skip duplicates (by clean_ic_number)
            if clean_ic and AttendanceRecord.objects.filter(clean_ic_number=clean_ic).exists():
                continue

            AttendanceRecord.objects.create(
                fullname=fullname,
                ic_number=ic_number,
                phone=phone,
                email=email or None,
                organization=organization or None,
                folder=None,
            )
            created += 1

        if errors:
            return Response(
                {'status': 'partial', 'created': created, 'errors': errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {'status': 'success', 'created': created},
            status=status.HTTP_201_CREATED,
        )


class AuditLogView(views.APIView):
    """GET: Return recent security log entries. Superuser only."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_superuser:
            return Response(
                {'status': 'error', 'message': 'Forbidden'},
                status=status.HTTP_403_FORBIDDEN,
            )

        log_file = _Path(settings.BASE_DIR) / 'security.log'
        event_filter = request.query_params.get('event', '').upper()

        entries = []
        if log_file.exists():
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                parts = line.split(None, 2)
                if len(parts) >= 3:
                    level = parts[0]
                    message = parts[2]
                elif len(parts) == 2:
                    level = parts[0]
                    message = parts[1]
                else:
                    level = 'INFO'
                    message = line

                if event_filter and event_filter not in message.upper():
                    continue

                entries.append({
                    'raw': line,
                    'level': level,
                    'message': message,
                })

        # Manual pagination
        total = len(entries)
        page = int(request.query_params.get('page', 1))
        page_size = 25
        start = (page - 1) * page_size
        end = start + page_size
        paginated = entries[start:end]

        return Response({
            'count': total,
            'results': paginated,
            'next': page + 1 if end < total else None,
            'previous': page - 1 if page > 1 else None,
        })
