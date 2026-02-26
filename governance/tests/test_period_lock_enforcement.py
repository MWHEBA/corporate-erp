"""
Tests for enhanced accounting period lock enforcement in AccountingGateway.
Validates that posted entries are immutable (reversals only) for selected workflows.
"""

import pytest
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError

from governance.services import AccountingGateway, JournalEntryLineData
from governance.exceptions import ValidationError as GovValidationError
from financial.models.journal_entry import JournalEntry, AccountingPeriod
from financial.models.chart_of_accounts import ChartOfAccounts

User = get_user_model()


class PeriodLockEnforcementTestCase(TestCase):
    """Test enhanced period lock enforcement for selected workflows"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create open accounting period
        self.open_period = AccountingPeriod.objects.create(
            name='Open Period 2024',
            start_date='2024-01-01',
            end_date='2024-12-31',
            status='open'
        )
        
        # Create closed accounting period
        self.closed_period = AccountingPeriod.objects.create(
            name='Closed Period 2023',
            start_date='2023-01-01',
            end_date='2023-12-31',
            status='closed',
            closed_at=timezone.now() - timezone.timedelta(days=30),
            closed_by=self.user
        )
        
        # Create test accounts
        self.cash_account = ChartOfAccounts.objects.create(
            code='10100',
            name='Cash',
            account_type='asset',
            is_active=True,
            is_leaf=True
        )
        
        self.receivable_account = ChartOfAccounts.objects.create(
            code='10301',
            name='Parents Receivable',
            account_type='asset',
            is_active=True,
            is_leaf=True
        )
        
        self.revenue_account = ChartOfAccounts.objects.create(
            code='41020',
            name='Tuition Revenue',
            account_type='revenue',
            is_active=True,
            is_leaf=True
        )
        
        self.gateway = AccountingGateway()
    
    def test_posted_entry_auto_locked(self):
        """Test that posted entries are automatically locked"""
        lines = [
            JournalEntryLineData(
                account_code='10301',
                debit=Decimal('1000.00'),
                credit=Decimal('0.00'),
                description='Student fee receivable'
            ),
            JournalEntryLineData(
                account_code='41020',
                debit=Decimal('0.00'),
                credit=Decimal('1000.00'),
                description='Tuition revenue'
            )
        ]
        
        # Create entry for high-priority workflow
        entry = self.gateway.create_journal_entry(
            source_module='students',
            source_model='StudentFee',
            source_id=123,
            lines=lines,
            idempotency_key='test-student-fee-123',
            user=self.user,
            description='Test student fee entry'
        )
        
        # Verify entry is posted and locked
        self.assertEqual(entry.status, 'posted')
        self.assertTrue(entry.is_locked)
        self.assertIsNotNone(entry.locked_at)
        self.assertEqual(entry.locked_by, self.user)
    
    def test_cannot_post_to_closed_period(self):
        """Test that entries cannot be posted to closed periods"""
        lines = [
            JournalEntryLineData(
                account_code='10301',
                debit=Decimal('1000.00'),
                credit=Decimal('0.00'),
                description='Student fee receivable'
            ),
            JournalEntryLineData(
                account_code='41020',
                debit=Decimal('0.00'),
                credit=Decimal('1000.00'),
                description='Tuition revenue'
            )
        ]
        
        # Try to create entry in closed period
        with self.assertRaises(GovValidationError) as context:
            self.gateway.create_journal_entry(
                source_module='students',
                source_model='StudentFee',
                source_id=124,
                lines=lines,
                idempotency_key='test-student-fee-124',
                user=self.user,
                description='Test student fee entry',
                date=self.closed_period.start_date,
                accounting_period=self.closed_period
            )
        
        self.assertIn('Cannot post entries to closed period', str(context.exception))
    
    def test_reversal_entry_creation(self):
        """Test that reversal entries can be created for posted entries"""
        lines = [
            JournalEntryLineData(
                account_code='10301',
                debit=Decimal('1000.00'),
                credit=Decimal('0.00'),
                description='Student fee receivable'
            ),
            JournalEntryLineData(
                account_code='41020',
                debit=Decimal('0.00'),
                credit=Decimal('1000.00'),
                description='Tuition revenue'
            )
        ]
        
        # Create original entry
        original_entry = self.gateway.create_journal_entry(
            source_module='students',
            source_model='StudentFee',
            source_id=125,
            lines=lines,
            idempotency_key='test-student-fee-125',
            user=self.user,
            description='Test student fee entry'
        )
        
        # Create reversal entry
        reversal_entry = self.gateway.create_reversal_entry(
            original_entry=original_entry,
            user=self.user,
            reason='Test reversal',
            idempotency_key='test-reversal-125'
        )
        
        # Verify reversal entry
        self.assertEqual(reversal_entry.status, 'posted')
        self.assertTrue(reversal_entry.is_locked)
        self.assertTrue(reversal_entry.is_reversal)
        self.assertEqual(reversal_entry.original_entry, original_entry)
        self.assertEqual(reversal_entry.total_amount, original_entry.total_amount)
    
    def test_period_lock_compliance_validation(self):
        """Test period lock compliance validation"""
        # Create entry
        lines = [
            JournalEntryLineData(
                account_code='10301',
                debit=Decimal('1000.00'),
                credit=Decimal('0.00'),
                description='Student fee receivable'
            ),
            JournalEntryLineData(
                account_code='41020',
                debit=Decimal('0.00'),
                credit=Decimal('1000.00'),
                description='Tuition revenue'
            )
        ]
        
        entry = self.gateway.create_journal_entry(
            source_module='students',
            source_model='StudentFee',
            source_id=126,
            lines=lines,
            idempotency_key='test-student-fee-126',
            user=self.user,
            description='Test student fee entry'
        )
        
        # Validate period lock compliance
        compliance_report = self.gateway.validate_period_lock_compliance(self.open_period)
        
        self.assertGreater(compliance_report['total_entries'], 0)
        self.assertGreater(compliance_report['locked_entries'], 0)
        self.assertEqual(compliance_report['unlocked_posted_entries'], 0)
        self.assertEqual(compliance_report['lock_compliance_ratio'], 1.0)
    
    def test_workflow_period_lock_enforcement(self):
        """Test period lock enforcement for specific workflows"""
        # Create entry
        lines = [
            JournalEntryLineData(
                account_code='10301',
                debit=Decimal('1000.00'),
                credit=Decimal('0.00'),
                description='Student fee receivable'
            ),
            JournalEntryLineData(
                account_code='41020',
                debit=Decimal('0.00'),
                credit=Decimal('1000.00'),
                description='Tuition revenue'
            )
        ]
        
        entry = self.gateway.create_journal_entry(
            source_module='students',
            source_model='StudentFee',
            source_id=127,
            lines=lines,
            idempotency_key='test-student-fee-127',
            user=self.user,
            description='Test student fee entry'
        )
        
        # Test workflow enforcement
        summary = self.gateway.enforce_period_locks_for_workflow(
            'students', 'StudentFee', self.user
        )
        
        self.assertEqual(summary['workflow'], 'students.StudentFee')
        self.assertEqual(summary['failed_count'], 0)
    
    def test_period_lock_status_report(self):
        """Test period lock status reporting"""
        # Create entries for different workflows
        lines = [
            JournalEntryLineData(
                account_code='10301',
                debit=Decimal('1000.00'),
                credit=Decimal('0.00'),
                description='Test entry'
            ),
            JournalEntryLineData(
                account_code='41020',
                debit=Decimal('0.00'),
                credit=Decimal('1000.00'),
                description='Test entry'
            )
        ]
        
        # StudentFee entry
        self.gateway.create_journal_entry(
            source_module='students',
            source_model='StudentFee',
            source_id=128,
            lines=lines,
            idempotency_key='test-student-fee-128',
            user=self.user,
            description='Test student fee entry'
        )
        
        # FeePayment entry
        self.gateway.create_journal_entry(
            source_module='students',
            source_model='FeePayment',
            source_id=129,
            lines=lines,
            idempotency_key='test-fee-payment-129',
            user=self.user,
            description='Test fee payment entry'
        )
        
        # Get status report
        status = self.gateway.get_period_lock_status()
        
        self.assertIn('workflows', status)
        self.assertIn('summary', status)
        self.assertGreater(status['summary']['total_posted_entries'], 0)
        self.assertEqual(status['summary']['compliance_ratio'], 1.0)
        
        # Check specific workflows
        self.assertIn('students.StudentFee', status['workflows'])
        self.assertIn('students.FeePayment', status['workflows'])
    
    def test_high_priority_workflow_validation(self):
        """Test enhanced validation for high-priority workflows"""
        lines = [
            JournalEntryLineData(
                account_code='10301',
                debit=Decimal('1000.00'),
                credit=Decimal('0.00'),
                description='Stock movement'
            ),
            JournalEntryLineData(
                account_code='41020',
                debit=Decimal('0.00'),
                credit=Decimal('1000.00'),
                description='Stock movement'
            )
        ]
        
        # Create StockMovement entry (high-priority workflow)
        entry = self.gateway.create_journal_entry(
            source_module='product',
            source_model='StockMovement',
            source_id=130,
            lines=lines,
            idempotency_key='test-stock-movement-130',
            user=self.user,
            description='Test stock movement entry'
        )
        
        # Verify high-priority workflow handling
        self.assertEqual(entry.status, 'posted')
        self.assertTrue(entry.is_locked)
        self.assertEqual(entry.created_by_service, 'AccountingGateway')
        
        # Verify source linkage
        self.assertEqual(entry.source_module, 'product')
        self.assertEqual(entry.source_model, 'StockMovement')
        self.assertEqual(entry.source_id, 130)