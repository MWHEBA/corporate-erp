# -*- coding: utf-8 -*-
"""
Example: Using @governed_service decorator

This file demonstrates how to use the governance decorators for services.
"""

from django.db import transaction
from governance.services import governed_service
from core.services.base_service import TransactionalService


class StudentFeeService(TransactionalService):
    """
    Example service using governance decorator.
    """
    
    @governed_service(
        critical=True,
        description="Create automatic fees for student",
        enable_idempotency=True,
        enable_audit=True,
        max_execution_time=10.0
    )
    def create_automatic_fees(self, student, academic_year):
        """
        Create automatic fees for a student.
        
        This method is automatically:
        - Protected by idempotency (won't create duplicate fees)
        - Audited (all operations logged)
        - Monitored (performance tracked)
        - Error-handled (failures quarantined)
        
        Args:
            student: Student instance
            academic_year: AcademicYear instance
        
        Returns:
            list: Created StudentFee instances
        """
        from students.models import StudentFee
        from academic.models import FeeType
        
        # Get required fee types
        fee_types = FeeType.objects.filter(
            is_mandatory=True,
            is_active=True
        )
        
        created_fees = []
        
        for fee_type in fee_types:
            # Check if fee already exists
            existing_fee = StudentFee.objects.filter(
                student=student,
                fee_type=fee_type,
                academic_year=academic_year
            ).first()
            
            if not existing_fee:
                fee = StudentFee.objects.create(
                    student=student,
                    fee_type=fee_type,
                    academic_year=academic_year,
                    total_amount=fee_type.default_amount,
                    status='pending'
                )
                created_fees.append(fee)
        
        return created_fees
    
    @governed_service(
        critical=False,
        description="Calculate outstanding fees",
        enable_idempotency=False,  # Read-only operation
        enable_audit=False,  # Not critical enough to audit
        max_execution_time=5.0
    )
    def calculate_outstanding_fees(self, student):
        """
        Calculate outstanding fees for a student.
        
        This is a read-only operation, so:
        - Idempotency is disabled (not needed for reads)
        - Audit is disabled (not critical)
        - Still monitored for performance
        
        Args:
            student: Student instance
        
        Returns:
            dict: Outstanding fees summary
        """
        from students.models import StudentFee
        
        fees = StudentFee.objects.filter(student=student)
        
        total_fees = sum(fee.total_amount for fee in fees)
        paid_amount = sum(fee.paid_amount for fee in fees)
        outstanding = total_fees - paid_amount
        
        return {
            'total_fees': total_fees,
            'paid_amount': paid_amount,
            'outstanding_amount': outstanding,
            'fee_count': fees.count()
        }
    
    @governed_service(
        critical=True,
        description="Process fee payment",
        enable_idempotency=True,
        enable_audit=True,
        max_execution_time=15.0,
        retry_count=2  # Retry twice on failure
    )
    def process_payment(self, student_fee, amount, payment_method, user):
        """
        Process a fee payment with retry logic.
        
        This method will:
        - Retry up to 2 times on transient failures
        - Be protected by idempotency
        - Be fully audited
        - Quarantine data on critical failure
        
        Args:
            student_fee: StudentFee instance
            amount: Payment amount
            payment_method: Payment method code
            user: User making the payment
        
        Returns:
            FeePayment: Created payment instance
        """
        from students.models import FeePayment
        from financial.services import FeeSyncService
        
        # Create payment
        payment = FeePayment.objects.create(
            student_fee=student_fee,
            amount=amount,
            payment_method=payment_method,
            payment_date=timezone.now().date(),
            created_by=user
        )
        
        # Update fee status
        student_fee.paid_amount += amount
        if student_fee.paid_amount >= student_fee.total_amount:
            student_fee.status = 'paid'
        else:
            student_fee.status = 'partial'
        student_fee.save()
        
        # Sync with financial system
        FeeSyncService.sync_payment_to_financial(payment)
        
        return payment


# Usage example in a view:
def create_student_with_fees(request, student_data):
    """
    Example view showing how to use the governed service.
    """
    from students.models import Student
    from academic.models import AcademicYear
    
    # Create student
    student = Student.objects.create(**student_data)
    
    # Use governed service to create fees
    fee_service = StudentFeeService()
    current_year = AcademicYear.objects.get(is_current=True)
    
    # This call is automatically:
    # - Idempotent (won't duplicate if called twice)
    # - Audited (logged in audit trail)
    # - Monitored (performance tracked)
    # - Error-handled (failures quarantined)
    fees = fee_service.create_automatic_fees(student, current_year)
    
    return {
        'student': student,
        'fees': fees,
        'message': f'Created {len(fees)} fees for student'
    }
