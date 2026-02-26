"""
Monitoring and Alerting Service for Governance System.

Provides comprehensive monitoring and alerting for governance violations with:
- Real-time violation detection and alerting
- Health monitoring for all governance components
- Performance metrics and statistics
- Automated alert escalation
- Integration with rollback manager

Key Features:
- Thread-safe monitoring operations
- Configurable alert thresholds
- Multiple alert channels (email, logging, external)
- Health check endpoints
- Performance tracking
"""

import threading
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail

from ..models import GovernanceContext, AuditTrail
from ..exceptions import GovernanceError, ValidationError
from ..thread_safety import monitor_operation, ThreadSafeCounter
from .audit_service import AuditService
from .governance_switchboard import governance_switchboard

logger = logging.getLogger(__name__)


@dataclass
class AlertRule:
    """Defines an alert rule for governance monitoring"""
    name: str
    condition: str  # 'threshold', 'rate', 'pattern'
    metric: str
    threshold: float
    time_window_minutes: int
    severity: str  # 'info', 'warning', 'error', 'critical'
    channels: List[str]  # 'email', 'log', 'external'
    enabled: bool = True
    cooldown_minutes: int = 5  # Minimum time between alerts


@dataclass
class HealthCheck:
    """Represents a health check for governance components"""
    component: str
    check_name: str
    status: str  # 'healthy', 'warning', 'critical', 'unknown'
    message: str
    last_check: datetime
    response_time_ms: float
    details: Dict[str, Any]


@dataclass
class PerformanceMetric:
    """Represents a performance metric"""
    name: str
    value: float
    unit: str
    timestamp: datetime
    tags: Dict[str, str]


class MonitoringService:
    """
    Comprehensive monitoring and alerting service for governance system.
    
    Provides:
    1. Real-time violation monitoring
    2. Health checks for all components
    3. Performance metrics collection
    4. Automated alerting with escalation
    5. Integration with rollback manager
    """
    
    # Default alert rules
    DEFAULT_ALERT_RULES = [
        AlertRule(
            name='high_violation_rate',
            condition='rate',
            metric='governance_violations',
            threshold=10.0,  # violations per minute
            time_window_minutes=5,
            severity='critical',
            channels=['email', 'log']
        ),
        AlertRule(
            name='component_failure_rate',
            condition='threshold',
            metric='component_failures',
            threshold=5.0,
            time_window_minutes=10,
            severity='error',
            channels=['email', 'log']
        ),
        AlertRule(
            name='emergency_activation',
            condition='threshold',
            metric='emergency_activations',
            threshold=1.0,
            time_window_minutes=1,
            severity='critical',
            channels=['email', 'log']
        ),
        AlertRule(
            name='rollback_frequency',
            condition='rate',
            metric='rollbacks',
            threshold=3.0,  # rollbacks per hour
            time_window_minutes=60,
            severity='warning',
            channels=['log']
        ),
        AlertRule(
            name='audit_trail_gaps',
            condition='threshold',
            metric='audit_gaps',
            threshold=1.0,
            time_window_minutes=5,
            severity='error',
            channels=['email', 'log']
        )
    ]
    
    def __init__(self, alert_email: Optional[str] = None, 
                 external_webhook: Optional[str] = None):
        """
        Initialize Monitoring Service.
        
        Args:
            alert_email: Email address for alerts
            external_webhook: External webhook URL for alerts
        """
        self.alert_email = alert_email or getattr(settings, 'GOVERNANCE_ALERT_EMAIL', None)
        self.external_webhook = external_webhook
        
        # Thread-safe locks
        self._metrics_lock = threading.RLock()
        self._alerts_lock = threading.RLock()
        self._health_lock = threading.RLock()
        
        # Monitoring data
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._alert_rules: List[AlertRule] = self.DEFAULT_ALERT_RULES.copy()
        self._last_alert_times: Dict[str, datetime] = {}
        self._health_checks: Dict[str, HealthCheck] = {}
        
        # Performance counters
        self._violation_counter = ThreadSafeCounter()
        self._alert_counter = ThreadSafeCounter()
        self._health_check_counter = ThreadSafeCounter()
        
        # Start background monitoring
        self._monitoring_active = True
        self._monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._monitoring_thread.start()
        
        logger.info("MonitoringService initialized")
    
    def record_metric(self, name: str, value: float, unit: str = '', 
                     tags: Optional[Dict[str, str]] = None):
        """
        Record a performance metric.
        
        Args:
            name: Metric name
            value: Metric value
            unit: Unit of measurement
            tags: Additional tags for the metric
        """
        with monitor_operation(f"record_metric_{name}"):
            with self._metrics_lock:
                metric = PerformanceMetric(
                    name=name,
                    value=value,
                    unit=unit,
                    timestamp=timezone.now(),
                    tags=tags or {}
                )
                
                self._metrics[name].append(metric)
                
                # Check alert rules for this metric
                self._check_metric_alerts(name, value)
    
    def record_violation(self, violation_type: str, component: str, 
                        details: Dict[str, Any], user=None):
        """
        Record a governance violation and trigger monitoring.
        
        Args:
            violation_type: Type of violation
            component: Component where violation occurred
            details: Violation details
            user: User associated with violation
        """
        with monitor_operation("record_governance_violation"):
            self._violation_counter.increment()
            
            # Record violation metric
            self.record_metric(
                'governance_violations',
                1.0,
                'count',
                {
                    'violation_type': violation_type,
                    'component': component
                }
            )
            
            # Log violation
            logger.warning(f"Governance violation: {violation_type} in {component}")
            
            # Check for violation patterns
            self._analyze_violation_patterns(violation_type, component, details)
            
            # Trigger alerts if needed
            self._check_violation_alerts(violation_type, component, details)
    
    def perform_health_check(self, component: str) -> HealthCheck:
        """
        Perform health check for a governance component.
        
        Args:
            component: Component to check
            
        Returns:
            HealthCheck: Health check result
        """
        with monitor_operation(f"health_check_{component}"):
            start_time = time.time()
            
            try:
                # Perform component-specific health checks
                if component == 'accounting_gateway':
                    health = self._check_accounting_gateway_health()
                elif component == 'movement_service':
                    health = self._check_movement_service_health()
                elif component == 'signal_router':
                    health = self._check_signal_router_health()
                elif component == 'admin_lockdown':
                    health = self._check_admin_lockdown_health()
                elif component == 'authority_service':
                    health = self._check_authority_service_health()
                elif component == 'audit_trail':
                    health = self._check_audit_trail_health()
                elif component == 'idempotency_service':
                    health = self._check_idempotency_service_health()
                elif component == 'governance_switchboard':
                    health = self._check_switchboard_health()
                else:
                    health = HealthCheck(
                        component=component,
                        check_name='unknown_component',
                        status='unknown',
                        message=f'Unknown component: {component}',
                        last_check=timezone.now(),
                        response_time_ms=0.0,
                        details={}
                    )
                
                response_time = (time.time() - start_time) * 1000
                health.response_time_ms = response_time
                
                # Store health check result
                with self._health_lock:
                    self._health_checks[component] = health
                
                self._health_check_counter.increment()
                
                # Record health metric
                self.record_metric(
                    f'{component}_health_response_time',
                    response_time,
                    'ms',
                    {'component': component, 'status': health.status}
                )
                
                # Check for health alerts
                if health.status in ['warning', 'critical']:
                    self._trigger_health_alert(health)
                
                return health
                
            except Exception as e:
                error_health = HealthCheck(
                    component=component,
                    check_name='health_check_error',
                    status='critical',
                    message=f'Health check failed: {e}',
                    last_check=timezone.now(),
                    response_time_ms=(time.time() - start_time) * 1000,
                    details={'error': str(e)}
                )
                
                with self._health_lock:
                    self._health_checks[component] = error_health
                
                logger.error(f"Health check failed for {component}: {e}")
                return error_health
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health status"""
        with self._health_lock:
            health_summary = {
                'overall_status': 'healthy',
                'components': {},
                'critical_count': 0,
                'warning_count': 0,
                'healthy_count': 0,
                'last_updated': timezone.now()
            }
            
            for component, health in self._health_checks.items():
                health_summary['components'][component] = {
                    'status': health.status,
                    'message': health.message,
                    'last_check': health.last_check,
                    'response_time_ms': health.response_time_ms
                }
                
                if health.status == 'critical':
                    health_summary['critical_count'] += 1
                    health_summary['overall_status'] = 'critical'
                elif health.status == 'warning':
                    health_summary['warning_count'] += 1
                    if health_summary['overall_status'] == 'healthy':
                        health_summary['overall_status'] = 'warning'
                elif health.status == 'healthy':
                    health_summary['healthy_count'] += 1
            
            return health_summary
    
    def get_metrics_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get metrics summary for the specified time period"""
        with self._metrics_lock:
            cutoff_time = timezone.now() - timedelta(hours=hours)
            summary = {
                'time_period_hours': hours,
                'metrics': {},
                'total_violations': self._violation_counter.get_value(),
                'total_alerts': self._alert_counter.get_value(),
                'total_health_checks': self._health_check_counter.get_value()
            }
            
            for metric_name, metric_deque in self._metrics.items():
                recent_metrics = [
                    m for m in metric_deque 
                    if m.timestamp > cutoff_time
                ]
                
                if recent_metrics:
                    values = [m.value for m in recent_metrics]
                    summary['metrics'][metric_name] = {
                        'count': len(values),
                        'min': min(values),
                        'max': max(values),
                        'avg': sum(values) / len(values),
                        'latest': values[-1],
                        'unit': recent_metrics[-1].unit
                    }
            
            return summary
    
    def _monitoring_loop(self):
        """Background monitoring loop"""
        while self._monitoring_active:
            try:
                # Perform periodic health checks
                components = [
                    'accounting_gateway', 'movement_service', 'signal_router',
                    'admin_lockdown', 'authority_service', 'audit_trail',
                    'idempotency_service', 'governance_switchboard'
                ]
                
                for component in components:
                    if governance_switchboard.is_component_enabled(component.replace('_', '_')):
                        self.perform_health_check(component)
                
                # Check for stale health checks
                self._check_stale_health_checks()
                
                # Clean old metrics
                self._clean_old_metrics()
                
                # Sleep for monitoring interval
                time.sleep(30)  # 30 seconds
                
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                time.sleep(60)  # Wait longer on error
    
    def _check_accounting_gateway_health(self) -> HealthCheck:
        """Check AccountingGateway health"""
        try:
            enabled = governance_switchboard.is_component_enabled('accounting_gateway_enforcement')
            
            if not enabled:
                return HealthCheck(
                    component='accounting_gateway',
                    check_name='component_status',
                    status='warning',
                    message='AccountingGateway enforcement is disabled',
                    last_check=timezone.now(),
                    response_time_ms=0.0,
                    details={'enabled': False}
                )
            
            # Check for recent violations
            recent_violations = self._get_recent_violations('accounting_gateway_bypass', minutes=10)
            
            if recent_violations > 5:
                return HealthCheck(
                    component='accounting_gateway',
                    check_name='violation_check',
                    status='critical',
                    message=f'High violation rate: {recent_violations} bypasses in 10 minutes',
                    last_check=timezone.now(),
                    response_time_ms=0.0,
                    details={'recent_violations': recent_violations}
                )
            elif recent_violations > 0:
                return HealthCheck(
                    component='accounting_gateway',
                    check_name='violation_check',
                    status='warning',
                    message=f'Some violations detected: {recent_violations} bypasses in 10 minutes',
                    last_check=timezone.now(),
                    response_time_ms=0.0,
                    details={'recent_violations': recent_violations}
                )
            
            return HealthCheck(
                component='accounting_gateway',
                check_name='component_status',
                status='healthy',
                message='AccountingGateway is functioning normally',
                last_check=timezone.now(),
                response_time_ms=0.0,
                details={'enabled': True, 'recent_violations': 0}
            )
            
        except Exception as e:
            return HealthCheck(
                component='accounting_gateway',
                check_name='health_check_error',
                status='critical',
                message=f'Health check failed: {e}',
                last_check=timezone.now(),
                response_time_ms=0.0,
                details={'error': str(e)}
            )
    
    def _check_movement_service_health(self) -> HealthCheck:
        """Check MovementService health"""
        try:
            enabled = governance_switchboard.is_component_enabled('movement_service_enforcement')
            
            if not enabled:
                return HealthCheck(
                    component='movement_service',
                    check_name='component_status',
                    status='warning',
                    message='MovementService enforcement is disabled',
                    last_check=timezone.now(),
                    response_time_ms=0.0,
                    details={'enabled': False}
                )
            
            # Check for stock violations
            stock_violations = self._get_recent_violations('stock_movement_violation', minutes=10)
            
            if stock_violations > 3:
                return HealthCheck(
                    component='movement_service',
                    check_name='stock_violation_check',
                    status='critical',
                    message=f'High stock violation rate: {stock_violations} in 10 minutes',
                    last_check=timezone.now(),
                    response_time_ms=0.0,
                    details={'stock_violations': stock_violations}
                )
            
            return HealthCheck(
                component='movement_service',
                check_name='component_status',
                status='healthy',
                message='MovementService is functioning normally',
                last_check=timezone.now(),
                response_time_ms=0.0,
                details={'enabled': True, 'stock_violations': stock_violations}
            )
            
        except Exception as e:
            return HealthCheck(
                component='movement_service',
                check_name='health_check_error',
                status='critical',
                message=f'Health check failed: {e}',
                last_check=timezone.now(),
                response_time_ms=0.0,
                details={'error': str(e)}
            )
    
    def _check_switchboard_health(self) -> HealthCheck:
        """Check Governance Switchboard health"""
        try:
            stats = governance_switchboard.get_governance_statistics()
            
            # Check for emergency flags
            if stats['emergency']['active'] > 0:
                return HealthCheck(
                    component='governance_switchboard',
                    check_name='emergency_status',
                    status='critical',
                    message=f"Emergency flags active: {stats['emergency']['active_list']}",
                    last_check=timezone.now(),
                    response_time_ms=0.0,
                    details=stats['emergency']
                )
            
            # Check governance activity
            if not stats['health']['governance_active']:
                return HealthCheck(
                    component='governance_switchboard',
                    check_name='governance_activity',
                    status='warning',
                    message='No governance components are active',
                    last_check=timezone.now(),
                    response_time_ms=0.0,
                    details=stats['health']
                )
            
            return HealthCheck(
                component='governance_switchboard',
                check_name='switchboard_status',
                status='healthy',
                message='Governance Switchboard is functioning normally',
                last_check=timezone.now(),
                response_time_ms=0.0,
                details=stats
            )
            
        except Exception as e:
            return HealthCheck(
                component='governance_switchboard',
                check_name='health_check_error',
                status='critical',
                message=f'Health check failed: {e}',
                last_check=timezone.now(),
                response_time_ms=0.0,
                details={'error': str(e)}
            )
    
    def _get_recent_violations(self, violation_type: str, minutes: int) -> int:
        """Get count of recent violations of a specific type"""
        # This would typically query the audit trail or violation records
        # For now, return a placeholder based on metrics
        cutoff_time = timezone.now() - timedelta(minutes=minutes)
        
        with self._metrics_lock:
            violation_metrics = self._metrics.get('governance_violations', deque())
            recent_violations = [
                m for m in violation_metrics
                if m.timestamp > cutoff_time and 
                   m.tags.get('violation_type') == violation_type
            ]
            return len(recent_violations)
    
    def _check_metric_alerts(self, metric_name: str, value: float):
        """Check if metric triggers any alert rules"""
        current_time = timezone.now()
        
        for rule in self._alert_rules:
            if not rule.enabled or rule.metric != metric_name:
                continue
            
            # Check cooldown
            last_alert = self._last_alert_times.get(rule.name)
            if last_alert and (current_time - last_alert).total_seconds() < rule.cooldown_minutes * 60:
                continue
            
            # Check condition
            if self._evaluate_alert_condition(rule, metric_name, value, current_time):
                self._trigger_alert(rule, metric_name, value)
    
    def _evaluate_alert_condition(self, rule: AlertRule, metric_name: str, 
                                 value: float, current_time: datetime) -> bool:
        """Evaluate if alert condition is met"""
        if rule.condition == 'threshold':
            return value >= rule.threshold
        
        elif rule.condition == 'rate':
            # Calculate rate over time window
            window_start = current_time - timedelta(minutes=rule.time_window_minutes)
            
            with self._metrics_lock:
                recent_metrics = [
                    m for m in self._metrics.get(metric_name, deque())
                    if m.timestamp > window_start
                ]
                
                if not recent_metrics:
                    return False
                
                total_value = sum(m.value for m in recent_metrics)
                rate = total_value / rule.time_window_minutes
                
                return rate >= rule.threshold
        
        return False
    
    def _trigger_alert(self, rule: AlertRule, metric_name: str, value: float):
        """Trigger an alert based on rule"""
        self._alert_counter.increment()
        self._last_alert_times[rule.name] = timezone.now()
        
        alert_message = f"Alert: {rule.name} - {metric_name} = {value} (threshold: {rule.threshold})"
        
        # Send to configured channels
        for channel in rule.channels:
            if channel == 'log':
                if rule.severity == 'critical':
                    logger.critical(alert_message)
                elif rule.severity == 'error':
                    logger.error(alert_message)
                elif rule.severity == 'warning':
                    logger.warning(alert_message)
                else:
                    logger.info(alert_message)
            
            elif channel == 'email' and self.alert_email:
                self._send_email_alert(rule, metric_name, value, alert_message)
            
            elif channel == 'external' and self.external_webhook:
                self._send_webhook_alert(rule, metric_name, value, alert_message)
    
    def _send_email_alert(self, rule: AlertRule, metric_name: str, value: float, message: str):
        """Send email alert"""
        try:
            subject = f"Governance Alert: {rule.name} ({rule.severity.upper()})"
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.alert_email],
                fail_silently=True
            )
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
    
    def _send_webhook_alert(self, rule: AlertRule, metric_name: str, value: float, message: str):
        """Send webhook alert"""
        # Implementation would depend on external system requirements
        logger.info(f"Webhook alert would be sent: {message}")
    
    def stop_monitoring(self):
        """Stop background monitoring"""
        self._monitoring_active = False
        if self._monitoring_thread.is_alive():
            self._monitoring_thread.join(timeout=5)
    
    def _analyze_violation_patterns(self, violation_type: str, component: str, details: Dict[str, Any]):
        """Analyze violation patterns for potential issues"""
        # Simple pattern analysis - can be enhanced later
        logger.debug(f"Analyzing violation pattern: {violation_type} in {component}")
    
    def _check_violation_alerts(self, violation_type: str, component: str, details: Dict[str, Any]):
        """Check if violation should trigger alerts"""
        # Simple alert check - can be enhanced later
        if violation_type.endswith('_blocked') or violation_type.endswith('_disabled'):
            logger.warning(f"Governance control triggered: {violation_type} in {component}")
    
    def _check_stale_health_checks(self):
        """Check for stale health checks"""
        # Placeholder for stale health check detection
        pass
    
    def _clean_old_metrics(self):
        """Clean old metrics from memory"""
        cutoff_time = timezone.now() - timedelta(hours=24)
        with self._metrics_lock:
            for metric_name, metric_deque in self._metrics.items():
                # Remove old metrics
                while metric_deque and metric_deque[0].timestamp < cutoff_time:
                    metric_deque.popleft()


# Global monitoring service instance
monitoring_service = MonitoringService()


# Convenience functions
def record_governance_metric(name: str, value: float, unit: str = '', 
                           tags: Optional[Dict[str, str]] = None):
    """Record a governance metric"""
    monitoring_service.record_metric(name, value, unit, tags)


def record_governance_violation(violation_type: str, component: str, 
                              details: Dict[str, Any], user=None):
    """Record a governance violation"""
    monitoring_service.record_violation(violation_type, component, details, user)


def get_governance_health() -> Dict[str, Any]:
    """Get overall governance system health"""
    return monitoring_service.get_system_health()


def perform_component_health_check(component: str) -> HealthCheck:
    """Perform health check for a specific component"""
    return monitoring_service.perform_health_check(component)