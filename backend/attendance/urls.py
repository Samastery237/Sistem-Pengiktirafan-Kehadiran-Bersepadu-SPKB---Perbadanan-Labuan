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
    HealthCheckView,
    ImportCSVView,
    AuditLogView,
    MarkCertificateGeneratedView,
)

urlpatterns = [
    # Health Check (no auth required, must be first)
    path('health/', HealthCheckView.as_view(), name='health_check'),

    # Auth
    path('auth/login/', auth_views.LoginView.as_view(), name='auth_login'),
    path('auth/logout/', auth_views.LogoutView.as_view(), name='auth_logout'),
    path('auth/check/', auth_views.CheckAuthView.as_view(), name='auth_check'),
    path('auth/password/', auth_views.ChangePasswordView.as_view(), name='auth_change_password'),
    path('auth/verify-email/<str:token>/', auth_views.VerifyEmailView.as_view(), name='auth_verify_email'),
    path('auth/resend-verification/', auth_views.ResendVerificationView.as_view(), name='auth_resend_verification'),
    path('auth/reset-password/', auth_views.PasswordResetRequestView.as_view(), name='auth_reset_password'),
    path('auth/reset-password/confirm/', auth_views.PasswordResetConfirmView.as_view(), name='auth_reset_password_confirm'),
    path('users/', auth_views.UserListView.as_view(), name='users_list'),
    path('users/<int:user_id>/', auth_views.UserDetailView.as_view(), name='users_detail'),
    path('auth/unlock/', auth_views.UnlockAccountView.as_view(), name='auth_unlock'),

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
    path('import/', ImportCSVView.as_view(), name='import_csv'),

    # Certificate
    path('download-certificate/<uuid:record_id>/', DownloadCertificateView.as_view(), name='download_certificate'),
    path('mark-cert-generated/<uuid:record_id>/', MarkCertificateGeneratedView.as_view(), name='mark_cert_generated'),

    # Audit log (superuser only)
    path('audit/', AuditLogView.as_view(), name='audit_log'),
]
