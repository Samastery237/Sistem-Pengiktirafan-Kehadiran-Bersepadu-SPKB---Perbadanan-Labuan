"""
Views for the SPKB Attendance API.
Provides endpoints for attendance submission, record management,
certificate generation, program management, and statistics.
"""
import re
import csv
from io import BytesIO

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import get_template
from django.utils import timezone

from rest_framework import status, views
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from .models import AttendanceRecord, Department, Folder
from .serializers import AttendanceRecordSerializer


# ──────────────────────────────────────────────
# Attendance Submission
# ──────────────────────────────────────────────

class SubmitAttendanceView(views.APIView):
    """POST: Submit a new attendance record."""
    authentication_classes = [] # Disable session auth to bypass CSRF validation for public form submission
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = AttendanceRecordSerializer(data=request.data)
        if serializer.is_valid():
            record = serializer.save()
            return Response({
                'status': 'success',
                'message': 'Attendance recorded successfully',
                'record_id': str(record.id),
                'data': _serialize_record(record),
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
    DELETE: Clear all records (optional ?folder=ID).
    """

    def get(self, request):
        folder_id = request.query_params.get('folder')
        search = request.query_params.get('search', '').strip()

        qs = AttendanceRecord.objects.select_related('folder__department').order_by('-timestamp')
        if folder_id:
            qs = qs.filter(folder_id=folder_id)
        if search:
            qs = qs.filter(
                Q(fullname__icontains=search) |
                Q(ic_number__icontains=search) |
                Q(email__icontains=search)
            )

        data = [_serialize_record(r) for r in qs]
        return Response({'status': 'success', 'data': data})

    def delete(self, request):
        """
        Danger! This will delete ALL attendance records for the system or specific folder.
        """
        ids = request.data.get('ids')
        if ids:
            qs = AttendanceRecord.objects.filter(id__in=ids)
            count, _ = qs.delete()
            return Response({'status': 'success', 'deleted': count})
            
        folder_id = request.query_params.get('folder')
        qs = AttendanceRecord.objects.all()
        if folder_id:
            qs = qs.filter(folder_id=folder_id)

        count, _ = qs.delete()
        return Response({'status': 'success', 'deleted': count})


class RecordDetailView(views.APIView):
    """DELETE: Delete a single attendance record."""

    def delete(self, request, record_id):
        record = get_object_or_404(AttendanceRecord, id=record_id)
        record.delete()
        return Response({'status': 'success'})

    def patch(self, request, record_id):
        record = get_object_or_404(AttendanceRecord, id=record_id)
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
    """GET: Find the most recent record for a given IC number."""
    permission_classes = [AllowAny]

    def get(self, request, ic_number):
        clean_ic = re.sub(r'\D', '', ic_number)
        if not clean_ic:
            return Response(
                {'status': 'error', 'message': 'Invalid IC'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Try exact match first, then digits-only match
        today = timezone.now().date()
        records = AttendanceRecord.objects.filter(
            ic_number=clean_ic,
            timestamp__gte=today
        ).select_related('folder__department').order_by('-timestamp')

        if not records.exists():
            all_records = AttendanceRecord.objects.select_related('folder__department').order_by('-timestamp')
            for r in all_records:
                if re.sub(r'\D', '', r.ic_number) == clean_ic:
                    records = AttendanceRecord.objects.filter(id=r.id)
                    break

        if records.exists():
            record = records.first()
            return Response({
                'status': 'success',
                'data': [_serialize_record(record)],
            })
        return Response(
            {'status': 'error', 'message': 'Not found'},
            status=status.HTTP_404_NOT_FOUND,
        )


# ──────────────────────────────────────────────
# Attendance Status
# ──────────────────────────────────────────────

class AttendanceStatusView(views.APIView):
    """GET: Check the status of a single attendance record."""
    permission_classes = [AllowAny]

    def get(self, request, record_id):
        record = get_object_or_404(AttendanceRecord, id=record_id)
        return Response(_serialize_record(record))


# ──────────────────────────────────────────────
# Statistics
# ──────────────────────────────────────────────

class StatsView(views.APIView):
    """GET: Return aggregate statistics (optional ?folder=ID)."""

    def get(self, request):
        folder_id = request.query_params.get('folder')
        qs = AttendanceRecord.objects.all()
        if folder_id:
            qs = qs.filter(folder_id=folder_id)

        today = timezone.now().date()
        return Response({
            'total': qs.count(),
            'today': qs.filter(timestamp__date=today).count(),
            'certs': qs.filter(certificate_generated=True).count(),
        })


# ──────────────────────────────────────────────
# Program Management
# ──────────────────────────────────────────────

class DepartmentFolderListView(views.APIView):
    """
    GET:  List all departments and their folders.
    POST: Create a new department or folder (body: {"department": "...", "folder": "..."}).
    """
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return super().get_permissions()

    def get(self, request):
        departments = Department.objects.prefetch_related('folders').all().order_by('name')
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
            
        department, _ = Department.objects.get_or_create(name=dept_name)
        folder, created = Folder.objects.get_or_create(department=department, name=folder_name)
        
        return Response(
            {'status': 'success', 'folder_id': folder.id, 'department': department.name, 'folder': folder.name,
             'cert_delay': folder.cert_delay, 'created': created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class FolderDetailView(views.APIView):
    """
    GET:    Get folder details (including cert_delay and cert_template).
    PATCH:  Update folder settings (cert_delay, cert_template).
    DELETE: Delete a folder and all its attendance records (CASCADE).
    """
    def get(self, request, folder_id):
        folder = get_object_or_404(Folder, id=folder_id)
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
        folder = get_object_or_404(Folder, id=folder_id)
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
        folder = get_object_or_404(Folder, id=folder_id)
        folder.delete()
        return Response({'status': 'success'})


# ──────────────────────────────────────────────
# CSV Export
# ──────────────────────────────────────────────

class ExportCSVView(views.APIView):
    """GET: Download attendance records as a UTF-8 CSV file."""

    def get(self, request):
        folder_id = request.query_params.get('folder')
        qs = AttendanceRecord.objects.select_related('folder__department').order_by('-timestamp')
        if folder_id:
            qs = qs.filter(folder_id=folder_id)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="kehadiran_{timezone.now().strftime("%Y-%m-%d")}.csv"'
        )
        response.write('\ufeff')  # BOM for Excel UTF-8 compat

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
    """GET: Generate and download a certificate PDF for a record."""
    permission_classes = [AllowAny]

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


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _serialize_record(record):
    """Convert an AttendanceRecord instance into a JSON-safe dict."""
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
        'timestamp': record.timestamp.strftime('%d %B %Y, %I:%M %p'),
        'raw_date': record.timestamp.isoformat(),
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
