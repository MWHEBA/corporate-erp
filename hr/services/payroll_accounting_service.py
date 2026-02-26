"""
HR payroll accounting integration using AccountingGateway.
"""
from governance.services.accounting_gateway import (
    AccountingGateway,
    JournalEntryLineData
)
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class PayrollAccountingService:
    """
    Service for creating payroll journal entries via AccountingGateway.
    """
    
    def __init__(self):
        self.gateway = AccountingGateway()
    
    def create_payroll_journal_entry(self, payroll, created_by):
        """
        Create journal entry for payroll via AccountingGateway.
        
        Args:
            payroll: Payroll instance
            created_by: User creating the entry
            
        Returns:
            JournalEntry: Created journal entry
        """
        # Prepare journal lines
        lines = self._prepare_journal_lines(payroll)
        
        # Generate idempotency key
        idempotency_key = f'JE:hr:Payroll:{payroll.id}:create'
        
        # Get financial subcategory from payroll
        financial_subcategory = payroll.financial_subcategory if hasattr(payroll, 'financial_subcategory') else None
        
        # Create entry via gateway
        entry = self.gateway.create_journal_entry(
            source_module='hr',
            source_model='Payroll',
            source_id=payroll.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=created_by,
            description=self._generate_description(payroll),
            reference=f'PAY-{payroll.id}',
            financial_category=payroll.financial_category,
            financial_subcategory=financial_subcategory
        )
        
        # Link to payroll
        payroll.journal_entry = entry
        payroll.save(update_fields=['journal_entry'])
        
        logger.info(
            f"✅ Journal entry created: {entry.number} "
            f"for payroll {payroll.id}"
        )
        
        return entry
    
    def _prepare_journal_lines(self, payroll):
        """Prepare journal entry lines for payroll."""
        lines = []
        
        # Debit: Salary Expense (gross salary)
        lines.append(JournalEntryLineData(
            account_code='50200',  # Salary Expense
            debit=payroll.gross_salary,
            credit=Decimal('0'),
            description=f'راتب {payroll.employee.get_full_name_ar()}'
        ))
        
        # Credit: Payment Account (net salary)
        if payroll.payment_account:
            lines.append(JournalEntryLineData(
                account_code=payroll.payment_account.code,
                debit=Decimal('0'),
                credit=payroll.net_salary,
                description=f'صافي راتب {payroll.employee.get_full_name_ar()}'
            ))
        
        # Credit: Deductions (insurance, tax, etc.)
        if payroll.social_insurance > 0:
            lines.append(JournalEntryLineData(
                account_code='21030',  # Insurance Payable
                debit=Decimal('0'),
                credit=payroll.social_insurance,
                description='تأمينات اجتماعية'
            ))
        
        if payroll.tax > 0:
            lines.append(JournalEntryLineData(
                account_code='21040',  # Tax Payable
                debit=Decimal('0'),
                credit=payroll.tax,
                description='ضرائب'
            ))
        
        return lines
    
    def _generate_description(self, payroll):
        """Generate journal entry description."""
        return (
            f'راتب {payroll.employee.get_full_name_ar()} - '
            f'{payroll.month.strftime("%Y-%m")}'
        )
