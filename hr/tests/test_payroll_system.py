"""
اختبارات معالجة الرواتب - المهمة 7.3
===================================
اختبارات شاملة لنظام معالجة الرواتب:
- حساب الراتب الشهري
- خصم الغيابات والتأخير
- إضافة البدلات والحوافز
- إنشاء قيود محاسبية للرواتب
"""
import pytest
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date, time, datetime, timedelta
from decimal import Decimal

from hr.models import (
    Department, JobTitle, Employee, Contract, Shift, Attendance,
    Payroll, PayrollLine, SalaryComponent, SalaryComponentTemplate,
    Advance, AdvanceInstallment
)

User = get_user_model()


class PayrollSystemTest(TestCase):
    """اختبارات نظام معالجة الرواتب الأساسية"""
    
    def setUp(self):
        """إعداد البيانات الأساسية للاختبارات"""
        self.admin_user = User.objects.create_user(
            username='admin_payroll',
            password='admin123',
            email='admin@test.com',
            is_staff=True
        )
        
        # إنشاء قسم ووظيفة
        self.department = Department.objects.create(
            code='FINANCE',
            name_ar='المالية',
            is_active=True
        )
        
        self.job_title = JobTitle.objects.create(
            code='ACCOUNTANT',
            title_ar='محاسب',
            department=self.department,
            is_active=True
        )
        
        # إنشاء وردية
        self.shift = Shift.objects.create(
            name='الوردية العادية',
            shift_type='morning',
            start_time=time(8, 0),
            end_time=time(16, 0),
            work_hours=Decimal('8.0'),
            is_active=True
        )
        
        # إنشاء موظف للاختبار
        self.employee_user = User.objects.create_user(
            username='payroll_employee',
            password='emp123',
            email='payroll@test.com'
        )
        
        self.employee = Employee.objects.create(
            user=self.employee_user,
            employee_number='EMP2025400',
            name='أحمد محمود',
            national_id='29001011234600',
            birth_date=date(1990, 1, 1),
            gender='male',
            marital_status='single',
            work_email='ahmed@company.com',
            mobile_phone='01234568000',
            department=self.department,
            job_title=self.job_title,
            shift=self.shift,
            hire_date=date.today() - timedelta(days=365),  # سنة من الخبرة
            status='active',
            created_by=self.admin_user
        )
        
        # إنشاء عقد العمل
        self.contract = Contract.objects.create(
            contract_number='CON2025400',
            employee=self.employee,
            contract_type='permanent',
            start_date=self.employee.hire_date,
            basic_salary=Decimal('10000.00'),
            status='active',
            created_by=self.admin_user
        )
    
    def test_basic_payroll_calculation(self):
        """
        اختبار حساب الراتب الأساسي
        Requirements: T044 - حساب الراتب الشهري
        """
        # إضافة بنود الراتب الأساسية
        basic_salary = SalaryComponent.objects.create(
            employee=self.employee,
            contract=self.contract,
            code='BASIC_SALARY',
            name='الراتب الأساسي',
            component_type='earning',
            calculation_method='fixed',
            amount=Decimal('10000.00'),
            is_basic=True,
            is_taxable=True,
            is_active=True,
            effective_from=self.contract.start_date,
            order=1
        )
        
        housing_allowance = SalaryComponent.objects.create(
            employee=self.employee,
            contract=self.contract,
            code='HOUSING_ALLOWANCE',
            name='بدل سكن',
            component_type='earning',
            calculation_method='fixed',
            amount=Decimal('2000.00'),
            is_taxable=False,
            is_active=True,
            effective_from=self.contract.start_date,
            order=2
        )
        
        # إنشاء قسيمة راتب
        payroll_month = date.today().replace(day=1)
        
        payroll = Payroll.objects.create(
            employee=self.employee,
            month=payroll_month,
            contract=self.contract,
            basic_salary=self.contract.basic_salary,
            gross_salary=self.contract.basic_salary,  # إضافة الحقل المطلوب
            net_salary=self.contract.basic_salary,    # إضافة الحقل المطلوب
            processed_by=self.admin_user,
            status='draft'
        )
        
        # إضافة بنود الراتب إلى القسيمة
        basic_line = PayrollLine.objects.create(
            payroll=payroll,
            code='BASIC_SALARY',
            name='الراتب الأساسي',
            component_type='earning',
            quantity=Decimal('1'),
            rate=basic_salary.amount,
            amount=basic_salary.amount,
            order=1
        )
        
        housing_line = PayrollLine.objects.create(
            payroll=payroll,
            code='HOUSING_ALLOWANCE',
            name='بدل سكن',
            component_type='earning',
            quantity=Decimal('1'),
            rate=housing_allowance.amount,
            amount=housing_allowance.amount,
            order=2
        )
        
        # التحقق من إنشاء البنود
        self.assertEqual(payroll.lines.count(), 2)
        self.assertEqual(basic_line.amount, Decimal('10000.00'))
        self.assertEqual(housing_line.amount, Decimal('2000.00'))
        
        # حساب الإجماليات
        payroll.calculate_totals_from_lines()
        payroll.save()  # حفظ التحديثات
        payroll.refresh_from_db()  # إعادة تحميل من قاعدة البيانات
        
        # التحقق من الحسابات
        self.assertEqual(payroll.basic_salary, Decimal('10000.00'))
        self.assertEqual(payroll.gross_salary, Decimal('12000.00'))  # 10000 + 2000
        self.assertEqual(payroll.total_deductions, Decimal('0'))
        self.assertEqual(payroll.net_salary, Decimal('12000.00'))
        self.assertEqual(payroll.status, 'draft')
    
    def test_payroll_with_deductions(self):
        """
        اختبار حساب الراتب مع الخصومات
        Requirements: T044 - خصم الغيابات والتأخير
        """
        # إضافة بنود الراتب
        SalaryComponent.objects.create(
            employee=self.employee,
            contract=self.contract,
            code='BASIC_SALARY',
            name='الراتب الأساسي',
            component_type='earning',
            amount=Decimal('8000.00'),
            is_active=True,
            effective_from=self.contract.start_date
        )
        
        # إنشاء قسيمة راتب
        payroll_month = date.today().replace(day=1)
        
        payroll = Payroll.objects.create(
            employee=self.employee,
            month=payroll_month,
            contract=self.contract,
            basic_salary=Decimal('8000.00'),
            gross_salary=Decimal('8000.00'),  # إضافة الحقل المطلوب
            net_salary=Decimal('8000.00'),    # إضافة الحقل المطلوب
            processed_by=self.admin_user,
            status='draft'
        )
        
        # إضافة المستحقات
        PayrollLine.objects.create(
            payroll=payroll,
            code='BASIC_SALARY',
            name='الراتب الأساسي',
            component_type='earning',
            quantity=Decimal('1'),
            rate=Decimal('8000.00'),
            amount=Decimal('8000.00'),
            order=1
        )
        
        # إضافة الخصومات
        PayrollLine.objects.create(
            payroll=payroll,
            code='SOCIAL_INSURANCE',
            name='التأمينات الاجتماعية',
            component_type='deduction',
            quantity=Decimal('1'),
            rate=Decimal('800.00'),
            amount=Decimal('800.00'),  # 10% من الراتب الأساسي
            order=10
        )
        
        PayrollLine.objects.create(
            payroll=payroll,
            code='INCOME_TAX',
            name='ضريبة الدخل',
            component_type='deduction',
            quantity=Decimal('1'),
            rate=Decimal('400.00'),
            amount=Decimal('400.00'),  # 5% من الراتب الأساسي
            order=11
        )
        
        PayrollLine.objects.create(
            payroll=payroll,
            code='ABSENCE_DEDUCTION',
            name='خصم غياب',
            component_type='deduction',
            quantity=Decimal('1'),
            rate=Decimal('266.67'),
            amount=Decimal('266.67'),  # يوم واحد غياب (8000/30)
            order=12
        )
        
        # حساب الإجماليات
        payroll.calculate_totals_from_lines()
        payroll.save()  # حفظ التحديثات
        payroll.refresh_from_db()  # إعادة تحميل من قاعدة البيانات
        
        # التحقق من الحسابات
        self.assertEqual(payroll.gross_salary, Decimal('8000.00'))
        self.assertEqual(payroll.total_deductions, Decimal('1467.00'))  # 800 + 400 + 267 (مقرب)
        self.assertEqual(payroll.net_salary, Decimal('6533.00'))  # 8000 - 1467
    
    def test_payroll_with_overtime(self):
        """
        اختبار حساب الراتب مع العمل الإضافي
        Requirements: T044 - إضافة البدلات والحوافز
        """
        # إضافة بنود الراتب
        SalaryComponent.objects.create(
            employee=self.employee,
            contract=self.contract,
            code='BASIC_SALARY',
            name='الراتب الأساسي',
            component_type='earning',
            amount=Decimal('9000.00'),
            is_active=True,
            effective_from=self.contract.start_date
        )
        
        # إنشاء قسيمة راتب
        payroll_month = date.today().replace(day=1)
        
        payroll = Payroll.objects.create(
            employee=self.employee,
            month=payroll_month,
            contract=self.contract,
            basic_salary=Decimal('9000.00'),
            gross_salary=Decimal('9000.00'),  # إضافة الحقل المطلوب
            net_salary=Decimal('9000.00'),    # إضافة الحقل المطلوب
            overtime_hours=Decimal('20.0'),  # 20 ساعة إضافية
            overtime_rate=Decimal('50.0'),   # 50 جنيه للساعة
            processed_by=self.admin_user,
            status='draft'
        )
        
        # حساب قيمة العمل الإضافي
        payroll.calculate_overtime()
        
        # إضافة بنود الراتب
        PayrollLine.objects.create(
            payroll=payroll,
            code='BASIC_SALARY',
            name='الراتب الأساسي',
            component_type='earning',
            quantity=Decimal('1'),
            rate=Decimal('9000.00'),
            amount=Decimal('9000.00'),
            order=1
        )
        
        PayrollLine.objects.create(
            payroll=payroll,
            code='OVERTIME',
            name='العمل الإضافي',
            component_type='earning',
            quantity=Decimal('1'),
            rate=payroll.overtime_amount,
            amount=payroll.overtime_amount,
            order=2
        )
        
        # إضافة مكافأة
        PayrollLine.objects.create(
            payroll=payroll,
            code='PERFORMANCE_BONUS',
            name='مكافأة أداء',
            component_type='earning',
            quantity=Decimal('1'),
            rate=Decimal('500.00'),
            amount=Decimal('500.00'),
            order=3
        )
        
        # حساب الإجماليات
        payroll.calculate_totals_from_lines()
        payroll.save()  # حفظ التحديثات
        payroll.refresh_from_db()  # إعادة تحميل من قاعدة البيانات
        
        # التحقق من الحسابات
        self.assertEqual(payroll.overtime_amount, Decimal('1000.00'))  # 20 * 50
        self.assertEqual(payroll.gross_salary, Decimal('10500.00'))  # 9000 + 1000 + 500
        self.assertEqual(payroll.net_salary, Decimal('10500.00'))  # بدون خصومات
    
    def test_payroll_with_advance_deduction(self):
        """
        اختبار خصم السلف من الراتب
        Requirements: T044 - خصم الغيابات والتأخير
        """
        # إنشاء سلفة للموظف
        advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('6000.00'),
            installments_count=6,
            reason='سلفة شخصية',
            status='paid',
            deduction_start_month=date.today().replace(day=1),
            approved_by=self.admin_user,
            approved_at=timezone.now()
        )
        
        # إنشاء قسيمة راتب
        payroll_month = date.today().replace(day=1)
        
        payroll = Payroll.objects.create(
            employee=self.employee,
            month=payroll_month,
            contract=self.contract,
            basic_salary=Decimal('8000.00'),
            gross_salary=Decimal('8000.00'),  # إضافة الحقل المطلوب
            net_salary=Decimal('7000.00'),    # إضافة الحقل المطلوب (بعد خصم السلفة)
            advance_deduction=advance.installment_amount,  # 1000 جنيه
            processed_by=self.admin_user,
            status='draft'
        )
        
        # إضافة بنود الراتب
        PayrollLine.objects.create(
            payroll=payroll,
            code='BASIC_SALARY',
            name='الراتب الأساسي',
            component_type='earning',
            quantity=Decimal('1'),
            rate=Decimal('8000.00'),
            amount=Decimal('8000.00'),
            order=1
        )
        
        PayrollLine.objects.create(
            payroll=payroll,
            code='ADVANCE_DEDUCTION',
            name='خصم سلفة',
            component_type='deduction',
            quantity=Decimal('1'),
            rate=advance.installment_amount,
            amount=advance.installment_amount,
            order=10
        )
        
        # تسجيل قسط السلفة
        installment = AdvanceInstallment.objects.create(
            advance=advance,
            month=payroll_month,
            amount=advance.installment_amount,
            installment_number=1,
            payroll=payroll
        )
        
        # حساب الإجماليات
        payroll.calculate_totals_from_lines()
        payroll.save()  # حفظ التحديثات
        payroll.refresh_from_db()  # إعادة تحميل من قاعدة البيانات
        
        # التحقق من الحسابات
        self.assertEqual(payroll.gross_salary, Decimal('8000.00'))
        self.assertEqual(payroll.total_deductions, Decimal('1000.00'))
        self.assertEqual(payroll.net_salary, Decimal('7000.00'))
        
        # التحقق من تسجيل القسط
        self.assertEqual(installment.amount, Decimal('1000.00'))
        self.assertEqual(installment.payroll, payroll)
    
    def test_payroll_attendance_based_deductions(self):
        """
        اختبار خصومات الحضور (غياب وتأخير)
        Requirements: T044 - خصم الغيابات والتأخير
        """
        # إنشاء سجلات حضور للشهر
        payroll_month = date.today().replace(day=1)
        
        # حضور عادي (22 يوم)
        for day in range(1, 23):
            attendance_date = payroll_month.replace(day=day)
            if attendance_date.weekday() < 5:  # أيام العمل فقط
                Attendance.objects.create(
                    employee=self.employee,
                    date=attendance_date,
                    shift=self.shift,
                    check_in=timezone.make_aware(
                        datetime.combine(attendance_date, time(8, 0))
                    ),
                    check_out=timezone.make_aware(
                        datetime.combine(attendance_date, time(16, 0))
                    ),
                    status='present',
                    work_hours=Decimal('8.0')
                )
        
        # غياب (يومين)
        for day in [23, 24]:
            if day <= 31:
                try:
                    attendance_date = payroll_month.replace(day=day)
                    if attendance_date.weekday() < 5:  # أيام العمل فقط
                        Attendance.objects.create(
                            employee=self.employee,
                            date=attendance_date,
                            shift=self.shift,
                            check_in=timezone.make_aware(
                                datetime.combine(attendance_date, time(8, 0))
                            ),
                            status='absent',
                            work_hours=Decimal('0')
                        )
                except ValueError:
                    # تجاهل الأيام غير الصالحة
                    pass
        
        # تأخير (يوم واحد)
        try:
            late_date = payroll_month.replace(day=25)
            if late_date.weekday() < 5:
                Attendance.objects.create(
                    employee=self.employee,
                    date=late_date,
                    shift=self.shift,
                    check_in=timezone.make_aware(
                        datetime.combine(late_date, time(8, 30))
                    ),
                    check_out=timezone.make_aware(
                        datetime.combine(late_date, time(16, 0))
                    ),
                    status='late',
                    work_hours=Decimal('7.5'),
                    late_minutes=30
                )
        except ValueError:
            pass
        
        # حساب خصومات الحضور
        monthly_attendances = Attendance.objects.filter(
            employee=self.employee,
            date__year=payroll_month.year,
            date__month=payroll_month.month
        )
        
        absent_days = monthly_attendances.filter(status='absent').count()
        total_late_minutes = sum(
            att.late_minutes for att in monthly_attendances.filter(status='late')
        )
        
        # إنشاء قسيمة راتب
        daily_salary = Decimal('8000.00') / 30  # راتب يومي
        absence_deduction = daily_salary * absent_days
        late_deduction = (daily_salary / 8) * (Decimal(str(total_late_minutes)) / 60)  # خصم بالساعة
        
        payroll = Payroll.objects.create(
            employee=self.employee,
            month=payroll_month,
            contract=self.contract,
            basic_salary=Decimal('8000.00'),
            gross_salary=Decimal('8000.00'),  # إضافة الحقل المطلوب
            net_salary=Decimal('8000.00'),    # إضافة الحقل المطلوب (سيتم تحديثه لاحقاً)
            absence_days=absent_days,
            absence_deduction=absence_deduction,
            late_deduction=late_deduction,
            processed_by=self.admin_user,
            status='calculated'
        )
        
        # إضافة بنود الراتب
        PayrollLine.objects.create(
            payroll=payroll,
            code='BASIC_SALARY',
            name='الراتب الأساسي',
            component_type='earning',
            quantity=Decimal('1'),
            rate=Decimal('8000.00'),
            amount=Decimal('8000.00'),
            order=1
        )
        
        if absence_deduction > 0:
            PayrollLine.objects.create(
                payroll=payroll,
                code='ABSENCE_DEDUCTION',
                name='خصم غياب',
                component_type='deduction',
                quantity=Decimal('1'),
                rate=absence_deduction,
                amount=absence_deduction,
                order=10
            )
        
        if late_deduction > 0:
            PayrollLine.objects.create(
                payroll=payroll,
                code='LATE_DEDUCTION',
                name='خصم تأخير',
                component_type='deduction',
                quantity=Decimal('1'),
                rate=late_deduction,
                amount=late_deduction,
                order=11
            )
        
        # حساب الإجماليات
        payroll.calculate_totals_from_lines()
        payroll.save()  # حفظ التحديثات
        payroll.refresh_from_db()  # إعادة تحميل من قاعدة البيانات
        
        # التحقق من الحسابات
        self.assertEqual(payroll.absence_days, absent_days)
        self.assertGreater(payroll.absence_deduction, Decimal('0'))
        if total_late_minutes > 0:
            self.assertGreater(payroll.late_deduction, Decimal('0'))
        
        expected_net = Decimal('8000.00') - payroll.total_deductions
        self.assertEqual(payroll.net_salary, expected_net)
    
    def test_payroll_approval_workflow(self):
        """
        اختبار سير عمل اعتماد الراتب
        Requirements: T044 - حساب الراتب الشهري
        """
        # إنشاء قسيمة راتب
        payroll_month = date.today().replace(day=1)
        
        payroll = Payroll.objects.create(
            employee=self.employee,
            month=payroll_month,
            contract=self.contract,
            basic_salary=Decimal('7000.00'),
            gross_salary=Decimal('7000.00'),  # إضافة الحقل المطلوب
            net_salary=Decimal('7000.00'),    # إضافة الحقل المطلوب
            processed_by=self.admin_user,
            status='draft'
        )
        
        # إضافة بنود الراتب
        PayrollLine.objects.create(
            payroll=payroll,
            code='BASIC_SALARY',
            name='الراتب الأساسي',
            component_type='earning',
            quantity=Decimal('1'),
            rate=Decimal('7000.00'),
            amount=Decimal('7000.00'),
            order=1
        )
        
        # حساب الإجماليات
        payroll.calculate_totals_from_lines()
        
        # التحقق من الحالة الأولية
        self.assertEqual(payroll.status, 'draft')
        self.assertIsNone(payroll.approved_by)
        self.assertIsNone(payroll.approved_at)
        
        # حساب الراتب
        payroll.status = 'calculated'
        payroll.processed_at = timezone.now()
        payroll.save()
        
        self.assertEqual(payroll.status, 'calculated')
        self.assertIsNotNone(payroll.processed_at)
        
        # اعتماد الراتب
        payroll.status = 'approved'
        payroll.approved_by = self.admin_user
        payroll.approved_at = timezone.now()
        payroll.save()
        
        self.assertEqual(payroll.status, 'approved')
        self.assertEqual(payroll.approved_by, self.admin_user)
        self.assertIsNotNone(payroll.approved_at)
        
        # دفع الراتب
        payroll.status = 'paid'
        payroll.payment_date = date.today()
        payroll.payment_reference = 'PAY2025001'
        payroll.save()
        
        self.assertEqual(payroll.status, 'paid')
        self.assertIsNotNone(payroll.payment_date)
        self.assertEqual(payroll.payment_reference, 'PAY2025001')
    
    def test_payroll_validation_rules(self):
        """
        اختبار قواعد التحقق من صحة الراتب
        """
        # محاولة إنشاء راتب بقيم سالبة
        payroll = Payroll(
            employee=self.employee,
            month=date.today().replace(day=1),
            contract=self.contract,
            basic_salary=Decimal('-1000.00'),  # راتب سالب
            gross_salary=Decimal('-1000.00'),  # إضافة الحقل المطلوب
            net_salary=Decimal('-1000.00'),    # إضافة الحقل المطلوب
            processed_by=self.admin_user
        )
        
        with self.assertRaises(ValidationError):
            payroll.full_clean()
        
        # محاولة إنشاء راتب بساعات عمل إضافي مفرطة
        payroll = Payroll(
            employee=self.employee,
            month=date.today().replace(day=1),
            contract=self.contract,
            basic_salary=Decimal('5000.00'),
            gross_salary=Decimal('5000.00'),  # إضافة الحقل المطلوب
            net_salary=Decimal('5000.00'),    # إضافة الحقل المطلوب
            overtime_hours=Decimal('200.0'),  # ساعات مفرطة
            processed_by=self.admin_user
        )
        
        with self.assertRaises(ValidationError):
            payroll.full_clean()


class PayrollIntegrationTest(TransactionTestCase):
    """اختبارات التكامل لنظام الرواتب"""
    
    def setUp(self):
        """إعداد البيانات للاختبارات التكاملية"""
        self.admin_user = User.objects.create_user(
            username='admin_payroll_int',
            password='admin123',
            is_staff=True,
            is_superuser=True
        )
        
        self.department = Department.objects.create(
            code='HR_PAYROLL',
            name_ar='الموارد البشرية - الرواتب'
        )
        
        self.job_title = JobTitle.objects.create(
            code='HR_MANAGER',
            title_ar='مدير موارد بشرية',
            department=self.department
        )
        
        self.shift = Shift.objects.create(
            name='وردية إدارية',
            shift_type='morning',
            start_time=time(9, 0),
            end_time=time(17, 0),
            work_hours=Decimal('8.0')
        )
        
        # إنشاء عدة موظفين للاختبار
        from datetime import datetime
        import time as time_module
        self.employees = []
        arabic_names = ['أحمد محمد', 'محمد علي', 'علي حسن']
        for i in range(3):
            time_module.sleep(0.01)  # Small delay for unique timestamp
            ts = datetime.now().strftime('%Y%m%d%H%M%S')
            user = User.objects.create_user(
                username=f'payroll_emp_{i+1}_{ts}',
                password='emp123',
                email=f'payroll_emp_{i+1}_{ts}@test.com'
            )
            
            employee = Employee.objects.create(
                user=user,
                employee_number=f'EMPPAY{ts[-8:]}{i}',
                name=arabic_names[i],  # Pure Arabic name
                national_id=f'2900101123470{i}',
                birth_date=date(1985 + i, 1, 1),
                gender='male',
                marital_status='single',
                work_email=f'payroll_emp_{i+1}_{ts}@company.com',
                mobile_phone=f'0123456800{i}',
                department=self.department,
                job_title=self.job_title,
                shift=self.shift,
                hire_date=date.today() - timedelta(days=180),
                status='active',
                created_by=self.admin_user
            )
            
            # إنشاء عقد لكل موظف
            contract = Contract.objects.create(
                contract_number=f'CON202550{i+1}',
                employee=employee,
                contract_type='permanent',
                start_date=employee.hire_date,
                basic_salary=Decimal(str(8000 + (i * 1000))),  # رواتب متدرجة
                status='active',
                created_by=self.admin_user
            )
            
            self.employees.append((employee, contract))
    
    def test_bulk_payroll_processing(self):
        """
        اختبار معالجة رواتب متعددة
        Requirements: T044 - حساب الراتب الشهري
        """
        payroll_month = date.today().replace(day=1)
        payrolls = []
        
        # إنشاء قسائم رواتب لجميع الموظفين
        for employee, contract in self.employees:
            # إضافة بنود راتب أساسية
            SalaryComponent.objects.create(
                employee=employee,
                contract=contract,
                code='BASIC_SALARY',
                name='الراتب الأساسي',
                component_type='earning',
                amount=contract.basic_salary,
                is_active=True,
                effective_from=contract.start_date
            )
            
            # إنشاء قسيمة راتب
            payroll = Payroll.objects.create(
                employee=employee,
                month=payroll_month,
                contract=contract,
                basic_salary=contract.basic_salary,
                gross_salary=contract.basic_salary,  # إضافة الحقل المطلوب
                net_salary=contract.basic_salary,    # إضافة الحقل المطلوب
                processed_by=self.admin_user,
                status='draft'
            )
            
            # إضافة بنود الراتب
            PayrollLine.objects.create(
                payroll=payroll,
                code='BASIC_SALARY',
                name='الراتب الأساسي',
                component_type='earning',
                quantity=Decimal('1'),
                rate=contract.basic_salary,
                amount=contract.basic_salary,
                order=1
            )
            
            # حساب الإجماليات
            payroll.calculate_totals_from_lines()
            payroll.status = 'calculated'
            payroll.save()  # حفظ التحديثات
            payroll.refresh_from_db()  # إعادة تحميل من قاعدة البيانات
            
            payrolls.append(payroll)
        
        # التحقق من معالجة جميع الرواتب
        self.assertEqual(len(payrolls), 3)
        
        for i, payroll in enumerate(payrolls):
            expected_salary = Decimal(str(8000 + (i * 1000)))
            self.assertEqual(payroll.basic_salary, expected_salary)
            self.assertEqual(payroll.gross_salary, expected_salary)
            self.assertEqual(payroll.net_salary, expected_salary)
            self.assertEqual(payroll.status, 'calculated')
        
        # اعتماد جميع الرواتب
        for payroll in payrolls:
            payroll.status = 'approved'
            payroll.approved_by = self.admin_user
            payroll.approved_at = timezone.now()
            payroll.save()
        
        # التحقق من الاعتماد
        approved_payrolls = Payroll.objects.filter(
            month=payroll_month,
            status='approved'
        )
        self.assertEqual(approved_payrolls.count(), 3)
        
        # حساب إجمالي الرواتب
        total_payroll = sum(p.net_salary for p in approved_payrolls)
        expected_total = Decimal('27000.00')  # 8000 + 9000 + 10000
        self.assertEqual(total_payroll, expected_total)


if __name__ == '__main__':
    pytest.main([__file__])