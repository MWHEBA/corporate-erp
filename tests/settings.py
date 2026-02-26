"""
إعدادات خاصة بالاختبارات - محسنة لـ pytest
"""
from corporate_erp.settings import *
import os

# قاعدة بيانات للاختبارات - استخدام in-memory لسرعة أكبر
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',  # استخدام memory للسرعة
        'OPTIONS': {
            'timeout': 20,
        },
        'TEST': {
            'NAME': ':memory:',
        }
    }
}

# إعدادات الاختبار
DEBUG = False
TESTING = True

# تسريع الاختبارات
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# تعطيل التخزين المؤقت
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# تعطيل الإيميل
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# إعدادات الأمان للاختبار
SECRET_KEY = 'test-secret-key-for-testing-only'
ALLOWED_HOSTS = ['*']

# تعطيل Celery
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# إعدادات إضافية
USE_TZ = True
TIME_ZONE = 'Africa/Cairo'  # استخدام قيمة ثابتة للاختبارات
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# تبسيط migrations للاختبارات
MIGRATION_MODULES = {}

# إعدادات الملفات المؤقتة
MEDIA_ROOT = os.path.join(BASE_DIR, 'test_media')
STATIC_ROOT = os.path.join(BASE_DIR, 'test_static')

# تعطيل logging للاختبارات
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'null': {
            'class': 'logging.NullHandler',
        },
    },
    'root': {
        'handlers': ['null'],
    },
}
