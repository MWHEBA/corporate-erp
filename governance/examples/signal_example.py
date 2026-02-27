# -*- coding: utf-8 -*-
"""
Example: Using @governed_signal_handler decorator

This file demonstrates how to use the governance decorators for Django signals.
"""

from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from governance.services import governed_signal_handler, SignalErrorHandler


# ============================================================================
# EXAMPLE 1: Critical Signal with Full Governance
# ============================================================================

@governed_signal_handler(
    signal_name="student_fee_creation",
    critical=True,
    description="Create automatic fees for new student",
    max_execution_time=5.0
)
@receiver(post_save, sender='students.Student')
def create_automatic_fees_for_new_student(sender, instance, created, **kwargs):
    """
    Create automatic fees when a new student is created.
    
    This signal is:
    - Critical (failures will be quarantined)
    - Audited (all executions logged)
    - Monitored (performance tracked)
    - Protected (won't break student creation)
    """
    if not created:
        return
    
    # Use transaction.on_commit to avoid nested transactions
    transaction.on_commit(
        lambda: _create_fees_for_student(instance)
    )


def _create_fees_for_student(student):
    """Helper function to create fees (called after transaction commits)"""
    from students.services import StudentFeeService
    from academic.models import AcademicYear
    
    if not student.current_enrollment:
        return
    
    fee_service = StudentFeeService()
    current_year = AcademicYear.objects.get(is_current=True)
    fee_service.create_automatic_fees(student, current_year)


# ============================================================================
# EXAMPLE 2: Non-Critical Signal (Won't Break Main Operation)
# ============================================================================

@governed_signal_handler(
    signal_name="payment_notification",
    critical=False,  # Failure won't break payment
    description="Send notification after payment",
    max_execution_time=3.0
)
@receiver(post_save, sender='students.FeePayment')
def send_payment_notification(sender, instance, created, **kwargs):
    """
    Send notification after payment is created.
    
    This signal is:
    - Non-critical (failures logged but won't break payment)
    - Audited
    - Monitored
    """
    if not created:
        return
    
    transaction.on_commit(
        lambda: _send_notification(instance)
    )


def _send_notification(payment):
    """Helper function to send notification"""
    from core.services import NotificationService
    
    NotificationService.send_payment_confirmation(
        student=payment.student_fee.student,
        amount=payment.amount,
        payment_date=payment.payment_date
    )


# ============================================================================
# EXAMPLE 3: Signal with Manual Error Handling
# ============================================================================

@governed_signal_handler(
    signal_name="parent_account_creation",
    critical=True,
    description="Create financial account for parent",
    max_execution_time=10.0
)
@receiver(post_save, sender='students.Parent')
def create_parent_financial_account(sender, instance, created, **kwargs):
    """
    Create financial account when parent is created.
    
    Uses manual error handling for specific cases.
    """
    if not created:
        return
    
    try:
        transaction.on_commit(
            lambda: _create_parent_account(instance)
        )
    except Exception as e:
        # Manual error handling for specific cases
        SignalErrorHandler.handle_signal_error(
            signal_name='parent_account_creation',
            instance=instance,
            error=e,
            critical=True
        )
        # Don't re-raise - let governance handle it


def _create_parent_account(parent):
    """Helper function to create parent account"""
    from financial.services import UnifiedAccountService
    
    UnifiedAccountService.create_parent_account(parent)


# ============================================================================
# EXAMPLE 4: Signal with Performance Monitoring
# ============================================================================

from governance.services import SignalPerformanceMonitor

@SignalPerformanceMonitor.monitor_signal_performance('payment_sync')
@governed_signal_handler(
    signal_name="payment_financial_sync",
    critical=True,
    description="Sync payment to financial system",
    max_execution_time=8.0
)
@receiver(post_save, sender='students.FeePayment')
def sync_payment_to_financial(sender, instance, created, **kwargs):
    """
    Sync payment to financial system with performance monitoring.
    
    This signal has:
    - Double monitoring (governance + performance monitor)
    - Critical error handling
    - Audit logging
    """
    if not created:
        return
    
    transaction.on_commit(
        lambda: _sync_payment(instance)
    )


def _sync_payment(payment):
    """Helper function to sync payment"""
    from financial.services import FeeSyncService
    
    if not payment.student_fee.is_transportation_fee():
        FeeSyncService.sync_payment_to_financial(payment)


# ============================================================================
# EXAMPLE 5: Pre-Delete Signal
# ============================================================================

@governed_signal_handler(
    signal_name="student_deletion_check",
    critical=True,
    description="Check if student can be deleted",
    max_execution_time=2.0
)
@receiver(pre_delete, sender='students.Student')
def check_student_deletion(sender, instance, **kwargs):
    """
    Check if student can be safely deleted.
    
    This signal:
    - Runs before deletion
    - Can prevent deletion by raising exception
    - Is fully audited
    """
    from students.models import StudentFee
    
    # Check if student has unpaid fees
    unpaid_fees = StudentFee.objects.filter(
        student=instance,
        status__in=['pending', 'partial']
    ).exists()
    
    if unpaid_fees:
        raise ValueError(
            f"Cannot delete student {instance.name} - has unpaid fees"
        )


# ============================================================================
# EXAMPLE 6: Unified Signal Manager (Best Practice)
# ============================================================================

class StudentSignalManager:
    """
    Unified manager for all student-related signals.
    Best practice: Group related signals in a manager class.
    """
    
    @staticmethod
    @governed_signal_handler(
        "student_lifecycle_management",
        critical=True,
        description="Manage student lifecycle events"
    )
    @receiver(post_save, sender='students.Student')
    def handle_student_lifecycle(sender, instance, created, **kwargs):
        """
        Unified handler for student lifecycle.
        Handles both creation and updates.
        """
        if created:
            transaction.on_commit(
                lambda: StudentSignalManager._handle_new_student(instance)
            )
        else:
            transaction.on_commit(
                lambda: StudentSignalManager._handle_student_update(instance)
            )
    
    @staticmethod
    def _handle_new_student(student):
        """Handle new student creation"""
        # Create parent account if needed
        if student.parent and not hasattr(student.parent, 'financial_account'):
            from financial.services import UnifiedAccountService
            UnifiedAccountService.create_parent_account(student.parent)
        
        # Create automatic fees if enrolled
        if student.current_enrollment:
            from students.services import StudentFeeService
            from academic.models import AcademicYear
            
            fee_service = StudentFeeService()
            current_year = AcademicYear.objects.get(is_current=True)
            fee_service.create_automatic_fees(student, current_year)
    
    @staticmethod
    def _handle_student_update(student):
        """Handle student updates"""
        # Update related records if needed
        pass


# ============================================================================
# How to Check Signal Performance
# ============================================================================

def check_signal_performance():
    """
    Example function to check signal performance statistics.
    Can be called from management command or admin panel.
    """
    from governance.services import SignalPerformanceMonitor
    
    signals = [
        'student_fee_creation',
        'payment_notification',
        'parent_account_creation',
        'payment_financial_sync'
    ]
    
    for signal_name in signals:
        stats = SignalPerformanceMonitor.get_signal_statistics(signal_name)
        print(f"\n📊 {signal_name}:")
        print(f"   Total Executions: {stats.get('total_executions', 0)}")
        print(f"   Failures: {stats.get('total_failures', 0)}")
        print(f"   Failure Rate: {stats.get('failure_rate', '0%')}")
        print(f"   Avg Time: {stats.get('avg_execution_time', '0s')}")
        print(f"   Max Time: {stats.get('max_execution_time', '0s')}")
