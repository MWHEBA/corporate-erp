"""
Comprehensive examples of SignalRouter usage with governance controls.
Demonstrates best practices for signal management in the governance system.
"""

import logging
from django.db.models.signals import post_save, pre_delete
from django.contrib.auth import get_user_model
from django.db import transaction

from governance.services.signal_router import signal_router, route_signal
from governance.signal_integration import (
    governed_signal_handler, 
    critical_signal_handler,
    side_effect_handler,
    connect_governed_signal,
    disable_signals_for_operation,
    maintenance_mode_operation
)
from governance.models import GovernanceContext

logger = logging.getLogger(__name__)
User = get_user_model()


# Example 1: Basic Signal Handler with Governance
@governed_signal_handler("user_profile_updated", critical=False, description="Update user profile cache")
def update_user_profile_cache(sender, instance, **kwargs):
    """
    Non-critical side effect: Update user profile cache.
    This can be safely disabled during maintenance without breaking core functionality.
    """
    try:
        # Simulate cache update
        logger.info(f"Updating profile cache for user {instance.username}")
        # cache.set(f"user_profile_{instance.id}", instance.get_profile_data())
        return "cache_updated"
    except Exception as e:
        logger.error(f"Failed to update user profile cache: {e}")
        # Non-critical failure - don't break the main operation
        return None


# Example 2: Critical Signal Handler
@critical_signal_handler("user_audit_trail", description="Create audit trail for user changes")
def create_user_audit_trail(sender, instance, **kwargs):
    """
    Critical side effect: Create audit trail.
    This should execute even during maintenance mode to ensure compliance.
    """
    from governance.services.audit_service import AuditService
    
    try:
        # This is critical for compliance - must not fail silently
        AuditService.log_operation(
            model_name=sender.__name__,
            object_id=instance.id,
            operation='UPDATE',
            source_service='UserSignals',
            user=GovernanceContext.get_current_user() or instance,
            after_data={'username': instance.username, 'email': instance.email}
        )
        return "audit_created"
    except Exception as e:
        logger.error(f"Critical audit trail creation failed: {e}")
        # For critical handlers, we might want to raise the exception
        # to ensure the issue is addressed
        raise


# Example 3: Financial Signal with Transaction Safety
@critical_signal_handler("journal_entry_integrity", description="Validate journal entry integrity")
def validate_journal_entry_integrity(sender, instance, **kwargs):
    """
    Critical financial validation that must execute within transaction boundaries.
    Demonstrates how signals should handle required side-effects.
    """
    try:
        # This validation is required for data integrity
        if hasattr(instance, 'validate_debit_credit_balance'):
            is_valid = instance.validate_debit_credit_balance()
            if not is_valid:
                raise ValueError("Journal entry debits and credits do not balance")
        
        # Log the validation for audit purposes
        logger.info(f"Journal entry {instance.id} validated successfully")
        return "validation_passed"
        
    except Exception as e:
        logger.error(f"Journal entry validation failed: {e}")
        # Critical validation failure should prevent the save
        raise


# Example 4: Bulk Operation with Disabled Signals
@disable_signals_for_operation(reason="Bulk user import")
def bulk_import_users(user_data_list):
    """
    Bulk operation that disables signals to improve performance.
    Demonstrates when it's appropriate to disable signals.
    """
    users_created = []
    
    try:
        with transaction.atomic():
            for user_data in user_data_list:
                # Create users without triggering signals
                user = User.objects.create(**user_data)
                users_created.append(user)
        
        logger.info(f"Bulk imported {len(users_created)} users")
        
        # Optionally trigger critical signals manually after bulk operation
        for user in users_created:
            route_signal(
                "user_audit_trail", 
                sender=User, 
                instance=user, 
                critical=True,
                bulk_operation=True
            )
        
        return users_created
        
    except Exception as e:
        logger.error(f"Bulk user import failed: {e}")
        raise


# Example 5: Maintenance Operation
@maintenance_mode_operation(reason="User data cleanup")
def cleanup_inactive_users():
    """
    Maintenance operation that runs in maintenance mode.
    Only critical signals (like audit trails) will execute.
    """
    inactive_users = User.objects.filter(is_active=False, last_login__lt='2023-01-01')
    
    deleted_count = 0
    for user in inactive_users:
        try:
            # Delete user - only critical signals will fire
            user.delete()
            deleted_count += 1
        except Exception as e:
            logger.error(f"Failed to delete user {user.username}: {e}")
    
    logger.info(f"Cleaned up {deleted_count} inactive users")
    return deleted_count


# Example 6: Signal Chain Management
class FinancialOperationHandler:
    """
    Example of managing complex signal chains for financial operations.
    Demonstrates proper signal depth management and chain control.
    """
    
    @staticmethod
    @governed_signal_handler("payment_received", critical=True, description="Process payment receipt")
    def handle_payment_received(sender, instance, **kwargs):
        """
        Handle payment receipt with proper signal chain management.
        This might trigger additional signals in a controlled manner.
        """
        try:
            # Step 1: Update account balance (critical)
            FinancialOperationHandler._update_account_balance(instance)
            
            # Step 2: Create journal entry (critical, might trigger more signals)
            journal_entry = FinancialOperationHandler._create_journal_entry(instance)
            
            # Step 3: Send notification (non-critical, separate signal)
            route_signal(
                "payment_notification",
                sender=sender,
                instance=instance,
                critical=False,
                journal_entry_id=journal_entry.id if journal_entry else None
            )
            
            return "payment_processed"
            
        except Exception as e:
            logger.error(f"Payment processing failed: {e}")
            # Critical payment processing failure should be raised
            raise
    
    @staticmethod
    def _update_account_balance(payment_instance):
        """Update account balance (critical operation)"""
        # This would update the account balance
        # Implementation would be in the authoritative service
        logger.info(f"Updating account balance for payment {payment_instance.id}")
        return True
    
    @staticmethod
    def _create_journal_entry(payment_instance):
        """Create journal entry (critical operation)"""
        # This would create a journal entry through AccountingGateway
        # Implementation would call the gateway service
        logger.info(f"Creating journal entry for payment {payment_instance.id}")
        return None  # Would return actual journal entry


# Example 7: Signal Router Configuration and Monitoring
class SignalGovernanceManager:
    """
    Manager class for signal governance operations.
    Demonstrates monitoring and management of signal routing.
    """
    
    @staticmethod
    def setup_signal_monitoring():
        """Set up signal monitoring and alerts"""
        
        def monitor_signal_health():
            """Monitor signal router health and alert on issues"""
            stats = signal_router.get_signal_statistics()
            
            # Check for high error rates
            counters = stats['counters']
            if counters['signals_processed'] > 0:
                error_rate = (counters['signal_errors'] / counters['signals_processed']) * 100
                if error_rate > 5:  # More than 5% error rate
                    logger.warning(f"High signal error rate: {error_rate:.2f}%")
            
            # Check for excessive blocking
            if counters['signals_blocked'] > counters['signals_processed'] * 0.1:
                logger.warning(f"High signal blocking rate: {counters['signals_blocked']} blocked")
            
            # Check call stack depth
            if stats['current_call_stack_depth'] > stats['depth_limit'] * 0.8:
                logger.warning(f"Signal chain approaching depth limit: {stats['current_call_stack_depth']}")
            
            return stats
        
        # This could be called periodically by a monitoring system
        return monitor_signal_health
    
    @staticmethod
    def emergency_signal_shutdown(reason="Emergency shutdown"):
        """Emergency shutdown of all signals"""
        logger.critical(f"EMERGENCY: Shutting down all signals - {reason}")
        signal_router.disable_global_signals(reason)
        
        # Notify administrators
        # send_emergency_notification(f"Signal system shutdown: {reason}")
    
    @staticmethod
    def graceful_maintenance_mode(reason="Scheduled maintenance"):
        """Enter maintenance mode gracefully"""
        logger.info(f"Entering maintenance mode: {reason}")
        signal_router.enter_maintenance_mode(reason)
        
        # Wait for current signals to complete
        import time
        time.sleep(1)  # Give current signals time to complete
        
        return signal_router.get_signal_statistics()
    
    @staticmethod
    def validate_signal_configuration():
        """Validate current signal configuration"""
        errors = signal_router.validate_configuration()
        
        if errors:
            logger.error(f"Signal configuration errors: {errors}")
            return False, errors
        else:
            logger.info("Signal configuration is valid")
            return True, []


# Example 8: Integration with Django Models
def setup_user_signal_governance():
    """
    Example of setting up governed signals for User model.
    This would typically be called in Django app ready() method.
    """
    
    # Connect the governed signal handlers to Django signals
    connect_governed_signal(
        signal=post_save,
        handler=update_user_profile_cache,
        sender=User,
        signal_name="user_profile_updated",
        critical=False,
        description="Update user profile cache on save"
    )
    
    connect_governed_signal(
        signal=post_save,
        handler=create_user_audit_trail,
        sender=User,
        signal_name="user_audit_trail",
        critical=True,
        description="Create audit trail for user changes"
    )
    
    # Example of connecting to pre_delete for cleanup
    @side_effect_handler("user_cleanup", "Clean up user-related data")
    def cleanup_user_data(sender, instance, **kwargs):
        """Clean up user-related data before deletion"""
        try:
            # Clean up user sessions, cache, etc.
            logger.info(f"Cleaning up data for user {instance.username}")
            # cleanup_user_sessions(instance)
            # clear_user_cache(instance)
            return "cleanup_completed"
        except Exception as e:
            logger.error(f"User cleanup failed: {e}")
            # Non-critical cleanup failure shouldn't prevent deletion
            return None
    
    connect_governed_signal(
        signal=pre_delete,
        handler=cleanup_user_data,
        sender=User,
        signal_name="user_cleanup",
        critical=False,
        description="Clean up user data before deletion"
    )
    
    logger.info("User signal governance configured")


# Example 9: Testing Signal Governance
class SignalGovernanceTestHelper:
    """
    Helper class for testing signal governance in unit tests.
    """
    
    @staticmethod
    def test_signal_blocking():
        """Test that signals can be properly blocked"""
        # Disable a specific signal
        signal_router.disable_signal("test_signal", "Unit test")
        
        # Try to route the signal
        result = route_signal("test_signal", User, critical=False)
        
        assert result['blocked'] == True
        assert result['handlers_executed'] == 0
        
        # Re-enable the signal
        signal_router.enable_signal("test_signal")
    
    @staticmethod
    def test_maintenance_mode():
        """Test maintenance mode behavior"""
        # Register critical and non-critical handlers
        @critical_signal_handler("critical_test", "Critical test handler")
        def critical_handler(sender, instance, **kwargs):
            return "critical_executed"
        
        @side_effect_handler("non_critical_test", "Non-critical test handler")
        def non_critical_handler(sender, instance, **kwargs):
            return "non_critical_executed"
        
        # Enter maintenance mode
        signal_router.enter_maintenance_mode("Test")
        
        # Test that critical signals still work
        critical_result = route_signal("critical_test", User, critical=True)
        assert critical_result['success'] == True
        assert not critical_result['blocked']
        
        # Test that non-critical signals are blocked
        non_critical_result = route_signal("non_critical_test", User, critical=False)
        assert non_critical_result['blocked'] == True
        
        # Exit maintenance mode
        signal_router.exit_maintenance_mode()
    
    @staticmethod
    def test_signal_independence():
        """Test that signal failures don't break main operations"""
        @side_effect_handler("failing_test", "Handler that always fails")
        def failing_handler(sender, instance, **kwargs):
            raise Exception("Test failure")
        
        # Route the failing signal
        result = route_signal("failing_test", User, critical=False)
        
        # Signal routing should succeed even though handler failed
        assert result['success'] == True
        assert result['handlers_failed'] > 0
        
        # Main operation would continue normally


# Example usage in Django app configuration
def configure_signal_governance():
    """
    Main configuration function for signal governance.
    This would be called from Django app ready() method.
    """
    try:
        # Set up user signals
        setup_user_signal_governance()
        
        # Set up monitoring
        monitor_func = SignalGovernanceManager.setup_signal_monitoring()
        
        # Validate configuration
        is_valid, errors = SignalGovernanceManager.validate_signal_configuration()
        if not is_valid:
            logger.error(f"Signal governance configuration invalid: {errors}")
        
        # Log successful setup
        stats = signal_router.get_signal_statistics()
        logger.info(f"Signal governance configured successfully. Handlers: {len(stats['registered_handlers'])}")
        
    except Exception as e:
        logger.error(f"Failed to configure signal governance: {e}")
        raise


if __name__ == "__main__":
    # Example of running signal governance operations
    print("Signal Router Usage Examples")
    print("=" * 40)
    
    # This would normally be run within Django context
    # configure_signal_governance()
    
    # Example of checking signal status
    stats = signal_router.get_signal_statistics()
    print(f"Signal Router Status:")
    print(f"  Global Enabled: {stats['global_enabled']}")
    print(f"  Maintenance Mode: {stats['maintenance_mode']}")
    print(f"  Registered Handlers: {len(stats['registered_handlers'])}")
    print(f"  Signals Processed: {stats['counters']['signals_processed']}")