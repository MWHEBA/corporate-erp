"""
Governance Monitoring Service - Real-time monitoring and alerting for governance violations.

This service provides comprehensive monitoring capabilities for the governance system:
- Real-time violation detection and alerting
- Performance metrics collection
- Health checks for governance components
- Automatic rollback triggers based on violation thresholds
- Integration with the governance switchboard for coordinated responses

Key Features:
- Thread-safe monitoring with proper locking
- Configurable violation thresholds and alerting
- Integration with audit trail for violation tracking
- Emergency response capabilities
- Performance impact monitoring
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque

from django.utils import timezone
from django.core.cache import cache
from django.db import connection
from django.conf import settings

from ..models import AuditTrail, GovernanceContext
from ..exceptions import GovernanceError, ValidationError
from ..thread_safety import ThreadSafeCounter, monitor_operation
from .audit_service import AuditService
from .governance_switchboard import governance_switchboard

logger = logging.getLogger(__name__)


class ViolationType(Enum):
    """Types of governance violations"""
    UNAUTHORIZED_ACCESS = 'unauthorized_access'
    GATEWAY_BYPASS = 'gateway_bypass'
    AUTHORITY_VIOLATION = 'authority_violation'
    DATA_CORRUPTION = 'data_corruption'
    IDEMPOTENCY_VIOLATION = 'idempotency_violation'
    SIGNAL_CHAIN_VIOLATION = 'signal_chain_violation'
    ADMIN_BYPASS = 'admin_bypass'
    PERFORMANCE_DEGRADATION = 'performance_degradation'


class AlertLevel(Enum):
    """Alert severity levels"""
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'
    CRITICAL = 'critical'


@dataclass
class ViolationEvent:
    """Data structure for governance violation events"""
    violation_type: ViolationType
    component: str
    severity: AlertLevel
    timestamp: datetime
    details: Dict[str, Any]
    user: Optional[str] = None
    source_service: Optional[str] = None
    affected_models: List[str] = field(default_factory=list)
    resolution_status: str = 'open'
    resolution_notes: str = ''


@dataclass
class MonitoringMetrics:
    """Data structure for monitoring metrics"""
    component: str
    metric_name: str
    value: float
    timestamp: datetime
    unit: str = ''
    tags: Dict[str, str] = field(default_factory=dict)


class GovernanceMonitoringService:
    """
    Real-time monitoring service for governance violations and system health.
    
    This service continuously monitors the governance system for violations,
    performance issues, and health problems, providing alerting and automatic
    response capabilities.
    """
    
    def __init__(self, 
                 violation_threshold: int = 10,
                 monitoring_interval: int = 30,
                 enable_auto_rollback: bool = False):
        """
        Initialize the monitoring service.
        
        Args:
            violation_threshold: Number of violations before triggering alerts
            monitoring_interval: Monitoring check interval in seconds
            enable_auto_rollback: Whether to enable automatic rollback on critical violations
        """
        self.violation_threshold = violation_threshold
        self.monitoring_interval = monitoring_interval
        self.enable_auto_rollback = enable_auto_rollback
        
        # Thread-safe storage
        self._lock = threading.RLock()
        self._monitoring_active = False
        self._monitoring_thread = None
        
        # Violation tracking
        self._violations: deque = deque(maxlen=1000)  # Keep last 1000 violations
        self._violation_counters = defaultdict(ThreadSafeCounter)
        self._violation_history = defaultdict(list)
        
        # Metrics tracking
        self._metrics: deque = deque(maxlen=5000)  # Keep last 5000 metrics
        self._performance_baselines = {}
        
        # Alert handlers
        self._alert_handlers: Dict[AlertLevel, List[Callable]] = defaultdict(list)
        
        # Component health status
        self._component_health = {}
        self._last_health_check = None
        
        logger.info("GovernanceMonitoringService initialized")
    
    def start_monitoring(self):
        """Start the monitoring service"""
        with self._lock:
            if self._monitoring_active:
                logger.warning("Monitoring service already active")
                return
            
            self._monitoring_active = True
            self._monitoring_thread = threading.Thread(
                target=self._monitoring_loop,
                daemon=True,
                name="GovernanceMonitoring"
            )
            self._monitoring_thread.start()
            
            logger.info("Governance monitoring service started")
    
    def stop_monitoring(self):
        """Stop the monitoring service"""
        with self._lock:
            if not self._monitoring_active:
                return
            
            self._monitoring_active = False
            
            if self._monitoring_thread and self._monitoring_thread.is_alive():
                self._monitoring_thread.join(timeout=10)
            
            logger.info("Governance monitoring service stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        logger.info("Governance monitoring loop started")
        
        while self._monitoring_active:
            try:
                with monitor_operation("governance_monitoring_cycle"):
                    # Check component health
                    self._check_component_health()
                    
                    # Check for violations
                    self._check_for_violations()
                    
                    # Collect performance metrics
                    self._collect_performance_metrics()
                    
                    # Check violation thresholds
                    self._check_violation_thresholds()
                    
                    # Update health status
                    self._update_health_status()
                
                # Sleep until next monitoring cycle
                time.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(self.monitoring_interval)
        
        logger.info("Governance monitoring loop stopped")
    
    def record_violation(self, 
                        violation_type: ViolationType,
                        component: str,
                        severity: AlertLevel,
                        details: Dict[str, Any],
                        user: Optional[str] = None,
                        source_service: Optional[str] = None,
                        affected_models: List[str] = None):
        """
        Record a governance violation.
        
        Args:
            violation_type: Type of violation
            component: Component where violation occurred
            severity: Severity level
            details: Violation details
            user: User associated with violation
            source_service: Service that detected the violation
            affected_models: Models affected by the violation
        """
        violation = ViolationEvent(
            violation_type=violation_type,
            component=component,
            severity=severity,
            timestamp=timezone.now(),
            details=details,
            user=user,
            source_service=source_service,
            affected_models=affected_models or []
        )
        
        with self._lock:
            # Store violation
            self._violations.append(violation)
            
            # Update counters
            self._violation_counters[violation_type.value].increment()
            self._violation_counters[f"{component}_{violation_type.value}"].increment()
            
            # Update history
            self._violation_history[violation_type.value].append(violation.timestamp)
            
            # Keep only recent history (last 24 hours)
            cutoff = timezone.now() - timedelta(hours=24)
            self._violation_history[violation_type.value] = [
                ts for ts in self._violation_history[violation_type.value] if ts > cutoff
            ]
        
        # Log violation
        logger.error(
            f"Governance violation recorded: {violation_type.value} in {component} "
            f"(Severity: {severity.value}) - {details}"
        )
        
        # Trigger alerts
        self._trigger_alerts(violation)
        
        # Record in governance switchboard
        governance_switchboard.record_governance_violation(
            violation_type.value, component, details, user
        )
        
        # Check for automatic response
        if severity == AlertLevel.CRITICAL and self.enable_auto_rollback:
            self._consider_automatic_rollback(violation)
    
    def record_metric(self,
                     component: str,
                     metric_name: str,
                     value: float,
                     unit: str = '',
                     tags: Dict[str, str] = None):
        """
        Record a performance metric.
        
        Args:
            component: Component name
            metric_name: Metric name
            value: Metric value
            unit: Unit of measurement
            tags: Additional tags for the metric
        """
        metric = MonitoringMetrics(
            component=component,
            metric_name=metric_name,
            value=value,
            timestamp=timezone.now(),
            unit=unit,
            tags=tags or {}
        )
        
        with self._lock:
            self._metrics.append(metric)
            
            # Update performance baselines
            baseline_key = f"{component}_{metric_name}"
            if baseline_key not in self._performance_baselines:
                self._performance_baselines[baseline_key] = []
            
            self._performance_baselines[baseline_key].append(value)
            
            # Keep only recent baseline data (last 100 measurements)
            if len(self._performance_baselines[baseline_key]) > 100:
                self._performance_baselines[baseline_key] = \
                    self._performance_baselines[baseline_key][-100:]
    
    def _check_component_health(self):
        """Check health of governance components"""
        components_to_check = [
            'accounting_gateway_enforcement',
            'movement_service_enforcement',
            'authority_boundary_enforcement',
            'audit_trail_enforcement',
            'idempotency_enforcement'
        ]
        
        health_status = {}
        
        for component in components_to_check:
            try:
                # Check if component is enabled
                enabled = governance_switchboard.is_component_enabled(component)
                
                # Check component responsiveness
                responsive = self._check_component_responsiveness(component)
                
                # Check for recent violations
                recent_violations = self._get_recent_violations(component, minutes=5)
                
                health_status[component] = {
                    'enabled': enabled,
                    'responsive': responsive,
                    'recent_violations': len(recent_violations),
                    'status': 'healthy' if enabled and responsive and len(recent_violations) == 0 else 'degraded',
                    'last_check': timezone.now()
                }
                
            except Exception as e:
                health_status[component] = {
                    'enabled': False,
                    'responsive': False,
                    'recent_violations': 0,
                    'status': 'error',
                    'error': str(e),
                    'last_check': timezone.now()
                }
        
        with self._lock:
            self._component_health = health_status
            self._last_health_check = timezone.now()
    
    def _check_component_responsiveness(self, component: str) -> bool:
        """Check if a component is responsive"""
        try:
            # Simple responsiveness check based on component type
            if component == 'accounting_gateway_enforcement':
                from .accounting_gateway import AccountingGateway
                gateway = AccountingGateway()
                return True
                
            elif component == 'movement_service_enforcement':
                from .movement_service import MovementService
                service = MovementService()
                return True
                
            elif component == 'authority_boundary_enforcement':
                from .authority_service import AuthorityService
                service = AuthorityService()
                return True
                
            else:
                return True  # Assume responsive for other components
                
        except Exception as e:
            logger.error(f"Component responsiveness check failed for {component}: {e}")
            return False
    
    def _check_for_violations(self):
        """Check for governance violations in recent audit trail"""
        try:
            # Check recent audit trail entries for violations
            cutoff = timezone.now() - timedelta(minutes=self.monitoring_interval // 60 + 1)
            
            recent_entries = AuditTrail.objects.filter(
                timestamp__gte=cutoff,
                operation__in=['GOVERNANCE_VIOLATION', 'AUTHORITY_VIOLATION', 'GATEWAY_BYPASS']
            )
            
            for entry in recent_entries:
                # Parse violation details from audit entry
                after_data = entry.after_data or {}
                violation_type = after_data.get('violation_type', 'unknown')
                component = after_data.get('component', 'unknown')
                
                # Record violation if not already recorded
                violation_key = f"{entry.id}_{violation_type}_{component}"
                if not cache.get(f"violation_processed_{violation_key}"):
                    self.record_violation(
                        violation_type=ViolationType(violation_type) if violation_type in [v.value for v in ViolationType] else ViolationType.UNAUTHORIZED_ACCESS,
                        component=component,
                        severity=AlertLevel.ERROR,
                        details=after_data,
                        user=entry.user.username if entry.user else None,
                        source_service=entry.source_service
                    )
                    
                    # Mark as processed
                    cache.set(f"violation_processed_{violation_key}", True, 3600)
                    
        except Exception as e:
            logger.error(f"Error checking for violations: {e}")
    
    def _collect_performance_metrics(self):
        """Collect performance metrics from governance components"""
        try:
            # Database connection metrics
            if hasattr(connection, 'queries'):
                query_count = len(connection.queries)
                self.record_metric('database', 'query_count', query_count)
            
            # Governance switchboard metrics
            stats = governance_switchboard.get_governance_statistics()
            
            self.record_metric('governance', 'enabled_components', stats['components']['enabled'])
            self.record_metric('governance', 'enabled_workflows', stats['workflows']['enabled'])
            self.record_metric('governance', 'governance_violations', stats['counters']['governance_violations'])
            self.record_metric('governance', 'flag_changes', stats['counters']['flag_changes'])
            
            # Component-specific metrics
            for component in ['accounting_gateway', 'movement_service', 'authority_service']:
                health = self._component_health.get(f"{component}_enforcement", {})
                if health:
                    self.record_metric(component, 'health_status', 1 if health.get('status') == 'healthy' else 0)
                    self.record_metric(component, 'recent_violations', health.get('recent_violations', 0))
            
        except Exception as e:
            logger.error(f"Error collecting performance metrics: {e}")
    
    def _check_violation_thresholds(self):
        """Check if violation thresholds have been exceeded"""
        try:
            # Check overall violation threshold
            recent_violations = self._get_recent_violations(minutes=60)  # Last hour
            
            if len(recent_violations) > self.violation_threshold:
                self.record_violation(
                    violation_type=ViolationType.PERFORMANCE_DEGRADATION,
                    component='monitoring_service',
                    severity=AlertLevel.CRITICAL,
                    details={
                        'violation_count': len(recent_violations),
                        'threshold': self.violation_threshold,
                        'time_window': '60 minutes'
                    },
                    source_service='GovernanceMonitoringService'
                )
            
            # Check component-specific thresholds
            for component in ['accounting_gateway', 'movement_service', 'authority_service']:
                component_violations = self._get_recent_violations(component, minutes=30)
                
                if len(component_violations) > self.violation_threshold // 2:
                    self.record_violation(
                        violation_type=ViolationType.PERFORMANCE_DEGRADATION,
                        component=component,
                        severity=AlertLevel.WARNING,
                        details={
                            'violation_count': len(component_violations),
                            'threshold': self.violation_threshold // 2,
                            'time_window': '30 minutes'
                        },
                        source_service='GovernanceMonitoringService'
                    )
                    
        except Exception as e:
            logger.error(f"Error checking violation thresholds: {e}")
    
    def _update_health_status(self):
        """Update overall health status"""
        try:
            # Calculate overall health score
            total_components = len(self._component_health)
            healthy_components = sum(1 for h in self._component_health.values() if h.get('status') == 'healthy')
            
            health_score = (healthy_components / total_components) * 100 if total_components > 0 else 0
            
            self.record_metric('governance', 'health_score', health_score, unit='%')
            
            # Update cache with current status
            cache.set('governance_health_score', health_score, 300)  # 5 minutes
            cache.set('governance_last_health_check', timezone.now(), 300)
            
        except Exception as e:
            logger.error(f"Error updating health status: {e}")
    
    def _get_recent_violations(self, component: str = None, minutes: int = 60) -> List[ViolationEvent]:
        """Get recent violations for a component or all components"""
        cutoff = timezone.now() - timedelta(minutes=minutes)
        
        with self._lock:
            violations = [
                v for v in self._violations
                if v.timestamp > cutoff and (component is None or v.component == component)
            ]
        
        return violations
    
    def _trigger_alerts(self, violation: ViolationEvent):
        """Trigger alerts for a violation"""
        handlers = self._alert_handlers.get(violation.severity, [])
        
        for handler in handlers:
            try:
                handler(violation)
            except Exception as e:
                logger.error(f"Error in alert handler: {e}")
    
    def _consider_automatic_rollback(self, violation: ViolationEvent):
        """Consider automatic rollback for critical violations"""
        if not self.enable_auto_rollback:
            return
        
        # Check if this is a pattern of critical violations
        recent_critical = [
            v for v in self._get_recent_violations(minutes=10)
            if v.severity == AlertLevel.CRITICAL
        ]
        
        if len(recent_critical) >= 3:  # 3 critical violations in 10 minutes
            logger.critical(
                f"Automatic rollback triggered due to {len(recent_critical)} critical violations"
            )
            
            # Trigger emergency disable for affected component
            try:
                if violation.component in ['accounting_gateway', 'movement_service']:
                    emergency_flag = f'emergency_disable_{violation.component.replace("_", "")}'
                    governance_switchboard.activate_emergency_flag(
                        emergency_flag,
                        f"Automatic rollback due to critical violations: {violation.details}",
                        user=None
                    )
                    
                    logger.critical(f"Emergency flag activated: {emergency_flag}")
                    
            except Exception as e:
                logger.error(f"Failed to trigger automatic rollback: {e}")
    
    def add_alert_handler(self, severity: AlertLevel, handler: Callable[[ViolationEvent], None]):
        """Add an alert handler for a specific severity level"""
        self._alert_handlers[severity].append(handler)
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status"""
        with self._lock:
            recent_violations = self._get_recent_violations(minutes=60)
            
            return {
                'monitoring_active': self._monitoring_active,
                'last_health_check': self._last_health_check,
                'component_health': dict(self._component_health),
                'recent_violations': len(recent_violations),
                'violation_threshold': self.violation_threshold,
                'monitoring_interval': self.monitoring_interval,
                'auto_rollback_enabled': self.enable_auto_rollback,
                'total_violations': len(self._violations),
                'total_metrics': len(self._metrics)
            }
    
    def get_violation_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get violation summary for the specified time period"""
        cutoff = timezone.now() - timedelta(hours=hours)
        
        with self._lock:
            recent_violations = [v for v in self._violations if v.timestamp > cutoff]
            
            # Group by type
            by_type = defaultdict(int)
            by_component = defaultdict(int)
            by_severity = defaultdict(int)
            
            for violation in recent_violations:
                by_type[violation.violation_type.value] += 1
                by_component[violation.component] += 1
                by_severity[violation.severity.value] += 1
            
            return {
                'time_period_hours': hours,
                'total_violations': len(recent_violations),
                'by_type': dict(by_type),
                'by_component': dict(by_component),
                'by_severity': dict(by_severity),
                'violations': [
                    {
                        'type': v.violation_type.value,
                        'component': v.component,
                        'severity': v.severity.value,
                        'timestamp': v.timestamp.isoformat(),
                        'details': v.details
                    }
                    for v in recent_violations[-50:]  # Last 50 violations
                ]
            }


# Global monitoring service instance
governance_monitoring = GovernanceMonitoringService()


# Convenience functions
def start_monitoring():
    """Start governance monitoring"""
    governance_monitoring.start_monitoring()


def stop_monitoring():
    """Stop governance monitoring"""
    governance_monitoring.stop_monitoring()


def record_violation(violation_type: ViolationType, component: str, severity: AlertLevel, 
                    details: Dict[str, Any], user: str = None, source_service: str = None):
    """Record a governance violation"""
    governance_monitoring.record_violation(
        violation_type, component, severity, details, user, source_service
    )


def record_metric(component: str, metric_name: str, value: float, unit: str = '', tags: Dict[str, str] = None):
    """Record a performance metric"""
    governance_monitoring.record_metric(component, metric_name, value, unit, tags)


def get_monitoring_status() -> Dict[str, Any]:
    """Get current monitoring status"""
    return governance_monitoring.get_monitoring_status()


def get_violation_summary(hours: int = 24) -> Dict[str, Any]:
    """Get violation summary"""
    return governance_monitoring.get_violation_summary(hours)