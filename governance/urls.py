from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = 'governance'

urlpatterns = [
    # Governance Dashboard
    path('dashboard/', views.GovernanceDashboardView.as_view(), name='dashboard'),
    
    # Audit Management
    path('audit/', views.AuditManagementView.as_view(), name='audit_management'),
    
    # System Health
    path('health/', views.SystemHealthView.as_view(), name='system_health'),
    
    # Security Center
    path('security/', views.SecurityCenterView.as_view(), name='security_center'),
    
    # Redirect old backup URL to new location
    path('backup/', RedirectView.as_view(url='/settings/backup/', permanent=True), name='backup_management'),
    
    # Security Policies
    path('policies/', views.SecurityPoliciesView.as_view(), name='security_policies'),
    
    # Signals Management
    path('signals/', views.SignalsManagementView.as_view(), name='signals_management'),
    
    # Permissions Matrix - Redirected to new unified system
    path('permissions/', RedirectView.as_view(url='/users/permissions/dashboard/', permanent=True), name='permissions_matrix_redirect'),
    
    # Reports Builder
    path('reports/', views.ReportsBuilderView.as_view(), name='reports_builder'),
    
    # Notifications Center
    path('notifications/', views.NotificationsCenterView.as_view(), name='notifications_center'),
    
    # Health Monitoring
    path('monitoring/', views.HealthMonitoringView.as_view(), name='health_monitoring'),
]