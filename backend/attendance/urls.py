# pyrefly: ignore [missing-import]
from django.urls import path
# pyrefly: ignore [missing-import]
from .views import (
    SubmitAttendanceView,
    AttendanceStatusView,
    DownloadCertificateView,
    GetParticipantByICView,
    RecordListView,
    RecordDetailView,
    StatsView,
    ProgramListView,
    ProgramDetailView,
    ExportCSVView,
)

urlpatterns = [
    # Attendance
    path('submit/', SubmitAttendanceView.as_view(), name='submit_attendance'),
    path('status/<uuid:record_id>/', AttendanceStatusView.as_view(), name='attendance_status'),
    path('records/', RecordListView.as_view(), name='record_list'),
    path('records/<uuid:record_id>/', RecordDetailView.as_view(), name='record_detail'),
    path('participant/<str:ic_number>/', GetParticipantByICView.as_view(), name='get_participant'),

    # Programs
    path('programs/', ProgramListView.as_view(), name='program_list'),
    path('programs/<int:program_id>/', ProgramDetailView.as_view(), name='program_detail'),

    # Stats & Export
    path('stats/', StatsView.as_view(), name='stats'),
    path('export/', ExportCSVView.as_view(), name='export_csv'),

    # Certificate
    path('download-certificate/<uuid:record_id>/', DownloadCertificateView.as_view(), name='download_certificate'),
]
