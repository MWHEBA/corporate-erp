from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class GovernanceBaseView(LoginRequiredMixin, TemplateView):
    """Base view for governance pages"""
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'active_menu': 'governance',
            'breadcrumb_items': [
                {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': _('الحوكمة والإدارة'), 'active': True}
            ]
        })
        return context

class GovernanceDashboardView(GovernanceBaseView):
    """Governance and Monitoring Unified Dashboard"""
    template_name = 'governance/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Update breadcrumb
        context['breadcrumb_items'][-1]['title'] = _('لوحة الحوكمة والمراقبة')
        
        context.update({
            'title': _('لوحة الحوكمة والمراقبة الموحدة'),
            'subtitle': _('مراقبة شاملة لسلامة النظام والعمليات الحرجة'),
            'icon': 'fas fa-shield-alt',
            'header_buttons': [
                {
                    'url': reverse('governance:system_health'),
                    'icon': 'fa-heartbeat',
                    'text': _('فحص صحة النظام'),
                    'class': 'btn-success'
                },
                {
                    'url': reverse('governance:security_center'),
                    'icon': 'fa-lock',
                    'text': _('مركز الأمان'),
                    'class': 'btn-warning'
                }
            ]
        })
        
        # Get governance statistics
        context.update(self._get_governance_stats())
        
        return context
    
    def _get_governance_stats(self):
        """Get governance and monitoring statistics"""
        try:
            from ..models import AuditTrail, QuarantineRecord, Alert
            from core.models import SystemLog
            
            # Time ranges
            today = timezone.now().date()
            week_ago = today - timedelta(days=7)
            
            stats = {
                # Audit stats
                'total_audit_records': AuditTrail.objects.count(),
                'recent_audit_records': AuditTrail.objects.filter(
                    created_at__date__gte=week_ago
                ).count(),
                
                # Quarantine stats
                'quarantined_items': QuarantineRecord.objects.filter(
                    is_resolved=False
                ).count(),
                
                # System logs
                'system_errors': SystemLog.objects.filter(
                    level='ERROR',
                    created_at__date__gte=week_ago
                ).count(),
                
                # Alerts
                'active_alerts': Alert.objects.filter(
                    is_active=True
                ).count(),
                
                # Health status
                'system_health_score': self._calculate_health_score(),
            }
            
        except Exception as e:
            logger.error(f"Error getting governance stats: {e}")
            stats = {
                'total_audit_records': 0,
                'recent_audit_records': 0,
                'quarantined_items': 0,
                'system_errors': 0,
                'active_alerts': 0,
                'system_health_score': 85,
            }
        
        return stats
    
    def _calculate_health_score(self):
        """Calculate system health score"""
        # Simple health calculation - can be enhanced
        base_score = 100
        
        try:
            from ..models import QuarantineRecord, Alert
            from core.models import SystemLog
            
            # Deduct points for issues
            quarantined = QuarantineRecord.objects.filter(is_resolved=False).count()
            active_alerts = Alert.objects.filter(is_active=True).count()
            recent_errors = SystemLog.objects.filter(
                level='ERROR',
                created_at__date__gte=timezone.now().date() - timedelta(days=1)
            ).count()
            
            # Calculate deductions
            score = base_score - (quarantined * 5) - (active_alerts * 3) - (recent_errors * 2)
            
            return max(score, 0)  # Don't go below 0
            
        except Exception:
            return 85  # Default score

class AuditManagementView(GovernanceBaseView):
    """Comprehensive Audit and Logs Management"""
    template_name = 'governance/audit_management.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context['breadcrumb_items'].append({
            'title': _('إدارة التدقيق والسجلات'), 'active': True
        })
        
        context.update({
            'title': _('إدارة شاملة للتدقيق والسجلات'),
            'subtitle': _('تتبع جميع العمليات والتغييرات في النظام'),
            'icon': 'fas fa-clipboard-list'
        })
        
        return context

class SystemHealthView(GovernanceBaseView):
    """System Health and Performance Monitoring"""
    template_name = 'governance/system_health.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context['breadcrumb_items'].append({
            'title': _('صحة النظام والأداء'), 'active': True
        })
        
        context.update({
            'title': _('صحة النظام والتنبيهات والأداء'),
            'subtitle': _('مراقبة شاملة لحالة النظام ومؤشرات الأداء'),
            'icon': 'fas fa-heartbeat'
        })
        
        return context

class SecurityCenterView(GovernanceBaseView):
    """Security Center for violations and incidents"""
    template_name = 'governance/security_center.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context['breadcrumb_items'].append({
            'title': _('مركز الأمان والحوادث'), 'active': True
        })
        
        context.update({
            'title': _('مركز الأمان والانتهاكات والحوادث'),
            'subtitle': _('مراقبة الانتهاكات الأمنية وإدارة الحوادث'),
            'icon': 'fas fa-shield-alt'
        })
        
        return context

class SecurityPoliciesView(GovernanceBaseView):
    """Security Policies and Encryption Center"""
    template_name = 'security/policies_center.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context['breadcrumb_items'].append({
            'title': _('مركز السياسات الأمنية'), 'active': True
        })
        
        context.update({
            'title': _('مركز السياسات الأمنية والتشفير'),
            'subtitle': _('إدارة السياسات الأمنية وإعدادات التشفير'),
            'icon': 'fas fa-lock'
        })
        
        return context

class SignalsManagementView(GovernanceBaseView):
    """Signals and Permissions Management Center"""
    template_name = 'signals/management_center.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context['breadcrumb_items'].append({
            'title': _('مركز إدارة الإشارات والأذونات'), 'active': True
        })
        
        context.update({
            'title': _('مركز إدارة الإشارات والأذونات'),
            'subtitle': _('مراقبة العمليات التلقائية وإدارة الصلاحيات'),
            'icon': 'fas fa-broadcast-tower'
        })
        
        return context

class ReportsBuilderView(GovernanceBaseView):
    """Advanced Reports Builder and Scheduler"""
    template_name = 'reports/builder_center.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context['breadcrumb_items'].append({
            'title': _('مركز بناء التقارير'), 'active': True
        })
        
        context.update({
            'title': _('مركز بناء التقارير المخصصة والجدولة'),
            'subtitle': _('إنشاء تقارير مخصصة وجدولة التقارير التلقائية'),
            'icon': 'fas fa-chart-line'
        })
        
        return context

class NotificationsCenterView(GovernanceBaseView):
    """Advanced Notifications Management Center"""
    template_name = 'notifications/management_center.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context['breadcrumb_items'].append({
            'title': _('مركز إدارة الإشعارات'), 'active': True
        })
        
        context.update({
            'title': _('مركز إدارة الإشعارات والقوالب'),
            'subtitle': _('إدارة شاملة للإشعارات والقوالب والجدولة'),
            'icon': 'fas fa-bell'
        })
        
        return context

class HealthMonitoringView(GovernanceBaseView):
    """Advanced Health Check and Monitoring Center"""
    template_name = 'health/monitoring_center.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context['breadcrumb_items'].append({
            'title': _('مركز مراقبة الصحة'), 'active': True
        })
        
        context.update({
            'title': _('مركز مراقبة صحة النظام والفحوصات المخصصة'),
            'subtitle': _('مراقبة استباقية للنظام وفحوصات مخصصة'),
            'icon': 'fas fa-stethoscope'
        })
        
        return context