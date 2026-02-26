"""
AccountingGateway - Thread-Safe Central Gateway for Journal Entry Creation

This service is the single entry point for creating journal entries in the system.
It provides thread-safe operations, full validation, and integration with the
IdempotencyService to prevent duplicate entries.

Key Features:
- Thread-safe journal entry creation with proper locking
- Debit/credit balance validation
- Source linkage validation and enforcement
- Idempotency protection using specific key format: JE:{source_module}:{source_model}:{source_id}:{event_type}
- Integration with audit trail and governance systems
- Support for StudentFee, StockMovement, and FeePayment workflows

Usage:
    gateway = AccountingGateway()
    entry = gateway.create_journal_entry(
        source_module='students',
        source_model='StudentFee', 
        source_id=123,
        lines=[...],
        idempotency_key='JE:students:StudentFee:123:create',
        user=request.user
    )
"""

import logging
from decimal import Decimal
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction, connection
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.apps import apps

from ..models import IdempotencyRecord, AuditTrail, GovernanceContext
from ..exceptions import (
    GovernanceError, AuthorityViolationError, ValidationError as GovValidationError,
    ConcurrencyError, IdempotencyError
)
from ..thread_safety import DatabaseLockManager, IdempotencyLock, monitor_operation
from .idempotency_service import IdempotencyService
from .audit_service import AuditService
from .authority_service import AuthorityService
from .source_linkage_service import SourceLinkageService

# Import financial models
from financial.models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod
from financial.models.chart_of_accounts import ChartOfAccounts

User = get_user_model()
logger = logging.getLogger(__name__)


@dataclass
class JournalEntryLineData:
    """Data structure for journal entry line information"""
    account_code: str
    debit: Decimal
    credit: Decimal
    description: str = ""
    cost_center: Optional[str] = None
    project: Optional[str] = None
    
    def __post_init__(self):
        """Validate line data after initialization"""
        if self.debit < 0 or self.credit < 0:
            raise ValueError("Debit and credit amounts must be non-negative")
        if self.debit > 0 and self.credit > 0:
            raise ValueError("Line cannot have both debit and credit amounts")
        if self.debit == 0 and self.credit == 0:
            raise ValueError("Line must have either debit or credit amount")


@dataclass
class SourceInfo:
    """Data structure for source linkage information"""
    module: str
    model: str
    object_id: int
    
    def __post_init__(self):
        """Validate source info after initialization"""
        if not all([self.module, self.model, self.object_id]):
            raise ValueError("All source info fields are required")
        if self.object_id <= 0:
            raise ValueError("Object ID must be positive")


class AccountingGateway:
    """
    Thread-safe central gateway for all journal entry creation.
    
    This class enforces the single entry point pattern for journal entries,
    ensuring data integrity, proper validation, and audit trail creation.
    """
    
    # Supported source models for journal entries (allowlist)
    ALLOWED_SOURCES = {
        'students.StudentFee',
        'students.FeePayment',
        'students.StudentRefund',  # Added for settlement/refund transactions
        'product.StockMovement',
        'purchase.PurchasePayment',
        'hr.Payroll',
        'hr.PayrollPayment',
        'transportation.TransportationFee',
        'finance.ManualAdjustment',
        'financial.PartnerTransaction',
        'financial.FinancialTransaction',  # Added for TransactionService
        'financial.BankReconciliation',  # Added for BankReconciliationService
        'financial.JournalEntry',  # Added for manual/quick entries that reference themselves
        'courses.CourseEnrollment',  # Added for CourseAccountingService
        'qr_applications.QRApplication',  # Added for QR application payments
        'activities.ActivityExpense',  # Added for activity expense tracking
        'sale.Sale',  # Added for sale invoices
        'sale.SalePayment',  # Added for sale payments
        'sale.SaleReturn',  # Added for sale returns
        'purchase.Purchase',  # Added for purchase invoices
        'purchase.PurchaseReturn',  # Added for purchase returns
    }
    
    # High-priority workflows that require strict validation
    HIGH_PRIORITY_WORKFLOWS = {
        'students.StudentFee',
        'product.StockMovement', 
        'students.FeePayment',
        'hr.Payroll'
    }
    
    def __init__(self):
        """Initialize the AccountingGateway with required services"""
        self.idempotency_service = IdempotencyService
        self.audit_service = AuditService
        self.authority_service = AuthorityService
        self.source_linkage_service = SourceLinkageService
    
    @staticmethod
    def generate_idempotency_key(
        module: str,
        model: str,
        object_id: int,
        operation: str = 'create'
    ) -> str:
        """
        Generate standardized idempotency key for journal entries.
        
        This method ensures consistent idempotency key format across the system.
        The format is: JE:{module}:{model}:{id}:{operation}
        
        Args:
            module: Source module (e.g., 'students', 'transportation', 'product')
            model: Source model (e.g., 'StudentFee', 'DriverPayment', 'ProductSale')
            object_id: Object ID (must be positive integer)
            operation: Operation type (e.g., 'create', 'refund', 'reverse', 'payment')
            
        Returns:
            Standardized idempotency key string
            
        Raises:
            ValueError: If parameters are invalid
            
        Examples:
            >>> AccountingGateway.generate_idempotency_key('students', 'StudentFee', 123, 'create')
            'JE:students:StudentFee:123:create'
            
            >>> AccountingGateway.generate_idempotency_key('transportation', 'DriverPayment', 456, 'payment')
            'JE:transportation:DriverPayment:456:payment'
            
            >>> AccountingGateway.generate_idempotency_key('students', 'FeePayment', 789, 'refund')
            'JE:students:FeePayment:789:refund'
        
        Notes:
            - Keys are deterministic - same inputs always produce same key
            - Keys do NOT include timestamps or random values
            - Keys are case-sensitive
            - Operation names should be lowercase
        """
        # Validate inputs
        if not module or not isinstance(module, str):
            raise ValueError("module must be a non-empty string")
        
        if not model or not isinstance(model, str):
            raise ValueError("model must be a non-empty string")
        
        if not isinstance(object_id, int) or object_id <= 0:
            raise ValueError("object_id must be a positive integer")
        
        if not operation or not isinstance(operation, str):
            raise ValueError("operation must be a non-empty string")
        
        # Normalize operation to lowercase
        operation = operation.lower()
        
        # Generate key
        return f"JE:{module}:{model}:{object_id}:{operation}"
    
    @staticmethod
    def validate_idempotency_key(key: str) -> bool:
        """
        Validate idempotency key format.
        
        Args:
            key: Idempotency key to validate
            
        Returns:
            True if valid, False otherwise
            
        Examples:
            >>> AccountingGateway.validate_idempotency_key('JE:students:StudentFee:123:create')
            True
            
            >>> AccountingGateway.validate_idempotency_key('invalid-key')
            False
            
            >>> AccountingGateway.validate_idempotency_key('JE:students:StudentFee:123:create:extra')
            False
        """
        if not key or not isinstance(key, str):
            return False
        
        parts = key.split(':')
        
        # Must have exactly 5 parts: JE, module, model, id, operation
        if len(parts) != 5:
            return False
        
        # First part must be 'JE'
        if parts[0] != 'JE':
            return False
        
        # Module and model must be non-empty
        if not parts[1] or not parts[2]:
            return False
        
        # ID must be a positive integer
        try:
            obj_id = int(parts[3])
            if obj_id <= 0:
                return False
        except (ValueError, TypeError):
            return False
        
        # Operation must be non-empty
        if not parts[4]:
            return False
        
        return True
    
    def create_journal_entry(
        self,
        source_module: str,
        source_model: str,
        source_id: int,
        lines: List[JournalEntryLineData],
        idempotency_key: str,
        user: User,
        entry_type: str = 'automatic',
        description: str = '',
        reference: str = '',
        date: Optional[datetime] = None,
        accounting_period: Optional[AccountingPeriod] = None,
        financial_category=None,
        financial_subcategory=None
    ) -> JournalEntry:
        """
        Create a journal entry with full validation and thread-safety.
        
        This is the main entry point for creating journal entries. It enforces
        all governance rules, validates data integrity, and ensures thread-safe
        operation with proper locking.
        
        Args:
            source_module: Source module name (e.g., 'students', 'product')
            source_model: Source model name (e.g., 'StudentFee', 'StockMovement')
            source_id: ID of the source record
            lines: List of journal entry lines
            idempotency_key: Unique key to prevent duplicate operations
            user: User creating the entry
            entry_type: Type of entry ('automatic', 'manual', etc.)
            description: Entry description
            reference: Reference number or identifier
            date: Entry date (defaults to today)
            accounting_period: Accounting period (auto-determined if not provided)
            financial_category: Optional financial category for tracking
            financial_subcategory: Optional financial subcategory for detailed tracking
            
        Returns:
            JournalEntry: The created journal entry
            
        Raises:
            AuthorityViolationError: If service lacks authority
            ValidationError: If validation fails
            IdempotencyError: If idempotency check fails
            ConcurrencyError: If concurrency conflict occurs
        """
        operation_start = timezone.now()
        
        try:
            with monitor_operation("accounting_gateway_create_entry"):
                # Set governance context
                GovernanceContext.set_context(
                    user=user,
                    service='AccountingGateway',
                    operation='create_journal_entry'
                )
                
                # Validate authority
                self._validate_authority(source_module, source_model)
                
                # Validate source linkage
                source_info = SourceInfo(source_module, source_model, source_id)
                self._validate_source_linkage(source_info)
                
                # Validate financial subcategory
                self._validate_financial_subcategory(financial_category, financial_subcategory)
                
                # Check idempotency
                is_duplicate, existing_record, existing_data = self.idempotency_service.check_and_record_operation(
                    operation_type='journal_entry',
                    idempotency_key=idempotency_key,
                    result_data={},  # Will be updated after creation
                    user=user,
                    expires_in_hours=24
                )
                
                if is_duplicate:
                    logger.info(f"Duplicate journal entry creation detected: {idempotency_key}")
                    # Return existing journal entry
                    entry_id = existing_data.get('journal_entry_id')
                    if entry_id:
                        return JournalEntry.objects.get(id=entry_id)
                    else:
                        raise IdempotencyError(
                            operation_type='journal_entry',
                            idempotency_key=idempotency_key,
                            context={'error': 'Existing record found but no journal entry ID'}
                        )
                
                # Create journal entry with thread-safe transaction
                journal_entry = self._create_journal_entry_atomic(
                    source_info=source_info,
                    lines=lines,
                    idempotency_key=idempotency_key,
                    user=user,
                    entry_type=entry_type,
                    description=description,
                    reference=reference,
                    date=date,
                    accounting_period=accounting_period,
                    financial_category=financial_category,
                    financial_subcategory=financial_subcategory
                )
                
                # Update idempotency record with result
                existing_record.result_data = {
                    'journal_entry_id': journal_entry.id,
                    'journal_entry_number': journal_entry.number,
                    'total_amount': str(journal_entry.total_amount),
                    'created_at': journal_entry.created_at.isoformat()
                }
                existing_record.save()
                
                # Create audit trail
                self.audit_service.log_operation(
                    model_name='JournalEntry',
                    object_id=journal_entry.id,
                    operation='CREATE',
                    user=user,
                    source_service='AccountingGateway',
                    after_data={
                        'number': journal_entry.number,
                        'source_module': source_module,
                        'source_model': source_model,
                        'source_id': source_id,
                        'total_amount': str(journal_entry.total_amount),
                        'lines_count': journal_entry.lines.count()
                    },
                    idempotency_key=idempotency_key,
                    operation_duration=(timezone.now() - operation_start).total_seconds()
                )
                
                logger.info(
                    f"Journal entry created successfully: {journal_entry.number} "
                    f"for {source_module}.{source_model}#{source_id}"
                )
                
                return journal_entry
                
        except Exception as e:
            logger.error(
                f"Failed to create journal entry for {source_module}.{source_model}#{source_id}: {str(e)}"
            )
            
            # Delete the idempotency record if journal entry creation failed
            # This allows retry without idempotency conflicts
            try:
                from governance.models import IdempotencyRecord
                IdempotencyRecord.objects.filter(
                    operation_type='journal_entry',
                    idempotency_key=idempotency_key
                ).delete()
                logger.info(f"Cleared idempotency record for failed journal entry: {idempotency_key}")
            except Exception as cleanup_error:
                logger.error(f"Failed to clear idempotency record: {cleanup_error}")
            
            # Create audit trail for failure
            self.audit_service.log_operation(
                model_name='JournalEntry',
                object_id=0,  # No entry created
                operation='CREATE_FAILED',
                user=user,
                source_service='AccountingGateway',
                additional_context={
                    'error': str(e),
                    'source_module': source_module,
                    'source_model': source_model,
                    'source_id': source_id,
                    'idempotency_key': idempotency_key
                }
            )
            
            raise
        
        finally:
            GovernanceContext.clear_context()
    
    def _create_journal_entry_atomic(
        self,
        source_info: SourceInfo,
        lines: List[JournalEntryLineData],
        idempotency_key: str,
        user: User,
        entry_type: str,
        description: str,
        reference: str,
        date: Optional[datetime],
        accounting_period: Optional[AccountingPeriod],
        financial_category=None,
        financial_subcategory=None
    ) -> JournalEntry:
        """
        Create journal entry within atomic transaction with proper locking.
        
        This method handles the actual database operations with appropriate
        locking mechanisms for thread safety.
        """
        with DatabaseLockManager.atomic_operation():
            # Validate and prepare data
            validated_lines = self._validate_and_prepare_lines(lines)
            entry_date = date or timezone.now().date()
            
            # Get or validate accounting period
            if accounting_period is None:
                accounting_period = self._get_accounting_period(entry_date)
            
            # Validate accounting period
            self._validate_accounting_period(accounting_period, entry_date)
            
            # Generate journal entry number
            entry_number = self._generate_entry_number(entry_type, source_info)
            
            # Create journal entry
            journal_entry = JournalEntry(
                number=entry_number,
                date=entry_date,
                entry_type=entry_type,
                status='posted',  # Auto-post entries from gateway
                description=description or self._generate_description(source_info),
                reference=reference,
                source_module=source_info.module,
                source_model=source_info.model,
                source_id=source_info.object_id,
                accounting_period=accounting_period,
                idempotency_key=idempotency_key,
                created_by_service='AccountingGateway',
                created_by=user,
                posted_at=timezone.now(),
                posted_by=user,
                financial_category=financial_category,
                financial_subcategory=financial_subcategory
            )
            
            # Mark as gateway approved to avoid development warnings
            journal_entry.mark_as_gateway_approved()
            journal_entry.save()
            
            # Create journal entry lines
            for line_data in validated_lines:
                line = JournalEntryLine(
                    journal_entry=journal_entry,
                    account=line_data['account'],
                    debit=line_data['debit'],
                    credit=line_data['credit'],
                    description=line_data['description'],
                    cost_center=line_data.get('cost_center'),
                    project=line_data.get('project')
                )
                line.save()
            
            # Final validation of complete entry
            self._validate_complete_entry(journal_entry)
            
            # Enforce posting controls (auto-lock posted entries)
            self._enforce_posting_controls(journal_entry)
            
            return journal_entry
    
    def _validate_authority(self, source_module: str, source_model: str) -> None:
        """
        Validate that AccountingGateway has authority to create entries.
        
        Args:
            source_module: Source module name
            source_model: Source model name
            
        Raises:
            AuthorityViolationError: If authority validation fails
        """
        # Check if this service has authority for JournalEntry operations
        if not self.authority_service.validate_authority(
            service_name='AccountingGateway',
            model_name='JournalEntry',
            operation='CREATE'
        ):
            raise AuthorityViolationError(
                message="AccountingGateway lacks authority to create JournalEntry records",
                error_code="AUTHORITY_VIOLATION",
                context={
                    'service': 'AccountingGateway',
                    'model': 'JournalEntry',
                    'operation': 'CREATE'
                }
            )
        
        # Additional validation for high-priority workflows
        source_key = f"{source_module}.{source_model}"
        if source_key in self.HIGH_PRIORITY_WORKFLOWS:
            logger.info(f"High-priority workflow detected: {source_key}")
            # Could add additional validation here if needed
    
    def _validate_source_linkage(self, source_info: SourceInfo) -> None:
        """
        Validate source linkage using SourceLinkageService.
        
        Args:
            source_info: Source information to validate
            
        Raises:
            ValidationError: If source linkage validation fails
        """
        source_key = f"{source_info.module}.{source_info.model}"
        
        # Check allowlist
        if source_key not in self.ALLOWED_SOURCES:
            raise GovValidationError(
                message=f"Source model not in allowlist: {source_key}",
                context={
                    'source_key': source_key,
                    'allowed_sources': list(self.ALLOWED_SOURCES)
                }
            )
        
        # Validate linkage exists
        if not self.source_linkage_service.validate_linkage(
            source_info.module,
            source_info.model,
            source_info.object_id
        ):
            raise GovValidationError(
                message=f"Invalid source linkage: {source_key}#{source_info.object_id}",
                context={
                    'source_module': source_info.module,
                    'source_model': source_info.model,
                    'source_id': source_info.object_id
                }
            )
    
    def _validate_financial_subcategory(
        self,
        category,
        subcategory
    ) -> None:
        """
        Validate financial subcategory belongs to the specified category.
        
        Args:
            category: FinancialCategory instance or None
            subcategory: FinancialSubcategory instance or None
            
        Raises:
            ValidationError: If subcategory validation fails
        """
        # Allow both None
        if category is None and subcategory is None:
            return
        
        # Subcategory without category is invalid
        if subcategory is not None and category is None:
            raise GovValidationError(
                message="Cannot specify financial_subcategory without financial_category",
                context={
                    'subcategory_id': subcategory.id,
                    'subcategory_name': subcategory.name
                }
            )
        
        # Validate subcategory belongs to category
        if subcategory is not None and category is not None:
            if subcategory.parent_category_id != category.id:
                raise GovValidationError(
                    message="Financial subcategory does not belong to the specified category",
                    context={
                        'category_id': category.id,
                        'category_name': category.name,
                        'subcategory_id': subcategory.id,
                        'subcategory_name': subcategory.name,
                        'subcategory_parent_category_id': subcategory.parent_category_id
                    }
                )
    
    def _validate_and_prepare_lines(self, lines: List[JournalEntryLineData]) -> List[Dict]:
        """
        Validate journal entry lines and prepare them for database insertion.
        
        Args:
            lines: List of journal entry line data
            
        Returns:
            List[Dict]: Validated and prepared line data
            
        Raises:
            ValidationError: If line validation fails
        """
        if not lines:
            raise GovValidationError(
                message="Journal entry must have at least one line",
                context={}
            )
        
        validated_lines = []
        total_debit = Decimal('0')
        total_credit = Decimal('0')
        
        for i, line_data in enumerate(lines):
            try:
                # Get account
                account = ChartOfAccounts.objects.get(
                    code=line_data.account_code,
                    is_active=True
                )
                
                # Validate account can post entries
                if not account.can_post_entries():
                    raise GovValidationError(
                message=f"Cannot post entries to account: {account.name}",
                context={'account_code': line_data.account_code}
                    )
                
                # Prepare line data
                prepared_line = {
                    'account': account,
                    'debit': line_data.debit,
                    'credit': line_data.credit,
                    'description': line_data.description or f"Line {i+1}",
                    'cost_center': line_data.cost_center,
                    'project': line_data.project
                }
                
                validated_lines.append(prepared_line)
                total_debit += line_data.debit
                total_credit += line_data.credit
                
            except ChartOfAccounts.DoesNotExist:
                raise GovValidationError(
                    message=f"Account not found: {line_data.account_code}",
                    context={'account_code': line_data.account_code}
                )
        
        # Validate debit/credit balance
        if total_debit != total_credit:
            raise GovValidationError(
                message=f"Entry not balanced: debit {total_debit} != credit {total_credit}",
                context={
                    'total_debit': str(total_debit),
                    'total_credit': str(total_credit),
                    'difference': str(total_debit - total_credit)
                }
            )
        
        return validated_lines
    
    def _get_accounting_period(self, date: datetime) -> AccountingPeriod:
        """
        Get accounting period for the given date.
        
        Args:
            date: Date to find period for
            
        Returns:
            AccountingPeriod: The accounting period
            
        Raises:
            ValidationError: If no valid period found
        """
        period = AccountingPeriod.get_period_for_date(date)
        if not period:
            raise GovValidationError(
                message=f"No accounting period found for date: {date}",
                context={'date': date.isoformat() if hasattr(date, 'isoformat') else str(date)}
            )
        
        return period
    
    def _validate_accounting_period(self, period: AccountingPeriod, date: datetime) -> None:
        """
        Validate accounting period can accept new entries with enhanced period lock enforcement.
        
        Args:
            period: Accounting period to validate
            date: Entry date
            
        Raises:
            ValidationError: If period validation fails
        """
        if not period.can_post_entries():
            raise GovValidationError(
                message=f"Cannot post entries to closed period: {period.name}",
                context={
                    'period_name': period.name,
                    'period_status': period.status,
                    'period_closed_at': period.closed_at.isoformat() if period.closed_at else None,
                    'attempted_date': date.isoformat() if hasattr(date, 'isoformat') else str(date)
                }
            )
        
        if not period.is_date_in_period(date):
            raise GovValidationError(
                message=f"Date {date} is outside period {period.name}",
                context={
                    'date': date.isoformat() if hasattr(date, 'isoformat') else str(date),
                    'period_start': period.start_date.isoformat(),
                    'period_end': period.end_date.isoformat(),
                    'period_name': period.name
                }
            )
        
        # Enhanced validation for period lock enforcement
        self._validate_period_lock_enforcement(period, date)
    
    def _validate_period_lock_enforcement(self, period: AccountingPeriod, date: datetime) -> None:
        """
        Enhanced period lock enforcement validation.
        
        Args:
            period: Accounting period to validate
            date: Entry date
            
        Raises:
            ValidationError: If period lock enforcement fails
        """
        # Check if period is approaching closure
        if period.status == 'open' and period.closed_at:
            time_to_closure = period.closed_at - timezone.now()
            if time_to_closure <= timezone.timedelta(hours=24):
                logger.warning(
                    f"Posting to period {period.name} which closes in {time_to_closure}"
                )
        
        # Validate period lock compliance for existing entries
        compliance_report = self.validate_period_lock_compliance(period)
        if compliance_report['unlocked_posted_entries'] > 0:
            logger.warning(
                f"Period {period.name} has {compliance_report['unlocked_posted_entries']} "
                f"unlocked posted entries - compliance issue detected"
            )
        
        # Additional validation for high-priority workflows
        current_context = GovernanceContext.get_context()
        if current_context:
            source_module = getattr(current_context, 'source_module', None)
            source_model = getattr(current_context, 'source_model', None)
            
            if source_module and source_model:
                source_key = f"{source_module}.{source_model}"
                if source_key in self.HIGH_PRIORITY_WORKFLOWS:
                    # Stricter validation for high-priority workflows
                    if compliance_report['high_priority_compliance_ratio'] < 0.95:
                        logger.warning(
                            f"High-priority workflow {source_key} posting to period {period.name} "
                            f"with low compliance ratio: {compliance_report['high_priority_compliance_ratio']:.2%}"
                        )
    
    def _enforce_posting_controls(self, journal_entry: JournalEntry) -> None:
        """
        Enforce posting controls and period lock for posted entries.
        Enhanced period lock enforcement for selected workflows.
        
        Args:
            journal_entry: Journal entry to enforce controls on
            
        Raises:
            ValidationError: If posting controls are violated
        """
        # Auto-post entries created through gateway
        if journal_entry.status == 'posted':
            # Enhanced period lock enforcement for selected workflows
            source_key = f"{journal_entry.source_module}.{journal_entry.source_model}"
            
            if source_key in self.HIGH_PRIORITY_WORKFLOWS:
                # Strict period lock enforcement for high-priority workflows
                self._enforce_strict_period_lock(journal_entry)
            
            # Lock the entry immediately after posting to prevent modification
            journal_entry.lock_entry(
                user=journal_entry.posted_by,
                reason=f"Auto-locked after posting through AccountingGateway - {source_key} workflow"
            )
            
            # Additional immutability enforcement for posted entries
            self._enforce_posted_entry_immutability(journal_entry)
            
            logger.info(f"Entry {journal_entry.number} auto-locked after posting with enhanced period controls")
    
    def create_reversal_entry(
        self,
        original_entry: JournalEntry,
        user: User,
        reason: str = "",
        partial_amount: Optional[Decimal] = None,
        idempotency_key: Optional[str] = None
    ) -> JournalEntry:
        """
        Create a reversal entry for a posted journal entry.
        This is the ONLY way to modify posted entries (period lock enforcement).
        
        Args:
            original_entry: Original journal entry to reverse
            user: User creating the reversal
            reason: Reason for reversal
            partial_amount: Optional partial amount to reverse
            idempotency_key: Optional idempotency key
            
        Returns:
            JournalEntry: The created reversal entry
            
        Raises:
            ValidationError: If reversal validation fails
        """
        operation_start = timezone.now()
        
        try:
            with monitor_operation("accounting_gateway_create_reversal"):
                # Set governance context
                GovernanceContext.set_context(
                    user=user,
                    service='AccountingGateway',
                    operation='create_reversal_entry'
                )
                
                # Validate authority
                self._validate_authority('financial', 'JournalEntry')
                
                # Validate original entry can be reversed
                if not original_entry.can_be_reversed:
                    raise GovValidationError(
                message="Original entry cannot be reversed",
                context={
                            'entry_number': original_entry.number,
                            'entry_status': original_entry.status,
                            'is_reversal': original_entry.is_reversal,
                            'already_reversed': bool(original_entry.reversed_entry),
                            'is_locked': original_entry.is_locked,
                            'period_status': original_entry.accounting_period.status
                        }
                    )
                
                # Enhanced period lock validation for reversals
                self._validate_reversal_period_controls(original_entry)
                
                # Generate idempotency key if not provided
                if idempotency_key is None:
                    idempotency_key = f"REV:{original_entry.source_module}:{original_entry.source_model}:{original_entry.source_id}:{original_entry.id}"
                
                # Check idempotency
                is_duplicate, existing_record, existing_data = self.idempotency_service.check_and_record_operation(
                    operation_type='reversal_entry',
                    idempotency_key=idempotency_key,
                    result_data={},  # Will be updated after creation
                    user=user,
                    expires_in_hours=24
                )
                
                if is_duplicate:
                    logger.info(f"Duplicate reversal entry creation detected: {idempotency_key}")
                    # Return existing reversal entry
                    entry_id = existing_data.get('reversal_entry_id')
                    if entry_id:
                        return JournalEntry.objects.get(id=entry_id)
                    else:
                        raise IdempotencyError(
                            operation_type='reversal_entry',
                            idempotency_key=idempotency_key,
                            context={'error': 'Existing record found but no reversal entry ID'}
                        )
                
                # Create reversal entry using the model method
                reversal_entry = original_entry.create_reversal_entry(
                    user=user,
                    reason=reason,
                    partial_amount=partial_amount
                )
                
                # Set idempotency key
                reversal_entry.idempotency_key = idempotency_key
                reversal_entry.save(update_fields=['idempotency_key'])
                
                # Enforce posting controls
                self._enforce_posting_controls(reversal_entry)
                
                # Update idempotency record with result
                existing_record.result_data = {
                    'reversal_entry_id': reversal_entry.id,
                    'reversal_entry_number': reversal_entry.number,
                    'original_entry_id': original_entry.id,
                    'original_entry_number': original_entry.number,
                    'reversal_amount': str(partial_amount or original_entry.total_amount),
                    'created_at': reversal_entry.created_at.isoformat()
                }
                existing_record.save()
                
                # Create audit trail
                self.audit_service.log_operation(
                    model_name='JournalEntry',
                    object_id=reversal_entry.id,
                    operation='CREATE_REVERSAL',
                    user=user,
                    source_service='AccountingGateway',
                    after_data={
                        'reversal_number': reversal_entry.number,
                        'original_number': original_entry.number,
                        'reversal_amount': str(partial_amount or original_entry.total_amount),
                        'reason': reason
                    },
                    idempotency_key=idempotency_key,
                    operation_duration=(timezone.now() - operation_start).total_seconds()
                )
                
                logger.info(
                    f"Reversal entry created successfully: {reversal_entry.number} "
                    f"for original entry {original_entry.number}"
                )
                
                return reversal_entry
                
        except Exception as e:
            logger.error(
                f"Failed to create reversal entry for {original_entry.number}: {str(e)}"
            )
            
            # Create audit trail for failure
            self.audit_service.log_operation(
                model_name='JournalEntry',
                object_id=0,  # No entry created
                operation='CREATE_REVERSAL_FAILED',
                user=user,
                source_service='AccountingGateway',
                additional_context={
                    'error': str(e),
                    'original_entry_id': original_entry.id,
                    'original_entry_number': original_entry.number,
                    'idempotency_key': idempotency_key
                }
            )
            
            raise
        
        finally:
            GovernanceContext.clear_context()
    
    def _generate_entry_number(self, entry_type: str, source_info: SourceInfo) -> str:
        """
        Generate unique journal entry number.
        
        Args:
            entry_type: Type of entry
            source_info: Source information
            
        Returns:
            str: Generated entry number
        """
        # Use source-specific prefix for better organization
        source_key = f"{source_info.module}.{source_info.model}"
        
        prefix_mapping = {
            'students.StudentFee': 'SF',
            'students.FeePayment': 'FP',
            'product.StockMovement': 'SM',
            'purchase.PurchasePayment': 'PP',
            'hr.Payroll': 'PR',
            'hr.PayrollPayment': 'HR',
            'transportation.TransportationFee': 'TF',
            'finance.ManualAdjustment': 'ADJ'
            # Note: 'sale.SalePayment' removed - Sale module has been replaced
        }
        
        prefix = prefix_mapping.get(source_key, 'JE')
        
        # Find next number for this prefix
        existing_entries = JournalEntry.objects.filter(
            number__startswith=f"{prefix}-"
        ).order_by('-id')
        
        max_number = 0
        for entry in existing_entries:
            try:
                parts = entry.number.split("-")
                if len(parts) >= 2:
                    current_number = int(parts[-1])
                    if current_number > max_number:
                        max_number = current_number
            except (ValueError, IndexError):
                continue
        
        new_number = max_number + 1
        return f"{prefix}-{new_number:04d}"
    
    def _generate_description(self, source_info: SourceInfo) -> str:
        """
        Generate default description for journal entry.
        
        Args:
            source_info: Source information
            
        Returns:
            str: Generated description
        """
        return f"Auto-generated entry for {source_info.module}.{source_info.model}#{source_info.object_id}"
    
    def _validate_complete_entry(self, journal_entry: JournalEntry) -> None:
        """
        Perform final validation on complete journal entry.
        
        Args:
            journal_entry: Complete journal entry to validate
            
        Raises:
            ValidationError: If final validation fails
        """
        try:
            # Use the model's built-in validation
            journal_entry.validate_entry()
            
            # Additional governance validation
            governance_result = journal_entry.validate_governance_rules()
            if not governance_result['is_valid']:
                raise GovValidationError(
                message="Governance validation failed",
                context=governance_result
                )
                
        except ValidationError as e:
            # Convert Django ValidationError to governance ValidationError
            raise GovValidationError(
                message=f"Entry validation failed: {str(e)}",
                context={'validation_errors': e.messages if hasattr(e, 'messages') else [str(e)]}
            )
    
    def validate_entry_balance(self, lines: List[JournalEntryLineData]) -> bool:
        """
        Validate that journal entry lines are balanced (debits = credits).
        
        Args:
            lines: List of journal entry lines to validate
            
        Returns:
            bool: True if balanced, False otherwise
        """
        total_debit = sum(line.debit for line in lines)
        total_credit = sum(line.credit for line in lines)
        return total_debit == total_credit
    
    def link_to_source(self, entry: JournalEntry, source_info: SourceInfo) -> None:
        """
        Link journal entry to its source record.
        
        Args:
            entry: Journal entry to link
            source_info: Source information
        """
        entry.source_module = source_info.module
        entry.source_model = source_info.model
        entry.source_id = source_info.object_id
        entry.save(update_fields=['source_module', 'source_model', 'source_id'])
    
    def get_entry_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about journal entries created through the gateway.
        
        Returns:
            Dict: Statistics including counts, amounts, and performance metrics
        """
        from django.db.models import Count, Sum, Avg
        
        stats = {}
        
        # Basic counts
        total_entries = JournalEntry.objects.filter(
            created_by_service='AccountingGateway'
        ).count()
        stats['total_entries'] = total_entries
        
        if total_entries == 0:
            return stats
        
        # Count by source model
        source_counts = JournalEntry.objects.filter(
            created_by_service='AccountingGateway'
        ).values('source_module', 'source_model').annotate(
            count=Count('id')
        ).order_by('-count')
        
        stats['by_source'] = {
            f"{item['source_module']}.{item['source_model']}": item['count']
            for item in source_counts
        }
        
        # Total amounts
        total_amount = JournalEntry.objects.filter(
            created_by_service='AccountingGateway'
        ).aggregate(
            total=Sum('lines__debit')
        )['total'] or Decimal('0')
        
        stats['total_amount'] = str(total_amount)
        
        # Recent activity (last 24 hours)
        recent_cutoff = timezone.now() - timedelta(hours=24)
        stats['recent_entries'] = JournalEntry.objects.filter(
            created_by_service='AccountingGateway',
            created_at__gte=recent_cutoff
        ).count()
        
        # High-priority workflow stats
        high_priority_count = JournalEntry.objects.filter(
            created_by_service='AccountingGateway'
        ).filter(
            source_module__in=['students', 'product'],
            source_model__in=['StudentFee', 'StockMovement', 'FeePayment']
        ).count()
        
        stats['high_priority_entries'] = high_priority_count
        stats['high_priority_ratio'] = high_priority_count / total_entries if total_entries > 0 else 0
        
        return stats
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get health status of the AccountingGateway.
        
        Returns:
            Dict: Health status with recommendations
        """
        stats = self.get_entry_statistics()
        
        health = {
            'status': 'healthy',
            'issues': [],
            'recommendations': [],
            'metrics': {
                'total_entries': stats.get('total_entries', 0),
                'recent_activity': stats.get('recent_entries', 0),
                'high_priority_ratio': stats.get('high_priority_ratio', 0)
            }
        }
        
        # Check for issues
        if stats.get('recent_entries', 0) == 0:
            health['issues'].append('No recent journal entry activity')
        
        if stats.get('high_priority_ratio', 0) < 0.5:
            health['issues'].append('Low ratio of high-priority entries')
            health['recommendations'].append('Verify high-priority workflows are using the gateway')
        
        # Check idempotency service health
        try:
            idempotency_health = self.idempotency_service.get_health_status()
            if idempotency_health and idempotency_health.get('status') != 'healthy':
                health['status'] = 'warning'
                health['issues'].append('Idempotency service issues detected')
                if 'recommendations' in idempotency_health:
                    health['recommendations'].extend(idempotency_health['recommendations'])
        except Exception as e:
            health['issues'].append(f'Could not check idempotency service health: {str(e)}')
        
        return health
        
    def lock_period_entries(self, period: AccountingPeriod, user: User) -> Dict[str, Any]:
        """
        Lock all posted entries in a closed accounting period.
        
        Args:
            period: Accounting period to lock entries for
            user: User performing the lock operation
            
        Returns:
            Dict: Summary of locked entries
        """
        if period.can_post_entries():
            raise GovValidationError(
                message="Cannot lock entries in open period",
                context={'period_name': period.name, 'period_status': period.status}
            )
        
        # Find all posted entries in the period that are not locked
        entries_to_lock = JournalEntry.objects.filter(
            accounting_period=period,
            status='posted',
            is_locked=False
        )
        
        locked_count = 0
        for entry in entries_to_lock:
            try:
                entry.lock_entry(user=user, reason=f"Period {period.name} closed")
                locked_count += 1
            except Exception as e:
                logger.error(f"Failed to lock entry {entry.number}: {str(e)}")
        
        summary = {
            'period_name': period.name,
            'total_entries': entries_to_lock.count(),
            'locked_entries': locked_count,
            'already_locked': JournalEntry.objects.filter(
                accounting_period=period,
                status='posted',
                is_locked=True
            ).count()
        }
        
        logger.info(f"Locked {locked_count} entries in period {period.name}")
        return summary
    
    def _enforce_strict_period_lock(self, journal_entry: JournalEntry) -> None:
        """
        Enforce strict period lock controls for high-priority workflows.
        
        Args:
            journal_entry: Journal entry to enforce strict controls on
            
        Raises:
            ValidationError: If strict period controls are violated
        """
        period = journal_entry.accounting_period
        
        # Validate period is still open at posting time
        if not period.can_post_entries():
            raise GovValidationError(
                message=f"Cannot post entries to closed period: {period.name}",
                context={
                    'period_name': period.name,
                    'period_status': period.status,
                    'period_closed_at': period.closed_at.isoformat() if period.closed_at else None,
                    'entry_number': journal_entry.number,
                    'source_workflow': f"{journal_entry.source_module}.{journal_entry.source_model}"
                }
            )
        
        # Additional validation for high-priority workflows
        source_key = f"{journal_entry.source_module}.{journal_entry.source_model}"
        
        # Check if period is approaching closure (within 24 hours)
        if period.closed_at and period.closed_at <= timezone.now() + timezone.timedelta(hours=24):
            logger.warning(
                f"Posting entry {journal_entry.number} to period {period.name} "
                f"which is scheduled to close soon: {period.closed_at}"
            )
        
        # Enforce additional controls for selected workflows
        if source_key == 'students.StudentFee':
            self._enforce_student_fee_period_controls(journal_entry, period)
        elif source_key == 'product.StockMovement':
            self._enforce_stock_movement_period_controls(journal_entry, period)
        elif source_key == 'students.FeePayment':
            self._enforce_fee_payment_period_controls(journal_entry, period)
    
    def _enforce_posted_entry_immutability(self, journal_entry: JournalEntry) -> None:
        """
        Enforce immutability of posted entries - only reversals allowed.
        
        Args:
            journal_entry: Posted journal entry to make immutable
        """
        # Set additional protection flags
        journal_entry._gateway_posted = True
        journal_entry._immutable_posted = True
        
        # Create audit trail for immutability enforcement
        self.audit_service.log_operation(
            model_name='JournalEntry',
            object_id=journal_entry.id,
            operation='ENFORCE_IMMUTABILITY',
            user=journal_entry.posted_by,
            source_service='AccountingGateway',
            additional_context={
                'entry_number': journal_entry.number,
                'period_name': journal_entry.accounting_period.name,
                'source_workflow': f"{journal_entry.source_module}.{journal_entry.source_model}",
                'enforcement_reason': 'Posted entry immutability - reversals only'
            }
        )
        
        logger.info(f"Enforced immutability on posted entry {journal_entry.number}")
    
    def _enforce_student_fee_period_controls(self, journal_entry: JournalEntry, period: AccountingPeriod) -> None:
        """
        Enforce specific period controls for StudentFee workflow.
        
        Args:
            journal_entry: StudentFee journal entry
            period: Accounting period
        """
        # Sale entries must be posted within the same period as the sale date
        if hasattr(journal_entry, 'source_id') and journal_entry.source_id:
            try:
                # Import here to avoid circular imports
                from sale.models import Sale
                sale = Sale.objects.get(id=journal_entry.source_id)
                
                # Validate sale date is within the posting period
                if not period.is_date_in_period(sale.created_at.date()):
                    logger.warning(
                        f"Sale {sale.id} created outside posting period {period.name}"
                    )
            except Exception as e:
                logger.warning(f"Could not validate Sale period controls: {str(e)}")
    
    def _enforce_stock_movement_period_controls(self, journal_entry: JournalEntry, period: AccountingPeriod) -> None:
        """
        Enforce specific period controls for StockMovement workflow.
        
        Args:
            journal_entry: StockMovement journal entry
            period: Accounting period
        """
        # StockMovement entries have stricter period controls due to inventory valuation
        if hasattr(journal_entry, 'source_id') and journal_entry.source_id:
            try:
                # Import here to avoid circular imports
                from product.models import StockMovement
                stock_movement = StockMovement.objects.get(id=journal_entry.source_id)
                
                # Validate movement date is within the posting period
                if not period.is_date_in_period(stock_movement.movement_date):
                    raise GovValidationError(
                        message="Stock movement date must be within the posting period",
                        context={
                            'movement_date': stock_movement.movement_date.isoformat(),
                            'period_start': period.start_date.isoformat(),
                            'period_end': period.end_date.isoformat(),
                            'stock_movement_id': stock_movement.id
                        }
                    )
            except Exception as e:
                logger.warning(f"Could not validate StockMovement period controls: {str(e)}")
    
    def _enforce_fee_payment_period_controls(self, journal_entry: JournalEntry, period: AccountingPeriod) -> None:
        """
        Enforce specific period controls for FeePayment workflow.
        
        Args:
            journal_entry: Payment journal entry
            period: Accounting period
        """
        # Payment entries must be posted in the period when payment was received
        if hasattr(journal_entry, 'source_id') and journal_entry.source_id:
            try:
                # Import here to avoid circular imports
                from sale.models import SalePayment
                payment = SalePayment.objects.get(id=journal_entry.source_id)
                
                # Validate payment date is within the posting period
                if not period.is_date_in_period(payment.payment_date):
                    logger.warning(
                        f"Payment {payment.id} payment date outside posting period {period.name}"
                    )
                    
                # Additional validation for payment timing
                # Check if payment was posted significantly after payment date
                days_diff = (journal_entry.date - payment.payment_date).days
                if days_diff > 1:
                    logger.warning(
                        f"Payment {fee_payment.id} posted {days_diff} days after payment date"
                    )
            except Exception as e:
                logger.warning(f"Could not validate FeePayment period controls: {str(e)}")
    
    def validate_period_lock_compliance(self, period: AccountingPeriod) -> Dict[str, Any]:
        """
        Validate period lock compliance for all entries in a period.
        
        Args:
            period: Accounting period to validate
            
        Returns:
            Dict: Compliance report
        """
        report = {
            'period_name': period.name,
            'period_status': period.status,
            'total_entries': 0,
            'locked_entries': 0,
            'unlocked_posted_entries': 0,
            'compliance_issues': [],
            'high_priority_entries': 0,
            'high_priority_locked': 0
        }
        
        # Get all entries in the period
        entries = JournalEntry.objects.filter(accounting_period=period)
        report['total_entries'] = entries.count()
        
        for entry in entries:
            source_key = f"{entry.source_module}.{entry.source_model}"
            is_high_priority = source_key in self.HIGH_PRIORITY_WORKFLOWS
            
            if is_high_priority:
                report['high_priority_entries'] += 1
            
            if entry.is_locked:
                report['locked_entries'] += 1
                if is_high_priority:
                    report['high_priority_locked'] += 1
            elif entry.status == 'posted':
                report['unlocked_posted_entries'] += 1
                report['compliance_issues'].append({
                    'entry_number': entry.number,
                    'issue': 'Posted entry not locked',
                    'source_workflow': source_key,
                    'is_high_priority': is_high_priority
                })
        
        # Calculate compliance ratios
        if report['total_entries'] > 0:
            report['lock_compliance_ratio'] = report['locked_entries'] / report['total_entries']
        else:
            report['lock_compliance_ratio'] = 1.0
            
        if report['high_priority_entries'] > 0:
            report['high_priority_compliance_ratio'] = report['high_priority_locked'] / report['high_priority_entries']
        else:
            report['high_priority_compliance_ratio'] = 1.0
        
        return report
    
    def _validate_reversal_period_controls(self, original_entry: JournalEntry) -> None:
        """
        Validate period controls for reversal entries.
        
        Args:
            original_entry: Original journal entry to be reversed
            
        Raises:
            ValidationError: If reversal period controls are violated
        """
        # Check if original entry is properly locked
        if not original_entry.is_locked:
            logger.warning(
                f"Reversing unlocked entry {original_entry.number} - "
                f"entry should have been locked when posted"
            )
        
        # Validate original entry period
        original_period = original_entry.accounting_period
        if not original_period:
            raise GovValidationError(
                message="Original entry has no accounting period",
                context={'entry_number': original_entry.number}
            )
        
        # Check if original period is closed (reversals allowed in closed periods)
        if original_period.status == 'closed':
            logger.info(
                f"Creating reversal for entry {original_entry.number} "
                f"in closed period {original_period.name} - this is allowed"
            )
        
        # Enhanced validation for high-priority workflows
        source_key = f"{original_entry.source_module}.{original_entry.source_model}"
        if source_key in self.HIGH_PRIORITY_WORKFLOWS:
            self._validate_high_priority_reversal(original_entry, source_key)
    
    def _validate_high_priority_reversal(self, original_entry: JournalEntry, source_key: str) -> None:
        """
        Enhanced validation for high-priority workflow reversals.
        
        Args:
            original_entry: Original journal entry
            source_key: Source workflow key
        """
        # Additional validation based on workflow type
        if source_key == 'students.StudentFee':
            # StudentFee reversals require special handling
            logger.info(f"Processing StudentFee reversal for entry {original_entry.number}")
            
        elif source_key == 'product.StockMovement':
            # StockMovement reversals affect inventory - extra validation
            logger.info(f"Processing StockMovement reversal for entry {original_entry.number}")
            # Could add inventory validation here
            
        elif source_key == 'students.FeePayment':
            # FeePayment reversals affect cash/bank accounts
            logger.info(f"Processing FeePayment reversal for entry {original_entry.number}")
            # Could add cash flow validation here
        
        # Ensure original entry was created through AccountingGateway
        if original_entry.created_by_service != 'AccountingGateway':
            logger.warning(
                f"Reversing entry {original_entry.number} that was not created through AccountingGateway: "
                f"created by {original_entry.created_by_service}"
            )
    
    def enforce_period_locks_for_workflow(self, source_module: str, source_model: str, user: User) -> Dict[str, Any]:
        """
        Enforce period locks for all posted entries of a specific workflow.
        
        Args:
            source_module: Source module name
            source_model: Source model name
            user: User performing the enforcement
            
        Returns:
            Dict: Summary of enforcement actions
        """
        source_key = f"{source_module}.{source_model}"
        
        # Find all posted entries for this workflow that are not locked
        unlocked_entries = JournalEntry.objects.filter(
            source_module=source_module,
            source_model=source_model,
            status='posted',
            is_locked=False,
            created_by_service='AccountingGateway'
        )
        
        summary = {
            'workflow': source_key,
            'total_unlocked': unlocked_entries.count(),
            'locked_count': 0,
            'failed_count': 0,
            'errors': []
        }
        
        for entry in unlocked_entries:
            try:
                entry.lock_entry(
                    user=user,
                    reason=f"Period lock enforcement for {source_key} workflow"
                )
                summary['locked_count'] += 1
                
                # Create audit trail for enforcement
                self.audit_service.log_operation(
                    model_name='JournalEntry',
                    object_id=entry.id,
                    operation='ENFORCE_PERIOD_LOCK',
                    user=user,
                    source_service='AccountingGateway',
                    additional_context={
                        'entry_number': entry.number,
                        'workflow': source_key,
                        'enforcement_reason': 'Retroactive period lock enforcement'
                    }
                )
                
            except Exception as e:
                summary['failed_count'] += 1
                summary['errors'].append({
                    'entry_number': entry.number,
                    'error': str(e)
                })
                logger.error(f"Failed to lock entry {entry.number}: {str(e)}")
        
        logger.info(
            f"Period lock enforcement for {source_key}: "
            f"locked {summary['locked_count']}/{summary['total_unlocked']} entries"
        )
        
        return summary
    
    def get_period_lock_status(self) -> Dict[str, Any]:
        """
        Get comprehensive period lock status for all workflows.
        
        Returns:
            Dict: Period lock status report
        """
        status = {
            'timestamp': timezone.now().isoformat(),
            'workflows': {},
            'summary': {
                'total_posted_entries': 0,
                'total_locked_entries': 0,
                'total_unlocked_posted': 0,
                'compliance_ratio': 0.0
            }
        }
        
        # Check each high-priority workflow
        for source_key in self.HIGH_PRIORITY_WORKFLOWS:
            module, model = source_key.split('.')
            
            posted_entries = JournalEntry.objects.filter(
                source_module=module,
                source_model=model,
                status='posted',
                created_by_service='AccountingGateway'
            )
            
            locked_entries = posted_entries.filter(is_locked=True)
            unlocked_entries = posted_entries.filter(is_locked=False)
            
            workflow_status = {
                'total_posted': posted_entries.count(),
                'locked': locked_entries.count(),
                'unlocked': unlocked_entries.count(),
                'compliance_ratio': locked_entries.count() / posted_entries.count() if posted_entries.count() > 0 else 1.0
            }
            
            status['workflows'][source_key] = workflow_status
            
            # Update summary
            status['summary']['total_posted_entries'] += workflow_status['total_posted']
            status['summary']['total_locked_entries'] += workflow_status['locked']
            status['summary']['total_unlocked_posted'] += workflow_status['unlocked']
        
        # Calculate overall compliance ratio
        if status['summary']['total_posted_entries'] > 0:
            status['summary']['compliance_ratio'] = (
                status['summary']['total_locked_entries'] / 
                status['summary']['total_posted_entries']
            )
        else:
            status['summary']['compliance_ratio'] = 1.0
        
        return status


# Convenience functions for common journal entry patterns

def create_student_fee_entry(
    student_fee,
    user: User,
    idempotency_key: Optional[str] = None
) -> JournalEntry:
    """
    Create journal entry for student fee using AccountingGateway.
    
    Args:
        student_fee: StudentFee instance
        user: User creating the entry
        idempotency_key: Optional idempotency key (auto-generated if not provided)
        
    Returns:
        JournalEntry: Created journal entry
    """
    gateway = AccountingGateway()
    
    if idempotency_key is None:
        idempotency_key = IdempotencyService.generate_journal_entry_key(
            'students', 'StudentFee', student_fee.id, 'create'
        )
    
    # Prepare journal entry lines for student fee
    lines = [
        JournalEntryLineData(
            account_code='10301',  # Parents Receivable
            debit=student_fee.total_amount,
            credit=Decimal('0'),
            description=f"Student fee - {student_fee.student.name}"
        ),
        JournalEntryLineData(
            account_code='41020',  # Tuition Revenue (or appropriate revenue account)
            debit=Decimal('0'),
            credit=student_fee.total_amount,
            description=f"Revenue - {student_fee.fee_type.name}"
        )
    ]
    
    return gateway.create_journal_entry(
        source_module='students',
        source_model='StudentFee',
        source_id=student_fee.id,
        lines=lines,
        idempotency_key=idempotency_key,
        user=user,
        description=f"Student fee entry for {student_fee.student.name}",
        reference=f"SF-{student_fee.id}"
    )


def create_student_fee_reversal(
    original_entry: JournalEntry,
    user: User,
    reason: str = "Student fee reversal",
    partial_amount: Optional[Decimal] = None,
    idempotency_key: Optional[str] = None
) -> JournalEntry:
    """
    Create reversal entry for student fee using AccountingGateway.
    This is the ONLY way to modify posted student fee entries.
    
    Args:
        original_entry: Original journal entry to reverse
        user: User creating the reversal
        reason: Reason for reversal
        partial_amount: Optional partial amount to reverse
        idempotency_key: Optional idempotency key
        
    Returns:
        JournalEntry: Created reversal entry
    """
    gateway = AccountingGateway()
    
    return gateway.create_reversal_entry(
        original_entry=original_entry,
        user=user,
        reason=reason,
        partial_amount=partial_amount,
        idempotency_key=idempotency_key
    )


def create_fee_payment_entry(
    fee_payment,
    user: User,
    idempotency_key: Optional[str] = None
) -> JournalEntry:
    """
    Create journal entry for fee payment using AccountingGateway.
    
    Args:
        fee_payment: FeePayment instance
        user: User creating the entry
        idempotency_key: Optional idempotency key (auto-generated if not provided)
        
    Returns:
        JournalEntry: Created journal entry
    """
    gateway = AccountingGateway()
    
    if idempotency_key is None:
        idempotency_key = IdempotencyService.generate_journal_entry_key(
            'students', 'FeePayment', fee_payment.id, 'create'
        )
    
    # النظام الجديد: payment_method هو account code مباشرة
    cash_account = fee_payment.payment_method
    
    # التحقق من أن الحساب موجود وصحيح
    try:
        from financial.models import ChartOfAccounts
        account = ChartOfAccounts.objects.filter(
            code=cash_account,
            is_active=True
        ).first()
        
        if not account:
            raise ValueError(f"الحساب المحاسبي {cash_account} غير موجود أو غير نشط")
            
    except Exception as e:
        logger.error(f"فشل في التحقق من الحساب {cash_account}: {str(e)}")
        raise
    
    # Prepare journal entry lines for fee payment
    lines = [
        JournalEntryLineData(
            account_code=cash_account,  # Cash or Bank account code
            debit=fee_payment.amount,
            credit=Decimal('0'),
            description=f"Payment received - {fee_payment.get_payment_method_display()}"
        ),
        JournalEntryLineData(
            account_code='10301',  # Parents Receivable
            debit=Decimal('0'),
            credit=fee_payment.amount,
            description=f"Payment from {fee_payment.student_fee.student.parent.name}"
        )
    ]
    
    return gateway.create_journal_entry(
        source_module='students',
        source_model='FeePayment',
        source_id=fee_payment.id,
        lines=lines,
        idempotency_key=idempotency_key,
        user=user,
        description=f"Fee payment from {fee_payment.student_fee.student.parent.name}",
        reference=fee_payment.reference_number or f"FP-{fee_payment.id}"
    )


def create_fee_payment_reversal(
    original_entry: JournalEntry,
    user: User,
    reason: str = "Fee payment reversal",
    partial_amount: Optional[Decimal] = None,
    idempotency_key: Optional[str] = None
) -> JournalEntry:
    """
    Create reversal entry for fee payment using AccountingGateway.
    This is the ONLY way to modify posted fee payment entries.
    
    Args:
        original_entry: Original journal entry to reverse
        user: User creating the reversal
        reason: Reason for reversal
        partial_amount: Optional partial amount to reverse
        idempotency_key: Optional idempotency key
        
    Returns:
        JournalEntry: Created reversal entry
    """
    gateway = AccountingGateway()
    
    return gateway.create_reversal_entry(
        original_entry=original_entry,
        user=user,
        reason=reason,
        partial_amount=partial_amount,
        idempotency_key=idempotency_key
    )


def create_stock_movement_entry(
    stock_movement,
    user: User,
    idempotency_key: Optional[str] = None
) -> JournalEntry:
    """
    Create journal entry for stock movement using AccountingGateway.
    
    Args:
        stock_movement: StockMovement instance
        user: User creating the entry
        idempotency_key: Optional idempotency key (auto-generated if not provided)
        
    Returns:
        JournalEntry: Created journal entry
    """
    gateway = AccountingGateway()
    
    if idempotency_key is None:
        idempotency_key = IdempotencyService.generate_journal_entry_key(
            'product', 'StockMovement', stock_movement.id, 'create'
        )
    
    # Calculate movement value
    movement_value = stock_movement.total_cost
    
    # Prepare journal entry lines based on movement type
    if stock_movement.movement_type == 'in':
        # Stock increase: Debit Inventory, Credit appropriate account
        lines = [
            JournalEntryLineData(
                account_code='10400',  # المخزون
                debit=movement_value,
                credit=Decimal('0'),
                description=f"Stock increase - {stock_movement.product.name}"
            ),
            JournalEntryLineData(
                account_code='2010001',  # مورد - مكتبة المعرفة التعليمية (leaf account)
                debit=Decimal('0'),
                credit=movement_value,
                description=f"Stock purchase - {stock_movement.document_number}"
            )
        ]
    elif stock_movement.movement_type in ['out', 'sale']:
        # Stock decrease: Credit Inventory, Debit Cost of Goods Sold
        lines = [
            JournalEntryLineData(
                account_code='50100',  # تكلفة الخدمات المقدمة
                debit=movement_value,
                credit=Decimal('0'),
                description=f"Cost of goods sold - {stock_movement.product.name}"
            ),
            JournalEntryLineData(
                account_code='10400',  # المخزون
                debit=Decimal('0'),
                credit=movement_value,
                description=f"Stock decrease - {stock_movement.product.name}"
            )
        ]
    elif stock_movement.movement_type == 'adjustment':
        # Stock adjustment: Debit/Credit Inventory based on quantity change
        if movement_value > 0:
            # Positive adjustment - increase inventory
            lines = [
                JournalEntryLineData(
                    account_code='10400',  # المخزون
                    debit=movement_value,
                    credit=Decimal('0'),
                    description=f"Stock adjustment increase - {stock_movement.product.name}"
                ),
                JournalEntryLineData(
                    account_code='50200',  # مصروفات أخرى
                    debit=Decimal('0'),
                    credit=movement_value,
                    description=f"Inventory adjustment - {stock_movement.notes or 'Stock count adjustment'}"
                )
            ]
        else:
            # Negative adjustment - decrease inventory
            lines = [
                JournalEntryLineData(
                    account_code='50200',  # مصروفات أخرى
                    debit=abs(movement_value),
                    credit=Decimal('0'),
                    description=f"Inventory adjustment loss - {stock_movement.notes or 'Stock count adjustment'}"
                ),
                JournalEntryLineData(
                    account_code='10400',  # المخزون
                    debit=Decimal('0'),
                    credit=abs(movement_value),
                    description=f"Stock adjustment decrease - {stock_movement.product.name}"
                )
            ]
    elif stock_movement.movement_type == 'transfer':
        # Stock transfer: No accounting impact (internal movement)
        # Create a memo entry with zero amounts for audit trail
        lines = [
            JournalEntryLineData(
                account_code='10400',  # المخزون
                debit=Decimal('0'),
                credit=Decimal('0'),
                description=f"Stock transfer memo - {stock_movement.product.name} (from {stock_movement.warehouse.name} to {stock_movement.destination_warehouse.name if stock_movement.destination_warehouse else 'unknown'})"
            )
        ]
    else:
        # Default handling for other movement types (return_in, return_out, etc.)
        if stock_movement.movement_type in ['return_in', 'purchase_return']:
            # Return inbound: Debit Inventory, Credit Returns/Adjustments
            lines = [
                JournalEntryLineData(
                    account_code='10400',  # المخزون
                    debit=movement_value,
                    credit=Decimal('0'),
                    description=f"Stock return inbound - {stock_movement.product.name}"
                ),
                JournalEntryLineData(
                    account_code='2010001',  # مورد - مكتبة المعرفة التعليمية
                    debit=Decimal('0'),
                    credit=movement_value,
                    description=f"Purchase return - {stock_movement.document_number}"
                )
            ]
        elif stock_movement.movement_type in ['return_out', 'sale_return']:
            # Return outbound: Credit Inventory, Debit Returns/Adjustments
            lines = [
                JournalEntryLineData(
                    account_code='41030',  # مردودات المبيعات
                    debit=movement_value,
                    credit=Decimal('0'),
                    description=f"Sales return - {stock_movement.product.name}"
                ),
                JournalEntryLineData(
                    account_code='10400',  # المخزون
                    debit=Decimal('0'),
                    credit=movement_value,
                    description=f"Stock return outbound - {stock_movement.product.name}"
                )
            ]
        else:
            # Fallback for unknown movement types
            lines = [
                JournalEntryLineData(
                    account_code='10400',  # المخزون
                    debit=movement_value if movement_value > 0 else Decimal('0'),
                    credit=abs(movement_value) if movement_value < 0 else Decimal('0'),
                    description=f"Stock movement ({stock_movement.movement_type}) - {stock_movement.product.name}"
                ),
                JournalEntryLineData(
                    account_code='50200',  # مصروفات أخرى
                    debit=abs(movement_value) if movement_value < 0 else Decimal('0'),
                    credit=movement_value if movement_value > 0 else Decimal('0'),
                    description=f"Stock movement adjustment - {stock_movement.movement_type}"
                )
            ]
    
    return gateway.create_journal_entry(
        source_module='product',
        source_model='StockMovement',
        source_id=stock_movement.id,
        lines=lines,
        idempotency_key=idempotency_key,
        user=user,
        description=f"Stock movement - {stock_movement.product.name}",
        reference=stock_movement.document_number or f"SM-{stock_movement.id}"
    )


def create_payroll_entry(
    payroll,
    user: User,
    idempotency_key: Optional[str] = None
) -> JournalEntry:
    """
    Create journal entry for payroll using AccountingGateway.
    
    Args:
        payroll: Payroll instance
        user: User creating the entry
        idempotency_key: Optional idempotency key (auto-generated if not provided)
        
    Returns:
        JournalEntry: Created journal entry
    """
    gateway = AccountingGateway()
    
    if idempotency_key is None:
        idempotency_key = IdempotencyService.generate_journal_entry_key(
            'hr', 'Payroll', payroll.id, 'create'
        )
    
    # Prepare comprehensive journal entry lines for payroll
    lines = []
    
    # Basic salary expense (debit)
    if payroll.basic_salary > 0:
        lines.append(JournalEntryLineData(
            account_code='5100',  # Salary Expense
            debit=payroll.basic_salary,
            credit=Decimal('0'),
            description=f"Basic salary - {payroll.employee.get_full_name_ar()}"
        ))
    
    # Allowances expense (debit)
    if payroll.allowances > 0:
        lines.append(JournalEntryLineData(
            account_code='5110',  # Allowances Expense
            debit=payroll.allowances,
            credit=Decimal('0'),
            description=f"Allowances - {payroll.employee.get_full_name_ar()}"
        ))
    
    # Overtime expense (debit)
    if payroll.overtime_amount > 0:
        lines.append(JournalEntryLineData(
            account_code='5120',  # Overtime Expense
            debit=payroll.overtime_amount,
            credit=Decimal('0'),
            description=f"Overtime - {payroll.employee.get_full_name_ar()}"
        ))
    
    # Bonus expense (debit)
    if payroll.bonus > 0:
        lines.append(JournalEntryLineData(
            account_code='5130',  # Bonus Expense
            debit=payroll.bonus,
            credit=Decimal('0'),
            description=f"Bonus - {payroll.employee.get_full_name_ar()}"
        ))
    
    # Social insurance payable (credit)
    if payroll.social_insurance > 0:
        lines.append(JournalEntryLineData(
            account_code='2200',  # Social Insurance Payable
            debit=Decimal('0'),
            credit=payroll.social_insurance,
            description=f"Social insurance - {payroll.employee.get_full_name_ar()}"
        ))
    
    # Tax payable (credit)
    if payroll.tax > 0:
        lines.append(JournalEntryLineData(
            account_code='2210',  # Tax Payable
            debit=Decimal('0'),
            credit=payroll.tax,
            description=f"Tax - {payroll.employee.get_full_name_ar()}"
        ))
    
    # Advance deduction coordination (credit to advance receivable)
    if payroll.advance_deduction > 0:
        lines.append(JournalEntryLineData(
            account_code='1300',  # Employee Advances Receivable
            debit=Decimal('0'),
            credit=payroll.advance_deduction,
            description=f"Advance deduction - {payroll.employee.get_full_name_ar()}"
        ))
    
    # Other deductions (credit to appropriate payable account)
    if payroll.other_deductions > 0:
        lines.append(JournalEntryLineData(
            account_code='2220',  # Other Payables
            debit=Decimal('0'),
            credit=payroll.other_deductions,
            description=f"Other deductions - {payroll.employee.get_full_name_ar()}"
        ))
    
    # Net salary payable (credit) - this is what the employee will receive
    if payroll.net_salary > 0:
        lines.append(JournalEntryLineData(
            account_code='2100',  # Salaries Payable
            debit=Decimal('0'),
            credit=payroll.net_salary,
            description=f"Net salary payable - {payroll.employee.get_full_name_ar()}"
        ))
    elif payroll.net_salary < 0:
        # Handle negative net salary (rare case where deductions exceed gross)
        lines.append(JournalEntryLineData(
            account_code='1300',  # Employee Advances Receivable (employee owes company)
            debit=abs(payroll.net_salary),
            credit=Decimal('0'),
            description=f"Employee owes company - {payroll.employee.get_full_name_ar()}"
        ))
    
    return gateway.create_journal_entry(
        source_module='hr',
        source_model='Payroll',
        source_id=payroll.id,
        lines=lines,
        idempotency_key=idempotency_key,
        user=user,
        description=f"Payroll entry for {payroll.employee.get_full_name_ar()} - {payroll.month.strftime('%Y-%m')}",
        reference=f"PAYROLL-{payroll.id}"
    )


def create_payroll_reversal(
    original_entry: JournalEntry,
    user: User,
    reason: str = "Payroll reversal",
    partial_amount: Optional[Decimal] = None,
    idempotency_key: Optional[str] = None
) -> JournalEntry:
    """
    Create reversal entry for payroll using AccountingGateway.
    This is the ONLY way to modify posted payroll entries.
    
    Args:
        original_entry: Original journal entry to reverse
        user: User creating the reversal
        reason: Reason for reversal
        partial_amount: Optional partial amount to reverse
        idempotency_key: Optional idempotency key
        
    Returns:
        JournalEntry: Created reversal entry
    """
    gateway = AccountingGateway()
    
    return gateway.create_reversal_entry(
        original_entry=original_entry,
        user=user,
        reason=reason,
        partial_amount=partial_amount,
        idempotency_key=idempotency_key
    )


def create_stock_movement_reversal(
    original_entry: JournalEntry,
    user: User,
    reason: str = "Stock movement reversal",
    partial_amount: Optional[Decimal] = None,
    idempotency_key: Optional[str] = None
) -> JournalEntry:
    """
    Create reversal entry for stock movement using AccountingGateway.
    This is the ONLY way to modify posted stock movement entries.
    
    Args:
        original_entry: Original journal entry to reverse
        user: User creating the reversal
        reason: Reason for reversal
        partial_amount: Optional partial amount to reverse
        idempotency_key: Optional idempotency key
        
    Returns:
        JournalEntry: Created reversal entry
    """
    gateway = AccountingGateway()
    
    return gateway.create_reversal_entry(
        original_entry=original_entry,
        user=user,
        reason=reason,
        partial_amount=partial_amount,
        idempotency_key=idempotency_key
    )