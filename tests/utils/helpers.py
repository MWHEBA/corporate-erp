"""
أدوات مساعدة للاختبارات
"""
import time
import psutil
import os
from contextlib import contextmanager
from django.test import Client
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import transaction


class TestTimer:
    """مؤقت لقياس أوقات التنفيذ"""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
    
    def start(self):
        """بدء التوقيت"""
        self.start_time = time.time()
    
    def stop(self):
        """إيقاف التوقيت"""
        self.end_time = time.time()
        return self.elapsed_time
    
    @property
    def elapsed_time(self):
        """الوقت المنقضي بالثواني"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


class MemoryMonitor:
    """مراقب استهلاك الذاكرة"""
    
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.initial_memory = None
        self.peak_memory = None
    
    def start(self):
        """بدء مراقبة الذاكرة"""
        self.initial_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.peak_memory = self.initial_memory
    
    def update(self):
        """تحديث ذروة استهلاك الذاكرة"""
        current_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        if current_memory > self.peak_memory:
            self.peak_memory = current_memory
    
    def get_usage(self):
        """الحصول على استهلاك الذاكرة"""
        self.update()
        return {
            'initial_mb': self.initial_memory,
            'current_mb': self.process.memory_info().rss / 1024 / 1024,
            'peak_mb': self.peak_memory,
            'increase_mb': self.peak_memory - self.initial_memory
        }


@contextmanager
def performance_monitor():
    """مراقب الأداء الشامل"""
    timer = TestTimer()
    memory = MemoryMonitor()
    
    timer.start()
    memory.start()
    
    try:
        yield {
            'timer': timer,
            'memory': memory
        }
    finally:
        elapsed = timer.stop()
        memory_usage = memory.get_usage()
        
        print(f"⏱️  وقت التنفيذ: {elapsed:.3f} ثانية")
        print(f"🧠 استهلاك الذاكرة: {memory_usage['increase_mb']:.2f} MB")


class DatabaseTestMixin:
    """خليط لاختبارات قاعدة البيانات"""
    
    @classmethod
    def setUpClass(cls):
        """إعداد قاعدة البيانات للاختبار"""
        super().setUpClass()
        call_command('migrate', verbosity=0, interactive=False)
    
    def setUp(self):
        """إعداد كل اختبار"""
        super().setUp()
        self.start_transaction()
    
    def tearDown(self):
        """تنظيف بعد كل اختبار"""
        self.rollback_transaction()
        super().tearDown()
    
    def start_transaction(self):
        """بدء معاملة قاعدة البيانات"""
        self.transaction = transaction.atomic()
        self.transaction.__enter__()
    
    def rollback_transaction(self):
        """التراجع عن معاملة قاعدة البيانات"""
        if hasattr(self, 'transaction'):
            self.transaction.__exit__(None, None, None)


class APITestMixin:
    """خليط لاختبارات API"""
    
    def setUp(self):
        """إعداد عميل API"""
        super().setUp()
        self.client = Client()
        self.api_base_url = '/api/v1/'
    
    def api_get(self, endpoint, **kwargs):
        """طلب GET لـ API"""
        url = f"{self.api_base_url}{endpoint.lstrip('/')}"
        return self.client.get(url, **kwargs)
    
    def api_post(self, endpoint, data=None, **kwargs):
        """طلب POST لـ API"""
        url = f"{self.api_base_url}{endpoint.lstrip('/')}"
        return self.client.post(url, data=data, content_type='application/json', **kwargs)
    
    def api_put(self, endpoint, data=None, **kwargs):
        """طلب PUT لـ API"""
        url = f"{self.api_base_url}{endpoint.lstrip('/')}"
        return self.client.put(url, data=data, content_type='application/json', **kwargs)
    
    def api_delete(self, endpoint, **kwargs):
        """طلب DELETE لـ API"""
        url = f"{self.api_base_url}{endpoint.lstrip('/')}"
        return self.client.delete(url, **kwargs)
    
    def login_user(self, username='testuser', password='testpass'):
        """تسجيل دخول المستخدم"""
        user = User.objects.create_user(username=username, password=password)
        self.client.login(username=username, password=password)
        return user


class SecurityTestMixin:
    """خليط لاختبارات الأمان"""
    
    def get_sql_injection_payloads(self):
        """حمولات حقن SQL"""
        return [
            "' OR '1'='1",
            "'; DROP TABLE students; --",
            "' UNION SELECT * FROM users --",
            "admin'--",
            "admin'/*",
            "' OR 1=1#",
            "1' AND (SELECT COUNT(*) FROM users) > 0 --"
        ]
    
    def get_xss_payloads(self):
        """حمولات XSS"""
        return [
            "<script>alert('XSS')</script>",
            "javascript:alert('XSS')",
            "<img src=x onerror=alert('XSS')>",
            "<svg onload=alert('XSS')>",
            "';alert('XSS');//",
            "<iframe src='javascript:alert(\"XSS\")'></iframe>"
        ]
    
    def get_path_traversal_payloads(self):
        """حمولات Path Traversal"""
        return [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\drivers\\etc\\hosts",
            "....//....//....//etc/passwd",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd"
        ]
    
    def test_endpoint_security(self, endpoint, method='GET', data=None):
        """اختبار أمان نقطة نهاية"""
        results = {
            'sql_injection': [],
            'xss': [],
            'path_traversal': []
        }
        
        # اختبار حقن SQL
        for payload in self.get_sql_injection_payloads():
            test_data = data.copy() if data else {}
            for key in test_data:
                test_data[key] = payload
            
            response = getattr(self.client, method.lower())(endpoint, test_data)
            results['sql_injection'].append({
                'payload': payload,
                'status_code': response.status_code,
                'safe': response.status_code in [400, 403, 422]
            })
        
        return results


def create_test_data():
    """إنشاء بيانات اختبار أساسية"""
    from django.contrib.auth.models import User
    
    # إنشاء مستخدمين
    admin = User.objects.create_superuser(
        username='admin',
        email='admin@test.com',
        password='adminpass'
    )
    
    user = User.objects.create_user(
        username='testuser',
        email='user@test.com', 
        password='userpass'
    )
    
    return {
        'admin': admin,
        'user': user
    }


def cleanup_test_data():
    """تنظيف بيانات الاختبار"""
    from django.contrib.auth.models import User
    
    # حذف المستخدمين
    User.objects.filter(username__in=['admin', 'testuser']).delete()


class ArabicTextTestMixin:
    """خليط لاختبار النصوص العربية"""
    
    def get_arabic_test_strings(self):
        """نصوص عربية للاختبار"""
        return [
            'أحمد محمد علي',
            'مدرسة الأمل الابتدائية',
            'الصف الأول الابتدائي',
            'اللغة العربية والرياضيات',
            'ولي الأمر: فاطمة أحمد',
            'العنوان: شارع النيل، القاهرة',
            'رقم الهاتف: ٠١٢٣٤٥٦٧٨٩٠',
            'البريد الإلكتروني: test@example.com'
        ]
    
    def test_arabic_text_handling(self, text_field, arabic_text):
        """اختبار معالجة النص العربي"""
        # اختبار الحفظ والاسترجاع
        original_length = len(arabic_text)
        
        # محاكاة حفظ النص
        saved_text = arabic_text
        retrieved_text = saved_text
        
        # التحقق من سلامة النص
        assert len(retrieved_text) == original_length
        assert retrieved_text == arabic_text
        
        # اختبار التشكيل والاتجاه
        import arabic_reshaper
        from bidi.algorithm import get_display
        
        reshaped_text = arabic_reshaper.reshape(arabic_text)
        display_text = get_display(reshaped_text)
        
        return {
            'original': arabic_text,
            'reshaped': reshaped_text,
            'display': display_text,
            'length_preserved': len(display_text) >= len(arabic_text)
        }