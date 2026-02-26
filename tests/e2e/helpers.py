# -*- coding: utf-8 -*-
"""
مساعدات لاختبارات E2E - توليد البيانات التجريبية
"""

import uuid
import time
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal
import random


class DataGenerator:
    """مولد البيانات التجريبية للاختبارات"""
    
    def __init__(self, prefix="E2E"):
        self.prefix = prefix
        
    def generate_unique_id(self):
        """توليد معرف فريد"""
        return f"{self.prefix}_{uuid.uuid4().hex[:8]}"
        
    def generate_national_id(self):
        """توليد رقم قومي تجريبي صحيح (14 رقم)"""
        # توليد رقم قومي يبدأ بـ 2 أو 3 (القرن 20 أو 21)
        # Format: CYYMMDDGGGGGGC (14 digits total)
        # C = Century (2 for 1900s, 3 for 2000s)
        # YY = Year (2 digits)
        # MM = Month (2 digits)
        # DD = Day (2 digits)
        # GGGGGG = Governorate + Sequence (6 digits)
        # C = Check digit (1 digit)
        # Total: 1 + 2 + 2 + 2 + 6 + 1 = 14 digits
        
        # استخدام قرن 2 (1900s) لتجنب مشاكل التحقق
        century = '2'
        year = f'{random.randint(80, 99):02d}'  # 1980-1999
        month = f'{random.randint(1, 12):02d}'
        day = f'{random.randint(1, 28):02d}'  # استخدام 28 لتجنب مشاكل الأشهر
        
        # Governorate code (2 digits) + Sequence (4 digits) = 6 digits
        governorate = f'{random.randint(1, 35):02d}'  # 35 governorate in Egypt
        sequence = f'{random.randint(1000, 9999)}'
        
        # تكوين أول 13 رقم
        national_id_13 = century + year + month + day + governorate + sequence
        
        # التأكد من أن الطول 13 رقم
        if len(national_id_13) != 13:
            # Fallback to fixed valid ID (13 digits)
            national_id_13 = '2951215011234'
        
        # حساب رقم التحقق
        weights = [2, 7, 6, 5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
        total = 0
        for i in range(13):
            total += int(national_id_13[i]) * weights[i]
        
        check_digit = (10 - (total % 10)) % 10
        
        # Final ID = 13 digits + 1 check digit = 14 digits
        final_id = national_id_13 + str(check_digit)
        
        return final_id
        
    def generate_phone_number(self):
        """توليد رقم هاتف تجريبي"""
        prefixes = ['010', '011', '012', '015']
        prefix = random.choice(prefixes)
        number = ''.join([str(random.randint(0, 9)) for _ in range(8)])
        return f"{prefix}{number}"


def generate_test_student_data(prefix="E2E"):
    """إنشاء بيانات طالب تجريبية"""
    generator = DataGenerator(prefix)
    
    # أسماء تجريبية
    first_names = ['أحمد', 'محمد', 'علي', 'حسن', 'فاطمة', 'عائشة', 'زينب', 'مريم']
    last_names = ['محمد', 'أحمد', 'علي', 'حسن', 'إبراهيم', 'عبدالله', 'عبدالرحمن']
    
    first_name = random.choice(first_names)
    father_name = random.choice(last_names)
    grandfather_name = random.choice(last_names)
    
    student_name = f"{prefix}_{first_name} {father_name} {grandfather_name}"
    
    # تاريخ ميلاد مناسب للفئة العمرية KG1 (4 سنوات)
    # نطاق آمن يضمن وجود فئة عمرية مناسبة
    today = date.today()
    years = 4  # عمر ثابت 4 سنوات
    months = random.randint(0, 11)  # من 4 سنوات إلى 4 سنوات و 11 شهر
    birth_date = today - relativedelta(years=years, months=months)
    
    return {
        'student_name': student_name,
        'birth_date': birth_date,
        'gender': random.choice(['M', 'F']),
        'nationality': 'مصري',
        'place_of_birth': f'{prefix}_القاهرة',
        'place_of_residence': f'{prefix}_المنصورة',
        'national_id': generator.generate_national_id()
    }


def generate_test_parent_data(prefix="E2E"):
    """إنشاء بيانات ولي أمر تجريبية"""
    generator = DataGenerator(prefix)
    
    # أسماء أولياء الأمور
    parent_names = ['أحمد محمد علي', 'محمد أحمد حسن', 'علي محمد إبراهيم', 'حسن علي محمد']
    parent_name = f"{prefix}_{random.choice(parent_names)}"
    
    # وظائف تجريبية
    jobs = ['مهندس', 'طبيب', 'محاسب', 'مدرس', 'موظف', 'تاجر']
    
    return {
        'parent_name': parent_name,
        'parent_phone': generator.generate_phone_number(),
        'parent_national_id': generator.generate_national_id(),
        'parent_job': random.choice(jobs),
        'address': f'{prefix}_شارع التجريب، المنصورة، مصر',
        'email': f'{prefix.lower()}_parent@test.com'
    }


def generate_qr_application_data(prefix="E2E"):
    """إنشاء بيانات طلب QR كاملة"""
    student_data = generate_test_student_data(prefix)
    parent_data = generate_test_parent_data(prefix)
    
    # دمج البيانات
    application_data = {
        # بيانات الطالب
        'student_name': student_data['student_name'],
        'birth_date': student_data['birth_date'],
        'gender': student_data['gender'],
        'nationality': student_data['nationality'],
        'place_of_birth': student_data['place_of_birth'],
        'place_of_residence': student_data['place_of_residence'],
        
        # بيانات ولي الأمر
        'parent_name': parent_data['parent_name'],
        'parent_phone': parent_data['parent_phone'],
        'parent_national_id': parent_data['parent_national_id'],
        'parent_job': parent_data['parent_job'],
        'address': parent_data['address'],
        
        # معلومات إضافية
        'terms_accepted': True,
        'ip_address': '127.0.0.1',
        'user_agent': 'Test Browser',
        
        # معلومات طبية (افتراضية آمنة)
        'has_allergies': False,
        'allergies_details': '',
        'has_diseases': False,
        'diseases_details': '',
        'has_treatment': False,
        'treatment_details': '',
        'wears_glasses': False,
        'notes': f'{prefix} - بيانات تجريبية للاختبار'
    }
    
    return application_data


def generate_fee_type_data(prefix="E2E"):
    """إنشاء بيانات أنواع الرسوم التجريبية"""
    fee_types = [
        {
            'name': f'{prefix}_رسوم التسجيل',
            'code': f'{prefix}_REG',
            'default_amount': Decimal('200.00'),
            'category': 'registration',
            'is_automatic': True,
            'supports_installments': False,
            'description': 'رسوم التسجيل الأولي'
        },
        {
            'name': f'{prefix}_الرسوم الشهرية',
            'code': f'{prefix}_MONTHLY',
            'default_amount': Decimal('300.00'),
            'category': 'tuition',
            'is_automatic': True,
            'supports_installments': True,
            'description': 'الرسوم الدراسية الشهرية'
        },
        {
            'name': f'{prefix}_رسوم الأنشطة',
            'code': f'{prefix}_ACTIVITIES',
            'default_amount': Decimal('100.00'),
            'category': 'activities',
            'is_automatic': False,
            'supports_installments': True,
            'description': 'رسوم الأنشطة الإضافية'
        }
    ]
    
    return fee_types


def generate_payment_data(prefix="E2E", amount=None):
    """إنشاء بيانات دفعة تجريبية"""
    if amount is None:
        amount = Decimal(str(random.randint(50, 500)))
    
    payment_methods = ['cash', 'bank_transfer', 'credit_card']
    
    return {
        'amount': amount,
        'payment_method': random.choice(payment_methods),
        'payment_date': date.today(),
        'reference_number': f'{prefix}_PAY_{uuid.uuid4().hex[:8].upper()}',
        'notes': f'{prefix} - دفعة تجريبية للاختبار'
    }


def create_test_academic_year(prefix="E2E"):
    """إنشاء سنة دراسية تجريبية"""
    current_year = date.today().year
    
    return {
        'year': current_year,
        'year_type': 'academic',
        'start_date': date(current_year, 9, 1),
        'end_date': date(current_year + 1, 6, 30),
        'is_active': True,
        'name': f'{prefix}_السنة الدراسية {current_year}-{current_year + 1}'
    }


def create_test_age_group(prefix="E2E"):
    """إنشاء فئة عمرية تجريبية"""
    return {
        'name': f'{prefix}_KG1',
        'code': f'{prefix}_KG1',
        'min_age_months': 36,  # 3 سنوات
        'max_age_months': 59,  # 5 سنوات - شهر
        'is_active': True,
        'order': 1,
        'description': 'فئة عمرية تجريبية للاختبار'
    }


def create_test_classroom(prefix="E2E"):
    """إنشاء فصل دراسي تجريبي"""
    return {
        'name': f'{prefix}_فصل أ',
        'code': f'{prefix}_CLS_A',
        'capacity': 25,
        'is_active': True,
        'description': 'فصل دراسي تجريبي للاختبار'
    }


# ============================================================================
# Form Data Preparation Helpers for HTTP POST Requests
# ============================================================================

def prepare_student_registration_form_data(prefix="E2E", academic_year=None, age_group=None, parent=None):
    """
    Prepare form data for student registration POST request
    
    Args:
        prefix: Prefix for test data
        academic_year: AcademicYear instance (optional)
        age_group: AgeGroup instance (optional)
        parent: Parent instance (optional, will be created if not provided)
    
    Returns:
        Dictionary matching the actual StudentForm fields
    """
    student_data = generate_test_student_data(prefix)
    
    # Match actual StudentForm field names
    form_data = {
        'name': student_data['student_name'],
        'date_of_birth': student_data['birth_date'].strftime('%Y-%m-%d'),
        'gender': student_data['gender'],
        'nationality': student_data['nationality'],
        'national_id': student_data['national_id'],
        'place_of_birth': student_data['place_of_birth'],
        'place_of_residence': student_data['place_of_residence'],
        'relationship_to_parent': 'father',  # Default relationship
        'is_active': True,
        
        # Medical information fields
        'has_allergies': 'no',
        'allergies_details': '',
        'has_diseases': 'no',
        'diseases_details': '',
        'has_treatment': 'no',
        'treatment_details': '',
        'wears_glasses': 'no',
        
        # Optional fields
        'medical_conditions': '',
        'special_needs': '',
        'notes': f'{prefix} - بيانات تجريبية للاختبار'
    }
    
    # Add parent if provided
    if parent:
        form_data['parent'] = parent.id
    
    return form_data


def prepare_parent_creation_form_data(prefix="E2E"):
    """
    Prepare form data for parent creation POST request
    
    Args:
        prefix: Prefix for test data
    
    Returns:
        Dictionary matching the actual ParentForm fields
    """
    parent_data = generate_test_parent_data(prefix)
    
    # Match actual ParentForm field names
    form_data = {
        'name': parent_data['parent_name'],
        'national_id': parent_data['parent_national_id'],
        'phone_primary': parent_data['parent_phone'],
        'phone_secondary': '',
        'email': parent_data.get('email', ''),
        'address': parent_data['address'],
        'city': 'المنصورة',
        'job_title': parent_data['parent_job'],
        'qualification': 'بكالوريوس',
        'work_phone': '',
        'work_address_detailed': '',
        'company_name': '',
        'tax_number': '',
        'credit_limit': 0
    }
    
    return form_data


def prepare_fee_payment_form_data(student_fee, amount=None, prefix="E2E"):
    """
    Prepare form data for fee payment POST request
    
    Args:
        student_fee: StudentFee instance
        amount: Payment amount (defaults to outstanding amount)
        prefix: Prefix for test data
    
    Returns:
        Dictionary matching the actual FeePaymentForm fields
    """
    if amount is None:
        amount = student_fee.outstanding_amount
    
    form_data = {
        'student_fee': student_fee.id,
        'amount': str(amount),
        'payment_method': 'cash',
        'payment_date': date.today().strftime('%Y-%m-%d'),
        'reference_number': f'{prefix}_PAY_{uuid.uuid4().hex[:8].upper()}',
        'notes': f'{prefix} - دفعة تجريبية للاختبار'
    }
    
    return form_data


def prepare_activity_creation_form_data(activity_type=None, supervisor=None, prefix="E2E"):
    """
    Prepare form data for activity creation POST request
    
    Args:
        activity_type: ActivityType instance (optional)
        supervisor: User instance for supervisor (optional)
        prefix: Prefix for test data
    
    Returns:
        Dictionary matching the actual ActivityForm fields
    """
    form_data = {
        'name': f'{prefix}_نشاط تجريبي',
        'description': f'{prefix} - وصف النشاط التجريبي',
        'start_date': date.today().strftime('%Y-%m-%d'),
        'end_date': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
        'expected_participants': 20,
        'price_per_student': '50',
        'location': f'{prefix}_قاعة الأنشطة',
        'max_participants': 25,
        'registration_deadline': (date.today() + timedelta(days=7)).strftime('%Y-%m-%d'),
        'notes': f'{prefix} - ملاحظات تجريبية'
    }
    
    # Add activity_type if provided
    if activity_type:
        form_data['activity_type'] = activity_type.id
    
    # Add supervisor if provided
    if supervisor:
        form_data['supervisor'] = supervisor.id
    
    return form_data


def prepare_activity_enrollment_form_data(student, prefix="E2E"):
    """
    Prepare form data for activity enrollment POST request
    
    Args:
        student: Student instance
        prefix: Prefix for test data
    
    Returns:
        Dictionary matching the actual ActivityEnrollmentForm fields
    """
    form_data = {
        'student': student.id,
        'parent_consent': True,
        'notes': f'{prefix} - تسجيل تجريبي في النشاط'
    }
    
    return form_data


def prepare_employee_creation_form_data(department=None, job_title=None, prefix="E2E"):
    """
    Prepare form data for employee creation POST request
    
    Args:
        department: Department instance (optional)
        job_title: JobTitle instance (optional)
        prefix: Prefix for test data
    
    Returns:
        Dictionary matching the actual EmployeeForm fields
    """
    generator = DataGenerator(prefix)
    
    # Generate employee data
    first_names = ['أحمد', 'محمد', 'علي', 'حسن', 'خالد']
    last_names = ['محمد', 'أحمد', 'علي', 'حسن', 'إبراهيم']
    
    first_name = random.choice(first_names)
    last_name = random.choice(last_names)
    
    # Birth date for employee (25-50 years old)
    today = date.today()
    birth_date = today - relativedelta(years=random.randint(25, 50), months=random.randint(0, 11))
    
    form_data = {
        # Employee number will be auto-generated
        'employee_number': '',
        
        # Basic information
        'name': f'{first_name} {last_name}',  # Pure Arabic name without prefix
        'national_id': generator.generate_national_id(),
        'birth_date': birth_date.strftime('%Y-%m-%d'),
        'gender': random.choice(['male', 'female']),  # Fixed: use 'male'/'female' not 'M'/'F'
        'marital_status': random.choice(['single', 'married']),
        'military_status': 'completed',
        
        # Contact information
        'personal_email': f'{prefix.lower()}_employee@test.com',
        'work_email': '',
        'mobile_phone': generator.generate_phone_number(),
        'home_phone': '',
        'address': f'{prefix}_شارع التجريب، المنصورة، مصر',
        'city': 'المنصورة',
        'postal_code': '35511',
        
        # Emergency contact
        'emergency_contact_name': f'{prefix}_جهة اتصال طوارئ',
        'emergency_contact_relation': 'أخ',
        'emergency_contact_phone': generator.generate_phone_number(),
        
        # Employment information
        'hire_date': date.today().strftime('%Y-%m-%d'),
        'employment_type': 'full_time',
        'biometric_user_id': '',
        'direct_manager': ''
    }
    
    # Add department if provided
    if department:
        form_data['department'] = department.id
    
    # Add job_title if provided
    if job_title:
        form_data['job_title'] = job_title.id
    
    return form_data


def prepare_purchase_order_form_data(supplier, warehouse, products_data, prefix="E2E"):
    """
    Prepare form data for purchase order creation POST request
    
    Args:
        supplier: Supplier instance
        warehouse: Warehouse instance
        products_data: List of dicts with keys: product (Product instance), quantity, unit_price
        prefix: Prefix for test data
    
    Returns:
        Dictionary matching the actual PurchaseForm fields
    """
    # Calculate totals
    subtotal = Decimal('0.00')
    for item in products_data:
        quantity = Decimal(str(item['quantity']))
        unit_price = Decimal(str(item['unit_price']))
        subtotal += quantity * unit_price
    
    # Generate purchase number
    import time
    purchase_number = f'PUR{int(time.time()) % 10000}'
    
    # Base form data
    form_data = {
        'number': purchase_number,
        'date': date.today().strftime('%Y-%m-%d'),
        'supplier': supplier.id,
        'warehouse': warehouse.id,
        'payment_method': 'credit',  # Default to credit (آجل)
        'discount': '0.00',
        'tax': '0.00',
        'notes': f'{prefix} - فاتورة شراء تجريبية',
        'subtotal': str(subtotal),
        'total': str(subtotal)
    }
    
    # Add product items as arrays (matching the view's expected format)
    product_ids = []
    quantities = []
    unit_prices = []
    discounts = []
    
    for item in products_data:
        product_ids.append(str(item['product'].id))
        quantities.append(str(item['quantity']))
        unit_prices.append(str(item['unit_price']))
        discounts.append('0.00')  # No discount by default
    
    form_data['product[]'] = product_ids
    form_data['quantity[]'] = quantities
    form_data['unit_price[]'] = unit_prices
    form_data['discount[]'] = discounts
    
    return form_data


def prepare_purchase_payment_form_data(purchase, amount=None, financial_account=None, prefix="E2E"):
    """
    Prepare form data for purchase payment POST request
    
    Args:
        purchase: Purchase instance
        amount: Payment amount (defaults to total amount)
        financial_account: ChartOfAccounts instance for payment (optional)
        prefix: Prefix for test data
    
    Returns:
        Dictionary matching the actual PurchasePaymentForm fields
    """
    if amount is None:
        amount = purchase.total
    
    form_data = {
        'amount': str(amount),
        'payment_date': date.today().strftime('%Y-%m-%d'),
        'payment_method': 'cash',
        'notes': f'{prefix} - دفعة تجريبية للمورد',
        'reference_number': f'{prefix}_PPAY_{uuid.uuid4().hex[:8].upper()}'
    }
    
    # Add financial account if provided
    if financial_account:
        form_data['financial_account'] = financial_account.id
    
    return form_data


def prepare_product_request_form_data(student, product, quantity=1, prefix="E2E"):
    """
    Prepare form data for product request POST request
    
    Args:
        student: Student instance
        product: Product instance
        quantity: Requested quantity (default: 1)
        prefix: Prefix for test data
    
    Returns:
        Dictionary matching the actual ProductRequestForm fields
    """
    form_data = {
        'student': student.id,
        'product': product.id,
        'quantity': quantity,
        'request_type': 'additional',
        'notes': f'{prefix} - طلب منتج تجريبي'
    }
    
    return form_data


def prepare_sale_form_data(student, items, prefix="E2E"):
    """
    Prepare form data for sale creation POST request
    
    Args:
        student: Student instance (optional, can be None for general sales)
        items: List of dicts with keys: product (Product instance), quantity, unit_price
        prefix: Prefix for test data
    
    Returns:
        Dictionary matching the actual SaleForm fields
    """
    import time
    
    # Calculate totals
    subtotal = Decimal('0.00')
    for item in items:
        quantity = Decimal(str(item['quantity']))
        unit_price = Decimal(str(item['unit_price']))
        subtotal += quantity * unit_price
    
    # Generate sale number
    sale_number = f'SALE{int(time.time()) % 10000}'
    
    # Base form data
    form_data = {
        'number': sale_number,
        'date': date.today().strftime('%Y-%m-%d'),
        'discount': '0.00',
        'tax': '0.00',
        'notes': f'{prefix} - عملية بيع تجريبية',
        'subtotal': str(subtotal),
        'total': str(subtotal)
    }
    
    # Add student if provided
    if student:
        form_data['student'] = student.id
    
    # Add product items as arrays
    product_ids = []
    quantities = []
    unit_prices = []
    discounts = []
    
    for item in items:
        product_ids.append(str(item['product'].id))
        quantities.append(str(item['quantity']))
        unit_prices.append(str(item['unit_price']))
        discounts.append('0.00')
    
    form_data['product[]'] = product_ids
    form_data['quantity[]'] = quantities
    form_data['unit_price[]'] = unit_prices
    form_data['discount[]'] = discounts
    
    return form_data


def prepare_sale_payment_form_data(sale, amount=None, prefix="E2E"):
    """
    Prepare form data for sale payment POST request
    
    Args:
        sale: Sale instance
        amount: Payment amount (defaults to total amount)
        prefix: Prefix for test data
    
    Returns:
        Dictionary matching the actual SalePaymentForm fields
    """
    if amount is None:
        amount = sale.total
    
    form_data = {
        'amount': str(amount),
        'payment_date': date.today().strftime('%Y-%m-%d'),
        'payment_method': 'cash',
        'notes': f'{prefix} - دفعة تجريبية للبيع',
        'reference_number': f'{prefix}_SPAY_{uuid.uuid4().hex[:8].upper()}'
    }
    
    return form_data



def prepare_activity_expense_form_data(activity, amount=None, prefix="E2E"):
    """
    Prepare form data for activity expense creation POST request
    
    Args:
        activity: Activity instance
        amount: Expense amount (default: 200.00)
        prefix: Prefix for test data
    
    Returns:
        Dictionary matching the actual ActivityExpenseForm fields
    """
    if amount is None:
        amount = Decimal('200.00')
    
    form_data = {
        'name': f'{prefix}_تكاليف تشغيل النشاط',
        'category': 'equipment',
        'amount': str(amount),
        'expense_date': date.today().strftime('%Y-%m-%d'),
        'payment_method': 'cash',
        'description': f'{prefix} - تكاليف تشغيل النشاط',
        'notes': f'{prefix} - مصروف تجريبي',
        'reference_number': f'{prefix}_EXP_{uuid.uuid4().hex[:8].upper()}'
    }
    
    return form_data


def prepare_contract_creation_form_data(employee, basic_salary, prefix="E2E"):
    """
    Prepare form data for contract creation POST request
    
    Args:
        employee: Employee instance
        basic_salary: Decimal - basic salary amount
        prefix: Prefix for test data
    
    Returns:
        Dictionary matching the actual ContractForm fields
    """
    from datetime import date
    from dateutil.relativedelta import relativedelta
    
    start_date = employee.hire_date if hasattr(employee, 'hire_date') else date.today()
    end_date = start_date + relativedelta(years=1)
    
    form_data = {
        'employee': employee.id,
        'contract_number': f'{prefix}_CON_{int(time.time() % 100000)}',
        'contract_type': 'permanent',
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'basic_salary': str(basic_salary),
        'housing_allowance': '0',
        'transportation_allowance': '0',
        'other_allowances': '0',
        'status': 'active',
        'notes': f'{prefix} - عقد عمل تجريبي',
        # Additional required fields
        'increase_frequency': 'annual',  # Valid choices: annual, semi_annual
        'increase_start_reference': 'contract_date',  # Valid choices: contract_date, january
        'contract_duration': '12',  # 12 months
    }
    
    return form_data


def prepare_attendance_checkin_form_data(employee, shift, attendance_date, prefix="E2E"):
    """
    Prepare form data for attendance check-in POST request
    
    Args:
        employee: Employee instance
        shift: Shift instance
        attendance_date: date - attendance date
        prefix: Prefix for test data
    
    Returns:
        Dictionary matching the actual attendance_check_in view fields
    """
    form_data = {
        'employee_id': employee.id,
        'shift_id': shift.id if shift else '',
    }
    
    return form_data


def prepare_attendance_checkout_form_data(attendance, shift, prefix="E2E"):
    """
    Prepare form data for attendance check-out POST request
    
    Args:
        attendance: Attendance instance
        shift: Shift instance
        prefix: Prefix for test data
    
    Returns:
        Dictionary matching the actual attendance_check_out view fields
    """
    form_data = {
        'employee_id': attendance.employee.id,
    }
    
    return form_data
    
    check_out_time = datetime.combine(attendance.date, end_time_obj)
    
    form_data = {
        'check_out': check_out_time.strftime('%Y-%m-%d %H:%M:%S')
    }
    
    return form_data


def prepare_advance_request_form_data(employee, amount, installments_count, prefix="E2E"):
    """
    Prepare form data for advance request POST request
    
    Args:
        employee: Employee instance
        amount: Decimal - advance amount
        installments_count: int - number of installments
        prefix: Prefix for test data
    
    Returns:
        Dictionary matching the actual AdvanceForm fields
    """
    from datetime import date
    from dateutil.relativedelta import relativedelta
    
    deduction_start = date.today().replace(day=1) + relativedelta(months=1)
    
    form_data = {
        'employee': employee.id,
        'amount': str(amount),
        'reason': f'{prefix} - سلفة لظروف طارئة - اختبار النظام',
        'installments_count': str(installments_count),
        'deduction_start_month': deduction_start.strftime('%Y-%m'),  # Format: YYYY-MM (not YYYY-MM-DD)
    }
    
    return form_data
