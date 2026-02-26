# Governance views package

# Import all main views
from .main_views import (
    GovernanceBaseView,
    GovernanceDashboardView,
    AuditManagementView,
    SystemHealthView,
    SecurityCenterView,
    SecurityPoliciesView,
    SignalsManagementView,
    ReportsBuilderView,
    NotificationsCenterView,
    HealthMonitoringView
)

# Import payroll signal dashboard views (commented out due to circular import)
# from .payroll_signal_dashboard import (
#     payroll_signal_dashboard,
#     enable_governance,
#     disable_governance,
#     activate_kill_switch,
#     deactivate_kill_switch,
#     promote_signal,
#     api_status,
#     api_signal_metrics,
#     PayrollSignalControlView
# )

# Make all views available at package level
__all__ = [
    'GovernanceBaseView',
    'GovernanceDashboardView',
    'AuditManagementView',
    'SystemHealthView',
    'SecurityCenterView',
    'SecurityPoliciesView',
    'SignalsManagementView',
    'ReportsBuilderView',
    'NotificationsCenterView',
    'HealthMonitoringView'
]