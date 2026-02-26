"""
اختبارات تكامل نظام التحقق من المعاملات المالية - وحدة Supplier
"""
import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from datetime import date, timedelta

from supplier.models import Supplier, MonthlyDriverInvoice
from financial.models import ChartOfAccounts, AccountingPeriod
from financial.exceptions import FinancialValidationError

User = get_user_model()


class SupplierFinancialValidationTestCase(TestCase):
    """اختبارات التحقق من المعاملات المالية للموردين"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        # إنشاء مستخدم
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # إنشاء حساب محاسبي للموردين
        self.suppliers_account = ChartOfAccounts.objects.create(
            code='20100',
            name='الموردين',
            account_type='liability',
            is_active=True,
            is_leaf=False
        )
        
        # إنشاء حساب محاسبي فرعي
        self.supplier_account = ChartOfAccounts.objects.create(
            code='2010001',
            name='مورد - سائق تجريبي',
            account_type='liability',
            parent=self.suppliers_account,
            is_active=True,
            is_leaf=True
        )
        
        # إنشاء فترة محاسبية مفتوحة
        self.open_period = AccountingPeriod.objects.create(
            name='يناير 2024',
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            status='open'
        )
        
        # إنشاء فترة محاسبية مغلقة
        self.closed_period = AccountingPeriod.objects.create(
            name='ديسمبر 2023',
            start_date=date(2023, 12, 1),
            end_date=date(2023, 12, 31),
            status='closed'
        )
        
        # إنشاء مورد سائق مع حساب محاسبي
        from supplier.models import SupplierType
        driver_type = SupplierType.objects.get(code='driver')
        self.driver_with_account = Supplier.objects.create(
            name='سائق تجريبي',
            code='DRV001',
            phone='01234567890',
            primary_type=driver_type,
            financial_account=self.supplier_account,
            monthly_salary=Decimal('3000.00'),
            is_active=True,
            created_by=self.user
        )
        
        # إنشاء مورد سائق بدون حساب محاسبي
        self.driver_without_account = Supplier.objects.create(
            name='سائق بدون حساب',
            code='DRV002',
            phone='01234567891',
            primary_type=driver_type,
            monthly_salary=Decimal('3000.00'),
            is_active=True,
            created_by=self.user
        )
    
    def test_create_invoice_with_valid_account_and_period(self):
        """اختبار إنشاء فاتورة مع حساب محاسبي صحيح وفترة مفتوحة"""
        # يجب أن تنجح العملية
        invoice = MonthlyDriverInvoice.objects.create(
            driver_supplier=self.driver_with_account,
            month=1,
            year=2024,
            students_count=Decimal('10.0'),
            cost_per_student=Decimal('100.00'),
            generated_by=self.user
        )
        
        self.assertIsNotNone(invoice.id)
        self.assertEqual(invoice.total_amount, Decimal('1000.00'))
        self.assertEqual(invoice.status, 'generated')
    
    def test_create_invoice_without_account(self):
        """اختبار إنشاء فاتورة بدون حساب محاسبي"""
        # يجب أن تفشل العملية
        with self.assertRaises(ValidationError) as context:
            MonthlyDriverInvoice.objects.create(
                driver_supplier=self.driver_without_account,
                month=1,
                year=2024,
                students_count=Decimal('10.0'),
                cost_per_student=Decimal('100.00'),
                generated_by=self.user
            )
        
        # التحقق من رسالة الخطأ
        self.assertIn('driver_supplier', context.exception.message_dict)
    
    def test_create_invoice_with_inactive_account(self):
        """اختبار إنشاء فاتورة مع حساب محاسبي غير مفعّل"""
        # تعطيل الحساب المحاسبي
        self.supplier_account.is_active = False
        self.supplier_account.save()
        
        # يجب أن تفشل العملية
        with self.assertRaises(ValidationError) as context:
            MonthlyDriverInvoice.objects.create(
                driver_supplier=self.driver_with_account,
                month=1,
                year=2024,
                students_count=Decimal('10.0'),
                cost_per_student=Decimal('100.00'),
                generated_by=self.user
            )
        
        # التحقق من رسالة الخطأ
        self.assertIn('driver_supplier', context.exception.message_dict)
        
        # إعادة تفعيل الحساب
        self.supplier_account.is_active = True
        self.supplier_account.save()
    
    def test_create_invoice_with_non_leaf_account(self):
        """اختبار إنشاء فاتورة مع حساب محاسبي غير نهائي"""
        # تغيير الحساب إلى غير نهائي
        self.supplier_account.is_leaf = False
        self.supplier_account.save()
        
        # يجب أن تفشل العملية
        with self.assertRaises(ValidationError) as context:
            MonthlyDriverInvoice.objects.create(
                driver_supplier=self.driver_with_account,
                month=1,
                year=2024,
                students_count=Decimal('10.0'),
                cost_per_student=Decimal('100.00'),
                generated_by=self.user
            )
        
        # التحقق من رسالة الخطأ
        self.assertIn('driver_supplier', context.exception.message_dict)
        
        # إعادة الحساب إلى نهائي
        self.supplier_account.is_leaf = True
        self.supplier_account.save()
    
    def test_create_invoice_in_closed_period(self):
        """اختبار إنشاء فاتورة في فترة محاسبية مغلقة"""
        # إغلاق الفترة المفتوحة
        self.open_period.status = 'closed'
        self.open_period.save()
        
        # يجب أن تفشل العملية
        with self.assertRaises(ValidationError) as context:
            MonthlyDriverInvoice.objects.create(
                driver_supplier=self.driver_with_account,
                month=1,
                year=2024,
                students_count=Decimal('10.0'),
                cost_per_student=Decimal('100.00'),
                generated_by=self.user
            )
        
        # التحقق من رسالة الخطأ
        self.assertIn('driver_supplier', context.exception.message_dict)
        
        # إعادة فتح الفترة
        self.open_period.status = 'open'
        self.open_period.save()
    
    def test_create_invoice_without_period(self):
        """اختبار إنشاء فاتورة بدون فترة محاسبية"""
        # حذف جميع الفترات المحاسبية
        AccountingPeriod.objects.all().delete()
        
        # يجب أن تفشل العملية
        with self.assertRaises(ValidationError) as context:
            MonthlyDriverInvoice.objects.create(
                driver_supplier=self.driver_with_account,
                month=1,
                year=2024,
                students_count=Decimal('10.0'),
                cost_per_student=Decimal('100.00'),
                generated_by=self.user
            )
        
        # التحقق من رسالة الخطأ
        self.assertIn('driver_supplier', context.exception.message_dict)
    
    def test_invoice_balance_update(self):
        """اختبار تحديث رصيد المورد عند إنشاء الفاتورة"""
        # الرصيد الأولي
        initial_balance = self.driver_with_account.balance
        
        # إنشاء فاتورة
        invoice = MonthlyDriverInvoice.objects.create(
            driver_supplier=self.driver_with_account,
            month=1,
            year=2024,
            students_count=Decimal('10.0'),
            cost_per_student=Decimal('100.00'),
            generated_by=self.user
        )
        
        # تحديث الكائن من قاعدة البيانات
        self.driver_with_account.refresh_from_db()
        
        # التحقق من تحديث الرصيد
        expected_balance = initial_balance + invoice.total_amount
        self.assertEqual(self.driver_with_account.balance, expected_balance)
    
    def test_error_message_in_arabic(self):
        """اختبار أن رسائل الخطأ بالعربية"""
        # محاولة إنشاء فاتورة بدون حساب محاسبي
        with self.assertRaises(ValidationError) as context:
            MonthlyDriverInvoice.objects.create(
                driver_supplier=self.driver_without_account,
                month=1,
                year=2024,
                students_count=Decimal('10.0'),
                cost_per_student=Decimal('100.00'),
                generated_by=self.user
            )
        
        # التحقق من أن الرسالة بالعربية
        error_message = str(context.exception)
        # يجب أن تحتوي على كلمات عربية
        self.assertTrue(
            any(arabic_word in error_message for arabic_word in ['حساب', 'محاسبي', 'مورد', 'فترة'])
        )


class SupplierViewsFinancialValidationTestCase(TestCase):
    """اختبارات معالجة الأخطاء في views"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
    
    def test_supplier_add_view_handles_validation_error(self):
        """اختبار معالجة أخطاء التحقق في view إضافة مورد"""
        # هذا الاختبار يتطلب إعداد أكثر تعقيداً
        # يمكن إضافته لاحقاً مع اختبارات integration كاملة
        pass


# يمكن إضافة المزيد من الاختبارات حسب الحاجة
