"""
AccountingGateway Usage Examples

This file demonstrates how to use the AccountingGateway service for creating
journal entries in a thread-safe manner with full validation.
"""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone

from governance.services import (
    AccountingGateway,
    JournalEntryLineData,
    IdempotencyService,
    create_student_fee_entry,
    create_fee_payment_entry,
    create_stock_movement_entry
)

User = get_user_model()


def example_basic_journal_entry():
    """
    Example: Create a basic journal entry using AccountingGateway
    """
    # Get user (in real usage, this would come from request.user)
    user = User.objects.first()
    
    # Initialize the gateway
    gateway = AccountingGateway()
    
    # Prepare journal entry lines
    lines = [
        JournalEntryLineData(
            account_code='10301',  # Parents Receivable
            debit=Decimal('1000.00'),
            credit=Decimal('0.00'),
            description='Student fee receivable'
        ),
        JournalEntryLineData(
            account_code='41020',  # Tuition Revenue
            debit=Decimal('0.00'),
            credit=Decimal('1000.00'),
            description='Tuition revenue earned'
        )
    ]
    
    # Generate idempotency key
    idempotency_key = IdempotencyService.generate_journal_entry_key(
        'students', 'StudentFee', 123, 'create'
    )
    
    # Create journal entry
    try:
        entry = gateway.create_journal_entry(
            source_module='students',
            source_model='StudentFee',
            source_id=123,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            description='Student fee entry for John Doe',
            reference='SF-123'
        )
        
        print(f"✓ Journal entry created: {entry.number}")
        print(f"  Total amount: {entry.total_amount}")
        print(f"  Status: {entry.status}")
        print(f"  Lines count: {entry.lines.count()}")
        
        return entry
        
    except Exception as e:
        print(f"❌ Failed to create journal entry: {e}")
        return None


def example_student_fee_entry():
    """
    Example: Create journal entry for student fee using convenience function
    """
    # Mock student fee object (in real usage, this would be a StudentFee instance)
    class MockStudentFee:
        id = 456
        total_amount = Decimal('750.00')
        student = type('Student', (), {
            'name': 'Jane Smith',
            'parent': type('Parent', (), {'name': 'Mr. Smith'})()
        })()
        fee_type = type('FeeType', (), {'name': 'Tuition Fee'})()
    
    student_fee = MockStudentFee()
    user = User.objects.first()
    
    try:
        # This would work with a real StudentFee instance
        # entry = create_student_fee_entry(student_fee, user)
        
        # For demonstration, we'll use the basic method
        gateway = AccountingGateway()
        lines = [
            JournalEntryLineData('10301', student_fee.total_amount, Decimal('0')),
            JournalEntryLineData('41020', Decimal('0'), student_fee.total_amount)
        ]
        
        entry = gateway.create_journal_entry(
            source_module='students',
            source_model='StudentFee',
            source_id=student_fee.id,
            lines=lines,
            idempotency_key=f'JE:students:StudentFee:{student_fee.id}:create',
            user=user,
            description=f'Student fee for {student_fee.student.name}'
        )
        
        print(f"✓ Student fee entry created: {entry.number}")
        return entry
        
    except Exception as e:
        print(f"❌ Failed to create student fee entry: {e}")
        return None


def example_fee_payment_entry():
    """
    Example: Create journal entry for fee payment
    """
    user = User.objects.first()
    gateway = AccountingGateway()
    
    # Payment details
    payment_amount = Decimal('500.00')
    # النظام الجديد: payment_method هو account code مباشرة
    payment_method = '10100'  # account code (e.g., 10100 for cash, 10200 for bank)
    
    lines = [
        JournalEntryLineData(
            account_code=payment_method,
            debit=payment_amount,
            credit=Decimal('0'),
            description=f'Payment received via account {payment_method}'
        ),
        JournalEntryLineData(
            account_code='10301',  # Parents Receivable
            debit=Decimal('0'),
            credit=payment_amount,
            description='Payment from parent'
        )
    ]
    
    try:
        entry = gateway.create_journal_entry(
            source_module='students',
            source_model='FeePayment',
            source_id=789,
            lines=lines,
            idempotency_key='JE:students:FeePayment:789:create',
            user=user,
            description='Fee payment received',
            reference='FP-789'
        )
        
        print(f"✓ Fee payment entry created: {entry.number}")
        return entry
        
    except Exception as e:
        print(f"❌ Failed to create fee payment entry: {e}")
        return None


def example_stock_movement_entry():
    """
    Example: Create journal entry for stock movement
    """
    user = User.objects.first()
    gateway = AccountingGateway()
    
    # Stock movement details
    movement_value = Decimal('300.00')
    movement_type = 'out'  # Stock decrease
    
    if movement_type == 'in':
        # Stock increase: Debit Inventory, Credit Accounts Payable
        lines = [
            JournalEntryLineData('13000', movement_value, Decimal('0'), 'Stock increase'),
            JournalEntryLineData('20100', Decimal('0'), movement_value, 'Purchase on credit')
        ]
    else:
        # Stock decrease: Debit Cost of Goods Sold, Credit Inventory
        lines = [
            JournalEntryLineData('51000', movement_value, Decimal('0'), 'Cost of goods sold'),
            JournalEntryLineData('13000', Decimal('0'), movement_value, 'Stock decrease')
        ]
    
    try:
        entry = gateway.create_journal_entry(
            source_module='product',
            source_model='StockMovement',
            source_id=101,
            lines=lines,
            idempotency_key='JE:product:StockMovement:101:create',
            user=user,
            description='Stock movement entry',
            reference='SM-101'
        )
        
        print(f"✓ Stock movement entry created: {entry.number}")
        return entry
        
    except Exception as e:
        print(f"❌ Failed to create stock movement entry: {e}")
        return None


def example_validation_and_error_handling():
    """
    Example: Demonstrate validation and error handling
    """
    user = User.objects.first()
    gateway = AccountingGateway()
    
    print("\n🧪 Testing validation and error handling...")
    
    # Test 1: Unbalanced entry
    try:
        unbalanced_lines = [
            JournalEntryLineData('10100', Decimal('100'), Decimal('0')),
            JournalEntryLineData('41020', Decimal('0'), Decimal('50'))  # Unbalanced!
        ]
        
        gateway.create_journal_entry(
            source_module='students',
            source_model='StudentFee',
            source_id=999,
            lines=unbalanced_lines,
            idempotency_key='test-unbalanced',
            user=user
        )
        
    except Exception as e:
        print(f"✓ Unbalanced entry correctly rejected: {e}")
    
    # Test 2: Invalid account
    try:
        invalid_account_lines = [
            JournalEntryLineData('99999', Decimal('100'), Decimal('0')),  # Invalid account
            JournalEntryLineData('41020', Decimal('0'), Decimal('100'))
        ]
        
        gateway.create_journal_entry(
            source_module='students',
            source_model='StudentFee',
            source_id=998,
            lines=invalid_account_lines,
            idempotency_key='test-invalid-account',
            user=user
        )
        
    except Exception as e:
        print(f"✓ Invalid account correctly rejected: {e}")
    
    # Test 3: Invalid source model
    try:
        valid_lines = [
            JournalEntryLineData('10100', Decimal('100'), Decimal('0')),
            JournalEntryLineData('41020', Decimal('0'), Decimal('100'))
        ]
        
        gateway.create_journal_entry(
            source_module='invalid',
            source_model='InvalidModel',
            source_id=997,
            lines=valid_lines,
            idempotency_key='test-invalid-source',
            user=user
        )
        
    except Exception as e:
        print(f"✓ Invalid source model correctly rejected: {e}")


def example_idempotency_protection():
    """
    Example: Demonstrate idempotency protection
    """
    user = User.objects.first()
    gateway = AccountingGateway()
    
    print("\n🔒 Testing idempotency protection...")
    
    lines = [
        JournalEntryLineData('10100', Decimal('200'), Decimal('0')),
        JournalEntryLineData('41020', Decimal('0'), Decimal('200'))
    ]
    
    idempotency_key = 'test-idempotency-123'
    
    # Create first entry
    entry1 = gateway.create_journal_entry(
        source_module='students',
        source_model='StudentFee',
        source_id=555,
        lines=lines,
        idempotency_key=idempotency_key,
        user=user,
        description='First attempt'
    )
    
    print(f"✓ First entry created: {entry1.number}")
    
    # Attempt to create duplicate entry
    entry2 = gateway.create_journal_entry(
        source_module='students',
        source_model='StudentFee',
        source_id=555,
        lines=lines,
        idempotency_key=idempotency_key,
        user=user,
        description='Duplicate attempt'
    )
    
    print(f"✓ Duplicate entry returned same result: {entry2.number}")
    print(f"✓ Same entry ID: {entry1.id == entry2.id}")


def example_gateway_statistics():
    """
    Example: Get gateway statistics and health status
    """
    gateway = AccountingGateway()
    
    print("\n📊 Gateway Statistics:")
    stats = gateway.get_entry_statistics()
    
    print(f"  Total entries: {stats.get('total_entries', 0)}")
    print(f"  Total amount: {stats.get('total_amount', '0.00')}")
    print(f"  Recent entries (24h): {stats.get('recent_entries', 0)}")
    print(f"  High-priority entries: {stats.get('high_priority_entries', 0)}")
    
    if stats.get('by_source'):
        print("  Entries by source:")
        for source, count in stats['by_source'].items():
            print(f"    {source}: {count}")
    
    print("\n🏥 Gateway Health Status:")
    health = gateway.get_health_status()
    
    print(f"  Status: {health.get('status', 'unknown')}")
    
    if health.get('issues'):
        print("  Issues:")
        for issue in health['issues']:
            print(f"    - {issue}")
    
    if health.get('recommendations'):
        print("  Recommendations:")
        for rec in health['recommendations']:
            print(f"    - {rec}")


if __name__ == '__main__':
    """
    Run examples (this would typically be called from Django shell or management command)
    """
    print("🚀 AccountingGateway Usage Examples\n")
    
    # Note: These examples require a properly configured Django environment
    # with database, users, and chart of accounts set up.
    
    print("To run these examples:")
    print("1. python manage.py shell")
    print("2. exec(open('governance/examples/accounting_gateway_usage.py').read())")
    print("\nOr import specific functions:")
    print("from governance.examples.accounting_gateway_usage import example_basic_journal_entry")
    print("example_basic_journal_entry()")