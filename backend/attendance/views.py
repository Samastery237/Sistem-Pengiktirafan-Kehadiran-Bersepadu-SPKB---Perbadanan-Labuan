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

from .models import AttendanceRecord, Program
from .serializers import AttendanceRecordSerializer


# ──────────────────────────────────────────────
# Attendance Submission
# ──────────────────────────────────────────────

class SubmitAttendanceView(views.APIView):
    """POST: Submit a new attendance record."""

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

class RecordListView(views.APIView):
    """
    GET:    List all attendance records (optional ?program=ID&search=TERM).
    DELETE: Clear all records (optional ?program=ID).
    """

    def get(self, request):
        program_id = request.query_params.get('program')
        search = request.query_params.get('search', '').strip().lower()

        qs = AttendanceRecord.objects.select_related('program').order_by('-timestamp')
        if program_id:
            qs = qs.filter(program_id=program_id)
        if search:
            qs = qs.filter(
                Q(fullname__icontains=search)
                | Q(ic_number__icontains=search)
                | Q(organization__icontains=search)
            )

        return Response({
            'status': 'success',
            'data': [_serialize_record(r) for r in qs],
        })

    def delete(self, request):
        qs = AttendanceRecord.objects.all()

        # Check if specific IDs are provided in JSON body
        ids = request.data.get('ids', [])
        if ids and isinstance(ids, list):
            qs = qs.filter(id__in=ids)
        
        program_id = request.query_params.get('program')
        if program_id:
            qs = qs.filter(program_id=program_id)
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

    def get(self, request, ic_number):
        clean_ic = re.sub(r'\D', '', ic_number)
        if not clean_ic:
            return Response(
                {'status': 'error', 'message': 'Invalid IC'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Try exact match first, then digits-only match
        records = AttendanceRecord.objects.filter(
            ic_number=ic_number
        ).select_related('program').order_by('-timestamp')

        if not records.exists():
            all_records = AttendanceRecord.objects.select_related('program').order_by('-timestamp')
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

    def get(self, request, record_id):
        record = get_object_or_404(AttendanceRecord, id=record_id)
        return Response(_serialize_record(record))


# ──────────────────────────────────────────────
# Statistics
# ──────────────────────────────────────────────

class StatsView(views.APIView):
    """GET: Return aggregate statistics (optional ?program=ID)."""

    def get(self, request):
        program_id = request.query_params.get('program')
        qs = AttendanceRecord.objects.all()
        if program_id:
            qs = qs.filter(program_id=program_id)

        today = timezone.now().date()
        return Response({
            'total': qs.count(),
            'today': qs.filter(timestamp__date=today).count(),
            'certs': qs.filter(certificate_generated=True).count(),
        })


# ──────────────────────────────────────────────
# Program Management
# ──────────────────────────────────────────────

class ProgramListView(views.APIView):
    """
    GET:  List all programs.
    POST: Create a new program (body: {"name": "..."}).
    """

    def get(self, request):
        programs = Program.objects.all().order_by('name')
        data = [
            {
                'id': p.id,
                'name': p.name,
                'cert_delay': p.cert_delay,
                'count': p.attendances.count(),
            }
            for p in programs
        ]
        return Response({'status': 'success', 'data': data})

    def post(self, request):
        name = (request.data.get('name') or '').strip()
        if not name:
            return Response(
                {'status': 'error', 'message': 'Program name is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        program, created = Program.objects.get_or_create(name=name)
        return Response(
            {'status': 'success', 'id': program.id, 'name': program.name,
             'cert_delay': program.cert_delay, 'created': created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ProgramDetailView(views.APIView):
    """
    GET:    Get program details (including cert_delay).
    PATCH:  Update program settings (cert_delay, name).
    DELETE: Delete a program and all its attendance records (CASCADE).
    """

    def get(self, request, program_id):
        program = get_object_or_404(Program, id=program_id)
        return Response({
            'status': 'success',
            'id': program.id,
            'name': program.name,
            'cert_delay': program.cert_delay,
        })

    def patch(self, request, program_id):
        program = get_object_or_404(Program, id=program_id)
        if 'cert_delay' in request.data:
            program.cert_delay = int(request.data['cert_delay'])
        if 'name' in request.data:
            program.name = request.data['name']
        program.save()
        return Response({
            'status': 'success',
            'id': program.id,
            'name': program.name,
            'cert_delay': program.cert_delay,
        })

    def delete(self, request, program_id):
        program = get_object_or_404(Program, id=program_id)
        program.delete()
        return Response({'status': 'success'})


# ──────────────────────────────────────────────
# CSV Export
# ──────────────────────────────────────────────

class ExportCSVView(views.APIView):
    """GET: Download attendance records as a UTF-8 CSV file."""

    def get(self, request):
        program_id = request.query_params.get('program')
        qs = AttendanceRecord.objects.select_related('program').order_by('-timestamp')
        if program_id:
            qs = qs.filter(program_id=program_id)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="kehadiran_{timezone.now().strftime("%Y-%m-%d")}.csv"'
        )
        response.write('\ufeff')  # BOM for Excel UTF-8 compat

        writer = csv.writer(response)
        writer.writerow(['Ref', 'Program', 'Nama Penuh', 'No. IC', 'No. Telefon',
                         'E-mel', 'Organisasi', 'Tarikh'])
        for r in qs:
            writer.writerow([
                r.ref, r.program.name, r.fullname, r.ic_number,
                r.phone, r.email, r.organization,
                r.timestamp.strftime('%d %B %Y, %I:%M %p'),
            ])
        return response


# ──────────────────────────────────────────────
# Certificate Download (PDF)
# ──────────────────────────────────────────────

class DownloadCertificateView(views.APIView):
    """GET: Generate and download a certificate PDF for a record."""

    def get(self, request, record_id):
        record = get_object_or_404(AttendanceRecord, id=record_id)

        if not record.certificate_generated:
            record.certificate_generated = True
            record.save(update_fields=['certificate_generated'])

        context = {
            'fullname': record.fullname.upper(),
            'program': record.program.name,
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
        'program_id': record.program_id,
        'program_name': record.program.name,
        'cert_delay': record.program.cert_delay,  # Use live program delay instead of snapshot
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
