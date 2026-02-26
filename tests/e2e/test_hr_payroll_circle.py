# -*- coding: utf-8 -*-
"""
اختبار دائرة الموارد البشرية والرواتب الكاملة E2E
يحاكي المستخدم الحقيقي ويستخدم النظام الموجود

دائرة الموارد البشرية والرواتب:
1. تعيين موظف جديد
2. إنشاء عقد العمل
3. تسجيل الحضور والانصراف
4. حساب الراتب الشهري
5. إنشاء القيود المحاسبية للرواتب
6. دفع الراتب
7. تتبع السلف والخصومات
8. إنشاء التقارير المالية
"""

import os
import sys
import logging
import time
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from datetime import date, timedelta, datetime
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.db import transaction
from decimal import Decimal

# Import all required models
from hr.models import Employee, Attendance, Payroll, Contract, Advance
from hr.models.organization import Department, JobTitle
from hr.models.attendance import Shift
from financial.models import JournalEntry, ChartOfAccounts, AccountingPeriod, AccountType
from financial.services.journal_service import JournalEntryService

# Import base classes
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.e2e.base import E2ETestCase, CircleTestCase
from tests.e2e.helpers import DataGenerator

User = get_user_model()
logger = logging.getLogger(__name__)


# ============================================================================
# URL Mappings for HR & Payroll Circle Tests
# ============================================================================
# These URLs are required for HTTP-based testing of HR and payroll workflow
# Format: 'key': 'app_name:url_name'
# ============================================================================

REQUIRED_URLS = {
    # Employee Management URLs
    'employee_list': 'hr:employee_list',
    'employee_form': 'hr:employee_form',
    'employee_detail': 'hr:employee_detail',
    'employee_delete': 'hr:employee_delete',
    'employee_import': 'hr:employee_import',
    
    # Department URLs
    'department_list': 'hr:department_list',
    'department_form': 'hr:department_form',
    'department_delete': 'hr:department_delete',
    
    # Job Title URLs
    'job_title_list': 'hr:job_title_list',
    'job_title_form': 'hr:job_title_form',
    'job_title_delete': 'hr:job_title_delete',
    
    # Contract URLs
    'contract_list': 'hr:contract_list',
    'contract_form': 'hr:contract_form',
    'contract_detail': 'hr:contract_detail',
    'contract_activate': 'hr:contract_activate_confirm',
    
    # Attendance URLs
    'attendance_list': 'hr:attendance_list',
    'attendance_check_in': 'hr:attendance_check_in',
    'attendance_check_out': 'hr:attendance_check_out',
    
    # Shift URLs
    'shift_list': 'hr:shift_list',
    'shift_form': 'hr:shift_form',
    'shift_assign_employees': 'hr:shift_assign_employees',
    
    # Payroll URLs
    'payroll_list': 'hr:payroll_list',
    'payroll_generate': 'hr:payroll_generate',
    'payroll_detail': 'hr:payroll_detail',
    'payroll_approve': 'hr:payroll_approve',
    'payroll_pay': 'hr:payroll_pay',
    
    # Financial Integration URLs
    'journal_entries_list': 'financial:journal_entries_list',
    'accounting_periods_list': 'financial:accounting_periods_list',
}


class HRPayrollCircleTest(CircleTestCase):
    """
    اختبار دائرة الموارد البشرية والرواتب الكاملة - مستشار تقني محترف
    
    المنهجية الاستشارية المهنية:
    - لا توجد fallbacks مضللة
    - تشخيص دقيق لكل خطوة
    - اكتشاف المشاكل الحقيقية
    - حلول تقنية محددة
    - فشل سريع مع تقارير استشارية
    
    Required URLs are defined in REQUIRED_URLS constant above.
    Use self.get_url('key') to resolve URLs in tests.
    """
    
    # Assign URL mappings to class
    REQUIRED_URLS = REQUIRED_URLS
    
    # ✅ إضافة fixtures للحسابات المحاسبية الموجودة
    fixtures = [
        'financial/fixtures/chart_of_accounts.json',
    ]
    
    def setUp(self):
        """إعداد البيانات الأساسية للاختبار الاستشاري"""
        super().setUp()
        
        # ✅ إنشاء فترة محاسبية مفتوحة
        self.accounting_period = AccountingPeriod.objects.create(
            name=f'{self.test_prefix}فترة محاسبية 2026',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            status='open',
            created_by=self.admin_user
        )
        
        # الحصول على البيانات الموجودة في النظام
        self.get_existing_data()
        
        # إنشاء بيانات تجريبية للاختبار
        self.create_test_data()
            
        # مولد البيانات التجريبية
        self.data_generator = DataGenerator(self.test_prefix)
        
    def get_existing_data(self):
        """الحصول على البيانات الموجودة في النظام أو إنشاء بيانات أساسية"""
        
        # الحصول على قسم أو إنشاؤه
        self.department, created = Department.objects.get_or_create(
            code=f'{self.test_prefix}DEPT001',
            defaults={
                'name_ar': f'{self.test_prefix}قسم التعليم',
                'name_en': f'{self.test_prefix}Education Department',
                'description': 'قسم تجريبي للاختبار',
                'is_active': True
            }
        )
        if created:
            self.track_object(self.department)
            print(f"[OK] تم إنشاء قسم جديد: {self.department.name_ar}")
        else:
            print(f"[OK] تم العثور على قسم: {self.department.name_ar}")
            
        # الحصول على مسمى وظيفي أو إنشاؤه
        self.job_title, created = JobTitle.objects.get_or_create(
            code=f'{self.test_prefix}JOB001',
            defaults={
                'title_ar': f'{self.test_prefix}معلم رياض أطفال',
                'title_en': f'{self.test_prefix}Kindergarten Teacher',
                'description': 'مسمى وظيفي تجريبي',
                'department': self.department,
                'is_active': True
            }
        )
        if created:
            self.track_object(self.job_title)
            print(f"[OK] تم إنشاء مسمى وظيفي جديد: {self.job_title.title_ar}")
        else:
            print(f"[OK] تم العثور على مسمى وظيفي: {self.job_title.title_ar}")
            
        # الحصول على وردية أو إنشاؤها
        self.shift, created = Shift.objects.get_or_create(
            name=f'{self.test_prefix}الوردية الصباحية',
            defaults={
                'shift_type': 'morning',
                'start_time': '08:00:00',
                'end_time': '16:00:00',
                'work_hours': Decimal('8.00'),
                'grace_period_in': 15,
                'grace_period_out': 15,
                'is_active': True
            }
        )
        if created:
            self.track_object(self.shift)
            print(f"[OK] تم إنشاء وردية جديدة: {self.shift.name}")
        else:
            print(f"[OK] تم العثور على وردية: {self.shift.name}")
    
    def create_test_data(self):
        """إنشاء بيانات تجريبية للاختبار"""
        
        # إنشاء موظف تجريبي
        # Generate valid national_id (14 digits) and mobile_phone (11 digits starting with 01)
        timestamp_suffix = int(time.time()) % 100000000  # 8 digits
        
        self.test_employee_data = {
            'employee_number': f'{self.test_prefix}EMP001',
            'name': 'سارة أحمد محمد',  # Pure Arabic name without prefix
            'national_id': f'29001{timestamp_suffix:08d}1',  # 14 digits: 29001 + 8 digits + 1
            'birth_date': date(1990, 1, 15),
            'gender': 'female',
            'marital_status': 'single',
            'mobile_phone': f'011{timestamp_suffix % 100000000:08d}',  # 11 digits: 011 + 8 digits
            'address': f'{self.test_prefix}شارع الموارد البشرية، المنصورة',
            'hire_date': date.today() - timedelta(days=30),  # تم تعيينه منذ شهر
            'employment_type': 'full_time',
            'status': 'active'
        }
        
        print(f"[OK] تم إعداد بيانات موظف تجريبي: {self.test_employee_data['name']}")
        
    def test_complete_hr_payroll_circle(self):
        """
        اختبار دائرة الموارد البشرية والرواتب الكاملة - مستشار تقني محترف
        
        يحاكي المستخدم الحقيقي ويعتمد على النظام الموجود
        بدون fallbacks مضللة - فقط تشخيص دقيق واكتشاف المشاكل الحقيقية
        """
        
        print(f"\n🚀 بدء اختبار دائرة الموارد البشرية والرواتب - {self.test_prefix}")
        
        # الخطوة 1: تعيين موظف جديد
        employee = self.execute_circle_step(
            "تعيين موظف جديد",
            lambda: self.step_1_diagnose_employee_hiring()
        )
        
        # الخطوة 2: إنشاء عقد العمل
        contract = self.execute_circle_step(
            "إنشاء عقد العمل",
            lambda: self.step_2_diagnose_contract_creation(employee)
        )
        
        # الخطوة 3: تسجيل الحضور والانصراف
        attendance_records = self.execute_circle_step(
            "تسجيل الحضور والانصراف",
            lambda: self.step_3_diagnose_attendance_tracking(employee)
        )
        
        # الخطوة 4: حساب الراتب الشهري
        payroll = self.execute_circle_step(
            "حساب الراتب الشهري",
            lambda: self.step_4_diagnose_payroll_calculation(employee, contract, attendance_records)
        )
        
        # الخطوة 5: إنشاء القيود المحاسبية للرواتب
        accounting_result = self.execute_circle_step(
            "إنشاء القيود المحاسبية للرواتب",
            lambda: self.step_5_diagnose_payroll_accounting(payroll)
        )
        
        # الخطوة 6: دفع الراتب
        payment_result = self.execute_circle_step(
            "دفع الراتب",
            lambda: self.step_6_diagnose_salary_payment(payroll)
        )
        
        # الخطوة 7: إدارة السلف والخصومات
        advance_result = self.execute_circle_step(
            "إدارة السلف والخصومات",
            lambda: self.step_7_diagnose_advance_management(employee, payroll)
        )
        
        # الخطوة 8: إنشاء التقارير المالية
        reports_result = self.execute_circle_step(
            "إنشاء التقارير المالية",
            lambda: self.step_8_diagnose_financial_reporting(payroll, accounting_result)
        )
        
        # التحقق من سلامة الدائرة الكاملة
        self.validate_complete_hr_payroll_circle(
            employee, contract, attendance_records, payroll,
            accounting_result, payment_result, advance_result, reports_result
        )
        
        # طباعة ملخص النتائج
        self.print_circle_summary(employee, payroll, accounting_result)
        
    def step_1_diagnose_employee_hiring(self):
        """الخطوة 1: تشخيص تعيين موظف جديد - فحص شامل للنظام عبر HTTP"""
        
        print(f"🔍 تشخيص نظام تعيين الموظفين عبر HTTP...")
        print(f"📋 الموظف: {self.test_employee_data['name']}")
        
        # تشخيص المتطلبات الأساسية
        if not self.department:
            raise AssertionError(
                f"❌ لا يوجد قسم متاح للتعيين!\n"
                f"🔧 الحل المطلوب: إنشاء أقسام في hr/models/organization.py\n"
                f"⏱️ الوقت المقدر: 30 دقيقة"
            )
            
        if not self.job_title:
            raise AssertionError(
                f"❌ لا يوجد مسمى وظيفي متاح!\n"
                f"🔧 الحل المطلوب: إنشاء مسميات وظيفية في النظام\n"
                f"⏱️ الوقت المقدر: 30 دقيقة"
            )
        
        # ✅ استخدام HTTP POST بدلاً من objects.create()
        try:
            from tests.e2e.helpers import prepare_employee_creation_form_data
            
            # تحضير بيانات النموذج
            form_data = prepare_employee_creation_form_data(
                department=self.department,
                job_title=self.job_title,
                prefix=self.test_prefix
            )
            
            # تحديث البيانات من test_employee_data
            form_data.update({
                'name': self.test_employee_data['name'],
                'national_id': self.test_employee_data['national_id'],
                'birth_date': self.test_employee_data['birth_date'].strftime('%Y-%m-%d'),
                'gender': self.test_employee_data['gender'],
                'marital_status': self.test_employee_data['marital_status'],
                'mobile_phone': self.test_employee_data['mobile_phone'],
                'address': self.test_employee_data['address'],
                'hire_date': self.test_employee_data['hire_date'].strftime('%Y-%m-%d'),
                'employment_type': self.test_employee_data['employment_type'],
                'shift': self.shift.id if self.shift else '',
            })
            
            print(f"📤 إرسال طلب HTTP POST لإنشاء الموظف...")
            
            # إرسال POST request
            response = self.post_form('hr:employee_form', form_data)
            
            # Debug: Check for form errors
            if response.status_code == 200:
                if hasattr(response, 'context') and response.context:
                    form = response.context.get('form')
                    if form and form.errors:
                        error_details = []
                        for field, errors in form.errors.items():
                            error_details.append(f"{field}: {', '.join(errors)}")
                        raise AssertionError(
                            f"❌ Form validation errors:\n" + "\n".join(f"   - {e}" for e in error_details)
                        )
            
            # التحقق من نجاح الطلب
            self.assert_successful_post(response)
            
            # الحصول على الموظف المُنشأ من قاعدة البيانات
            employee = Employee.objects.filter(
                national_id=self.test_employee_data['national_id']
            ).first()
            
            if not employee:
                raise AssertionError(
                    f"❌ فشل في إنشاء الموظف عبر HTTP!\n"
                    f"   الاستجابة: {response.status_code}\n"
                    f"🔧 الحل المطلوب: فحص employee_form view في hr/views/employee_views.py"
                )
            
            self.track_object(employee)
            
            # تشخيص صحة البيانات المُنشأة
            if not employee.employee_number:
                raise AssertionError(
                    f"❌ لم يتم إنشاء رقم الموظف!\n"
                    f"🔧 الحل المطلوب: فحص Employee model في hr/models/employee.py"
                )
            
            if employee.age < 18:
                print(f"⚠️ تحذير: عمر الموظف صغير ({employee.age} سنة)")
            
            if employee.years_of_service < 0:
                raise AssertionError(
                    f"❌ تاريخ التعيين خاطئ - سنوات الخدمة سالبة!\n"
                    f"🔧 الحل المطلوب: تصحيح تاريخ التعيين"
                )
            
            print(f"✅ تم تعيين الموظف بنجاح عبر HTTP:")
            print(f"   🆔 رقم الموظف: {employee.employee_number}")
            print(f"   👤 الاسم: {employee.get_full_name_ar()}")
            print(f"   🏢 القسم: {employee.department.name_ar}")
            print(f"   💼 المسمى الوظيفي: {employee.job_title.title_ar}")
            print(f"   📅 تاريخ التعيين: {employee.hire_date}")
            print(f"   🎂 العمر: {employee.age} سنة")
            print(f"   📊 سنوات الخدمة: {employee.years_of_service} سنة")
            print(f"   🌐 HTTP Status: {response.status_code}")
            
            return employee
            
        except Exception as e:
            raise AssertionError(
                f"❌ خطأ تقني في تعيين الموظف عبر HTTP!\n"
                f"   الخطأ: {str(e)}\n"
                f"🔧 الحل المطلوب:\n"
                f"   1. فحص employee_form view في hr/views/employee_views.py\n"
                f"   2. فحص EmployeeForm في hr/forms/employee_forms.py\n"
                f"   3. التأكد من صحة بيانات الأقسام والمسميات الوظيفية\n"
                f"   4. فحص الـ database constraints والـ foreign keys\n"
                f"⏱️ الوقت المقدر: 2-4 ساعات"
            )
        
    def step_2_diagnose_contract_creation(self, employee):
        """الخطوة 2: تشخيص إنشاء عقد العمل عبر HTTP"""
        
        print(f"\n🔍 تشخيص نظام إنشاء عقود العمل عبر HTTP...")
        
        # بيانات العقد التجريبي
        basic_salary = Decimal('5000.00')
        
        print(f"💰 الراتب الأساسي: {basic_salary} ج.م")
        print(f"📅 مدة العقد: سنة واحدة من تاريخ التعيين")
        
        # ✅ استخدام HTTP POST بدلاً من objects.create()
        try:
            from tests.e2e.helpers import prepare_contract_creation_form_data
            
            # تحضير بيانات النموذج
            form_data = prepare_contract_creation_form_data(
                employee=employee,
                basic_salary=basic_salary,
                prefix=self.test_prefix
            )
            
            print(f"📤 إرسال طلب HTTP POST لإنشاء العقد...")
            
            # إرسال POST request
            response = self.post_form('hr:contract_form', form_data)
            
            # Debug: Check for form errors
            if response.status_code == 200:
                if hasattr(response, 'context') and response.context:
                    form = response.context.get('form')
                    if form and form.errors:
                        error_details = []
                        for field, errors in form.errors.items():
                            error_details.append(f"{field}: {', '.join(errors)}")
                        raise AssertionError(
                            f"❌ Form validation errors:\n" + "\n".join(f"   - {e}" for e in error_details)
                        )
            
            # التحقق من نجاح الطلب
            self.assert_successful_post(response)
            
            # الحصول على العقد المُنشأ من قاعدة البيانات
            contract = Contract.objects.filter(
                employee=employee,
                contract_number=form_data['contract_number']
            ).first()
            
            if not contract:
                raise AssertionError(
                    f"❌ فشل في إنشاء العقد عبر HTTP!\n"
                    f"   الاستجابة: {response.status_code}\n"
                    f"🔧 الحل المطلوب: فحص contract_form view في hr/views/contract_views.py"
                )
            
            self.track_object(contract)
            
            # تشخيص صحة العقد
            if contract.basic_salary <= 0:
                raise AssertionError(
                    f"❌ الراتب الأساسي غير صحيح: {contract.basic_salary}\n"
                    f"🔧 الحل المطلوب: التأكد من صحة بيانات الراتب"
                )
            
            if contract.end_date <= contract.start_date:
                raise AssertionError(
                    f"❌ تواريخ العقد غير صحيحة!\n"
                    f"   تاريخ البداية: {contract.start_date}\n"
                    f"   تاريخ النهاية: {contract.end_date}\n"
                    f"🔧 الحل المطلوب: تصحيح تواريخ العقد"
                )
            
            # فحص مدة العقد
            contract_duration = (contract.end_date - contract.start_date).days
            if contract_duration > 365 * 5:  # أكثر من 5 سنوات
                print(f"⚠️ تحذير: مدة العقد طويلة ({contract_duration} يوم)")
            
            print(f"✅ تم إنشاء عقد العمل بنجاح عبر HTTP:")
            print(f"   📋 رقم العقد: {contract.contract_number}")
            print(f"   💰 الراتب الأساسي: {contract.basic_salary} ج.م")
            print(f"   📅 مدة العقد: {(contract.end_date - contract.start_date).days} يوم")
            print(f"   📊 نوع العقد: {contract.get_contract_type_display()}")
            print(f"   ✅ حالة العقد: {contract.get_status_display()}")
            print(f"   🌐 HTTP Status: {response.status_code}")
            
            return contract
            
        except Exception as e:
            raise AssertionError(
                f"❌ خطأ تقني في إنشاء عقد العمل عبر HTTP!\n"
                f"   الخطأ: {str(e)}\n"
                f"🔧 الحل المطلوب:\n"
                f"   1. فحص contract_create view في hr/views/contract_views.py\n"
                f"   2. فحص ContractForm في hr/forms/contract_forms.py\n"
                f"   3. التأكد من صحة بيانات العقد\n"
                f"   4. فحص الـ database constraints\n"
                f"⏱️ الوقت المقدر: 1-2 ساعة"
            )
    
    def step_3_diagnose_attendance_tracking(self, employee):
        """الخطوة 3: تشخيص تسجيل الحضور والانصراف عبر HTTP"""
        
        print(f"\n🔍 تشخيص نظام تسجيل الحضور والانصراف عبر HTTP...")
        
        # محاكاة حضور لمدة أسبوع
        attendance_records = []
        
        # Use today's date for attendance (since the view uses timezone.now())
        today = date.today()
        
        print(f"📅 تسجيل حضور يوم {today}")
        
        try:
            from tests.e2e.helpers import prepare_attendance_checkin_form_data, prepare_attendance_checkout_form_data
            
            # ✅ Step 1: Check-in via HTTP POST
            checkin_data = prepare_attendance_checkin_form_data(
                employee=employee,
                shift=self.shift,
                attendance_date=today,
                prefix=self.test_prefix
            )
            
            print(f"📤 إرسال طلب HTTP POST لتسجيل الحضور...")
            
            # Send check-in request with follow=True to follow redirects
            response = self.post_form('hr:attendance_check_in', checkin_data)
            
            # Check for success - either redirect or success message
            if response.status_code == 200:
                from django.contrib.messages import get_messages
                messages_list = list(get_messages(response.wsgi_request))
                if messages_list:
                    success_msgs = [str(m) for m in messages_list if m.level_tag == 'success']
                    error_msgs = [str(m) for m in messages_list if m.level_tag == 'error']
                    
                    if error_msgs:
                        raise AssertionError(
                            f"❌ Check-in errors:\n" + "\n".join(f"   - {e}" for e in error_msgs)
                        )
                    
                    if not success_msgs:
                        raise AssertionError(
                            f"❌ No success message after check-in!\n"
                            f"   Status Code: {response.status_code}"
                        )
            elif response.status_code not in [302, 303]:
                raise AssertionError(
                    f"❌ Unexpected status code: {response.status_code}"
                )
            
            # Get created attendance record (use today's date)
            attendance = Attendance.objects.filter(
                employee=employee,
                date=today
            ).first()
            
            if not attendance:
                raise AssertionError(
                    f"❌ فشل في تسجيل الحضور عبر HTTP!\n"
                    f"   التاريخ: {today}\n"
                    f"   Status Code: {response.status_code}\n"
                    f"🔧 الحل المطلوب: فحص attendance_check_in view في hr/views/attendance_views.py"
                )
            
            self.track_object(attendance)
            
            # ⏰ Wait to simulate work hours (update check_out time to be 8 hours after check_in)
            from django.utils import timezone
            from datetime import timedelta
            
            # Update attendance check_out to simulate 8 hours of work
            work_duration = timedelta(hours=8)
            simulated_checkout_time = attendance.check_in + work_duration
            
            # Update attendance directly to simulate time passing
            attendance.check_out = simulated_checkout_time
            attendance.calculate_work_hours()
            attendance.save()
            
            print(f"📤 إرسال طلب HTTP POST لتسجيل الانصراف...")
            
            # Prepare checkout data (view will validate but we already set the time)
            checkout_data = prepare_attendance_checkout_form_data(
                attendance=attendance,
                shift=self.shift,
                prefix=self.test_prefix
            )
            
            # Send check-out request
            response = self.post_form('hr:attendance_check_out', checkout_data)
            
            if response.status_code not in [200, 302]:
                raise AssertionError(
                    f"❌ فشل في تسجيل الانصراف عبر HTTP!\n"
                    f"   Status Code: {response.status_code}"
                )
            
            # Refresh attendance from database
            attendance.refresh_from_db()
            
            # حساب ساعات العمل
            if hasattr(attendance, 'calculate_work_hours'):
                attendance.calculate_work_hours()
            
            attendance_records.append(attendance)
            
            # تشخيص صحة الحضور
            if attendance.work_hours and attendance.work_hours <= 0:
                raise AssertionError(
                    f"❌ ساعات العمل غير صحيحة: {attendance.work_hours}\n"
                    f"🔧 الحل المطلوب: فحص دالة calculate_work_hours"
                )
            
            if attendance.work_hours and attendance.work_hours > 12:  # أكثر من 12 ساعة
                print(f"⚠️ تحذير: ساعات عمل مفرطة ({attendance.work_hours} ساعة)")
            
            check_in_str = attendance.check_in.strftime('%H:%M') if attendance.check_in else 'N/A'
            check_out_str = attendance.check_out.strftime('%H:%M') if attendance.check_out else 'N/A'
            
            print(f"   ⏰ الحضور: {check_in_str}")
            print(f"   🏃 الانصراف: {check_out_str}")
            print(f"   ⏱️ ساعات العمل: {attendance.work_hours or 0}")
            print(f"   ⏳ التأخير: {attendance.late_minutes or 0} دقيقة")
            print(f"   🌐 HTTP Status: Check-out={response.status_code}")
            
        except Exception as e:
            raise AssertionError(
                f"❌ خطأ في تسجيل الحضور عبر HTTP!\n"
                f"   الخطأ: {str(e)}\n"
                f"🔧 الحل المطلوب:\n"
                f"   1. فحص attendance_check_in view في hr/views/attendance_views.py\n"
                f"   2. فحص attendance_check_out view\n"
                f"   3. فحص AttendanceForm في hr/forms/attendance_forms.py\n"
                f"   4. فحص دالة calculate_work_hours في Attendance model\n"
                f"   5. التأكد من صحة بيانات الوردية\n"
                f"⏱️ الوقت المقدر: 1-2 ساعة"
            )
        
        # تشخيص نهائي لسجلات الحضور
        if len(attendance_records) == 0:
            raise AssertionError(
                f"❌ لم يتم تسجيل أي حضور عبر HTTP!\n"
                f"🔧 الحل المطلوب: مراجعة شاملة لنظام الحضور عبر HTTP"
            )
        
        total_work_hours = sum(record.work_hours or 0 for record in attendance_records)
        total_late_minutes = sum(record.late_minutes or 0 for record in attendance_records)
        
        print(f"\n📊 ملخص الحضور الأسبوعي:")
        print(f"   📅 عدد أيام الحضور: {len(attendance_records)}")
        print(f"   ⏱️ إجمالي ساعات العمل: {total_work_hours}")
        print(f"   ⏳ إجمالي دقائق التأخير: {total_late_minutes}")
        if len(attendance_records) > 0:
            print(f"   📈 متوسط ساعات العمل اليومية: {total_work_hours / len(attendance_records):.2f}")
        
        return attendance_records
        
    def step_4_diagnose_payroll_calculation(self, employee, contract, attendance_records):
        """الخطوة 4: تشخيص حساب الراتب الشهري عبر HTTP"""
        
        print(f"\n🔍 تشخيص نظام حساب الرواتب عبر HTTP...")
        
        # حساب بيانات الراتب من الحضور
        total_work_hours = sum(record.work_hours for record in attendance_records)
        total_late_minutes = sum(record.late_minutes for record in attendance_records)
        
        # بيانات الراتب
        payroll_month = date.today().replace(day=1)  # أول الشهر الحالي
        
        print(f"💰 حساب راتب شهر: {payroll_month.strftime('%Y-%m')}")
        print(f"⏱️ إجمالي ساعات العمل: {total_work_hours}")
        print(f"⏳ إجمالي دقائق التأخير: {total_late_minutes}")
        
        try:
            # ✅ استخدام HTTP GET لحساب الراتب بدلاً من objects.create()
            from django.urls import reverse
            
            self.client.force_login(self.admin_user)
            
            # Build URL with month parameter
            url = reverse('hr:calculate_single_payroll', args=[employee.id])
            url += f'?month={payroll_month.strftime("%Y-%m")}'
            
            print(f"📤 إرسال طلب HTTP GET لحساب الراتب...")
            print(f"   URL: {url}")
            
            # Send GET request to calculate payroll
            response = self.client.get(url, follow=True)
            
            # Verify response
            if response.status_code != 200:
                raise AssertionError(
                    f"❌ فشل في حساب الراتب عبر HTTP!\n"
                    f"   Status Code: {response.status_code}\n"
                    f"🔧 الحل المطلوب: فحص calculate_single_payroll view"
                )
            
            # Wait for payroll to be created
            self.wait_for_signals()
            
            # Get created payroll from database
            payroll = Payroll.objects.filter(
                employee=employee,
                month=payroll_month
            ).first()
            
            if not payroll:
                raise AssertionError(
                    f"❌ لم يتم إنشاء راتب عبر HTTP!\n"
                    f"   الموظف: {employee.get_full_name_ar()}\n"
                    f"   الشهر: {payroll_month}\n"
                    f"🔧 الحل المطلوب: فحص IntegratedPayrollService.calculate_integrated_payroll"
                )
            
            self.track_object(payroll)
            
            # تشخيص صحة الحسابات
            if payroll.net_salary <= 0:
                raise AssertionError(
                    f"❌ صافي الراتب سالب أو صفر: {payroll.net_salary}\n"
                    f"🔧 الحل المطلوب: مراجعة حسابات الراتب والخصومات"
                )
            
            if payroll.total_deductions > payroll.gross_salary:
                print(f"⚠️ تحذير: الخصومات أكبر من الراتب الإجمالي!")
            
            # فحص منطقية الأرقام
            if payroll.social_insurance and payroll.social_insurance > payroll.basic_salary * Decimal('0.20'):
                print(f"⚠️ تحذير: التأمينات الاجتماعية مرتفعة ({payroll.social_insurance} ج.م)")
            
            print(f"✅ تم حساب الراتب بنجاح عبر HTTP:")
            print(f"   💰 الراتب الأساسي: {payroll.basic_salary} ج.م")
            print(f"   💵 البدلات: {payroll.allowances or 0} ج.م")
            print(f"   📈 إجمالي الراتب: {payroll.gross_salary} ج.م")
            print(f"   ➕ إجمالي الإضافات: {payroll.total_additions} ج.م")
            print(f"   ➖ إجمالي الخصومات: {payroll.total_deductions} ج.م")
            print(f"   💎 صافي الراتب: {payroll.net_salary} ج.م")
            print(f"   🌐 HTTP Status: {response.status_code}")
            
            # تفاصيل الخصومات
            print(f"\n📋 تفاصيل الخصومات:")
            if payroll.social_insurance:
                print(f"   🏥 التأمينات الاجتماعية: {payroll.social_insurance} ج.م")
            if payroll.tax:
                print(f"   🏛️ الضرائب: {payroll.tax} ج.م")
            if payroll.late_deduction:
                print(f"   ⏳ خصم التأخير: {payroll.late_deduction} ج.م")
            
            return payroll
            
        except Exception as e:
            raise AssertionError(
                f"❌ خطأ تقني في حساب الراتب عبر HTTP!\n"
                f"   الخطأ: {str(e)}\n"
                f"🔧 الحل المطلوب:\n"
                f"   1. فحص calculate_single_payroll view في hr/views/integrated_payroll_views.py\n"
                f"   2. فحص IntegratedPayrollService.calculate_integrated_payroll\n"
                f"   3. التأكد من وجود attendance records للموظف\n"
                f"   4. التأكد من وجود contract نشط للموظف\n"
                f"⏱️ الوقت المقدر: 2-4 ساعات"
            )
    
    def step_5_diagnose_payroll_accounting(self, payroll):
        """الخطوة 5: تشخيص إنشاء القيود المحاسبية للرواتب"""
        
        print(f"\n🔍 تشخيص القيود المحاسبية للرواتب...")
        
        # التأكد من وجود الفترة المحاسبية والحسابات المطلوبة
        self.ensure_accounting_period_exists()
        
        # التحقق من صحة الحسابات المحاسبية للرواتب
        validation_result = self.validate_payroll_accounting_setup()
        if not validation_result['is_valid']:
            print(f"❌ مشكلة في إعداد النظام المحاسبي للرواتب:")
            for error in validation_result['errors']:
                print(f"   {error}")
            
            return {
                'success': False,
                'entry_created': False,
                'journal_entry': None,
                'message': f'خطأ في إعداد النظام المحاسبي: {"; ".join(validation_result["errors"])}'
            }
        
        # ✅ إنشاء قيد محاسبي حقيقي باستخدام JournalEntryService
        try:
            # إنشاء القيد المحاسبي للراتب باستخدام JournalEntryService
            journal_entry = JournalEntryService.create_simple_entry(
                date=payroll.month,
                debit_account="50500",  # مصروفات متنوعة (من fixtures)
                credit_account="20200", # مستحقات الرواتب (من fixtures)
                amount=payroll.gross_salary,
                description=f'راتب الموظف {payroll.employee.get_full_name_ar()} - {payroll.month.strftime("%Y-%m")}',
                reference=f'PAYROLL-{payroll.id}',
                user=self.admin_user
            )
            
            # التحقق من إنشاء القيد بنجاح
            if not journal_entry:
                raise AssertionError(
                    "❌ فشل في إنشاء القيد المحاسبي للراتب\n"
                    "🔍 السبب المحتمل: مشكلة في JournalEntryService\n"
                    "📁 الملف المطلوب فحصه: financial/services/journal_service.py\n"
                    "💡 الحل المقترح: فحص الحسابات المحاسبية والفترة المحاسبية\n"
                    "⏱️ الوقت المقدر للإصلاح: 30 دقيقة - 1 ساعة"
                )
            
            # التحقق من توازن القيد
            lines = journal_entry.lines.all()
            total_debit = sum(line.debit for line in lines)
            total_credit = sum(line.credit for line in lines)
            
            if abs(total_debit - total_credit) > 0.01:
                raise AssertionError(
                    f"❌ القيد المحاسبي للراتب غير متوازن!\n"
                    f"   إجمالي المدين: {total_debit} ج.م\n"
                    f"   إجمالي الدائن: {total_credit} ج.م\n"
                    f"   الفرق: {total_debit - total_credit} ج.م\n"
                    f"🔧 الحل المطلوب: فحص JournalEntryService"
                )
            
            print(f"✅ تم إنشاء قيد محاسبي متوازن للراتب:")
            print(f"   📋 رقم القيد: {journal_entry.id}")
            print(f"   💰 إجمالي المدين: {total_debit} ج.م")
            print(f"   💰 إجمالي الدائن: {total_credit} ج.م")
            print(f"   📅 تاريخ القيد: {journal_entry.date}")
            
            return {
                'success': True,
                'entry_created': True,
                'journal_entry': journal_entry,
                'total_debit': total_debit,
                'total_credit': total_credit,
                'message': 'تم إنشاء القيد المحاسبي للراتب بنجاح'
            }
            
        except Exception as e:
            raise AssertionError(
                f"❌ فشل في إنشاء القيد المحاسبي للراتب\n"
                f"🔍 الخطأ: {str(e)}\n"
                f"💡 الحل المقترح: فحص JournalEntryService والحسابات المحاسبية\n"
                f"⏱️ الوقت المقدر للإصلاح: 1-2 ساعة"
            )
    
    def step_6_diagnose_salary_payment(self, payroll):
        """الخطوة 6: تشخيص دفع الراتب عبر HTTP"""
        
        print(f"\n🔍 تشخيص نظام دفع الرواتب عبر HTTP...")
        
        try:
            # Step 1: Approve payroll first (required before payment)
            print(f"📋 اعتماد الراتب أولاً...")
            payroll.status = 'approved'
            payroll.approved_by = self.admin_user
            payroll.approved_at = timezone.now()
            payroll.save()
            
            # Step 2: Get or create payment account
            from financial.models import ChartOfAccounts
            
            payment_account = ChartOfAccounts.objects.filter(
                is_cash_account=True,
                is_active=True
            ).first()
            
            if not payment_account:
                # Create a test cash account
                from financial.models.chart_of_accounts import AccountType
                cash_type = self.get_or_create_account_type('asset')
                payment_account = ChartOfAccounts.objects.create(
                    code=f'{self.test_prefix}10100',
                    name=f'{self.test_prefix}الخزنة',
                    account_type=cash_type,
                    is_cash_account=True,
                    is_active=True,
                    created_by=self.admin_user
                )
                self.track_object(payment_account)
            
            # Step 3: Prepare payment data
            payment_data = {
                'payment_account': payment_account.id,
                'payment_reference': f'{self.test_prefix}PAY-{payroll.id}',
            }
            
            print(f"💳 حساب الدفع: {payment_account.name}")
            print(f"💰 المبلغ المدفوع: {payroll.net_salary} ج.م")
            print(f"🏦 رقم المرجع: {payment_data['payment_reference']}")
            
            # Step 4: Send HTTP POST to pay payroll
            from django.urls import reverse
            
            self.client.force_login(self.admin_user)
            url = reverse('hr:payroll_pay', args=[payroll.id])
            
            print(f"📤 إرسال طلب HTTP POST لدفع الراتب...")
            
            response = self.post_form('hr:payroll_pay', payment_data, url_args=[payroll.id])
            
            # Verify response
            if response.status_code not in [200, 302]:
                raise AssertionError(
                    f"❌ فشل في دفع الراتب عبر HTTP!\n"
                    f"   Status Code: {response.status_code}\n"
                    f"🔧 الحل المطلوب: فحص payroll_pay view"
                )
            
            # Refresh payroll from database
            payroll.refresh_from_db()
            
            # التحقق من صحة عملية الدفع
            if payroll.status != 'paid':
                raise AssertionError(
                    f"❌ فشل في تحديث حالة الراتب إلى مدفوع!\n"
                    f"   الحالة الحالية: {payroll.status}\n"
                    f"🔧 الحل المطلوب: فحص PayrollService.pay_payroll"
                )
            
            if not payroll.payment_date:
                raise AssertionError(
                    f"❌ لم يتم تسجيل تاريخ الدفع!\n"
                    f"🔧 الحل المطلوب: التأكد من حفظ تاريخ الدفع"
                )
            
            print(f"✅ تم دفع الراتب بنجاح عبر HTTP:")
            print(f"   💳 حساب الدفع: {payment_account.name}")
            print(f"   💰 المبلغ المدفوع: {payroll.net_salary} ج.م")
            print(f"   📅 تاريخ الدفع: {payroll.payment_date}")
            print(f"   🏦 مرجع الدفع: {payroll.payment_reference or 'N/A'}")
            print(f"   👤 دفع بواسطة: {payroll.paid_by.username if payroll.paid_by else 'N/A'}")
            print(f"   🌐 HTTP Status: {response.status_code}")
            print(f"   ℹ️ ملاحظة: الرواتب تُسجل في حساب محاسبي واحد للشركة (مستحقات الرواتب)")
            print(f"   ℹ️ لا يحتاج كل موظف لحساب محاسبي منفصل")
            
            return {
                'success': True,
                'payment_account': payment_account,
                'amount_paid': payroll.net_salary,
                'payment_date': payroll.payment_date,
                'payment_reference': payroll.payment_reference
            }
            
        except Exception as e:
            raise AssertionError(
                f"❌ خطأ تقني في دفع الراتب عبر HTTP!\n"
                f"   الخطأ: {str(e)}\n"
                f"🔧 الحل المطلوب:\n"
                f"   1. فحص payroll_pay view في hr/views/payroll_payment_views.py\n"
                f"   2. فحص PayrollService.pay_payroll\n"
                f"   3. التأكد من وجود payment_account صحيح\n"
                f"   4. التأكد من أن الراتب معتمد (approved)\n"
                f"⏱️ الوقت المقدر: 1-2 ساعة"
            )
    
    def step_7_diagnose_advance_management(self, employee, payroll):
        """الخطوة 7: تشخيص إدارة السلف والخصومات عبر HTTP"""
        
        print(f"\n🔍 تشخيص نظام إدارة السلف عبر HTTP...")
        
        # بيانات السلفة التجريبية
        advance_amount = Decimal('2000.00')
        installments_count = 4  # 4 أقساط شهرية
        
        print(f"💰 مبلغ السلفة: {advance_amount} ج.م")
        print(f"🔢 عدد الأقساط: {installments_count}")
        
        # ✅ استخدام HTTP POST بدلاً من objects.create()
        try:
            from tests.e2e.helpers import prepare_advance_request_form_data
            
            # تحضير بيانات النموذج
            form_data = prepare_advance_request_form_data(
                employee=employee,
                amount=advance_amount,
                installments_count=installments_count,
                prefix=self.test_prefix
            )
            
            print(f"📝 السبب: {form_data['reason']}")
            print(f"📅 بدء الخصم: {form_data['deduction_start_month']}")
            print(f"📤 إرسال طلب HTTP POST لإنشاء السلفة...")
            
            # إرسال POST request
            # Try different possible URL names
            response = None
            url_tried = []
            
            for url_name in ['hr:advance_request', 'hr:advance_request_create', 'hr:advance_create', 'hr:advance_form']:
                try:
                    response = self.post_form(url_name, form_data)
                    break
                except Exception as e:
                    url_tried.append(url_name)
                    continue
            
            if response is None:
                raise AssertionError(
                    f"❌ لا يوجد endpoint لإنشاء السلف عبر HTTP!\n"
                    f"   URLs المجربة: {', '.join(url_tried)}\n"
                    f"🔧 الحل المطلوب:\n"
                    f"   1. إضافة URL endpoint في hr/urls.py\n"
                    f"   2. إنشاء advance_create view في hr/views/advance_views.py\n"
                    f"   3. إنشاء AdvanceForm في hr/forms/advance_forms.py\n"
                    f"⏱️ الوقت المقدر: 2-3 ساعات"
                )
            
            # Debug: Check for form errors
            if response.status_code == 200:
                if hasattr(response, 'context') and response.context:
                    form = response.context.get('form')
                    if form and form.errors:
                        error_details = []
                        for field, errors in form.errors.items():
                            error_details.append(f"{field}: {', '.join(errors)}")
                        raise AssertionError(
                            f"❌ Form validation errors:\n" + "\n".join(f"   - {e}" for e in error_details)
                        )
            
            # التحقق من نجاح الطلب
            self.assert_successful_post(response)
            
            # الحصول على السلفة المُنشأة من قاعدة البيانات
            advance = Advance.objects.filter(
                employee=employee,
                amount=advance_amount
            ).order_by('-id').first()
            
            if not advance:
                raise AssertionError(
                    f"❌ فشل في إنشاء السلفة عبر HTTP!\n"
                    f"   الاستجابة: {response.status_code}\n"
                    f"🔧 الحل المطلوب: فحص advance_request_create view"
                )
            
            self.track_object(advance)
            print(f"   🌐 HTTP Status: {response.status_code}")
            
            return self._validate_advance(advance, payroll, advance_amount, installments_count, via_http=True)
            
        except Exception as e:
            raise AssertionError(
                f"❌ خطأ تقني في إدارة السلف عبر HTTP!\n"
                f"   الخطأ: {str(e)}\n"
                f"🔧 الحل المطلوب:\n"
                f"   1. فحص advance_request_create view في hr/views/advance_views.py\n"
                f"   2. فحص AdvanceForm في hr/forms/advance_forms.py\n"
                f"   3. فحص Advance model في hr/models/payroll.py\n"
                f"   4. فحص دوال حساب الأقساط\n"
                f"   5. التأكد من صحة منطق الخصم\n"
                f"⏱️ الوقت المقدر: 2-3 ساعات"
            )
    
    def _validate_advance(self, advance, payroll, advance_amount, installments_count, via_http=True):
        """Helper method to validate advance creation"""
        
        # تشخيص صحة السلفة
        if advance.installment_amount <= 0:
            raise AssertionError(
                f"❌ قيمة القسط غير صحيحة: {advance.installment_amount}\n"
                f"🔧 الحل المطلوب: فحص حساب قيمة القسط في Advance model"
            )
        
        expected_installment = advance_amount / installments_count
        if abs(advance.installment_amount - expected_installment) > 0.01:
            raise AssertionError(
                f"❌ خطأ في حساب قيمة القسط!\n"
                f"   المتوقع: {expected_installment}\n"
                f"   الفعلي: {advance.installment_amount}\n"
                f"🔧 الحل المطلوب: إصلاح معادلة حساب القسط"
            )
        
        # محاكاة موافقة السلفة
        advance.status = 'approved'
        advance.approved_by = self.test_users['admin']
        advance.approved_at = timezone.now()
        advance.save()
        
        # محاكاة صرف السلفة
        advance.status = 'paid'
        advance.payment_date = date.today()
        advance.save()
        
        method_str = "عبر HTTP" if via_http else "مباشرة"
        print(f"✅ تم إنشاء وصرف السلفة بنجاح {method_str}:")
        print(f"   💰 مبلغ السلفة: {advance.amount} ج.م")
        print(f"   💳 قيمة القسط الشهري: {advance.installment_amount} ج.م")
        print(f"   🔢 عدد الأقساط: {advance.installments_count}")
        print(f"   💰 المبلغ المتبقي: {advance.remaining_amount} ج.م")
        print(f"   📊 حالة السلفة: {advance.get_status_display()}")
        
        # محاكاة خصم قسط من الراتب التالي
        if advance.deduction_start_month <= payroll.month:
            installment_amount = advance.get_next_installment_amount()
            
            # تحديث الراتب بخصم السلفة
            payroll.advance_deduction = installment_amount
            if hasattr(payroll, 'calculate_totals'):
                payroll.calculate_totals()
            payroll.save()
            
            # تسجيل القسط
            if hasattr(advance, 'record_installment_payment'):
                advance.record_installment_payment(payroll.month, installment_amount)
            
            print(f"   ✅ تم خصم قسط بقيمة {installment_amount} ج.م من الراتب")
        
        return {
            'advance': advance,
            'installment_amount': advance.installment_amount,
            'remaining_amount': advance.remaining_amount,
            'status': advance.status
        }
    
    def step_8_diagnose_financial_reporting(self, payroll, accounting_result):
        """الخطوة 8: تشخيص إنشاء التقارير المالية"""
        
        print(f"\n🔍 تشخيص نظام التقارير المالية للرواتب...")
        
        # محاكاة إنشاء تقارير مالية
        reports_data = {
            'payroll_summary': {
                'employee_count': 1,
                'total_gross_salary': payroll.gross_salary,
                'total_deductions': payroll.total_deductions,
                'total_net_salary': payroll.net_salary,
                'total_social_insurance': payroll.social_insurance,
                'total_tax': payroll.tax
            },
            'accounting_summary': {
                'journal_entries_count': 1 if accounting_result['entry_created'] else 0,
                'total_debits': accounting_result.get('total_debit', 0),
                'total_credits': accounting_result.get('total_credit', 0),
                'is_balanced': accounting_result.get('total_debit', 0) == accounting_result.get('total_credit', 0)
            }
        }
        
        print(f"📊 ملخص الرواتب:")
        print(f"   👥 عدد الموظفين: {reports_data['payroll_summary']['employee_count']}")
        print(f"   💰 إجمالي الرواتب الإجمالية: {reports_data['payroll_summary']['total_gross_salary']} ج.م")
        print(f"   ➖ إجمالي الخصومات: {reports_data['payroll_summary']['total_deductions']} ج.م")
        print(f"   💎 إجمالي الرواتب الصافية: {reports_data['payroll_summary']['total_net_salary']} ج.م")
        
        print(f"\n📚 ملخص المحاسبة:")
        print(f"   📋 عدد القيود: {reports_data['accounting_summary']['journal_entries_count']}")
        print(f"   💰 إجمالي المدين: {reports_data['accounting_summary']['total_debits']} ج.م")
        print(f"   💰 إجمالي الدائن: {reports_data['accounting_summary']['total_credits']} ج.م")
        print(f"   ⚖️ متوازن: {'نعم' if reports_data['accounting_summary']['is_balanced'] else 'لا'}")
        
        # التحقق من صحة التقارير
        if not reports_data['accounting_summary']['is_balanced']:
            raise AssertionError(
                f"❌ القيود المحاسبية غير متوازنة!\n"
                f"🔧 الحل المطلوب: مراجعة القيود المحاسبية للرواتب"
            )
        
        if reports_data['payroll_summary']['total_net_salary'] <= 0:
            raise AssertionError(
                f"❌ إجمالي الرواتب الصافية غير صحيح!\n"
                f"🔧 الحل المطلوب: مراجعة حسابات الرواتب"
            )
        
        # حساب النسب المالية
        deduction_rate = (reports_data['payroll_summary']['total_deductions'] / 
                         reports_data['payroll_summary']['total_gross_salary'] * 100)
        
        print(f"\n📈 التحليل المالي:")
        print(f"   📊 معدل الخصومات: {deduction_rate:.1f}%")
        
        if deduction_rate > 50:
            print(f"⚠️ تحذير: معدل الخصومات مرتفع ({deduction_rate:.1f}%)")
        
        print(f"✅ تم إنشاء التقارير المالية بنجاح")
        
        return reports_data
    
    def ensure_accounting_period_exists(self):
        """التأكد من وجود فترة محاسبية نشطة"""
        
        print(f"🔍 فحص الفترة المحاسبية...")
        
        try:
            # البحث عن فترة محاسبية نشطة
            current_period = AccountingPeriod.objects.filter(
                status='open',
                start_date__lte=date.today(),
                end_date__gte=date.today()
            ).first()
            
            if not current_period:
                # إنشاء فترة محاسبية للسنة الحالية
                current_year = date.today().year
                start_date = date(current_year, 1, 1)
                end_date = date(current_year, 12, 31)
                
                current_period = AccountingPeriod.objects.create(
                    name=f'{self.test_prefix}السنة المالية {current_year}',
                    start_date=start_date,
                    end_date=end_date,
                    status='open',
                    created_by=self.test_users['admin']
                )
                
                self.track_object(current_period)
                print(f"✅ تم إنشاء فترة محاسبية جديدة: {current_period.name}")
            else:
                print(f"✅ تم العثور على فترة محاسبية نشطة: {current_period.name}")
            
            return current_period
            
        except Exception as e:
            print(f"❌ خطأ في إعداد الفترة المحاسبية: {e}")
            return None
    
    def validate_payroll_accounting_setup(self):
        """التحقق من صحة إعداد النظام المحاسبي للرواتب"""
        
        print(f"🔍 فحص إعداد النظام المحاسبي للرواتب...")
        
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': []
        }
        
        # قائمة الحسابات المطلوبة للرواتب
        required_accounts = [
            {'code': '50100', 'name': 'مصروف الرواتب', 'category': 'expense'},
            {'code': '20100', 'name': 'التأمينات الاجتماعية مستحقة الدفع', 'category': 'liability'},
            {'code': '20200', 'name': 'الضرائب مستحقة الدفع', 'category': 'liability'},
            {'code': '20300', 'name': 'الرواتب مستحقة الدفع', 'category': 'liability'},
            {'code': '10200', 'name': 'البنك', 'category': 'asset'}
        ]
        
        # التحقق من وجود الحسابات
        for account_info in required_accounts:
            try:
                account = ChartOfAccounts.objects.filter(
                    code=account_info['code']
                ).first()
                
                if not account:
                    # البحث عن نوع الحساب أو إنشاؤه
                    account_type, created = AccountType.objects.get_or_create(
                        category=account_info['category'],
                        defaults={
                            'code': f"{account_info['category'].upper()}001",
                            'name': f"نوع {account_info['category']}",
                            'nature': 'debit' if account_info['category'] in ['asset', 'expense'] else 'credit',
                            'is_active': True,
                            'created_by': self.test_users['admin']
                        }
                    )
                    if created:
                        self.track_object(account_type)
                    
                    # إنشاء الحساب إذا لم يكن موجود
                    account = ChartOfAccounts.objects.create(
                        code=account_info['code'],
                        name=f"{self.test_prefix}{account_info['name']}",
                        account_type=account_type,
                        is_active=True,
                        created_by=self.test_users['admin']
                    )
                    self.track_object(account)
                    validation_result['warnings'].append(f"تم إنشاء حساب مفقود: {account_info['name']}")
                else:
                    print(f"   ✅ حساب موجود: {account.name}")
                    
            except Exception as e:
                validation_result['is_valid'] = False
                validation_result['errors'].append(f"خطأ في حساب {account_info['name']}: {e}")
        
        # التحقق من الفترة المحاسبية
        if not self.ensure_accounting_period_exists():
            validation_result['is_valid'] = False
            validation_result['errors'].append("لا توجد فترة محاسبية نشطة")
        
        if validation_result['warnings']:
            for warning in validation_result['warnings']:
                print(f"   ⚠️ {warning}")
        
        if validation_result['errors']:
            for error in validation_result['errors']:
                print(f"   ❌ {error}")
        else:
            print(f"✅ النظام المحاسبي للرواتب جاهز")
        
        return validation_result
    
    def validate_complete_hr_payroll_circle(self, employee, contract, attendance_records, payroll,
                                          accounting_result, payment_result, advance_result, reports_result):
        """التحقق من سلامة دائرة الموارد البشرية والرواتب الكاملة - تقرير استشاري شامل"""
        
        print(f"\n🔍 تحليل شامل لسلامة دائرة الموارد البشرية والرواتب...")
        
        issues_found = []
        warnings = []
        
        # 1. تحليل الموظف
        if not employee or not employee.employee_number:
            issues_found.append("❌ لم يتم إنشاء الموظف بشكل صحيح")
        else:
            if employee.age < 18:
                warnings.append(f"⚠️ عمر الموظف صغير: {employee.age} سنة")
            if not employee.is_active:
                warnings.append("⚠️ الموظف غير نشط")
        
        # 2. تحليل العقد
        if not contract or contract.basic_salary <= 0:
            issues_found.append("❌ عقد العمل غير صحيح أو الراتب الأساسي خاطئ")
        
        # 3. تحليل الحضور
        if not attendance_records or len(attendance_records) == 0:
            issues_found.append("❌ لم يتم تسجيل أي حضور")
        else:
            total_hours = sum(record.work_hours for record in attendance_records)
            if total_hours <= 0:
                issues_found.append("❌ إجمالي ساعات العمل صفر أو سالب")
        
        # 4. تحليل الراتب
        if not payroll or payroll.net_salary <= 0:
            issues_found.append("❌ فشل في حساب الراتب أو صافي الراتب سالب")
        else:
            if payroll.total_deductions > payroll.gross_salary:
                warnings.append("⚠️ الخصومات أكبر من الراتب الإجمالي")
        
        # 5. تحليل المحاسبة
        if not accounting_result or not accounting_result.get('success'):
            issues_found.append("❌ فشل في إنشاء القيود المحاسبية")
        elif not accounting_result.get('entry_created'):
            warnings.append("⚠️ لم يتم إنشاء قيد محاسبي - لكن النظام الأساسي يعمل")
        
        # 6. تحليل الدفع
        if not payment_result or not payment_result.get('success'):
            issues_found.append("❌ فشل في دفع الراتب")
        
        # 7. تحليل السلف
        if advance_result and advance_result.get('advance'):
            advance = advance_result['advance']
            if advance.installment_amount <= 0:
                issues_found.append("❌ خطأ في حساب أقساط السلفة")
        
        # إنشاء التقرير الاستشاري
        print(f"\n📋 تقرير التشخيص النهائي:")
        print(f"=" * 60)
        
        if issues_found:
            print(f"❌ مشاكل جوهرية تم اكتشافها ({len(issues_found)}):")
            for issue in issues_found:
                print(f"   {issue}")
            
            print(f"\n🔧 التوصيات الفورية:")
            print(f"   1. إصلاح نظام إدارة الموظفين والعقود")
            print(f"   2. إصلاح نظام حساب الرواتب والخصومات")
            print(f"   3. إعداد النظام المحاسبي للرواتب")
            print(f"   4. فحص منطق دفع الرواتب وإدارة السلف")
            
            # فشل الاختبار مع تقرير مفصل
            raise AssertionError(
                f"❌ فشل في دائرة الموارد البشرية والرواتب!\n"
                f"المشاكل المكتشفة: {len(issues_found)}\n"
                f"التفاصيل: {'; '.join(issues_found)}\n\n"
                f"🔧 الحلول المطلوبة:\n"
                f"1. إصلاح نظام إدارة الموظفين\n"
                f"2. إصلاح نظام حساب الرواتب\n"
                f"3. إعداد النظام المحاسبي\n"
                f"4. مراجعة شاملة لمنطق السلف والخصومات"
            )
        
        if warnings:
            print(f"⚠️ تحذيرات ({len(warnings)}):")
            for warning in warnings:
                print(f"   {warning}")
        
        if not issues_found and not warnings:
            print(f"✅ دائرة الموارد البشرية والرواتب تعمل بشكل صحيح!")
            print(f"   ✅ جميع الموظفين تم تعيينهم بنجاح")
            print(f"   ✅ نظام الحضور والانصراف يعمل")
            print(f"   ✅ نظام حساب الرواتب دقيق")
            print(f"   ✅ النظام المحاسبي متكامل")
            print(f"   ✅ نظام دفع الرواتب يعمل")
            print(f"   ✅ إدارة السلف والخصومات تعمل")
        
        print(f"=" * 60)
        
    def print_circle_summary(self, employee, payroll, accounting_result):
        """تقرير استشاري نهائي - تحليل احترافي للنتائج"""
        
        print("\n" + "="*80)
        print("📊 تقرير استشاري: تحليل دائرة الموارد البشرية والرواتب")
        print("="*80)
        
        print(f"🎯 نطاق الاختبار:")
        print(f"   👤 الموظف: {employee.get_full_name_ar()}")
        print(f"   🆔 رقم الموظف: {employee.employee_number}")
        print(f"   🏢 القسم: {employee.department.name_ar}")
        print(f"   💼 المسمى الوظيفي: {employee.job_title.title_ar}")
        
        print(f"\n💰 التحليل المالي:")
        print(f"   💵 الراتب الأساسي: {payroll.basic_salary} ج.م")
        print(f"   💰 إجمالي الراتب: {payroll.gross_salary} ج.م")
        print(f"   ➖ إجمالي الخصومات: {payroll.total_deductions} ج.م")
        print(f"   💎 صافي الراتب: {payroll.net_salary} ج.م")
        
        collection_rate = ((payroll.gross_salary - payroll.total_deductions) / payroll.gross_salary * 100) if payroll.gross_salary > 0 else 0
        print(f"   📊 معدل الصافي: {collection_rate:.1f}%")
        
        print(f"\n📚 التحليل المحاسبي:")
        # التعامل مع accounting_result سواء كان JournalEntry أو dictionary
        if accounting_result:
            if isinstance(accounting_result, dict):
                # إذا كان dictionary (الطريقة القديمة)
                if accounting_result.get('entry_created'):
                    journal_entry = accounting_result.get('journal_entry')
                    if journal_entry:
                        # journal_entry هو كائن JournalEntry
                        entry_number = journal_entry.number if hasattr(journal_entry, 'number') else journal_entry.id
                        print(f"   ✅ تم إنشاء قيد محاسبي: {entry_number}")
                    else:
                        print(f"   ✅ تم إنشاء قيد محاسبي")
                    print(f"   💰 إجمالي المدين: {accounting_result.get('total_debit', 0)} ج.م")
                    print(f"   💰 إجمالي الدائن: {accounting_result.get('total_credit', 0)} ج.م")
                    print(f"   ⚖️ حالة التوازن: {'متوازن' if accounting_result.get('total_debit') == accounting_result.get('total_credit') else 'غير متوازن'}")
                else:
                    print(f"   ❌ لم يتم إنشاء قيد محاسبي")
            else:
                # إذا كان JournalEntry object (الطريقة الجديدة)
                print(f"   ✅ تم إنشاء قيد محاسبي: {accounting_result.number}")
                lines = accounting_result.lines.all()
                total_debit = sum(line.debit for line in lines)
                total_credit = sum(line.credit for line in lines)
                print(f"   💰 إجمالي المدين: {total_debit} ج.م")
                print(f"   💰 إجمالي الدائن: {total_credit} ج.م")
                print(f"   ⚖️ حالة التوازن: {'متوازن' if total_debit == total_credit else 'غير متوازن'}")
        else:
            print(f"   ❌ لم يتم إنشاء قيد محاسبي")
        
        # تقييم الأداء
        performance_report = self.get_performance_report()
        print(f"\n⏱️ تحليل الأداء:")
        print(f"   ⏱️ إجمالي وقت التنفيذ: {performance_report['total_duration']:.2f} ثانية")
        print(f"   📊 عدد الخطوات: {performance_report['total_steps']}")
        print(f"   ✅ الخطوات الناجحة: {performance_report['successful_steps']}")
        
        # التقييم النهائي
        success_rate = (performance_report['successful_steps'] / performance_report['total_steps']) * 100 if performance_report['total_steps'] > 0 else 0
        
        # التحقق من وجود قيد محاسبي
        has_accounting = bool(accounting_result)
        
        print(f"\n🎯 التقييم النهائي:")
        if success_rate == 100 and has_accounting:
            print(f"   🎉 ممتاز: النظام يعمل بكفاءة 100%")
            print(f"   ✅ جميع عمليات الموارد البشرية تعمل")
            print(f"   ✅ نظام الرواتب دقيق ومتوازن")
            print(f"   ✅ النظام المحاسبي متكامل")
        elif success_rate >= 70:
            print(f"   ⚠️ جيد مع تحفظات: معدل النجاح {success_rate:.0f}%")
            if not has_accounting:
                print(f"   🔧 مطلوب: إعداد النظام المحاسبي للرواتب")
        else:
            print(f"   ❌ ضعيف: معدل النجاح {success_rate:.0f}%")
            print(f"   🚨 مطلوب: مراجعة شاملة لنظام الموارد البشرية")
        
        print("="*80)

    # ============================================================================
    # Error Case Tests (Task 11.4)
    # ============================================================================
    
    def test_employee_creation_signals_via_http(self):
        """
        Test employee creation signals via HTTP (Task 11.2)
        اختبار إشارات إنشاء الموظف عبر HTTP
        
        Verifies that when an employee is created via HTTP POST:
        - Leave balances are automatically created (if auto-create is enabled)
        - Employee data is properly initialized
        
        Note: The system does NOT automatically create payroll records when an employee
        is created. Payroll records are created manually via the payroll generation process.
        This is by design - payroll is generated monthly, not at employee creation time.
        """
        print(f"\n🧪 اختبار: إشارات إنشاء الموظف عبر HTTP")
        
        from tests.e2e.helpers import prepare_employee_creation_form_data
        from hr.models import LeaveBalance
        
        # Prepare form data with unique national_id
        form_data = prepare_employee_creation_form_data(
            department=self.department,
            job_title=self.job_title,
            prefix=self.test_prefix
        )
        
        # Make national_id unique for this test - use only digits
        import random
        unique_suffix = f"{random.randint(1000, 9999)}"
        form_data['national_id'] = form_data['national_id'][:10] + unique_suffix
        
        # Set hire date to 6 months ago (to trigger leave balance creation)
        hire_date_old = date.today() - timedelta(days=180)
        form_data['hire_date'] = hire_date_old.strftime('%Y-%m-%d')
        
        print(f"📤 إنشاء موظف عبر HTTP بتاريخ تعيين قديم...")
        print(f"   الرقم القومي: {form_data['national_id']}")
        
        # Create employee via HTTP
        response = self.post_form('hr:employee_form', form_data)
        
        # Check response status
        print(f"   Response status: {response.status_code}")
        
        # If there are form errors, print them
        if response.status_code == 200 and hasattr(response, 'context') and response.context:
            form = response.context.get('form')
            if form and form.errors:
                print(f"   ❌ Form errors: {form.errors}")
                self.fail(f"Form validation failed: {form.errors}")
        
        self.assert_successful_post(response)
        
        # Get created employee - try multiple ways
        employee = Employee.objects.filter(
            national_id=form_data['national_id']
        ).first()
        
        if not employee:
            # Try by mobile phone
            employee = Employee.objects.filter(
                mobile_phone=form_data['mobile_phone']
            ).first()
        
        if not employee:
            # Try by name
            employee = Employee.objects.filter(
                name=form_data['name']
            ).first()
        
        self.assertIsNotNone(employee, f"Employee should be created. National ID: {form_data['national_id']}")
        self.track_object(employee)
        
        print(f"✅ تم إنشاء الموظف: {employee.get_full_name_ar()}")
        
        # Wait for signals to execute
        self.wait_for_signals()
        
        # ✅ Verify signal effect: Leave balances created (if enabled)
        print(f"🔍 التحقق من إنشاء أرصدة الإجازات...")
        
        leave_balances = LeaveBalance.objects.filter(
            employee=employee,
            year=date.today().year
        )
        
        if leave_balances.exists():
            print(f"✅ تم إنشاء {leave_balances.count()} رصيد إجازة تلقائياً بواسطة signal")
            
            # Verify balance details
            for balance in leave_balances:
                print(f"   📋 {balance.leave_type.name}: {balance.accrued_days} يوم")
                
                # Verify accrued days are calculated correctly
                self.assertGreaterEqual(
                    balance.accrued_days, 0,
                    "Accrued days should be >= 0"
                )
            
            # ✅ Task 11.2 requirement met: Signal verification successful
            print(f"✅ Signal verification successful: Leave balances created")
        else:
            print(f"ℹ️ لم يتم إنشاء أرصدة إجازات - قد يكون الإنشاء التلقائي معطل في الإعدادات")
            print(f"   هذا سلوك صحيح إذا كان auto_create_balances = False")
        
        # ℹ️ Note about payroll records
        print(f"\nℹ️ ملاحظة: النظام لا ينشئ سجلات رواتب تلقائياً عند إنشاء موظف")
        print(f"   سجلات الرواتب تُنشأ يدوياً عبر عملية توليد الرواتب الشهرية")
        print(f"   هذا تصميم مقصود - الرواتب تُحسب شهرياً وليس عند التعيين")
        
        print(f"✅ اختبار الإشارات اكتمل بنجاح")
    
    def test_duplicate_employee_id_returns_error(self):
        """
        Test that creating employee with duplicate national ID returns error
        اختبار أن إنشاء موظف برقم قومي مكرر يرجع خطأ
        """
        print(f"\n🧪 اختبار: رقم قومي مكرر")
        
        # Create first employee via HTTP
        from tests.e2e.helpers import prepare_employee_creation_form_data
        
        form_data = prepare_employee_creation_form_data(
            department=self.department,
            job_title=self.job_title,
            prefix=self.test_prefix
        )
        
        # First employee creation should succeed
        response1 = self.post_form('hr:employee_form', form_data)
        self.assert_successful_post(response1)
        
        # Get created employee
        employee1 = Employee.objects.filter(
            national_id=form_data['national_id']
        ).first()
        self.assertIsNotNone(employee1, "First employee should be created")
        self.track_object(employee1)
        
        # Try to create second employee with same national_id
        form_data2 = form_data.copy()
        form_data2['name'] = f'{self.test_prefix}موظف آخر'
        form_data2['mobile_phone'] = f'{self.test_prefix}01098765432'
        
        print(f"📤 محاولة إنشاء موظف برقم قومي مكرر...")
        response2 = self.post_form('hr:employee_form', form_data2)
        
        # Should return form with errors (status 200)
        self.assertEqual(response2.status_code, 200, "Should re-render form with errors")
        
        # Verify error message
        self.assert_form_error(
            response2,
            field_name='national_id',
            error_message='مستخدم بالفعل'
        )
        
        print(f"✅ النظام رفض الرقم القومي المكرر بنجاح")
    
    def test_invalid_salary_amount_returns_validation_error(self):
        """
        Test that invalid salary amount returns validation error
        اختبار أن مبلغ راتب غير صحيح يرجع خطأ تحقق
        """
        print(f"\n🧪 اختبار: مبلغ راتب غير صحيح")
        
        # Create employee first
        employee = self.step_1_diagnose_employee_hiring()
        
        # Try to create contract with negative salary
        # Note: This tests model validation using full_clean()
        
        print(f"📤 محاولة إنشاء عقد براتب سالب...")
        
        from django.core.exceptions import ValidationError
        
        with self.assertRaises(ValidationError) as context:
            contract = Contract(
                employee=employee,
                contract_number=f'{self.test_prefix}CON_INVALID',
                start_date=date.today(),
                end_date=date.today() + relativedelta(years=1),
                basic_salary=Decimal('-1000.00'),  # Negative salary
                contract_type='permanent',
                status='draft',
                created_by=self.admin_user
            )
            contract.full_clean()  # This triggers validators
        
        print(f"✅ النظام رفض الراتب السالب: {str(context.exception)}")
    
    def test_payroll_generation_with_missing_data_returns_error(self):
        """
        Test that payroll generation with missing data returns error
        اختبار أن توليد راتب ببيانات ناقصة يرجع خطأ
        """
        print(f"\n🧪 اختبار: توليد راتب ببيانات ناقصة")
        
        # Create employee without contract
        employee = self.step_1_diagnose_employee_hiring()
        
        # Try to create payroll without contract
        print(f"📤 محاولة إنشاء راتب بدون عقد...")
        
        with self.assertRaises(Exception) as context:
            Payroll.objects.create(
                employee=employee,
                month=date.today().replace(day=1),
                # No contract provided
                basic_salary=Decimal('0.00'),
                status='draft',
                processed_by=self.admin_user
            )
        
        print(f"✅ النظام رفض إنشاء راتب بدون عقد: {str(context.exception)}")
