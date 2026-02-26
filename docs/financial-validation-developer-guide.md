# Financial Transaction Validation System - Developer Guide

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Core Components](#core-components)
4. [Quick Start](#quick-start)
5. [Using the Decorator](#using-the-decorator)
6. [Using the Validation Service](#using-the-validation-service)
7. [Error Handling](#error-handling)
8. [Integrating with New Modules](#integrating-with-new-modules)
9. [Testing](#testing)
10. [Best Practices](#best-practices)
11. [Troubleshooting](#troubleshooting)

---

## Overview

The Financial Transaction Validation System is a comprehensive protection layer that ensures no financial transaction occurs in the system without meeting basic accounting requirements. It validates:

1. **Chart of Accounts**: Ensures entities have valid, active, and leaf accounting accounts
2. **Accounting Period**: Ensures transactions occur within open accounting periods

### Key Features

- **Unified Validation**: Single validation mechanism across all modules
- **Automatic Logging**: All failed validation attempts are logged for audit
- **Arabic Error Messages**: Clear, descriptive error messages in Arabic
- **Special Cases Support**: Handles opening entries and adjustments
- **Decorator Pattern**: Easy-to-apply validation using Python decorators
- **Service Layer**: Direct service access for custom validation logic

### Supported Modules

- `financial`: Direct financial transactions and journal entries
- `students`: Student fees and parent payments
- `activities`: Activity fees and events
- `transportation`: Transportation fees and bus payments
- `product`: Product and inventory transactions
- `sale`: Sales transactions
- `purchase`: Purchase transactions
- `supplier`: Supplier payments
- `hr`: Employee salaries and payments

---

## Architecture

### System Design

The system follows the **Decorator Pattern** and **Service Layer Pattern** to provide transparent and extensible validation.

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                         │
│  (Views, Services, Signals handling financial transactions) │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Validation Layer (Decorator/Service)            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  @require_financial_validation                       │  │
│  │  - Check Chart of Accounts                           │  │
│  │  - Check Accounting Period                           │  │
│  │  - Log validation attempts                           │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Data Layer                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ChartOfAccounts│  │AccountingPeriod│  │ValidationAuditLog│  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```


### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                  Validation Components                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  FinancialValidationService                        │    │
│  │  - validate_chart_of_accounts()                    │    │
│  │  - validate_accounting_period()                    │    │
│  │  - validate_transaction()                          │    │
│  └────────────────────────────────────────────────────┘    │
│                          │                                   │
│                          ├──────────────────┐               │
│                          │                  │               │
│  ┌──────────────────────▼──┐  ┌───────────▼──────────┐    │
│  │  EntityAccountMapper    │  │  ErrorMessageGenerator│    │
│  │  - get_account()        │  │  - chart_of_accounts_ │    │
│  │  - detect_entity_type() │  │    missing()          │    │
│  └─────────────────────────┘  │  - accounting_period_ │    │
│                                │    closed()           │    │
│                                └───────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Decorators                                        │    │
│  │  - @require_financial_validation                   │    │
│  │  - @require_chart_of_accounts_only                 │    │
│  │  - @require_accounting_period_only                 │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Custom Exceptions                                 │    │
│  │  - FinancialValidationError                        │    │
│  │  - ChartOfAccountsValidationError                  │    │
│  │  - AccountingPeriodValidationError                 │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. FinancialValidationService

**Location**: `financial/services/validation_service.py`

The central validation service that provides all validation operations.

**Key Methods**:

- `validate_chart_of_accounts(entity, entity_type, raise_exception)`: Validates chart of accounts
- `validate_accounting_period(transaction_date, entity, entity_type, raise_exception)`: Validates accounting period
- `validate_transaction(entity, transaction_date, ...)`: Comprehensive validation

### 2. EntityAccountMapper

**Location**: `financial/services/entity_mapper.py`

Maps entities to their accounting accounts and auto-detects entity types.

**Key Methods**:

- `get_account(entity, entity_type)`: Gets the accounting account for an entity
- `detect_entity_type(entity)`: Auto-detects entity type from model
- `get_entity_info(entity, entity_type)`: Gets comprehensive entity information

### 3. ErrorMessageGenerator

**Location**: `financial/services/error_messages.py`

Generates clear, descriptive error messages in Arabic.

**Key Methods**:

- `chart_of_accounts_missing(entity_name, entity_type)`: Missing account message
- `chart_of_accounts_inactive(account_code, account_name, ...)`: Inactive account message
- `accounting_period_closed(period_name, ...)`: Closed period message
- `generate_comprehensive_message(errors, ...)`: Comprehensive error message

### 4. Decorators

**Location**: `financial/decorators.py`

Python decorators for automatic validation.

**Available Decorators**:

- `@require_financial_validation`: Full validation (account + period)
- `@require_chart_of_accounts_only`: Account validation only
- `@require_accounting_period_only`: Period validation only

### 5. Custom Exceptions

**Location**: `financial/exceptions.py`

Specialized exceptions for validation errors.

**Exception Hierarchy**:

```
ValidationError (Django)
    └── FinancialValidationError
            ├── ChartOfAccountsValidationError
            └── AccountingPeriodValidationError
```

### 6. ValidationAuditLog Model

**Location**: `financial/models/validation_audit_log.py`

Logs all failed validation attempts for audit and analysis.

**Key Fields**:

- `user`: User who attempted the transaction
- `entity_type`, `entity_id`, `entity_name`: Entity information
- `validation_type`: Type of validation that failed
- `failure_reason`: Reason for failure
- `error_message`: Full error message
- `module`: Module where validation occurred

---

## Quick Start

### Step 1: Import Required Components

```python
from financial.decorators import require_financial_validation
from financial.services.validation_service import FinancialValidationService
from financial.exceptions import FinancialValidationError
```

### Step 2: Apply Validation to a Function

```python
from datetime import date
from financial.decorators import require_financial_validation

@require_financial_validation(
    entity_param='student',
    date_param='payment_date',
    module='students'
)
def process_student_payment(student, amount, payment_date):
    """Process a student payment with automatic validation"""
    # Your payment processing logic here
    payment = FeePayment.objects.create(
        student=student,
        amount=amount,
        payment_date=payment_date
    )
    return payment
```

### Step 3: Handle Validation Errors

```python
from django.contrib import messages
from financial.exceptions import FinancialValidationError

def payment_view(request, student_id):
    try:
        student = Student.objects.get(id=student_id)
        payment_date = request.POST.get('payment_date')
        amount = request.POST.get('amount')
        
        # This will automatically validate before processing
        payment = process_student_payment(
            student=student,
            amount=amount,
            payment_date=payment_date
        )
        
        messages.success(request, 'تم معالجة الدفعة بنجاح')
        return redirect('payment_success')
        
    except FinancialValidationError as e:
        # Display the Arabic error message to the user
        messages.error(request, str(e))
        return redirect('payment_form', student_id=student_id)
```


---

## Using the Decorator

### Basic Usage

The `@require_financial_validation` decorator is the easiest way to add validation to your functions.

#### Example 1: Simple Function

```python
from datetime import date
from financial.decorators import require_financial_validation

@require_financial_validation(
    entity_param='student',
    date_param='payment_date',
    module='students'
)
def create_student_payment(student, amount, payment_date):
    """Create a student payment with validation"""
    payment = FeePayment.objects.create(
        student=student,
        amount=amount,
        payment_date=payment_date
    )
    return payment

# Usage
student = Student.objects.get(id=1)
payment = create_student_payment(
    student=student,
    amount=1000,
    payment_date=date(2024, 6, 15)
)
```

#### Example 2: Class-Based View

```python
from django.views import View
from django.contrib import messages
from financial.decorators import require_financial_validation
from financial.exceptions import FinancialValidationError

class StudentPaymentView(View):
    @require_financial_validation(
        entity_param='student',
        date_param='payment_date',
        module='students'
    )
    def post(self, request, student_id):
        """Process student payment with validation"""
        student = Student.objects.get(id=student_id)
        payment_date = request.POST.get('payment_date')
        amount = request.POST.get('amount')
        
        # Validation happens automatically before this code runs
        payment = FeePayment.objects.create(
            student=student,
            amount=amount,
            payment_date=payment_date
        )
        
        messages.success(request, 'تم معالجة الدفعة بنجاح')
        return redirect('payment_success')
```

#### Example 3: With Transaction Type

```python
@require_financial_validation(
    entity_param='supplier',
    date_param='payment_date',
    transaction_type='payment',
    amount_param='amount',
    module='supplier'
)
def process_supplier_payment(supplier, amount, payment_date, description):
    """Process supplier payment with validation"""
    payment = SupplierPayment.objects.create(
        supplier=supplier,
        amount=amount,
        payment_date=payment_date,
        description=description
    )
    return payment
```

#### Example 4: Dynamic Transaction Type

```python
@require_financial_validation(
    entity_param='entity',
    date_param='transaction_date',
    transaction_type_param='trans_type',  # Read from parameter
    module='financial'
)
def create_financial_transaction(entity, transaction_date, trans_type, amount):
    """Create a financial transaction with dynamic type"""
    # trans_type could be 'payment', 'opening', 'adjustment', etc.
    transaction = FinancialTransaction.objects.create(
        entity=entity,
        transaction_date=transaction_date,
        transaction_type=trans_type,
        amount=amount
    )
    return transaction
```

### Decorator Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `entity_param` | str | `'entity'` | Name of the parameter containing the financial entity |
| `entity_type_param` | str | `None` | Name of the parameter containing entity type (auto-detected if None) |
| `date_param` | str | `'date'` | Name of the parameter containing transaction date |
| `transaction_type_param` | str | `None` | Name of the parameter containing transaction type |
| `transaction_type` | str | `None` | Fixed transaction type (used if transaction_type_param is None) |
| `amount_param` | str | `None` | Name of the parameter containing transaction amount |
| `allow_bypass` | bool | `False` | Allow validation bypass for special cases |
| `module` | str | `'financial'` | Module name for logging |

### Special Decorators

#### Chart of Accounts Only

Use when you only need to validate the accounting account (e.g., for reports):

```python
from financial.decorators import require_chart_of_accounts_only

@require_chart_of_accounts_only(
    entity_param='student',
    module='students'
)
def generate_student_account_report(student):
    """Generate report - only needs valid account"""
    account = student.parent.financial_account
    # Generate report logic
    return report
```

#### Accounting Period Only

Use when you only need to validate the accounting period (e.g., for general journal entries):

```python
from financial.decorators import require_accounting_period_only

@require_accounting_period_only(
    date_param='entry_date',
    module='financial'
)
def create_general_journal_entry(entry_date, description, amount):
    """Create general journal entry - only needs open period"""
    entry = JournalEntry.objects.create(
        entry_date=entry_date,
        description=description,
        amount=amount
    )
    return entry
```

### Accessing Validation Results

The decorator adds validation results to kwargs as `_validation_result`:

```python
@require_financial_validation(
    entity_param='student',
    date_param='payment_date',
    module='students'
)
def process_payment_with_details(student, amount, payment_date, **kwargs):
    """Process payment and access validation details"""
    
    # Access validation result
    validation_result = kwargs.get('_validation_result')
    
    if validation_result:
        account = validation_result['account']
        period = validation_result['period']
        warnings = validation_result['warnings']
        
        # Use the information
        print(f"Using account: {account.code} - {account.name}")
        print(f"In period: {period.name}")
        
        if warnings:
            for warning in warnings:
                print(f"Warning: {warning}")
    
    # Process payment
    payment = FeePayment.objects.create(
        student=student,
        amount=amount,
        payment_date=payment_date
    )
    return payment
```


---

## Using the Validation Service

For more control or custom validation logic, use the `FinancialValidationService` directly.

### Basic Service Usage

#### Example 1: Validate Before Processing

```python
from datetime import date
from financial.services.validation_service import FinancialValidationService
from financial.exceptions import FinancialValidationError

def process_payment_manually(student, amount, payment_date):
    """Process payment with manual validation"""
    
    # Perform validation
    validation_result = FinancialValidationService.validate_transaction(
        entity=student,
        transaction_date=payment_date,
        module='students',
        raise_exception=False  # Don't raise exception, check result instead
    )
    
    # Check if valid
    if not validation_result['is_valid']:
        # Handle errors
        for error in validation_result['errors']:
            print(f"Error: {error}")
        return None
    
    # Check warnings
    if validation_result['warnings']:
        for warning in validation_result['warnings']:
            print(f"Warning: {warning}")
    
    # Process payment
    payment = FeePayment.objects.create(
        student=student,
        amount=amount,
        payment_date=payment_date
    )
    
    return payment
```

#### Example 2: Validate with Exception

```python
from financial.services.validation_service import FinancialValidationService
from financial.exceptions import FinancialValidationError

def process_payment_with_exception(student, amount, payment_date):
    """Process payment with exception on validation failure"""
    
    try:
        # Validate and raise exception on failure
        validation_result = FinancialValidationService.validate_transaction(
            entity=student,
            transaction_date=payment_date,
            module='students',
            raise_exception=True  # Raise exception on failure
        )
        
        # If we reach here, validation passed
        payment = FeePayment.objects.create(
            student=student,
            amount=amount,
            payment_date=payment_date
        )
        
        return payment
        
    except FinancialValidationError as e:
        # Handle validation error
        print(f"Validation failed: {str(e)}")
        raise
```

### Validate Chart of Accounts Only

```python
from financial.services.validation_service import FinancialValidationService

def check_student_account(student):
    """Check if student has valid accounting account"""
    
    is_valid, error_msg, account = FinancialValidationService.validate_chart_of_accounts(
        entity=student,
        entity_type='student',
        raise_exception=False
    )
    
    if not is_valid:
        print(f"Account validation failed: {error_msg}")
        return None
    
    print(f"Valid account: {account.code} - {account.name}")
    return account
```

### Validate Accounting Period Only

```python
from datetime import date
from financial.services.validation_service import FinancialValidationService

def check_period_for_date(transaction_date):
    """Check if there's an open accounting period for a date"""
    
    is_valid, error_msg, period = FinancialValidationService.validate_accounting_period(
        transaction_date=transaction_date,
        raise_exception=False
    )
    
    if not is_valid:
        print(f"Period validation failed: {error_msg}")
        return None
    
    print(f"Valid period: {period.name} ({period.start_date} to {period.end_date})")
    return period
```

### Comprehensive Validation with All Options

```python
from datetime import date
from financial.services.validation_service import FinancialValidationService

def comprehensive_validation_example(request, student, payment_date, amount):
    """Example showing all validation options"""
    
    validation_result = FinancialValidationService.validate_transaction(
        entity=student,
        transaction_date=payment_date,
        entity_type='student',  # Optional: auto-detected if not provided
        transaction_type='payment',  # Optional: for special handling
        transaction_amount=amount,  # Optional: for logging
        user=request.user,  # Optional: for audit logging
        module='students',  # Module name for logging
        view_name='process_payment',  # Optional: view name for logging
        request=request,  # Optional: for request path logging
        raise_exception=False,  # Don't raise exception
        log_failures=True  # Log failures to ValidationAuditLog
    )
    
    # Check validation result
    if not validation_result['is_valid']:
        print("Validation failed!")
        print(f"Errors: {validation_result['errors']}")
        return None
    
    # Check warnings (validation passed but with notes)
    if validation_result['warnings']:
        print(f"Warnings: {validation_result['warnings']}")
    
    # Access validated data
    account = validation_result['account']
    period = validation_result['period']
    
    print(f"Account: {account.code} - {account.name}")
    print(f"Period: {period.name}")
    
    # Check validation details
    details = validation_result['validation_details']
    print(f"Chart of accounts valid: {details['chart_of_accounts_valid']}")
    print(f"Accounting period valid: {details['accounting_period_valid']}")
    print(f"Special transaction: {details['special_transaction']}")
    print(f"Bypass applied: {details['bypass_applied']}")
    
    return validation_result
```

### Check Repeated Attempts

```python
from financial.services.validation_service import FinancialValidationService

def check_user_repeated_attempts(user):
    """Check if user has repeated failed validation attempts"""
    
    has_repeated, count = FinancialValidationService.check_repeated_attempts(
        user=user,
        hours=1,  # Check last 1 hour
        threshold=3  # Threshold is 3 attempts
    )
    
    if has_repeated:
        print(f"User {user.username} has {count} failed attempts in the last hour")
        # Send notification to admins
        send_admin_notification(user, count)
    
    return has_repeated, count
```

### Using EntityAccountMapper

```python
from financial.services.entity_mapper import EntityAccountMapper

# Get account for an entity
student = Student.objects.get(id=1)
account = EntityAccountMapper.get_account(student)

if account:
    print(f"Account: {account.code} - {account.name}")
else:
    print("No account found")

# Detect entity type
entity_type = EntityAccountMapper.detect_entity_type(student)
print(f"Entity type: {entity_type}")  # Output: 'student'

# Get comprehensive entity info
info = EntityAccountMapper.get_entity_info(student)
print(f"Entity: {info['entity_name']}")
print(f"Type: {info['entity_type']}")
print(f"Has account: {info['has_account']}")
print(f"Account field path: {info['account_field_path']}")

# Validate entity account
is_valid, message = EntityAccountMapper.validate_entity_account(student)
if not is_valid:
    print(f"Validation failed: {message}")
```


---

## Error Handling

### Exception Hierarchy

```python
ValidationError (Django)
    └── FinancialValidationError
            ├── ChartOfAccountsValidationError
            └── AccountingPeriodValidationError
```

### Catching Specific Exceptions

```python
from financial.exceptions import (
    FinancialValidationError,
    ChartOfAccountsValidationError,
    AccountingPeriodValidationError
)

def process_payment_with_specific_handling(student, amount, payment_date):
    """Handle different validation errors differently"""
    
    try:
        payment = create_student_payment(student, amount, payment_date)
        return payment
        
    except ChartOfAccountsValidationError as e:
        # Handle chart of accounts errors
        print(f"Account error: {str(e)}")
        print(f"Error code: {e.code}")
        print(f"Entity: {e.entity}")
        print(f"Account: {e.account}")
        
        # Redirect to account setup
        return redirect('setup_account', student_id=student.id)
        
    except AccountingPeriodValidationError as e:
        # Handle accounting period errors
        print(f"Period error: {str(e)}")
        print(f"Error code: {e.code}")
        print(f"Period: {e.period}")
        print(f"Transaction date: {e.transaction_date}")
        
        # Redirect to period management
        return redirect('manage_periods')
        
    except FinancialValidationError as e:
        # Handle general validation errors
        print(f"Validation error: {str(e)}")
        print(f"Error code: {e.code}")
        print(f"Validation type: {e.validation_type}")
        
        # Show error to user
        messages.error(request, str(e))
        return redirect('payment_form')
```

### Error Codes

Each exception includes a `code` attribute for programmatic error handling:

**ChartOfAccountsValidationError codes**:
- `missing_account`: No accounting account linked to entity
- `inactive_account`: Accounting account is not active
- `not_leaf_account`: Accounting account is not a leaf account
- `unknown_entity_type`: Entity type could not be determined

**AccountingPeriodValidationError codes**:
- `missing_period`: No accounting period exists for the date
- `closed_period`: Accounting period is closed
- `out_of_range`: Date is outside all accounting periods
- `database_error`: Database error occurred

### Displaying Errors in Views

#### Function-Based View

```python
from django.shortcuts import render, redirect
from django.contrib import messages
from financial.exceptions import FinancialValidationError

def payment_view(request, student_id):
    """Function-based view with error handling"""
    
    if request.method == 'POST':
        try:
            student = Student.objects.get(id=student_id)
            amount = request.POST.get('amount')
            payment_date = request.POST.get('payment_date')
            
            # Process payment (validation happens automatically)
            payment = process_student_payment(student, amount, payment_date)
            
            messages.success(request, 'تم معالجة الدفعة بنجاح')
            return redirect('payment_success', payment_id=payment.id)
            
        except FinancialValidationError as e:
            # Display Arabic error message
            messages.error(request, str(e))
            return redirect('payment_form', student_id=student_id)
        
        except Exception as e:
            # Handle unexpected errors
            messages.error(request, 'حدث خطأ غير متوقع. يرجى المحاولة لاحقاً.')
            logger.error(f"Unexpected error in payment_view: {str(e)}")
            return redirect('payment_form', student_id=student_id)
    
    # GET request - show form
    student = Student.objects.get(id=student_id)
    return render(request, 'students/payment_form.html', {'student': student})
```

#### Class-Based View

```python
from django.views.generic import CreateView
from django.contrib import messages
from financial.exceptions import FinancialValidationError

class StudentPaymentCreateView(CreateView):
    """Class-based view with error handling"""
    model = FeePayment
    template_name = 'students/payment_form.html'
    fields = ['amount', 'payment_date', 'description']
    
    def form_valid(self, form):
        """Process valid form with validation"""
        try:
            student = Student.objects.get(id=self.kwargs['student_id'])
            
            # Validate before saving
            validation_result = FinancialValidationService.validate_transaction(
                entity=student,
                transaction_date=form.cleaned_data['payment_date'],
                transaction_amount=form.cleaned_data['amount'],
                user=self.request.user,
                module='students',
                raise_exception=True
            )
            
            # Save payment
            payment = form.save(commit=False)
            payment.student = student
            payment.save()
            
            messages.success(self.request, 'تم معالجة الدفعة بنجاح')
            return redirect('payment_success', payment_id=payment.id)
            
        except FinancialValidationError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)
    
    def form_invalid(self, form):
        """Handle invalid form"""
        messages.error(self.request, 'يرجى تصحيح الأخطاء في النموذج')
        return super().form_invalid(form)
```

### Custom Error Messages

You can use `ErrorMessageGenerator` to create custom error messages:

```python
from financial.services.error_messages import ErrorMessageGenerator

# Generate custom error message
error_msg = ErrorMessageGenerator.chart_of_accounts_missing(
    entity_name="أحمد محمد",
    entity_type="student"
)
print(error_msg)
# Output: لا يوجد حساب محاسبي مرتبط بـ الطالب: أحمد محمد.
#         الإجراء المطلوب: يرجى ربط حساب محاسبي بهذا الطالب...

# Generate comprehensive message
errors = [
    "لا يوجد حساب محاسبي",
    "لا توجد فترة محاسبية"
]
comprehensive_msg = ErrorMessageGenerator.generate_comprehensive_message(
    errors=errors,
    entity_name="أحمد محمد",
    entity_type="student",
    transaction_date=date(2024, 6, 15)
)
print(comprehensive_msg)
```


---

## Integrating with New Modules

Follow these steps to integrate the validation system with a new module.

### Step 1: Identify Financial Transactions

Identify all functions, methods, or views that handle financial transactions in your module.

Examples:
- Payment processing functions
- Invoice creation
- Fee calculation and recording
- Refund processing
- Financial report generation (if it requires valid accounts)

### Step 2: Add Entity to EntityAccountMapper

If your module introduces a new entity type, add it to `EntityAccountMapper`.

**Edit**: `financial/services/entity_mapper.py`

```python
class EntityAccountMapper:
    # Add your entity's account field mapping
    ENTITY_ACCOUNT_FIELDS = {
        'student': 'parent.financial_account',
        'supplier': 'financial_account',
        # ... existing mappings ...
        
        # Add your new entity
        'your_entity': 'account_field_name',  # e.g., 'financial_account'
    }
    
    # Add model name mapping
    MODEL_TO_ENTITY_TYPE = {
        'Student': 'student',
        'Supplier': 'supplier',
        # ... existing mappings ...
        
        # Add your new model
        'YourModel': 'your_entity',
    }
```

**Example**: Adding a `Customer` entity

```python
class EntityAccountMapper:
    ENTITY_ACCOUNT_FIELDS = {
        # ... existing mappings ...
        'customer': 'financial_account',  # Customer.financial_account
    }
    
    MODEL_TO_ENTITY_TYPE = {
        # ... existing mappings ...
        'Customer': 'customer',
    }
```

### Step 3: Apply Validation Decorator

Apply the `@require_financial_validation` decorator to your transaction functions.

**Example**: New module `customers`

```python
# customers/services.py
from datetime import date
from financial.decorators import require_financial_validation
from financial.exceptions import FinancialValidationError

@require_financial_validation(
    entity_param='customer',
    date_param='payment_date',
    transaction_type='payment',
    amount_param='amount',
    module='customers'
)
def process_customer_payment(customer, amount, payment_date, description):
    """Process customer payment with automatic validation"""
    payment = CustomerPayment.objects.create(
        customer=customer,
        amount=amount,
        payment_date=payment_date,
        description=description
    )
    return payment

@require_financial_validation(
    entity_param='customer',
    date_param='invoice_date',
    transaction_type='invoice',
    amount_param='total_amount',
    module='customers'
)
def create_customer_invoice(customer, items, invoice_date, total_amount):
    """Create customer invoice with automatic validation"""
    invoice = CustomerInvoice.objects.create(
        customer=customer,
        invoice_date=invoice_date,
        total_amount=total_amount
    )
    
    # Add invoice items
    for item in items:
        InvoiceItem.objects.create(
            invoice=invoice,
            product=item['product'],
            quantity=item['quantity'],
            price=item['price']
        )
    
    return invoice
```

### Step 4: Update Views to Handle Errors

Update your views to catch and display validation errors.

```python
# customers/views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from financial.exceptions import FinancialValidationError
from .services import process_customer_payment

def customer_payment_view(request, customer_id):
    """View for processing customer payments"""
    
    if request.method == 'POST':
        try:
            customer = Customer.objects.get(id=customer_id)
            amount = request.POST.get('amount')
            payment_date = request.POST.get('payment_date')
            description = request.POST.get('description')
            
            # Process payment (validation happens automatically)
            payment = process_customer_payment(
                customer=customer,
                amount=amount,
                payment_date=payment_date,
                description=description
            )
            
            messages.success(request, 'تم معالجة الدفعة بنجاح')
            return redirect('customer_payment_success', payment_id=payment.id)
            
        except FinancialValidationError as e:
            # Display validation error in Arabic
            messages.error(request, str(e))
            return redirect('customer_payment_form', customer_id=customer_id)
        
        except Exception as e:
            messages.error(request, 'حدث خطأ غير متوقع')
            logger.error(f"Error in customer_payment_view: {str(e)}")
            return redirect('customer_payment_form', customer_id=customer_id)
    
    # GET request
    customer = Customer.objects.get(id=customer_id)
    return render(request, 'customers/payment_form.html', {
        'customer': customer
    })
```

### Step 5: Add Error Messages to Templates

Display validation errors in your templates.

```django
<!-- customers/templates/customers/payment_form.html -->
{% extends "base.html" %}

{% block content %}
<div class="container">
    <h2>معالجة دفعة العميل: {{ customer.name }}</h2>
    
    <!-- Display messages (including validation errors) -->
    {% if messages %}
        {% for message in messages %}
            <div class="alert alert-{{ message.tags }}">
                {{ message }}
            </div>
        {% endfor %}
    {% endif %}
    
    <form method="post">
        {% csrf_token %}
        
        <div class="form-group">
            <label>المبلغ</label>
            <input type="number" name="amount" class="form-control" required>
        </div>
        
        <div class="form-group">
            <label>تاريخ الدفعة</label>
            <input type="date" name="payment_date" class="form-control" required>
        </div>
        
        <div class="form-group">
            <label>الوصف</label>
            <textarea name="description" class="form-control"></textarea>
        </div>
        
        <button type="submit" class="btn btn-primary">معالجة الدفعة</button>
    </form>
</div>
{% endblock %}
```

### Step 6: Add Tests

Create tests for your validation integration.

```python
# customers/tests/test_validation.py
import pytest
from datetime import date
from django.test import TestCase
from financial.exceptions import ChartOfAccountsValidationError, AccountingPeriodValidationError
from customers.services import process_customer_payment
from customers.models import Customer
from financial.models import ChartOfAccounts, AccountingPeriod

class CustomerValidationTestCase(TestCase):
    """Test validation for customer transactions"""
    
    def setUp(self):
        """Set up test data"""
        # Create accounting account
        self.account = ChartOfAccounts.objects.create(
            code='1010',
            name='حساب العملاء',
            is_active=True,
            is_leaf=True
        )
        
        # Create customer with account
        self.customer = Customer.objects.create(
            name='أحمد محمد',
            financial_account=self.account
        )
        
        # Create open accounting period
        self.period = AccountingPeriod.objects.create(
            name='يناير 2024',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            status='open'
        )
    
    def test_valid_payment(self):
        """Test that valid payment is processed"""
        payment = process_customer_payment(
            customer=self.customer,
            amount=1000,
            payment_date=date(2024, 1, 15),
            description='دفعة اختبار'
        )
        
        self.assertIsNotNone(payment)
        self.assertEqual(payment.amount, 1000)
    
    def test_payment_without_account(self):
        """Test that payment without account is rejected"""
        # Create customer without account
        customer_no_account = Customer.objects.create(
            name='محمد علي',
            financial_account=None
        )
        
        with self.assertRaises(ChartOfAccountsValidationError):
            process_customer_payment(
                customer=customer_no_account,
                amount=1000,
                payment_date=date(2024, 1, 15),
                description='دفعة اختبار'
            )
    
    def test_payment_in_closed_period(self):
        """Test that payment in closed period is rejected"""
        # Close the period
        self.period.status = 'closed'
        self.period.save()
        
        with self.assertRaises(AccountingPeriodValidationError):
            process_customer_payment(
                customer=self.customer,
                amount=1000,
                payment_date=date(2024, 1, 15),
                description='دفعة اختبار'
            )
```

### Step 7: Update Documentation

Add your module to the list of supported modules in the user guide and update any relevant documentation.

### Complete Integration Checklist

- [ ] Identify all financial transactions in the module
- [ ] Add entity to `EntityAccountMapper` (if new entity type)
- [ ] Apply `@require_financial_validation` decorator to transaction functions
- [ ] Update views to catch and display `FinancialValidationError`
- [ ] Add error message display to templates
- [ ] Create unit tests for validation
- [ ] Create integration tests for complete workflows
- [ ] Update module documentation
- [ ] Test manually with various scenarios
- [ ] Update user guide with module-specific instructions


---

## Testing

### Unit Tests

Test individual validation components.

#### Testing FinancialValidationService

```python
# tests/unit/test_validation_service.py
import pytest
from datetime import date
from django.test import TestCase
from financial.services.validation_service import FinancialValidationService
from financial.models import ChartOfAccounts, AccountingPeriod
from students.models import Student, Parent

class TestFinancialValidationService(TestCase):
    """Unit tests for FinancialValidationService"""
    
    def setUp(self):
        """Set up test data"""
        # Create chart of accounts
        self.active_account = ChartOfAccounts.objects.create(
            code='1010',
            name='حساب الطلاب',
            is_active=True,
            is_leaf=True
        )
        
        self.inactive_account = ChartOfAccounts.objects.create(
            code='1020',
            name='حساب غير مفعل',
            is_active=False,
            is_leaf=True
        )
        
        # Create parent with account
        self.parent = Parent.objects.create(
            name='ولي الأمر',
            financial_account=self.active_account
        )
        
        # Create student
        self.student = Student.objects.create(
            name='أحمد محمد',
            parent=self.parent
        )
        
        # Create accounting period
        self.open_period = AccountingPeriod.objects.create(
            name='يناير 2024',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            status='open'
        )
    
    def test_validate_chart_of_accounts_valid(self):
        """Test validation with valid account"""
        is_valid, error_msg, account = FinancialValidationService.validate_chart_of_accounts(
            entity=self.student,
            entity_type='student'
        )
        
        self.assertTrue(is_valid)
        self.assertEqual(error_msg, "")
        self.assertEqual(account, self.active_account)
    
    def test_validate_chart_of_accounts_missing(self):
        """Test validation with missing account"""
        # Create student without parent
        student_no_parent = Student.objects.create(
            name='طالب بدون ولي أمر',
            parent=None
        )
        
        is_valid, error_msg, account = FinancialValidationService.validate_chart_of_accounts(
            entity=student_no_parent,
            entity_type='student'
        )
        
        self.assertFalse(is_valid)
        self.assertIn('لا يوجد حساب محاسبي', error_msg)
        self.assertIsNone(account)
    
    def test_validate_accounting_period_valid(self):
        """Test validation with open period"""
        is_valid, error_msg, period = FinancialValidationService.validate_accounting_period(
            transaction_date=date(2024, 1, 15)
        )
        
        self.assertTrue(is_valid)
        self.assertEqual(error_msg, "")
        self.assertEqual(period, self.open_period)
    
    def test_validate_accounting_period_closed(self):
        """Test validation with closed period"""
        self.open_period.status = 'closed'
        self.open_period.save()
        
        is_valid, error_msg, period = FinancialValidationService.validate_accounting_period(
            transaction_date=date(2024, 1, 15)
        )
        
        self.assertFalse(is_valid)
        self.assertIn('مغلقة', error_msg)
        self.assertEqual(period, self.open_period)
    
    def test_validate_transaction_comprehensive(self):
        """Test comprehensive transaction validation"""
        result = FinancialValidationService.validate_transaction(
            entity=self.student,
            transaction_date=date(2024, 1, 15),
            module='students'
        )
        
        self.assertTrue(result['is_valid'])
        self.assertEqual(len(result['errors']), 0)
        self.assertEqual(result['account'], self.active_account)
        self.assertEqual(result['period'], self.open_period)
```

#### Testing Decorators

```python
# tests/unit/test_decorators.py
import pytest
from datetime import date
from django.test import TestCase
from financial.decorators import require_financial_validation
from financial.exceptions import FinancialValidationError
from financial.models import ChartOfAccounts, AccountingPeriod
from students.models import Student, Parent

class TestDecorators(TestCase):
    """Unit tests for validation decorators"""
    
    def setUp(self):
        """Set up test data"""
        # Create account and period
        self.account = ChartOfAccounts.objects.create(
            code='1010',
            name='حساب الطلاب',
            is_active=True,
            is_leaf=True
        )
        
        self.period = AccountingPeriod.objects.create(
            name='يناير 2024',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            status='open'
        )
        
        # Create student with account
        parent = Parent.objects.create(
            name='ولي الأمر',
            financial_account=self.account
        )
        
        self.student = Student.objects.create(
            name='أحمد محمد',
            parent=parent
        )
    
    def test_decorator_allows_valid_transaction(self):
        """Test that decorator allows valid transaction"""
        
        @require_financial_validation(
            entity_param='student',
            date_param='payment_date',
            module='students'
        )
        def process_payment(student, amount, payment_date):
            return f"Payment processed: {amount}"
        
        # Should not raise exception
        result = process_payment(
            student=self.student,
            amount=1000,
            payment_date=date(2024, 1, 15)
        )
        
        self.assertEqual(result, "Payment processed: 1000")
    
    def test_decorator_blocks_invalid_transaction(self):
        """Test that decorator blocks invalid transaction"""
        
        # Create student without account
        student_no_account = Student.objects.create(
            name='طالب بدون حساب',
            parent=None
        )
        
        @require_financial_validation(
            entity_param='student',
            date_param='payment_date',
            module='students'
        )
        def process_payment(student, amount, payment_date):
            return f"Payment processed: {amount}"
        
        # Should raise exception
        with self.assertRaises(FinancialValidationError):
            process_payment(
                student=student_no_account,
                amount=1000,
                payment_date=date(2024, 1, 15)
            )
```

### Integration Tests

Test complete workflows with validation.

```python
# tests/integration/test_student_payment_validation.py
import pytest
from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from financial.models import ChartOfAccounts, AccountingPeriod, ValidationAuditLog
from students.models import Student, Parent, FeePayment

class TestStudentPaymentValidation(TestCase):
    """Integration tests for student payment validation"""
    
    def setUp(self):
        """Set up test data"""
        # Create user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Create account
        self.account = ChartOfAccounts.objects.create(
            code='1010',
            name='حساب الطلاب',
            is_active=True,
            is_leaf=True
        )
        
        # Create period
        self.period = AccountingPeriod.objects.create(
            name='يناير 2024',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            status='open'
        )
        
        # Create student with account
        parent = Parent.objects.create(
            name='ولي الأمر',
            financial_account=self.account
        )
        
        self.student = Student.objects.create(
            name='أحمد محمد',
            parent=parent
        )
        
        # Create client and login
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')
    
    def test_successful_payment_flow(self):
        """Test complete successful payment flow"""
        # Submit payment
        response = self.client.post(
            reverse('students:process_payment', args=[self.student.id]),
            {
                'amount': 1000,
                'payment_date': '2024-01-15',
                'description': 'دفعة اختبار'
            }
        )
        
        # Check payment was created
        self.assertEqual(FeePayment.objects.count(), 1)
        payment = FeePayment.objects.first()
        self.assertEqual(payment.student, self.student)
        self.assertEqual(payment.amount, 1000)
        
        # Check no validation audit log (success)
        self.assertEqual(ValidationAuditLog.objects.count(), 0)
    
    def test_rejected_payment_without_account(self):
        """Test payment rejection without account"""
        # Create student without account
        student_no_account = Student.objects.create(
            name='طالب بدون حساب',
            parent=None
        )
        
        # Submit payment
        response = self.client.post(
            reverse('students:process_payment', args=[student_no_account.id]),
            {
                'amount': 1000,
                'payment_date': '2024-01-15',
                'description': 'دفعة اختبار'
            }
        )
        
        # Check payment was NOT created
        self.assertEqual(FeePayment.objects.count(), 0)
        
        # Check validation audit log was created
        self.assertEqual(ValidationAuditLog.objects.count(), 1)
        log = ValidationAuditLog.objects.first()
        self.assertEqual(log.entity_type, 'student')
        self.assertEqual(log.entity_id, student_no_account.id)
        self.assertEqual(log.validation_type, 'chart_of_accounts')
        self.assertIn('لا يوجد حساب محاسبي', log.error_message)
    
    def test_rejected_payment_in_closed_period(self):
        """Test payment rejection in closed period"""
        # Close the period
        self.period.status = 'closed'
        self.period.save()
        
        # Submit payment
        response = self.client.post(
            reverse('students:process_payment', args=[self.student.id]),
            {
                'amount': 1000,
                'payment_date': '2024-01-15',
                'description': 'دفعة اختبار'
            }
        )
        
        # Check payment was NOT created
        self.assertEqual(FeePayment.objects.count(), 0)
        
        # Check validation audit log
        self.assertEqual(ValidationAuditLog.objects.count(), 1)
        log = ValidationAuditLog.objects.first()
        self.assertEqual(log.validation_type, 'accounting_period')
        self.assertIn('مغلقة', log.error_message)
```


---

## Best Practices

### 1. Always Use Validation for Financial Transactions

**DO**: Apply validation to all financial transactions

```python
@require_financial_validation(
    entity_param='student',
    date_param='payment_date',
    module='students'
)
def process_payment(student, amount, payment_date):
    # Process payment
    pass
```

**DON'T**: Skip validation for financial transactions

```python
# ❌ Bad - No validation
def process_payment(student, amount, payment_date):
    # Direct payment processing without validation
    payment = FeePayment.objects.create(...)
```

### 2. Handle Validation Errors Gracefully

**DO**: Catch and display validation errors to users

```python
try:
    payment = process_payment(student, amount, payment_date)
    messages.success(request, 'تم معالجة الدفعة بنجاح')
except FinancialValidationError as e:
    messages.error(request, str(e))  # Display Arabic error message
```

**DON'T**: Let validation errors crash the application

```python
# ❌ Bad - Unhandled exception
payment = process_payment(student, amount, payment_date)
# If validation fails, this will crash
```

### 3. Use Appropriate Decorator for Your Use Case

**Full Validation** (account + period):

```python
@require_financial_validation(...)
def process_payment(...):
    pass
```

**Account Only** (for reports, queries):

```python
@require_chart_of_accounts_only(...)
def generate_account_report(...):
    pass
```

**Period Only** (for general entries):

```python
@require_accounting_period_only(...)
def create_journal_entry(...):
    pass
```

### 4. Provide Context in Validation Calls

**DO**: Provide user, module, and view name for better logging

```python
validation_result = FinancialValidationService.validate_transaction(
    entity=student,
    transaction_date=payment_date,
    user=request.user,  # For audit logging
    module='students',  # For categorization
    view_name='process_payment',  # For debugging
    request=request  # For request path logging
)
```

**DON'T**: Provide minimal context

```python
# ❌ Less useful for debugging and auditing
validation_result = FinancialValidationService.validate_transaction(
    entity=student,
    transaction_date=payment_date
)
```

### 5. Log Validation Failures

**DO**: Enable logging for audit trail

```python
validation_result = FinancialValidationService.validate_transaction(
    entity=student,
    transaction_date=payment_date,
    log_failures=True  # Default, but be explicit
)
```

### 6. Test Validation Integration

**DO**: Write tests for both success and failure cases

```python
def test_valid_payment(self):
    """Test successful payment"""
    payment = process_payment(student, 1000, date(2024, 1, 15))
    self.assertIsNotNone(payment)

def test_payment_without_account(self):
    """Test payment rejection without account"""
    with self.assertRaises(ChartOfAccountsValidationError):
        process_payment(student_no_account, 1000, date(2024, 1, 15))
```

### 7. Use Entity Type Auto-Detection

**DO**: Let the system detect entity type

```python
@require_financial_validation(
    entity_param='entity',  # Generic parameter name
    date_param='date',
    module='financial'
)
def process_transaction(entity, amount, date):
    # Entity type is auto-detected
    pass
```

**DON'T**: Hardcode entity types unless necessary

```python
# Only specify entity_type if auto-detection doesn't work
@require_financial_validation(
    entity_param='entity',
    entity_type_param='entity_type',  # Only if needed
    date_param='date'
)
def process_transaction(entity, entity_type, amount, date):
    pass
```

### 8. Handle Special Transaction Types

**DO**: Specify transaction type for special handling

```python
# Opening entries bypass period validation
@require_financial_validation(
    entity_param='entity',
    date_param='date',
    transaction_type='opening',  # Special handling
    module='financial'
)
def create_opening_entry(entity, amount, date):
    pass

# Adjustments with special permissions
@require_financial_validation(
    entity_param='entity',
    date_param='date',
    transaction_type='adjustment',  # Special handling
    module='financial'
)
def create_adjustment(entity, amount, date):
    pass
```

### 9. Display Helpful Error Messages

**DO**: Show the full Arabic error message to users

```python
except FinancialValidationError as e:
    # The error message includes:
    # - What went wrong
    # - Entity details
    # - Suggested actions
    messages.error(request, str(e))
```

**DON'T**: Show generic error messages

```python
# ❌ Bad - Not helpful to users
except FinancialValidationError as e:
    messages.error(request, 'حدث خطأ')
```

### 10. Monitor Validation Audit Logs

Regularly review `ValidationAuditLog` to:
- Identify entities with missing accounts
- Find users with repeated failures
- Detect patterns in validation failures
- Improve system configuration

```python
# Check for repeated failures
from financial.models import ValidationAuditLog

# Entities with most failures
problem_entities = ValidationAuditLog.objects.values(
    'entity_type', 'entity_id', 'entity_name'
).annotate(
    failure_count=Count('id')
).filter(
    failure_count__gt=5
).order_by('-failure_count')

# Users with most failures
problem_users = ValidationAuditLog.objects.values(
    'user__username'
).annotate(
    failure_count=Count('id')
).filter(
    failure_count__gt=10
).order_by('-failure_count')
```

---

## Troubleshooting

### Common Issues and Solutions

#### Issue 1: "نوع الكيان غير معروف" (Unknown Entity Type)

**Cause**: Entity type not registered in `EntityAccountMapper`

**Solution**: Add your entity to `EntityAccountMapper.MODEL_TO_ENTITY_TYPE`

```python
# financial/services/entity_mapper.py
MODEL_TO_ENTITY_TYPE = {
    # ... existing mappings ...
    'YourModel': 'your_entity',  # Add this
}
```

#### Issue 2: Validation Always Fails for a Specific Entity

**Cause**: Incorrect account field path in `EntityAccountMapper`

**Solution**: Check and fix the account field path

```python
# financial/services/entity_mapper.py
ENTITY_ACCOUNT_FIELDS = {
    'your_entity': 'correct_field_name',  # Fix this
}

# Test the mapping
from financial.services.entity_mapper import EntityAccountMapper
entity = YourModel.objects.first()
account = EntityAccountMapper.get_account(entity)
print(f"Account: {account}")  # Should not be None
```

#### Issue 3: Decorator Not Working in Class Methods

**Cause**: Incorrect parameter extraction from `self`

**Solution**: Ensure parameters are in `kwargs`, not `self`

```python
class PaymentView(View):
    @require_financial_validation(
        entity_param='student',  # Must be in kwargs
        date_param='payment_date',
        module='students'
    )
    def post(self, request, student_id):
        # Get parameters
        student = Student.objects.get(id=student_id)
        payment_date = request.POST.get('payment_date')
        
        # Pass as kwargs (not self.student)
        return self.process_payment(
            student=student,  # ✓ Correct
            payment_date=payment_date
        )
```

#### Issue 4: Validation Errors Not Logged

**Cause**: `log_failures=False` or missing user/request context

**Solution**: Enable logging and provide context

```python
validation_result = FinancialValidationService.validate_transaction(
    entity=student,
    transaction_date=payment_date,
    user=request.user,  # Provide user
    request=request,  # Provide request
    log_failures=True  # Enable logging
)
```

#### Issue 5: Special Transactions Not Bypassing Validation

**Cause**: Incorrect transaction type or missing permissions

**Solution**: Check transaction type and user permissions

```python
# For opening entries
@require_financial_validation(
    transaction_type='opening',  # Must be exactly 'opening'
    ...
)

# For adjustments
# User must have 'financial.bypass_period_check' permission
user.user_permissions.add(
    Permission.objects.get(codename='bypass_period_check')
)
```

#### Issue 6: Arabic Error Messages Not Displaying

**Cause**: Template not rendering messages or encoding issues

**Solution**: Ensure proper template setup

```django
<!-- In your template -->
{% if messages %}
    {% for message in messages %}
        <div class="alert alert-{{ message.tags }}">
            {{ message }}  <!-- Will display Arabic text -->
        </div>
    {% endfor %}
{% endif %}
```

#### Issue 7: Performance Issues with Validation

**Cause**: Missing database indexes or N+1 queries

**Solution**: Ensure indexes exist and use select_related

```python
# Indexes are created automatically by ValidationAuditLog model
# Use select_related to avoid N+1 queries
student = Student.objects.select_related(
    'parent',
    'parent__financial_account'
).get(id=student_id)
```

### Debugging Tips

#### Enable Debug Logging

```python
# settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'financial': {
            'handlers': ['console'],
            'level': 'DEBUG',  # Enable debug logging
        },
    },
}
```

#### Check Validation Result Details

```python
result = FinancialValidationService.validate_transaction(
    entity=student,
    transaction_date=payment_date,
    raise_exception=False  # Don't raise, check result
)

print(f"Valid: {result['is_valid']}")
print(f"Errors: {result['errors']}")
print(f"Warnings: {result['warnings']}")
print(f"Account: {result['account']}")
print(f"Period: {result['period']}")
print(f"Details: {result['validation_details']}")
```

#### Test Entity Account Mapping

```python
from financial.services.entity_mapper import EntityAccountMapper

entity = YourModel.objects.first()

# Get comprehensive info
info = EntityAccountMapper.get_entity_info(entity)
print(f"Entity type: {info['entity_type']}")
print(f"Has account: {info['has_account']}")
print(f"Account: {info['account']}")
print(f"Field path: {info['account_field_path']}")

# Validate
is_valid, message = EntityAccountMapper.validate_entity_account(entity)
print(f"Valid: {is_valid}")
print(f"Message: {message}")
```

---

## Additional Resources

### Related Documentation

- [User Guide (Arabic)](./financial-validation-user-guide-ar.md) - For end users
- [Architecture Document](./architecture.md) - System architecture overview
- [Financial System Documentation](./financial-system.md) - Financial module details

### Code References

- **Validation Service**: `financial/services/validation_service.py`
- **Entity Mapper**: `financial/services/entity_mapper.py`
- **Error Messages**: `financial/services/error_messages.py`
- **Decorators**: `financial/decorators.py`
- **Exceptions**: `financial/exceptions.py`
- **Audit Log Model**: `financial/models/validation_audit_log.py`

### Support

For questions or issues:
1. Check this documentation
2. Review the code comments in the source files
3. Check the ValidationAuditLog for error patterns
4. Contact the development team

---

## Changelog

### Version 1.0 (Initial Release)

- Complete validation system for financial transactions
- Support for all major modules (students, supplier, hr, activities, transportation)
- Arabic error messages with suggestions
- Comprehensive audit logging
- Special transaction type handling (opening, adjustment)
- Decorator and service-based validation
- Full test coverage

---

**Last Updated**: 2024
**Maintained By**: Development Team
