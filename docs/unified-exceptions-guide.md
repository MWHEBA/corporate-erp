# دليل توحيد نظام الاستثناءات والإشعارات - Unified Exception & Notification System Guide

## نظرة عامة
هذا الدليل يوضح كيفية توحيد نظام الاستثناءات والإشعارات في المشروع لضمان معالجة أخطاء متسقة وتجربة مستخدم موحدة.

## 1. البنية الموحدة للاستثناءات

### BaseException - الاستثناء الأساسي
```python
# core/exceptions/base_exceptions.py
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class BaseApplicationException(Exception):
    """استثناء أساسي لجميع استثناءات التطبيق"""
    
    def __init__(
        self, 
        message: str, 
        error_code: str = None,
        details: Dict[str, Any] = None,
        user_message: str = None
    ):
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        self.user_message = user_message or message
        
        super().__init__(self.message)
        
        # تسجيل الاستثناء
        self._log_exception()
    
    def _log_exception(self):
        """تسجيل الاستثناء"""
        logger.error(
            f"استثناء التطبيق: {self.error_code} - {self.message}",
            extra={
                'error_code': self.error_code,
                'details': self.details,
                'exception_class': self.__class__.__name__
            }
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """تحويل الاستثناء إلى قاموس"""
        return {
            'error_code': self.error_code,
            'message': self.message,
            'user_message': self.user_message,
            'details': self.details
        }
    
    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"

class ValidationException(BaseApplicationException):
    """استثناء التحقق من صحة البيانات"""
    
    def __init__(self, message: str, field: str = None, value: Any = None, **kwargs):
        details = kwargs.get('details', {})
        if field:
            details['field'] = field
        if value is not None:
            details['invalid_value'] = str(value)
        
        super().__init__(
            message=message,
            error_code='VALIDATION_ERROR',
            details=details,
            user_message=f"خطأ في البيانات: {message}",
            **kwargs
        )

class BusinessLogicException(BaseApplicationException):
    """استثناء منطق العمل"""
    
    def __init__(self, message: str, operation: str = None, **kwargs):
        details = kwargs.get('details', {})
        if operation:
            details['operation'] = operation
        
        super().__init__(
            message=message,
            error_code='BUSINESS_LOGIC_ERROR',
            details=details,
            user_message=f"خطأ في العملية: {message}",
            **kwargs
        )
```

## 2. استثناءات الطلاب الموحدة

### StudentExceptions - استثناءات الطلاب
```python
# students/exceptions.py
from core.exceptions.base_exceptions import ValidationException, BusinessLogicException

class StudentValidationError(ValidationException):
    """خطأ في التحقق من بيانات الطالب"""
    
    def __init__(self, message: str, student_field: str = None, student_id: int = None, **kwargs):
        details = kwargs.get('details', {})
        if student_id:
            details['student_id'] = student_id
        
        super().__init__(
            message=message,
            field=student_field,
            error_code='STUDENT_VALIDATION_ERROR',
            details=details,
            **kwargs
        )

class StudentNotFoundError(BusinessLogicException):
    """طالب غير موجود"""
    
    def __init__(self, student_id: int = None, national_id: str = None, **kwargs):
        if student_id:
            message = f"الطالب غير موجود بالرقم: {student_id}"
            details = {'student_id': student_id}
        elif national_id:
            message = f"الطالب غير موجود بالرقم القومي: {national_id}"
            details = {'national_id': national_id}
        else:
            message = "الطالب غير موجود"
            details = {}
        
        super().__init__(
            message=message,
            error_code='STUDENT_NOT_FOUND',
            operation='student_lookup',
            details=details,
            user_message="الطالب المطلوب غير موجود في النظام",
            **kwargs
        )
```

## 3. معالج الاستثناءات الموحد

### ExceptionHandler - معالج الاستثناءات
```python
# core/exceptions/exception_handler.py
from typing import Dict, Any, Optional
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.contrib import messages
import logging

logger = logging.getLogger(__name__)

class UnifiedExceptionHandler:
    """معالج موحد للاستثناءات"""
    
    @staticmethod
    def handle_exception(
        exception: Exception, 
        request=None, 
        return_json: bool = False
    ) -> Optional[HttpResponse]:
        """معالجة الاستثناء"""
        
        # تحديد نوع الاستثناء
        if isinstance(exception, BaseApplicationException):
            return UnifiedExceptionHandler._handle_application_exception(
                exception, request, return_json
            )
        else:
            return UnifiedExceptionHandler._handle_system_exception(
                exception, request, return_json
            )
    
    @staticmethod
    def _handle_application_exception(
        exception: BaseApplicationException, 
        request=None, 
        return_json: bool = False
    ) -> HttpResponse:
        """معالجة استثناءات التطبيق"""
        
        error_data = exception.to_dict()
        
        if return_json or (request and request.content_type == 'application/json'):
            return JsonResponse({
                'success': False,
                'error': error_data
            }, status=400)
        
        # إضافة رسالة للمستخدم
        if request:
            messages.error(request, exception.user_message)
        
        # إرجاع صفحة خطأ مخصصة
        return render(request, 'errors/application_error.html', {
            'error': error_data,
            'title': 'خطأ في التطبيق'
        }, status=400)

# Decorator لمعالجة الاستثناءات في الـ Views
def handle_exceptions(return_json: bool = False):
    """Decorator لمعالجة الاستثناءات"""
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            try:
                return view_func(request, *args, **kwargs)
            except Exception as e:
                return UnifiedExceptionHandler.handle_exception(
                    e, request, return_json
                )
        return wrapper
    return decorator
```

## 4. قواعد التطوير

### إنشاء استثناء جديد
```python
# 1. وراثة من الاستثناء المناسب
# 2. تحديد error_code واضح
# 3. إضافة تفاصيل مفيدة في details
# 4. كتابة user_message واضحة
# 5. إضافة اختبارات

from core.exceptions.base_exceptions import BusinessLogicException

class MyCustomError(BusinessLogicException):
    """وصف الاستثناء الجديد"""
    
    def __init__(self, message: str, custom_field: str = None, **kwargs):
        details = kwargs.get('details', {})
        if custom_field:
            details['custom_field'] = custom_field
        
        super().__init__(
            message=message,
            error_code='MY_CUSTOM_ERROR',
            operation='my_operation',
            details=details,
            user_message=f"خطأ مخصص: {message}",
            **kwargs
        )
```

### استخدام الاستثناءات في الكود
```python
# ✅ صحيح - استثناء محدد ومفيد
def create_student(student_data):
    if not student_data.get('national_id'):
        raise StudentValidationError(
            message="الرقم القومي مطلوب",
            student_field="national_id"
        )
    
    if Student.objects.filter(national_id=student_data['national_id']).exists():
        raise DuplicateStudentError(
            national_id=student_data['national_id']
        )

# ❌ خطأ - استثناء عام وغير مفيد
def create_student(student_data):
    if not student_data.get('national_id'):
        raise Exception("خطأ في البيانات")  # غير محدد!
```

## 5. نصائح مهمة

### أفضل الممارسات
- **استخدم** استثناءات محددة بدلاً من Exception العامة
- **أضف** تفاصيل مفيدة في details
- **اكتب** رسائل واضحة للمستخدم
- **سجل** الاستثناءات بمستوى مناسب
- **اختبر** جميع حالات الاستثناءات

### أخطاء شائعة يجب تجنبها
```python
# ❌ خطأ - استثناء عام
raise Exception("حدث خطأ")

# ❌ خطأ - رسالة غير واضحة
raise ValidationException("خطأ")

# ✅ صحيح - استثناء محدد ومفيد
raise StudentNotFoundError(
    student_id=123,
    details={'search_criteria': 'national_id'}
)
```

---

**تاريخ الإنشاء**: 4 فبراير 2026  
**الحالة**: جاهز للتطبيق  
**الأولوية**: عالية 🔥

---

# الجزء الثاني: دليل توحيد الإشعارات

## المشكلة المحددة

### الإشعارات غير الموحدة
النظام حالياً يستخدم أنظمة إشعارات متعددة:

#### 1. **Toastr (الصحيح)**
```html
<div id="toast-container" class="toast-top-left">
    <div class="toast toast-success rtl" aria-live="polite" style="display: block;">
        <div class="toast-progress" style="width: 0%;"></div>
        <button type="button" class="toast-close-button" role="button">×</button>
        <div class="toast-message">تم إنشاء الطالب بنجاح</div>
    </div>
</div>
```

#### 2. **Custom Message System (خطأ)**
```html
<div class="message-content">
    <div class="message-icon"><i class="fas fa-exclamation-circle"></i></div>
    <div class="message-body">
        <div class="message-text">خطأ: فشل في تسجيل الطالب</div>
    </div>
    <div class="message-controls">
        <div class="message-timer animate" style="animation-duration: 8000ms;"></div>
        <button type="button" class="message-close" aria-label="إغلاق الرسالة">
            <i class="fas fa-times"></i>
        </button>
    </div>
</div>
```

## الحل الموحد للإشعارات

### 1. استخدام Toastr فقط
جميع الإشعارات يجب أن تستخدم Toastr library للحصول على تنسيق موحد.

### 2. الطرق الصحيحة لعرض الإشعارات

#### أ. في Django Views (Server-side)
```python
from django.contrib import messages

# للنجاح
messages.success(request, _('تم إنشاء الطالب بنجاح'))

# للأخطاء
messages.error(request, _('الفصل المحدد لا يتوافق مع الفئة العمرية للطالب'))

# للتحذيرات
messages.warning(request, _('تحذير: البيانات غير مكتملة'))

# للمعلومات
messages.info(request, _('تم حفظ البيانات مؤقتاً'))
```

#### ب. في JavaScript (Client-side)
```javascript
// الطريقة الصحيحة - استخدام toastr مباشرة
if (typeof toastr !== 'undefined') {
    toastr.success('تم إنشاء الطالب بنجاح');
    toastr.error('الفصل المحدد لا يتوافق مع الفئة العمرية للطالب');
    toastr.warning('تحذير: البيانات غير مكتملة');
    toastr.info('تم حفظ البيانات مؤقتاً');
}

// الطريقة البديلة - استخدام showAlert (إذا كان متوفر)
showAlert('success', 'تم إنشاء الطالب بنجاح');
showAlert('danger', 'الفصل المحدد لا يتوافق مع الفئة العمرية للطالب');
```

### 3. إزالة تعارضات CSS

#### التأكد من تحميل Toastr CSS
```django
<!-- Toastr CSS - موجود بالفعل -->
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/toastr.js/latest/toastr.min.css">
```

#### إزالة CSS المتعارض
```css
/* إخفاء الأنظمة اللي بتتعارض مع toastr */
.message-content,
.swal2-container,
.django-message.position-fixed {
    display: none !important;
}

/* التأكد إن toastr يظهر */
#toast-container {
    display: block !important;
    z-index: 9999 !important;
}
```

### 4. Template للتعديل السريع
```javascript
// Template للاستبدال في JavaScript
function showUnifiedNotification(message, type = 'info') {
    if (typeof toastr !== 'undefined') {
        switch(type) {
            case 'success':
                toastr.success(message);
                break;
            case 'error':
            case 'danger':
                toastr.error(message);
                break;
            case 'warning':
                toastr.warning(message);
                break;
            case 'info':
            default:
                toastr.info(message);
                break;
        }
    } else if (typeof showAlert !== 'undefined') {
        showAlert(type === 'error' ? 'danger' : type, message);
    } else {
        alert(message);
    }
}
```

## أفضل الممارسات الموحدة

### للاستثناءات والإشعارات
- **استخدم** استثناءات محددة بدلاً من Exception العامة
- **أضف** تفاصيل مفيدة في details
- **اكتب** رسائل واضحة للمستخدم
- **سجل** الاستثناءات بمستوى مناسب
- **استخدم** Toastr فقط للإشعارات
- **تجنب** الأنظمة المتعددة للإشعارات

### أخطاء شائعة يجب تجنبها
```python
# ❌ خطأ - استثناء عام
raise Exception("حدث خطأ")

# ❌ خطأ - رسالة غير واضحة
raise ValidationException("خطأ")

# ❌ خطأ - استخدام أنظمة إشعارات متعددة
Swal.fire({icon: 'error', title: 'خطأ'})

# ✅ صحيح - استثناء محدد ومفيد
raise StudentNotFoundError(
    student_id=123,
    details={'search_criteria': 'national_id'}
)

# ✅ صحيح - إشعار موحد
if (typeof toastr !== 'undefined') {
    toastr.error('رسالة الخطأ');
}
```