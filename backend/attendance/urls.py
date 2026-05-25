# pyrefly: ignore [missing-import]
from django.urls import path
from . import auth_views
# pyrefly: ignore [missing-import]
from .views import (
    SubmitAttendanceView,
    AttendanceStatusView,
    DownloadCertificateView,
    GetParticipantByICView,
    AttendanceListView,
    RecordDetailView,
    StatsView,
    DepartmentFolderListView,
    FolderDetailView,
    ExportCSVView,
    DepartmentDetailView,
)

urlpatterns = [
    # Auth
    path('auth/login/', auth_views.LoginView.as_view(), name='auth_login'),
    path('auth/logout/', auth_views.LogoutView.as_view(), name='auth_logout'),
    path('auth/check/', auth_views.CheckAuthView.as_view(), name='auth_check'),
    path('auth/change-password/', auth_views.ChangePasswordView.as_view(), name='auth_change_password'),

    # Attendance
    path('submit/', SubmitAttendanceView.as_view(), name='submit_attendance'),
    path('status/<uuid:record_id>/', AttendanceStatusView.as_view(), name='attendance_status'),
    path('records/', AttendanceListView.as_view(), name='record_list'),
    path('records/<uuid:record_id>/', RecordDetailView.as_view(), name='record_detail'),
    path('participant/<str:ic_number>/', GetParticipantByICView.as_view(), name='get_participant'),

    # Programs/Folders
    path('departments/<int:dept_id>/', DepartmentDetailView.as_view(), name='department_detail'),
    path('folders/', DepartmentFolderListView.as_view(), name='folder_list'),
    path('folders/<int:folder_id>/', FolderDetailView.as_view(), name='folder_detail'),

    # Stats & Export
    path('stats/', StatsView.as_view(), name='stats'),
    path('export/', ExportCSVView.as_view(), name='export_csv'),

    # Certificate
    path('download-certificate/<uuid:record_id>/', DownloadCertificateView.as_view(), name='download_certificate'),
]
