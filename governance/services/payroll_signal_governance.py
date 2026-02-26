"""
Payroll Signal Governance Service - Gradual Rollout Implementation

This service implements gradual rollout controls for payroll signal governance,
providing monitoring, kill switches, and rollback capabilities specifically
for payroll-related signals.

Key Features:
- Gradual activation with percentage-based rollout
- Real-time monitoring of payroll signal performance
- Kill switches for problematic payroll signals
- Automatic rollback on error thresholds
- Integration with existing SignalRouter and GovernanceSwitchboard

Requirements: 9.2, 9.3, 9.5 - Signal governance with gradual rollout
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from contextlib import contextmanager
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.conf import settings

from ..models import GovernanceContext, AuditTrail
from ..exceptions import GovernanceError, ValidationError, SignalError
from ..thread_safety import monitor_operation, ThreadSafeCounter
from .signal_router import signal_router
from .governance_switchboard import governance_switchboard
from .audit_service import AuditService
from .payroll_gateway import PayrollGateway

# Import payroll signal components
from ..signals.payroll_signals import PayrollSignalFeatureFlags, PayrollSignalMonitor

User = get_user_model()
logger = logging.getLogger('governance.payroll_signal_governance')


@dataclass
class PayrollSignalMetrics:
    """Metrics for payroll signal performance monitoring"""
    signal_name: str
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    average_execution_time: float = 0.0
    last_execution_time: Optional[datetime] = None
    error_rate: float = 0.0
    rollout_percentage: int = 0
    is_enabled: bool = False
    last_error: Optional[str] = None
    consecutive_failures: int = 0
    
    def update_execution(self, success: bool, execution_time: float, error: Optional[str] = None):
        """Update metrics after signal execution"""
        self.total_executions += 1
        self.last_execution_time = timezone.now()
        
        if success:
            self.successful_executions += 1
            self.consecutive_failures = 0
        else:
            self.failed_executions += 1
            self.consecutive_failures += 1
            self.last_error = error
        
        # Update error rate
        self.error_rate = (self.failed_executions / self.total_executions) * 100 if self.total_executions > 0 else 0
        
        # Update average execution time (simple moving average)
        if self.total_executions == 1:
            self.average_execution_time = execution_time
        else:
            self.average_execution_time = (self.average_execution_time * 0.9) + (execution_time * 0.1)


@dataclass
class RolloutConfiguration:
    """Configuration for gradual rollout of payroll signals"""
    signal_name: str
    initial_percentage: int = 5
    increment_percentage: int = 10
    increment_interval_minutes: int = 30
    max_error_rate: float = 5.0  # Maximum error rate before rollback
    max_consecutive_failures: int = 3
    min_executions_for_promotion: int = 10
    rollback_on_error: bool = True
    auto_promote: bool = True
    target_percentage: int = 100
    
    def __post_init__(self):
        """Validate configuration after initialization"""
        if not (0 <= self.initial_percentage <= 100):
            raise ValueError("initial_percentage must be between 0 and 100")
        if not (0 <= self.increment_percentage <= 100):
            raise ValueError("increment_percentage must be between 0 and 100")
        if self.increment_interval_minutes < 1:
            raise ValueError("increment_interval_minutes must be at least 1")
        if not (0 <= self.max_error_rate <= 100):
            raise ValueError("max_error_rate must be between 0 and 100")


class PayrollSignalGovernanceService:
    """
    Service for managing gradual rollout of payroll signal governance controls.
    
    This service provides:
    - Gradual activation with monitoring
    - Kill switches for problematic signals
    - Automatic rollback capabilities
    - Real-time performance monitoring
    """
    
    # Payroll signals that support gradual rollout
    PAYROLL_SIGNALS = {
        'payroll_creation_notifications': {
            'description': 'Notifications when payroll is created',
            'critical': False,
            'default_config': RolloutConfiguration(
                signal_name='payroll_creation_notifications',
                initial_percentage=10,
                increment_percentage=15,
                increment_interval_minutes=20,
                max_error_rate=3.0
            )
        },
        'payroll_status_notifications': {
            'description': 'Notifications when payroll status changes',
            'critical': False,
            'default_config': RolloutConfiguration(
                signal_name='payroll_status_notifications',
                initial_percentage=10,
                increment_percentage=15,
                increment_interval_minutes=20,
                max_error_rate=3.0
            )
        },
        'payroll_cache_invalidation': {
            'description': 'Cache invalidation for payroll changes',
            'critical': False,
            'default_config': RolloutConfiguration(
                signal_name='payroll_cache_invalidation',
                initial_percentage=20,
                increment_percentage=20,
                increment_interval_minutes=15,
                max_error_rate=5.0
            )
        },
        'payroll_analytics_tracking': {
            'description': 'Analytics tracking for payroll operations',
            'critical': False,
            'default_config': RolloutConfiguration(
                signal_name='payroll_analytics_tracking',
                initial_percentage=15,
                increment_percentage=20,
                increment_interval_minutes=25,
                max_error_rate=10.0  # Analytics can tolerate higher error rates
            )
        },
        'payroll_audit_enhancements': {
            'description': 'Enhanced audit logging for payroll',
            'critical': False,
            'default_config': RolloutConfiguration(
                signal_name='payroll_audit_enhancements',
                initial_percentage=25,
                increment_percentage=25,
                increment_interval_minutes=15,
                max_error_rate=2.0  # Audit should be very reliable
            )
        }
    }
    
    def __init__(self):
        """Initialize the payroll signal governance service"""
        self.payroll_gateway = PayrollGateway()
        
        # Thread-safe locks
        self._metrics_lock = threading.RLock()
        self._rollout_lock = threading.RLock()
        self._kill_switch_lock = threading.RLock()
        
        # Signal metrics storage
        self._signal_metrics: Dict[str, PayrollSignalMetrics] = {}
        self._rollout_configs: Dict[str, RolloutConfiguration] = {}
        
        # Kill switches for individual signals
        self._kill_switches: Dict[str, bool] = {}
        
        # Global payroll signal governance state
        self._governance_enabled = False
        self._master_kill_switch = False
        
        # Monitoring counters
        self._rollout_promotions = ThreadSafeCounter()
        self._rollout_rollbacks = ThreadSafeCounter()
        self._kill_switch_activations = ThreadSafeCounter()
        
        # Background monitoring
        self._monitoring_thread = None
        self._monitoring_active = False
        
        # Initialize metrics and configurations
        self._initialize_signal_metrics()
        
        logger.info("PayrollSignalGovernanceService initialized")
    
    def _initialize_signal_metrics(self):
        """Initialize metrics and configurations for all payroll signals"""
        with self._metrics_lock:
            for signal_name, config in self.PAYROLL_SIGNALS.items():
                # Initialize metrics
                self._signal_metrics[signal_name] = PayrollSignalMetrics(signal_name=signal_name)
                
                # Initialize rollout configuration
                self._rollout_configs[signal_name] = config['default_config']
                
                # Initialize kill switch (disabled by default)
                self._kill_switches[signal_name] = False
                
                logger.debug(f"Initialized metrics for payroll signal: {signal_name}")
    
    def enable_payroll_signal_governance(self, user: User, reason: str = "Gradual rollout activation") -> bool:
        """
        Enable payroll signal governance with gradual rollout.
        
        Args:
            user: User enabling the governance
            reason: Reason for enabling
            
        Returns:
            bool: True if successfully enabled
        """
        try:
            with monitor_operation("enable_payroll_signal_governance"):
                # Set governance context
                GovernanceContext.set_context(
                    user=user,
                    service='PayrollSignalGovernanceService',
                    operation='enable_governance'
                )
                
                # Enable master payroll signals switch
                PayrollSignalFeatureFlags.PAYROLL_SIGNALS_ENABLED = True
                
                # Enable payroll governance component in switchboard
                governance_switchboard.enable_component(
                    'payroll_governance',
                    reason=reason,
                    user=user
                )
                
                # Set internal governance state
                self._governance_enabled = True
                self._master_kill_switch = False
                
                # Start background monitoring
                self._start_monitoring()
                
                # Begin gradual rollout for all signals
                self._begin_gradual_rollout(user, reason)
                
                # Create audit trail
                AuditService.log_operation(
                    model_name='PayrollSignalGovernanceService',
                    object_id=0,
                    operation='ENABLE_GOVERNANCE',
                    source_service='PayrollSignalGovernanceService',
                    user=user,
                    after_data={
                        'reason': reason,
                        'signals_count': len(self.PAYROLL_SIGNALS),
                        'monitoring_started': True
                    }
                )
                
                logger.info(f"Payroll signal governance enabled by {user.username}: {reason}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to enable payroll signal governance: {e}")
            
            # Create audit trail for failure
            AuditService.log_operation(
                model_name='PayrollSignalGovernanceService',
                object_id=0,
                operation='ENABLE_GOVERNANCE_FAILED',
                source_service='PayrollSignalGovernanceService',
                user=user,
                after_data={
                    'error': str(e),
                    'reason': reason
                }
            )
            
            raise
        
        finally:
            GovernanceContext.clear_context()
    
    def disable_payroll_signal_governance(self, user: User, reason: str = "Manual disable") -> bool:
        """
        Disable payroll signal governance (safe rollback).
        
        Args:
            user: User disabling the governance
            reason: Reason for disabling
            
        Returns:
            bool: True if successfully disabled
        """
        try:
            with monitor_operation("disable_payroll_signal_governance"):
                # Set governance context
                GovernanceContext.set_context(
                    user=user,
                    service='PayrollSignalGovernanceService',
                    operation='disable_governance'
                )
                
                # Stop background monitoring
                self._stop_monitoring()
                
                # Disable all payroll signal feature flags
                PayrollSignalFeatureFlags.disable_all()
                
                # Disable payroll governance component in switchboard
                governance_switchboard.disable_component(
                    'payroll_governance',
                    reason=reason,
                    user=user
                )
                
                # Set internal governance state
                self._governance_enabled = False
                self._master_kill_switch = True
                
                # Reset all rollout percentages to 0
                with self._rollout_lock:
                    for signal_name in self.PAYROLL_SIGNALS:
                        if signal_name in self._signal_metrics:
                            self._signal_metrics[signal_name].rollout_percentage = 0
                            self._signal_metrics[signal_name].is_enabled = False
                
                # Create audit trail
                AuditService.log_operation(
                    model_name='PayrollSignalGovernanceService',
                    object_id=0,
                    operation='DISABLE_GOVERNANCE',
                    source_service='PayrollSignalGovernanceService',
                    user=user,
                    after_data={
                        'reason': reason,
                        'signals_disabled': len(self.PAYROLL_SIGNALS),
                        'monitoring_stopped': True
                    }
                )
                
                logger.warning(f"Payroll signal governance disabled by {user.username}: {reason}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to disable payroll signal governance: {e}")
            raise
        
        finally:
            GovernanceContext.clear_context()
    
    def _begin_gradual_rollout(self, user: User, reason: str):
        """Begin gradual rollout for all payroll signals"""
        with self._rollout_lock:
            for signal_name, signal_config in self.PAYROLL_SIGNALS.items():
                config = self._rollout_configs[signal_name]
                
                # Set initial rollout percentage
                self._signal_metrics[signal_name].rollout_percentage = config.initial_percentage
                self._signal_metrics[signal_name].is_enabled = True
                
                # Enable the specific signal feature flag if rollout > 0
                if config.initial_percentage > 0:
                    flag_name = self._get_feature_flag_name(signal_name)
                    if flag_name:
                        PayrollSignalFeatureFlags.enable_flag(flag_name)
                
                logger.info(
                    f"Started gradual rollout for {signal_name}: {config.initial_percentage}%"
                )
    
    def _get_feature_flag_name(self, signal_name: str) -> Optional[str]:
        """Map signal name to feature flag name"""
        signal_to_flag_map = {
            'payroll_creation_notifications': 'PAYROLL_CREATION_NOTIFICATIONS',
            'payroll_status_notifications': 'PAYROLL_APPROVAL_NOTIFICATIONS',  # Covers both approval and payment
            'payroll_cache_invalidation': 'PAYROLL_CACHE_INVALIDATION',
            'payroll_analytics_tracking': 'PAYROLL_ANALYTICS_TRACKING',
            'payroll_audit_enhancements': 'PAYROLL_AUDIT_ENHANCEMENTS'
        }
        return signal_to_flag_map.get(signal_name)
    
    def should_execute_signal(self, signal_name: str, payroll_id: Optional[int] = None) -> bool:
        """
        Determine if a payroll signal should execute based on rollout percentage.
        
        Args:
            signal_name: Name of the signal
            payroll_id: Optional payroll ID for consistent routing
            
        Returns:
            bool: True if signal should execute
        """
        # Check master kill switch
        if self._master_kill_switch or not self._governance_enabled:
            return False
        
        # Check individual kill switch
        if self._kill_switches.get(signal_name, False):
            logger.debug(f"Signal {signal_name} blocked by kill switch")
            return False
        
        # Check if signal is in our managed list
        if signal_name not in self.PAYROLL_SIGNALS:
            return True  # Allow non-managed signals to execute normally
        
        # Get rollout percentage
        with self._metrics_lock:
            metrics = self._signal_metrics.get(signal_name)
            if not metrics or not metrics.is_enabled:
                return False
            
            rollout_percentage = metrics.rollout_percentage
        
        # If 100% rollout, always execute
        if rollout_percentage >= 100:
            return True
        
        # If 0% rollout, never execute
        if rollout_percentage <= 0:
            return False
        
        # Use consistent hash-based routing for gradual rollout
        # This ensures the same payroll always gets the same routing decision
        routing_key = f"{signal_name}:{payroll_id}" if payroll_id else signal_name
        hash_value = hash(routing_key) % 100
        
        should_execute = hash_value < rollout_percentage
        
        logger.debug(
            f"Signal {signal_name} rollout decision: {should_execute} "
            f"(hash: {hash_value}, rollout: {rollout_percentage}%)"
        )
        
        return should_execute
    
    def record_signal_execution(self, signal_name: str, success: bool, 
                              execution_time: float, error: Optional[str] = None):
        """
        Record the execution of a payroll signal for monitoring.
        
        Args:
            signal_name: Name of the signal
            success: Whether execution was successful
            execution_time: Execution time in seconds
            error: Error message if execution failed
        """
        if signal_name not in self.PAYROLL_SIGNALS:
            return  # Only track managed signals
        
        with self._metrics_lock:
            metrics = self._signal_metrics.get(signal_name)
            if metrics:
                metrics.update_execution(success, execution_time, error)
                
                # Check for automatic rollback conditions
                self._check_rollback_conditions(signal_name, metrics)
                
                logger.debug(
                    f"Recorded execution for {signal_name}: "
                    f"success={success}, time={execution_time:.3f}s, "
                    f"error_rate={metrics.error_rate:.1f}%"
                )
    
    def _check_rollback_conditions(self, signal_name: str, metrics: PayrollSignalMetrics):
        """Check if signal should be rolled back due to errors"""
        config = self._rollout_configs.get(signal_name)
        if not config or not config.rollback_on_error:
            return
        
        should_rollback = False
        rollback_reason = ""
        
        # Check error rate threshold
        if metrics.error_rate > config.max_error_rate and metrics.total_executions >= 5:
            should_rollback = True
            rollback_reason = f"Error rate {metrics.error_rate:.1f}% exceeds threshold {config.max_error_rate}%"
        
        # Check consecutive failures
        elif metrics.consecutive_failures >= config.max_consecutive_failures:
            should_rollback = True
            rollback_reason = f"Consecutive failures {metrics.consecutive_failures} exceeds threshold {config.max_consecutive_failures}"
        
        if should_rollback:
            logger.warning(f"Auto-rollback triggered for {signal_name}: {rollback_reason}")
            self._rollback_signal(signal_name, rollback_reason, auto_rollback=True)
    
    def _rollback_signal(self, signal_name: str, reason: str, auto_rollback: bool = False):
        """Rollback a signal to 0% rollout"""
        with self._rollout_lock:
            metrics = self._signal_metrics.get(signal_name)
            if metrics:
                old_percentage = metrics.rollout_percentage
                metrics.rollout_percentage = 0
                metrics.is_enabled = False
                
                # Disable feature flag
                flag_name = self._get_feature_flag_name(signal_name)
                if flag_name:
                    PayrollSignalFeatureFlags.disable_flag(flag_name)
                
                # Increment rollback counter
                self._rollout_rollbacks.increment()
                
                # Log rollback
                rollback_type = "AUTO" if auto_rollback else "MANUAL"
                logger.warning(
                    f"{rollback_type} ROLLBACK: {signal_name} from {old_percentage}% to 0% - {reason}"
                )
                
                # Create audit trail
                AuditService.log_operation(
                    model_name='PayrollSignalGovernanceService',
                    object_id=0,
                    operation=f'{rollback_type}_ROLLBACK',
                    source_service='PayrollSignalGovernanceService',
                    user=GovernanceContext.get_current_user(),
                    after_data={
                        'signal_name': signal_name,
                        'old_percentage': old_percentage,
                        'new_percentage': 0,
                        'reason': reason,
                        'error_rate': metrics.error_rate,
                        'consecutive_failures': metrics.consecutive_failures
                    }
                )
    
    def activate_kill_switch(self, signal_name: str, user: User, reason: str) -> bool:
        """
        Activate kill switch for a specific payroll signal.
        
        Args:
            signal_name: Name of the signal to kill
            user: User activating the kill switch
            reason: Reason for activation
            
        Returns:
            bool: True if successfully activated
        """
        if signal_name not in self.PAYROLL_SIGNALS:
            raise ValidationError(f"Unknown payroll signal: {signal_name}")
        
        with self._kill_switch_lock:
            # Activate kill switch
            self._kill_switches[signal_name] = True
            
            # Set rollout to 0%
            with self._metrics_lock:
                metrics = self._signal_metrics.get(signal_name)
                if metrics:
                    metrics.rollout_percentage = 0
                    metrics.is_enabled = False
            
            # Disable feature flag
            flag_name = self._get_feature_flag_name(signal_name)
            if flag_name:
                PayrollSignalFeatureFlags.disable_flag(flag_name)
            
            # Increment counter
            self._kill_switch_activations.increment()
            
            # Log kill switch activation
            logger.critical(f"KILL SWITCH ACTIVATED: {signal_name} by {user.username} - {reason}")
            
            # Create audit trail
            AuditService.log_operation(
                model_name='PayrollSignalGovernanceService',
                object_id=0,
                operation='KILL_SWITCH_ACTIVATED',
                source_service='PayrollSignalGovernanceService',
                user=user,
                after_data={
                    'signal_name': signal_name,
                    'reason': reason,
                    'activated_by': user.username
                }
            )
            
            return True
    
    def deactivate_kill_switch(self, signal_name: str, user: User, reason: str) -> bool:
        """
        Deactivate kill switch for a specific payroll signal.
        
        Args:
            signal_name: Name of the signal to reactivate
            user: User deactivating the kill switch
            reason: Reason for deactivation
            
        Returns:
            bool: True if successfully deactivated
        """
        if signal_name not in self.PAYROLL_SIGNALS:
            raise ValidationError(f"Unknown payroll signal: {signal_name}")
        
        with self._kill_switch_lock:
            # Check if kill switch is actually active
            if not self._kill_switches.get(signal_name, False):
                logger.info(f"Kill switch already inactive for {signal_name}")
                return True
            
            # Deactivate kill switch
            self._kill_switches[signal_name] = False
            
            # Reset signal to initial rollout percentage
            config = self._rollout_configs.get(signal_name)
            if config:
                with self._metrics_lock:
                    metrics = self._signal_metrics.get(signal_name)
                    if metrics:
                        metrics.rollout_percentage = config.initial_percentage
                        metrics.is_enabled = True
                        metrics.consecutive_failures = 0  # Reset failure count
                
                # Re-enable feature flag if rollout > 0
                if config.initial_percentage > 0:
                    flag_name = self._get_feature_flag_name(signal_name)
                    if flag_name:
                        PayrollSignalFeatureFlags.enable_flag(flag_name)
            
            # Log kill switch deactivation
            logger.warning(f"KILL SWITCH DEACTIVATED: {signal_name} by {user.username} - {reason}")
            
            # Create audit trail
            AuditService.log_operation(
                model_name='PayrollSignalGovernanceService',
                object_id=0,
                operation='KILL_SWITCH_DEACTIVATED',
                source_service='PayrollSignalGovernanceService',
                user=user,
                after_data={
                    'signal_name': signal_name,
                    'reason': reason,
                    'deactivated_by': user.username,
                    'reset_to_percentage': config.initial_percentage if config else 0
                }
            )
            
            return True
    
    def promote_signal_rollout(self, signal_name: str, user: User, 
                             target_percentage: Optional[int] = None) -> bool:
        """
        Manually promote a signal to higher rollout percentage.
        
        Args:
            signal_name: Name of the signal to promote
            user: User performing the promotion
            target_percentage: Target percentage (if None, use increment)
            
        Returns:
            bool: True if successfully promoted
        """
        if signal_name not in self.PAYROLL_SIGNALS:
            raise ValidationError(f"Unknown payroll signal: {signal_name}")
        
        with self._rollout_lock:
            metrics = self._signal_metrics.get(signal_name)
            config = self._rollout_configs.get(signal_name)
            
            if not metrics or not config:
                return False
            
            # Check if kill switch is active
            if self._kill_switches.get(signal_name, False):
                logger.warning(f"Cannot promote {signal_name}: kill switch is active")
                return False
            
            # Calculate new percentage
            old_percentage = metrics.rollout_percentage
            if target_percentage is not None:
                new_percentage = min(target_percentage, config.target_percentage)
            else:
                new_percentage = min(
                    old_percentage + config.increment_percentage,
                    config.target_percentage
                )
            
            # Validate promotion conditions
            if not self._validate_promotion_conditions(signal_name, metrics, config):
                logger.warning(f"Promotion conditions not met for {signal_name}")
                return False
            
            # Update rollout percentage
            metrics.rollout_percentage = new_percentage
            
            # Enable feature flag if not already enabled
            if new_percentage > 0 and not metrics.is_enabled:
                metrics.is_enabled = True
                flag_name = self._get_feature_flag_name(signal_name)
                if flag_name:
                    PayrollSignalFeatureFlags.enable_flag(flag_name)
            
            # Increment promotion counter
            self._rollout_promotions.increment()
            
            # Log promotion
            logger.info(
                f"PROMOTED: {signal_name} from {old_percentage}% to {new_percentage}% "
                f"by {user.username}"
            )
            
            # Create audit trail
            AuditService.log_operation(
                model_name='PayrollSignalGovernanceService',
                object_id=0,
                operation='ROLLOUT_PROMOTED',
                source_service='PayrollSignalGovernanceService',
                user=user,
                after_data={
                    'signal_name': signal_name,
                    'old_percentage': old_percentage,
                    'new_percentage': new_percentage,
                    'promoted_by': user.username,
                    'error_rate': metrics.error_rate,
                    'total_executions': metrics.total_executions
                }
            )
            
            return True
    
    def _validate_promotion_conditions(self, signal_name: str, metrics: PayrollSignalMetrics, 
                                     config: RolloutConfiguration) -> bool:
        """Validate that conditions are met for promoting rollout"""
        # Check minimum executions
        if metrics.total_executions < config.min_executions_for_promotion:
            logger.debug(
                f"Not enough executions for {signal_name}: "
                f"{metrics.total_executions} < {config.min_executions_for_promotion}"
            )
            return False
        
        # Check error rate
        if metrics.error_rate > config.max_error_rate:
            logger.debug(
                f"Error rate too high for {signal_name}: "
                f"{metrics.error_rate}% > {config.max_error_rate}%"
            )
            return False
        
        # Check consecutive failures
        if metrics.consecutive_failures >= config.max_consecutive_failures:
            logger.debug(
                f"Too many consecutive failures for {signal_name}: "
                f"{metrics.consecutive_failures} >= {config.max_consecutive_failures}"
            )
            return False
        
        return True
    
    def _start_monitoring(self):
        """Start background monitoring thread"""
        if self._monitoring_active:
            return
        
        self._monitoring_active = True
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            name="PayrollSignalMonitoring",
            daemon=True
        )
        self._monitoring_thread.start()
        logger.info("Started payroll signal monitoring thread")
    
    def _stop_monitoring(self):
        """Stop background monitoring thread"""
        if not self._monitoring_active:
            return
        
        self._monitoring_active = False
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            self._monitoring_thread.join(timeout=5)
        logger.info("Stopped payroll signal monitoring thread")
    
    def _monitoring_loop(self):
        """Background monitoring loop for automatic promotions and health checks"""
        logger.info("Payroll signal monitoring loop started")
        
        while self._monitoring_active:
            try:
                # Check for automatic promotions
                self._check_automatic_promotions()
                
                # Perform health checks
                self._perform_health_checks()
                
                # Sleep for monitoring interval (30 seconds)
                time.sleep(30)
                
            except Exception as e:
                logger.error(f"Error in payroll signal monitoring loop: {e}", exc_info=True)
                time.sleep(60)  # Longer sleep on error
        
        logger.info("Payroll signal monitoring loop stopped")
    
    def _check_automatic_promotions(self):
        """Check if any signals are ready for automatic promotion"""
        if not self._governance_enabled:
            return
        
        current_time = timezone.now()
        
        with self._rollout_lock:
            for signal_name, config in self._rollout_configs.items():
                if not config.auto_promote:
                    continue
                
                metrics = self._signal_metrics.get(signal_name)
                if not metrics or not metrics.is_enabled:
                    continue
                
                # Check if kill switch is active
                if self._kill_switches.get(signal_name, False):
                    continue
                
                # Check if already at target percentage
                if metrics.rollout_percentage >= config.target_percentage:
                    continue
                
                # Check if enough time has passed since last promotion
                # (This is simplified - in a real implementation, you'd track last promotion time)
                
                # Check if conditions are met for promotion
                if self._validate_promotion_conditions(signal_name, metrics, config):
                    # Auto-promote
                    old_percentage = metrics.rollout_percentage
                    new_percentage = min(
                        old_percentage + config.increment_percentage,
                        config.target_percentage
                    )
                    
                    metrics.rollout_percentage = new_percentage
                    self._rollout_promotions.increment()
                    
                    logger.info(
                        f"AUTO-PROMOTED: {signal_name} from {old_percentage}% to {new_percentage}%"
                    )
                    
                    # Create audit trail
                    AuditService.log_operation(
                        model_name='PayrollSignalGovernanceService',
                        object_id=0,
                        operation='AUTO_PROMOTION',
                        source_service='PayrollSignalGovernanceService',
                        user=None,
                        after_data={
                            'signal_name': signal_name,
                            'old_percentage': old_percentage,
                            'new_percentage': new_percentage,
                            'error_rate': metrics.error_rate,
                            'total_executions': metrics.total_executions
                        }
                    )
    
    def _perform_health_checks(self):
        """Perform health checks on payroll signal governance"""
        try:
            # Check signal router health
            router_stats = signal_router.get_signal_statistics()
            if router_stats.get('signal_errors', 0) > 10:
                logger.warning(f"High signal router error count: {router_stats['signal_errors']}")
            
            # Check payroll gateway health
            gateway_health = self.payroll_gateway.get_health_status()
            if gateway_health.get('status') != 'healthy':
                logger.warning(f"PayrollGateway health issues: {gateway_health.get('issues', [])}")
            
            # Check governance switchboard health
            governance_stats = governance_switchboard.get_governance_statistics()
            if governance_stats.get('counters', {}).get('governance_violations', 0) > 5:
                logger.warning("High governance violation count detected")
            
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
    
    def get_rollout_status(self) -> Dict[str, Any]:
        """
        Get comprehensive rollout status for all payroll signals.
        
        Returns:
            dict: Complete rollout status with metrics and recommendations
        """
        with self._metrics_lock:
            status = {
                'governance_enabled': self._governance_enabled,
                'master_kill_switch': self._master_kill_switch,
                'monitoring_active': self._monitoring_active,
                'signals': {},
                'summary': {
                    'total_signals': len(self.PAYROLL_SIGNALS),
                    'enabled_signals': 0,
                    'fully_rolled_out': 0,
                    'kill_switches_active': 0,
                    'average_error_rate': 0.0
                },
                'counters': {
                    'rollout_promotions': self._rollout_promotions.get_value(),
                    'rollout_rollbacks': self._rollout_rollbacks.get_value(),
                    'kill_switch_activations': self._kill_switch_activations.get_value()
                },
                'recommendations': []
            }
            
            total_error_rate = 0.0
            enabled_count = 0
            
            # Collect signal-specific status
            for signal_name, signal_config in self.PAYROLL_SIGNALS.items():
                metrics = self._signal_metrics.get(signal_name)
                config = self._rollout_configs.get(signal_name)
                kill_switch_active = self._kill_switches.get(signal_name, False)
                
                signal_status = {
                    'description': signal_config['description'],
                    'critical': signal_config['critical'],
                    'rollout_percentage': metrics.rollout_percentage if metrics else 0,
                    'is_enabled': metrics.is_enabled if metrics else False,
                    'kill_switch_active': kill_switch_active,
                    'metrics': {
                        'total_executions': metrics.total_executions if metrics else 0,
                        'successful_executions': metrics.successful_executions if metrics else 0,
                        'failed_executions': metrics.failed_executions if metrics else 0,
                        'error_rate': metrics.error_rate if metrics else 0.0,
                        'average_execution_time': metrics.average_execution_time if metrics else 0.0,
                        'consecutive_failures': metrics.consecutive_failures if metrics else 0,
                        'last_execution_time': metrics.last_execution_time.isoformat() if metrics and metrics.last_execution_time else None,
                        'last_error': metrics.last_error if metrics else None
                    },
                    'config': {
                        'initial_percentage': config.initial_percentage if config else 0,
                        'increment_percentage': config.increment_percentage if config else 0,
                        'max_error_rate': config.max_error_rate if config else 0.0,
                        'target_percentage': config.target_percentage if config else 100,
                        'auto_promote': config.auto_promote if config else False
                    }
                }
                
                status['signals'][signal_name] = signal_status
                
                # Update summary statistics
                if metrics and metrics.is_enabled:
                    enabled_count += 1
                    total_error_rate += metrics.error_rate
                    
                    if metrics.rollout_percentage >= 100:
                        status['summary']['fully_rolled_out'] += 1
                
                if kill_switch_active:
                    status['summary']['kill_switches_active'] += 1
            
            # Calculate summary statistics
            status['summary']['enabled_signals'] = enabled_count
            status['summary']['average_error_rate'] = (
                total_error_rate / enabled_count if enabled_count > 0 else 0.0
            )
            
            # Generate recommendations
            if not self._governance_enabled:
                status['recommendations'].append('Payroll signal governance is disabled')
            
            if status['summary']['kill_switches_active'] > 0:
                status['recommendations'].append(
                    f"{status['summary']['kill_switches_active']} kill switches are active"
                )
            
            if status['summary']['average_error_rate'] > 5.0:
                status['recommendations'].append(
                    f"High average error rate: {status['summary']['average_error_rate']:.1f}%"
                )
            
            if enabled_count == 0 and self._governance_enabled:
                status['recommendations'].append('No signals are enabled despite governance being active')
            
            return status
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get health status of payroll signal governance.
        
        Returns:
            dict: Health status with issues and recommendations
        """
        rollout_status = self.get_rollout_status()
        
        health = {
            'status': 'healthy',
            'issues': [],
            'recommendations': [],
            'metrics': {
                'governance_enabled': rollout_status['governance_enabled'],
                'monitoring_active': rollout_status['monitoring_active'],
                'enabled_signals': rollout_status['summary']['enabled_signals'],
                'average_error_rate': rollout_status['summary']['average_error_rate'],
                'kill_switches_active': rollout_status['summary']['kill_switches_active']
            }
        }
        
        # Check for issues
        if not rollout_status['governance_enabled']:
            health['status'] = 'warning'
            health['issues'].append('Payroll signal governance is disabled')
        
        if rollout_status['master_kill_switch']:
            health['status'] = 'critical'
            health['issues'].append('Master kill switch is active')
        
        if rollout_status['summary']['kill_switches_active'] > 0:
            health['status'] = 'warning'
            health['issues'].append(f"{rollout_status['summary']['kill_switches_active']} kill switches active")
        
        if rollout_status['summary']['average_error_rate'] > 10.0:
            health['status'] = 'critical'
            health['issues'].append(f"High error rate: {rollout_status['summary']['average_error_rate']:.1f}%")
        elif rollout_status['summary']['average_error_rate'] > 5.0:
            health['status'] = 'warning'
            health['issues'].append(f"Elevated error rate: {rollout_status['summary']['average_error_rate']:.1f}%")
        
        if not rollout_status['monitoring_active'] and rollout_status['governance_enabled']:
            health['status'] = 'warning'
            health['issues'].append('Monitoring is not active')
        
        # Add recommendations from rollout status
        health['recommendations'].extend(rollout_status['recommendations'])
        
        return health


# Global service instance
payroll_signal_governance = PayrollSignalGovernanceService()


# Convenience functions for integration

def should_execute_payroll_signal(signal_name: str, payroll_id: Optional[int] = None) -> bool:
    """Check if a payroll signal should execute based on rollout"""
    return payroll_signal_governance.should_execute_signal(signal_name, payroll_id)


def record_payroll_signal_execution(signal_name: str, success: bool, 
                                   execution_time: float, error: Optional[str] = None):
    """Record payroll signal execution for monitoring"""
    payroll_signal_governance.record_signal_execution(signal_name, success, execution_time, error)


def activate_payroll_kill_switch(signal_name: str, user: User, reason: str) -> bool:
    """Activate kill switch for a payroll signal"""
    return payroll_signal_governance.activate_kill_switch(signal_name, user, reason)


def get_payroll_rollout_status() -> Dict[str, Any]:
    """Get payroll signal rollout status"""
    return payroll_signal_governance.get_rollout_status()