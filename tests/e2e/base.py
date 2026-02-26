# -*- coding: utf-8 -*-
"""
Base classes for E2E Integration Tests
الفئات الأساسية لاختبارات التكامل المتكاملة
"""

import os
import time
import uuid
from datetime import datetime, date, timedelta
from decimal import Decimal
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from django.db import transaction
from PIL import Image
import io
import logging

# Import models with error handling
try:
    from client.models import Customer
    from sale.models import Sale
    from financial.models import ChartOfAccounts, JournalEntry, AccountingPeriod
except ImportError as e:
    logger.warning(f"Some models not available: {e}")
    
try:
    from product.models import Product
except ImportError:
    Product = None

User = get_user_model()
logger = logging.getLogger(__name__)


class E2ETestCase(TransactionTestCase):
    """
    الفئة الأساسية لجميع اختبارات E2E
    تدعم استخدام قاعدة البيانات الحقيقية مع تنظيف آمن للبيانات
    """
    
    # استخدام قاعدة البيانات الحقيقية
    databases = '__all__'
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ensure_test_prerequisites()
        
    def setUp(self):
        """إعداد الاختبار"""
        # إنشاء prefix فريد لكل اختبار
        self.test_prefix = f"E2E_TEST_{int(time.time())}_{uuid.uuid4().hex[:8]}_"
        
        # قوائم لتتبع الكائنات المُنشأة
        self.created_objects = []
        self.uploaded_files = []
        self.test_users = {}
        
        # إعداد المستخدمين الأساسيين
        self.setup_test_users()
        
        logger.info(f"بدء اختبار E2E: {self.__class__.__name__}.{self._testMethodName}")
        
    def tearDown(self):
        """تنظيف البيانات بعد الاختبار"""
        try:
            self.cleanup_test_data()
            logger.info(f"انتهاء اختبار E2E: {self.__class__.__name__}.{self._testMethodName}")
        except Exception as e:
            logger.error(f"خطأ في تنظيف البيانات: {e}")
            
    @classmethod
    def ensure_test_prerequisites(cls):
        """التأكد من وجود البيانات الأساسية المطلوبة"""
        
        try:
            # إنشاء Academic Year إذا لم يكن موجود
            if not AcademicYear.objects.exists():
                AcademicYear.objects.create(
                    year=2024,
                    year_type="academic",
                    start_date=date(2024, 9, 1),
                    end_date=date(2025, 6, 30),
                    is_active=True
                )
                
            # إنشاء Fee Types أساسية إذا كانت متاحة
            if FeeType and not FeeType.objects.exists():
                FeeType.objects.create(
                    name="رسوم دراسية شهرية",
                    code="MONTHLY_TUITION",
                    default_amount=500.00,
                    is_active=True
                )
                FeeType.objects.create(
                    name="رسوم تسجيل",
                    code="REGISTRATION",
                    default_amount=200.00,
                    is_active=True
                )
        except Exception as e:
            logger.warning(f"Could not create prerequisites: {e}")
            # لا نرفع خطأ هنا لأن بعض النماذج قد لا تكون متاحة
            
    def setup_test_users(self):
        """إعداد المستخدمين للاختبار"""
        # مستخدم إداري
        self.test_users['admin'] = self.create_test_user(
            username=f"{self.test_prefix}admin",
            email=f"{self.test_prefix}admin@test.com",
            is_staff=True,
            is_superuser=True
        )
        
        # مستخدم عادي
        self.test_users['user'] = self.create_test_user(
            username=f"{self.test_prefix}user",
            email=f"{self.test_prefix}user@test.com"
        )
        
    def create_test_user(self, username, email, password="testpass123", **kwargs):
        """إنشاء مستخدم للاختبار"""
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            **kwargs
        )
        self.track_object(user)
        return user
        
    def track_object(self, obj):
        """تتبع الكائنات المُنشأة للحذف لاحقاً"""
        self.created_objects.append(obj)
        return obj
        
    def track_file(self, file_path):
        """تتبع الملفات المرفوعة للحذف لاحقاً"""
        self.uploaded_files.append(file_path)
        return file_path
        
    def cleanup_test_data(self):
        """تنظيف البيانات التجريبية"""
        
        # حذف الكائنات بالترتيب العكسي لتجنب مشاكل Foreign Keys
        for obj in reversed(self.created_objects):
            try:
                if hasattr(obj, 'delete') and obj.pk:
                    # تجاهل أخطاء حذف المستخدمين (قد يكونوا محميين بواسطة AuditTrail)
                    if isinstance(obj, User):
                        try:
                            obj.delete()
                        except Exception as user_error:
                            logger.debug(f"تعذر حذف المستخدم {obj} (محمي): {user_error}")
                    else:
                        obj.delete()
            except Exception as e:
                logger.warning(f"تعذر حذف الكائن {obj}: {e}")
                
        # حذف الملفات المرفوعة
        for file_path in self.uploaded_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.warning(f"تعذر حذف الملف {file_path}: {e}")
                
        # تنظيف إضافي للكائنات بالـ prefix
        self.cleanup_objects_by_prefix()
        
    def cleanup_objects_by_prefix(self):
        """تنظيف الكائنات بناءً على الـ prefix"""
        try:
            # حذف QR Applications أولاً (قبل QR Codes)
            if QRApplication:
                QRApplication.objects.filter(
                    student_name__startswith=self.test_prefix
                ).delete()
            
            # حذف QR Codes (قبل المستخدمين لأنها تحتوي على created_by)
            if QRCode:
                QRCode.objects.filter(
                    token__startswith=self.test_prefix
                ).delete()
            
            # حذف الطلاب
            Student.objects.filter(
                name__startswith=self.test_prefix
            ).delete()
            
            # حذف أولياء الأمور
            Parent.objects.filter(
                name__startswith=self.test_prefix
            ).delete()
            
            # حذف المستخدمين (آخر شيء، وقد يفشل بسبب AuditTrail)
            try:
                User.objects.filter(username__startswith=self.test_prefix).delete()
            except Exception as user_delete_error:
                # تجاهل أخطاء حذف المستخدمين (قد يكونوا محميين بواسطة AuditTrail)
                logger.debug(f"تعذر حذف المستخدمين (محميين): {user_delete_error}")
            
        except Exception as e:
            logger.warning(f"خطأ في التنظيف بالـ prefix: {e}")
            
    def create_test_image(self, filename="test_image.jpg", size=(100, 100)):
        """إنشاء صورة تجريبية للاختبار"""
        # إنشاء صورة بسيطة
        image = Image.new('RGB', size, color='red')
        
        # حفظها في memory
        image_io = io.BytesIO()
        image.save(image_io, format='JPEG')
        image_io.seek(0)
        
        # إنشاء ملف مرفوع
        uploaded_file = SimpleUploadedFile(
            name=filename,
            content=image_io.getvalue(),
            content_type='image/jpeg'
        )
        
        return uploaded_file
        
    def wait_for_signals(self, timeout=2):
        """انتظار تنفيذ الـ signals"""
        time.sleep(0.5)  # انتظار قصير للـ signals
        
    def assert_signal_fired(self, signal_description, **checks):
        """التحقق من تشغيل signal معين"""
        # يمكن تطوير هذا لاحقاً لتتبع الـ signals بدقة أكبر
        logger.info(f"التحقق من تشغيل signal: {signal_description}")
        
        # التحقق من النتائج المتوقعة
        for check_name, expected_value in checks.items():
            if hasattr(self, f'verify_{check_name}'):
                getattr(self, f'verify_{check_name}')(expected_value)
                
    def simulate_form_submission(self, url, data, files=None, user=None):
        """محاكاة تقديم فورم بـ CSRF وكل التفاصيل"""
        if user:
            self.client.force_login(user)
            
        # الحصول على CSRF token
        response = self.client.get(url)
        if response.status_code == 200:
            csrf_token = response.context.get('csrf_token')
            if csrf_token:
                data['csrfmiddlewaretoken'] = csrf_token
                
        # تقديم الفورم
        return self.client.post(url, data=data, files=files, follow=True)
        
    def get_current_academic_year(self):
        """الحصول على السنة الدراسية الحالية"""
        return AcademicYear.objects.filter(is_active=True).first()
        
    def get_available_classroom(self, grade_level=1):
        """الحصول على فصل متاح"""
        if ClassroomYear:
            return ClassroomYear.objects.filter(
                grade_level=grade_level,
                is_active=True
            ).first()
        return None


class CircleTestCase(E2ETestCase):
    """
    فئة متخصصة لاختبار دائرة متكاملة
    """
    
    def setUp(self):
        super().setUp()
        self.circle_data = {}
        self.circle_steps = []
        self.performance_metrics = {}
        
        # ✅ إضافة admin_user كـ shortcut للوصول السريع
        self.admin_user = self.test_users['admin']
        
        # ✅ Task 17.1: HTTP metrics tracking
        self.http_metrics = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_response_time': 0.0,
            'requests': []  # List of individual request details
        }
    
    def get_url(self, url_key, *args, **kwargs):
        """
        Get URL by key with arguments
        الحصول على URL باستخدام المفتاح مع المعاملات
        
        Args:
            url_key: URL key from REQUIRED_URLS mapping
            *args: Positional arguments for URL reverse
            **kwargs: Keyword arguments for URL reverse
            
        Returns:
            Resolved URL string
            
        Raises:
            ValueError: If URL key is not found in REQUIRED_URLS
        """
        if not hasattr(self, 'REQUIRED_URLS'):
            raise AttributeError(
                f"Test class {self.__class__.__name__} must define REQUIRED_URLS dictionary"
            )
        
        url_name = self.REQUIRED_URLS.get(url_key)
        if not url_name:
            raise ValueError(
                f"Unknown URL key: {url_key}. "
                f"Available keys: {', '.join(self.REQUIRED_URLS.keys())}"
            )
        
        return reverse(url_name, args=args, kwargs=kwargs)

    def post_form(self, url_name, data, url_args=None, user=None, follow=True):
        """
        Helper to POST form data with proper CSRF handling
        مساعد لإرسال بيانات النموذج مع معالجة CSRF بشكل صحيح

        Args:
            url_name: URL name for reverse()
            data: Form data dictionary
            url_args: Arguments for URL reverse
            user: User to authenticate (defaults to admin_user)
            follow: Whether to follow redirects

        Returns:
            Response object
        """
        if user is None:
            user = self.admin_user

        self.client.force_login(user)
        url = reverse(url_name, args=url_args) if url_args else reverse(url_name)

        # Get CSRF token
        get_response = self.client.get(url)
        if hasattr(get_response, 'context') and get_response.context:
            csrf_token = get_response.context.get('csrf_token')
            if csrf_token:
                data['csrfmiddlewaretoken'] = str(csrf_token)

        # ✅ Task 17.1: Track HTTP request metrics
        start_time = time.time()
        response = self.client.post(url, data=data, follow=follow)
        duration = time.time() - start_time
        
        # Record metrics
        self.http_metrics['total_requests'] += 1
        self.http_metrics['total_response_time'] += duration
        
        if response.status_code in [200, 201, 302, 303]:
            self.http_metrics['successful_requests'] += 1
        else:
            self.http_metrics['failed_requests'] += 1
        
        self.http_metrics['requests'].append({
            'method': 'POST',
            'url': url,
            'status_code': response.status_code,
            'duration': duration
        })
        
        return response

    def assert_successful_post(self, response, expected_redirect=None):
        """
        Assert that a POST request was successful
        التحقق من نجاح طلب POST

        Args:
            response: Response object from POST request
            expected_redirect: Expected redirect URL (optional)
        """
        self.assertIn(response.status_code, [200, 201, 302, 303])

        if expected_redirect:
            self.assertRedirects(response, expected_redirect)
        elif response.status_code in [302, 303]:
            # Just verify it redirected somewhere
            self.assertTrue(response.url)

    def assert_form_error(self, response, field_name=None, error_message=None):
        """
        Assert that a form submission resulted in errors
        التحقق من وجود أخطاء في تقديم النموذج

        Args:
            response: Response object from POST request
            field_name: Specific field to check (optional)
            error_message: Expected error message substring (optional)
        """
        self.assertEqual(response.status_code, 200)  # Form re-rendered with errors

        if hasattr(response, 'context') and response.context:
            form = response.context.get('form')
            self.assertIsNotNone(form, "No form in context")
            self.assertTrue(form.errors, "Form has no errors")

            if field_name:
                self.assertIn(field_name, form.errors)

            if error_message:
                all_errors = str(form.errors)
                self.assertIn(error_message, all_errors)

    def verify_signal_effect(self, model_class, filter_kwargs, expected_count=None,
                             error_message=None):
        """
        Verify that a signal created expected objects
        التحقق من أن الإشارة أنشأت الكائنات المتوقعة

        Args:
            model_class: Model class to query
            filter_kwargs: Filter arguments for query
            expected_count: Expected number of objects (optional)
            error_message: Custom error message (optional)

        Returns:
            QuerySet of found objects
        """
        queryset = model_class.objects.filter(**filter_kwargs)

        if expected_count is not None:
            actual_count = queryset.count()
            msg = error_message or f"Expected {expected_count} {model_class.__name__} objects, found {actual_count}"
            self.assertEqual(actual_count, expected_count, msg)
        else:
            msg = error_message or f"No {model_class.__name__} objects found with {filter_kwargs}"
            self.assertTrue(queryset.exists(), msg)

        # ✅ Task 17.2: Track signal verification
        if not hasattr(self, 'signal_verifications'):
            self.signal_verifications = []
        
        self.signal_verifications.append({
            'model': model_class.__name__,
            'filter': filter_kwargs,
            'expected_count': expected_count,
            'actual_count': queryset.count(),
            'verified': queryset.exists() and (expected_count is None or queryset.count() == expected_count)
        })

        return queryset

        
    def execute_circle_step(self, step_name, step_function):
        """تنفيذ خطوة من خطوات الدائرة مع قياس الأداء"""
        start_time = time.time()
        
        logger.info(f"تنفيذ خطوة: {step_name}")
        
        try:
            result = step_function()
            end_time = time.time()
            
            step_data = {
                'name': step_name,
                'result': result,
                'duration': end_time - start_time,
                'success': True,
                'timestamp': datetime.now()
            }
            
            self.circle_steps.append(step_data)
            self.performance_metrics[step_name] = end_time - start_time
            
            logger.info(f"✅ نجحت خطوة {step_name} في {step_data['duration']:.2f} ثانية")
            
            return result
            
        except Exception as e:
            end_time = time.time()
            
            step_data = {
                'name': step_name,
                'error': str(e),
                'duration': end_time - start_time,
                'success': False,
                'timestamp': datetime.now()
            }
            
            self.circle_steps.append(step_data)
            
            logger.error(f"❌ فشلت خطوة {step_name}: {e}")
            raise
            
    def validate_circle_integrity(self):
        """التحقق من سلامة الدائرة الكاملة"""
        logger.info("التحقق من سلامة الدائرة الكاملة...")
        
        # التحقق من نجاح جميع الخطوات
        failed_steps = [step for step in self.circle_steps if not step['success']]
        if failed_steps:
            self.fail(f"فشلت خطوات: {[step['name'] for step in failed_steps]}")
            
        # التحقق من الأداء
        slow_steps = [
            step for step in self.circle_steps 
            if step['success'] and step['duration'] > 5.0
        ]
        if slow_steps:
            logger.warning(f"خطوات بطيئة: {[(step['name'], step['duration']) for step in slow_steps]}")
            
        logger.info("✅ تم التحقق من سلامة الدائرة بنجاح")
        
    def get_performance_report(self):
        """إنشاء تقرير الأداء"""
        total_time = sum(self.performance_metrics.values())
        
        report = {
            'total_steps': len(self.circle_steps),
            'successful_steps': len([s for s in self.circle_steps if s['success']]),
            'total_duration': total_time,
            'average_step_duration': total_time / len(self.circle_steps) if self.circle_steps else 0,
            'slowest_step': max(self.performance_metrics.items(), key=lambda x: x[1]) if self.performance_metrics else None,
            'fastest_step': min(self.performance_metrics.items(), key=lambda x: x[1]) if self.performance_metrics else None,
            'steps_details': self.circle_steps
        }
        
        return report
    
    def ensure_accounting_period_exists(self):
        """التأكد من وجود فترة محاسبية مفتوحة"""
        if not hasattr(self, 'accounting_period') or not self.accounting_period:
            current_year = date.today().year
            # البحث عن فترة موجودة أولاً
            self.accounting_period = AccountingPeriod.objects.filter(
                start_date__lte=date.today(),
                end_date__gte=date.today(),
                status='open'
            ).first()
            
            # إنشاء فترة جديدة إذا لم توجد
            if not self.accounting_period:
                self.accounting_period = AccountingPeriod.objects.create(
                    name=f'{self.test_prefix}فترة محاسبية {current_year}',
                    start_date=date(current_year, 1, 1),
                    end_date=date(current_year, 12, 31),
                    status='open',
                    created_by=self.admin_user
                )
                self.track_object(self.accounting_period)
    
    def validate_fees_accounting_setup(self):
        """التحقق من إعداد النظام المحاسبي للرسوم"""
        errors = []
        
        # التحقق من وجود الحسابات المطلوبة
        required_accounts = {
            '10100': 'الخزنة',
            '40100': 'إيرادات الرسوم الدراسية',
            '20200': 'مستحقات الرواتب'
        }
        
        for code, name in required_accounts.items():
            if not ChartOfAccounts.objects.filter(code=code).exists():
                errors.append(f"الحساب {name} ({code}) غير موجود")
        
        return {
            'is_valid': len(errors) == 0,
            'errors': errors
        }
    
    def validate_payroll_accounting_setup(self):
        """التحقق من إعداد النظام المحاسبي للرواتب"""
        errors = []
        
        # التحقق من وجود الحسابات المطلوبة
        required_accounts = {
            '50500': 'مصروفات متنوعة',
            '20200': 'مستحقات الرواتب',
            '20300': 'الرواتب مستحقة الدفع',
            '10200': 'البنك'
        }
        
        for code, name in required_accounts.items():
            if not ChartOfAccounts.objects.filter(code=code).exists():
                errors.append(f"الحساب {name} ({code}) غير موجود")
        
        return {
            'is_valid': len(errors) == 0,
            'errors': errors
        }
    
    def get_or_create_account_type(self, category):
        """الحصول على نوع حساب أو إنشاؤه"""
        from financial.models.chart_of_accounts import AccountType
        
        account_type_map = {
            'asset': {'name': 'أصول', 'nature': 'debit', 'code': 'ASSET'},
            'liability': {'name': 'خصوم', 'nature': 'credit', 'code': 'LIABILITY'},
            'revenue': {'name': 'إيرادات', 'nature': 'credit', 'code': 'REVENUE'},
            'expense': {'name': 'مصروفات', 'nature': 'debit', 'code': 'EXPENSE'},
            'equity': {'name': 'حقوق ملكية', 'nature': 'credit', 'code': 'EQUITY'}
        }
        
        if category not in account_type_map:
            raise ValueError(f"نوع حساب غير معروف: {category}")
        
        type_data = account_type_map[category]
        account_type, created = AccountType.objects.get_or_create(
            code=type_data['code'],
            defaults={
                'name': type_data['name'],
                'category': category,
                'nature': type_data['nature']
            }
        )
        
        if created:
            self.track_object(account_type)
        
        return account_type
    
    def calculate_account_balance(self, account):
        """حساب رصيد حساب محاسبي"""
        from financial.models import JournalEntryLine
        from django.db.models import Sum
        
        lines = JournalEntryLine.objects.filter(account=account)
        
        total_debit = lines.aggregate(total=Sum('debit'))['total'] or Decimal('0.00')
        total_credit = lines.aggregate(total=Sum('credit'))['total'] or Decimal('0.00')
        
        # حساب الرصيد حسب طبيعة الحساب
        if account.account_type.nature == 'debit':
            return total_debit - total_credit
        else:
            return total_credit - total_debit
    
    def analyze_error(self, error, step_name):
        """تحليل الخطأ وإنشاء تقرير استشاري"""
        error_str = str(error).lower()
        
        analysis = {
            'step': step_name,
            'error': str(error),
            'type': 'UNKNOWN',
            'severity': 'HIGH',
            'recommendation': 'فحص يدوي للخطأ'
        }
        
        if 'does not exist' in error_str or 'no such table' in error_str:
            analysis['type'] = 'DATABASE_SCHEMA'
            analysis['recommendation'] = 'تشغيل المهاجرات: python manage.py migrate'
        elif 'foreign key' in error_str:
            analysis['type'] = 'FOREIGN_KEY_CONSTRAINT'
            analysis['recommendation'] = 'التحقق من وجود الكائنات المرتبطة'
        elif 'not null' in error_str:
            analysis['type'] = 'NULL_CONSTRAINT'
            analysis['recommendation'] = 'توفير قيمة للحقول المطلوبة'
        
        return analysis
    
    def calculate_success_rate(self):
        """حساب معدل نجاح الدائرة"""
        if not self.circle_steps:
            return 0
        
        successful = len([s for s in self.circle_steps if s.get('success', False)])
        return int((successful / len(self.circle_steps)) * 100)
    
    def generate_professional_advisory_report(self):
        """إنشاء تقرير استشاري مهني"""
        report_lines = []
        report_lines.append("\n" + "="*80)
        report_lines.append("📊 التقرير الاستشاري المهني - دائرة الاختبار")
        report_lines.append("="*80)
        
        # معدل النجاح
        success_rate = self.calculate_success_rate()
        report_lines.append(f"\n🎯 معدل النجاح: {success_rate}%")
        
        # الخطوات المنفذة
        report_lines.append(f"\n📋 الخطوات المنفذة: {len(self.circle_steps)}")
        for step in self.circle_steps:
            status = "✅" if step.get('success') else "❌"
            duration = step.get('duration', 0)
            report_lines.append(f"   {status} {step['name']} ({duration:.2f}s)")
        
        # ✅ Task 17.3: HTTP metrics in advisory report
        if hasattr(self, 'http_metrics') and self.http_metrics['total_requests'] > 0:
            report_lines.append(f"\n🌐 مقاييس HTTP:")
            report_lines.append(f"   📊 إجمالي الطلبات: {self.http_metrics['total_requests']}")
            report_lines.append(f"   ✅ طلبات ناجحة: {self.http_metrics['successful_requests']}")
            report_lines.append(f"   ❌ طلبات فاشلة: {self.http_metrics['failed_requests']}")
            
            avg_time = self.http_metrics['total_response_time'] / self.http_metrics['total_requests']
            report_lines.append(f"   ⏱️ متوسط وقت الاستجابة: {avg_time:.3f}s")
            
            # Slowest request
            if self.http_metrics['requests']:
                slowest = max(self.http_metrics['requests'], key=lambda x: x['duration'])
                report_lines.append(f"   🐌 أبطأ طلب: {slowest['url']} ({slowest['duration']:.3f}s)")
        
        # ✅ Task 17.2: Signal verification tracking
        if hasattr(self, 'signal_verifications'):
            total_signals = len(self.signal_verifications)
            working_signals = len([s for s in self.signal_verifications if s.get('verified')])
            report_lines.append(f"\n🔔 التحقق من الإشارات:")
            report_lines.append(f"   📊 إجمالي الإشارات المختبرة: {total_signals}")
            report_lines.append(f"   ✅ إشارات تعمل: {working_signals}")
            report_lines.append(f"   ❌ إشارات فاشلة: {total_signals - working_signals}")
        
        # المشاكل الحرجة
        if hasattr(self, 'advisory_report') and self.advisory_report.get('critical_issues'):
            report_lines.append(f"\n🚨 المشاكل الحرجة: {len(self.advisory_report['critical_issues'])}")
            for issue in self.advisory_report['critical_issues']:
                report_lines.append(f"   ❌ {issue.get('message', 'مشكلة غير محددة')}")
        
        # التحذيرات
        if hasattr(self, 'advisory_report') and self.advisory_report.get('warnings'):
            report_lines.append(f"\n⚠️ التحذيرات: {len(self.advisory_report['warnings'])}")
            for warning in self.advisory_report['warnings'][:5]:  # أول 5 تحذيرات فقط
                report_lines.append(f"   ⚠️ {warning.get('message', 'تحذير غير محدد')}")
        
        report_lines.append("\n" + "="*80)
        
        return "\n".join(report_lines)

    # ============================================================================
    # Helper Methods for Common Test Patterns
    # ============================================================================

    def create_student_via_http(self, student_data=None, parent_data=None):
        """
        Helper to create student via HTTP POST
        مساعد لإنشاء طالب عبر HTTP POST

        Args:
            student_data: Student data dictionary (optional, will use defaults)
            parent_data: Parent data dictionary (optional, will use defaults)

        Returns:
            tuple: (response, student) - Response object and created Student instance
        """
        from tests.e2e.helpers import prepare_student_registration_form_data

        # Prepare form data
        form_data = prepare_student_registration_form_data(prefix=self.test_prefix)

        # Override with provided data
        if student_data:
            form_data.update(student_data)
        if parent_data:
            form_data.update(parent_data)

        # Submit registration
        response = self.post_form('students:register', form_data)

        # Get created student
        student = None
        if response.status_code in [200, 302]:
            student = Student.objects.filter(
                name=form_data.get('name')
            ).first()
            if student:
                self.track_object(student)

        return response, student

    def create_payment_via_http(self, fee, amount, payment_data=None):
        """
        Helper to create payment via HTTP POST
        مساعد لإنشاء دفعة عبر HTTP POST

        Args:
            fee: StudentFee instance
            amount: Payment amount
            payment_data: Additional payment data (optional)

        Returns:
            tuple: (response, payment) - Response object and created FeePayment instance
        """
        from tests.e2e.helpers import prepare_fee_payment_form_data

        # Prepare form data
        form_data = prepare_fee_payment_form_data(
            fee_id=fee.id,
            amount=amount,
            prefix=self.test_prefix
        )

        # Override with provided data
        if payment_data:
            form_data.update(payment_data)

        # Submit payment
        response = self.post_form('fees:payment_create', form_data)

        # Get created payment
        payment = None
        if response.status_code in [200, 302]:
            payment = FeePayment.objects.filter(
                fee=fee,
                amount=amount
            ).order_by('-created_at').first()
            if payment:
                self.track_object(payment)

        return response, payment

    def verify_error_response(self, response, expected_errors=None, field_name=None):
        """
        Helper to verify error response contains expected errors
        مساعد للتحقق من أن استجابة الخطأ تحتوي على الأخطاء المتوقعة

        Args:
            response: Response object
            expected_errors: List of expected error messages (optional)
            field_name: Specific field to check (optional)
        """
        # Verify response status
        self.assertEqual(response.status_code, 200, "Expected form re-render with errors")

        # Check for form errors
        if hasattr(response, 'context') and response.context:
            form = response.context.get('form')
            if form:
                self.assertTrue(form.errors, "Form should have errors")

                if field_name:
                    self.assertIn(field_name, form.errors,
                                f"Expected error in field: {field_name}")

                if expected_errors:
                    all_errors = str(form.errors)
                    for error_msg in expected_errors:
                        self.assertIn(error_msg, all_errors,
                                    f"Expected error message: {error_msg}")

    def verify_success_message(self, response, message_substring=None):
        """
        Helper to verify success message in response
        مساعد للتحقق من رسالة النجاح في الاستجابة

        Args:
            response: Response object
            message_substring: Expected message substring (optional)
        """
        # Check for messages in context
        if hasattr(response, 'context') and response.context:
            messages = list(response.context.get('messages', []))

            if message_substring:
                found = any(message_substring in str(msg) for msg in messages)
                self.assertTrue(found,
                              f"Expected success message containing: {message_substring}")
            else:
                self.assertTrue(len(messages) > 0, "Expected at least one message")

    def verify_object_in_list(self, list_url, object_identifier, identifier_field='name'):
        """
        Helper to verify object appears in list view
        مساعد للتحقق من ظهور الكائن في عرض القائمة

        Args:
            list_url: URL name for list view
            object_identifier: Value to search for
            identifier_field: Field name to check (default: 'name')

        Returns:
            bool: True if object found in list
        """
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse(list_url))

        self.assertEqual(response.status_code, 200, "List view should be accessible")

        # Check in context
        if hasattr(response, 'context') and response.context:
            object_list = response.context.get('object_list') or response.context.get('students')
            if object_list:
                found = any(
                    getattr(obj, identifier_field, None) == object_identifier
                    for obj in object_list
                )
                return found

        # Check in content
        return object_identifier in response.content.decode('utf-8')

    def setup_basic_student_with_fees(self):
        """
        Helper to setup a basic student with fees for testing
        مساعد لإعداد طالب أساسي مع رسوم للاختبار

        Returns:
            dict: {'student': Student, 'fees': QuerySet, 'response': Response}
        """
        # Create student via HTTP
        response, student = self.create_student_via_http()

        # Verify student created
        self.assertIsNotNone(student, "Student should be created")

        # Wait for signals to create fees
        self.wait_for_signals()

        # Get created fees
        fees = StudentFee.objects.filter(student=student)

        return {
            'student': student,
            'fees': fees,
            'response': response
        }

    def verify_journal_entry_created(self, reference_id, expected_amount=None):
        """
        Helper to verify journal entry was created
        مساعد للتحقق من إنشاء قيد محاسبي

        Args:
            reference_id: Reference ID to search for
            expected_amount: Expected total amount (optional)

        Returns:
            JournalEntry: Found journal entry
        """
        journal_entry = JournalEntry.objects.filter(
            reference_id=reference_id
        ).first()

        self.assertIsNotNone(journal_entry,
                           f"Journal entry should exist for reference: {reference_id}")

        if expected_amount:
            # Verify balanced entry
            from financial.models import JournalEntryLine
            lines = JournalEntryLine.objects.filter(journal_entry=journal_entry)

            total_debit = sum(line.debit for line in lines)
            total_credit = sum(line.credit for line in lines)

            self.assertEqual(total_debit, total_credit,
                           "Journal entry should be balanced")
            self.assertEqual(total_debit, Decimal(str(expected_amount)),
                           f"Expected amount: {expected_amount}")

        return journal_entry

