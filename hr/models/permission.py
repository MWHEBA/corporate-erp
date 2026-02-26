"""
نماذج الأذونات (Permission Requests)
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Count, Sum
from datetime import datetime, time, timedelta

User = get_user_model()


class PermissionType(models.Model):
    """نموذج أنواع الأذونات"""
    
    name_ar = models.CharField(max_length=100, verbose_name='اسم النوع (عربي)')
    name_en = models.CharField(max_length=100, verbose_name='اسم النوع (إنجليزي)', blank=True)
    code = models.CharField(max_length=20, unique=True, verbose_name='الكود')
    
    # الإعدادات
    max_hours_per_request = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=4.0,
        verbose_name='الحد الأقصى للساعات في الطلب الواحد'
    )
    requires_advance_request = models.BooleanField(
        default=True,
        verbose_name='يتطلب طلب مسبق'
    )
    advance_hours = models.IntegerField(
        default=24,
        verbose_name='عدد ساعات الطلب المسبق'
    )
    affects_salary = models.BooleanField(
        default=False,
        verbose_name='يؤثر على الراتب'
    )
    
    # الحالة
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    
    class Meta:
        verbose_name = 'نوع إذن'
        verbose_name_plural = 'أنواع الأذونات'
    
    def __str__(self):
        return self.name_ar


class PermissionRequest(models.Model):
    """نموذج طلبات الأذونات"""
    
    STATUS_CHOICES = [
        ('pending', 'قيد الانتظار'),
        ('approved', 'معتمد'),
        ('rejected', 'مرفوض'),
        ('cancelled', 'ملغي'),
    ]
    
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.CASCADE,
        related_name='permissions',
        verbose_name='الموظف'
    )
    permission_type = models.ForeignKey(
        PermissionType,
        on_delete=models.PROTECT,
        verbose_name='نوع الإذن'
    )
    
    # التاريخ والوقت
    date = models.DateField(verbose_name='التاريخ')
    start_time = models.TimeField(verbose_name='وقت البداية')
    end_time = models.TimeField(verbose_name='وقت النهاية')
    duration_hours = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        verbose_name='المدة بالساعات'
    )
    
    # السبب
    reason = models.TextField(verbose_name='السبب')
    is_emergency = models.BooleanField(default=False, verbose_name='ظرف طارئ')
    
    # سير العمل
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='الحالة'
    )
    
    # المراجعة
    requested_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الطلب')
    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requested_permissions',
        verbose_name='طلبه'
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_permissions',
        verbose_name='راجعه'
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاريخ المراجعة'
    )
    review_notes = models.TextField(blank=True, verbose_name='ملاحظات المراجعة')
    
    # الاعتماد
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_permissions',
        verbose_name='اعتمده'
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاريخ الاعتماد'
    )
    
    # التكامل مع الحضور
    attendance = models.ForeignKey(
        'Attendance',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='permissions',
        verbose_name='سجل الحضور'
    )
    
    class Meta:
        verbose_name = 'إذن'
        verbose_name_plural = 'الأذونات'
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['employee', 'status']),
            models.Index(fields=['date']),
        ]
        permissions = [
            ("can_approve_permissions", "اعتماد الأذونات"),
            ("can_view_all_permissions", "عرض جميع الأذونات"),
        ]
    
    def __str__(self):
        return f"{self.employee.get_full_name_ar()} - {self.permission_type.name_ar} ({self.date})"
    
    def clean(self):
        """التحقق من صحة البيانات"""
        from datetime import date
        errors = {}
        
        # التحقق من الأوقات
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                errors['end_time'] = 'وقت النهاية يجب أن يكون بعد وقت البداية'
            
            # حساب المدة
            start_datetime = datetime.combine(date.today(), self.start_time)
            end_datetime = datetime.combine(date.today(), self.end_time)
            duration = (end_datetime - start_datetime).total_seconds() / 3600
            
            # التحقق من الحد الأقصى للإذن الواحد
            if self.permission_type_id:
                max_hours = float(self.permission_type.max_hours_per_request)
                if duration > max_hours:
                    errors['end_time'] = f'المدة تتجاوز الحد الأقصى ({max_hours} ساعة)'
        
        # التحقق من التاريخ
        if self.date:
            # لا يمكن طلب إذن في الماضي البعيد (أكثر من 7 أيام)
            if self.date < date.today() and not self.pk:
                days_past = (date.today() - self.date).days
                if days_past > 7:
                    errors['date'] = 'لا يمكن طلب إذن قبل أكثر من 7 أيام'
        
        # التحقق من الحصة الشهرية (on-the-fly)
        if self.employee_id and self.date and not self.pk:
            usage = self.get_monthly_usage(self.employee, self.date)
            
            # الحد الأقصى للأذونات الشهرية (4 أذونات)
            if usage['total_count'] >= 4:
                errors['date'] = 'تجاوزت الحد الأقصى للأذونات الشهرية (4 أذونات)'
            
            # الحد الأقصى لساعات الأذونات الشهرية (12 ساعة)
            if self.duration_hours:
                total_hours = (usage['total_hours'] or 0) + float(self.duration_hours)
                if total_hours > 12:
                    errors['duration_hours'] = f'تجاوزت الحد الأقصى لساعات الأذونات الشهرية (12 ساعة). المتبقي: {12 - (usage["total_hours"] or 0)} ساعة'
        
        if errors:
            raise ValidationError(errors)
    
    def calculate_duration(self):
        """حساب مدة الإذن بالساعات"""
        from datetime import date
        start_datetime = datetime.combine(date.today(), self.start_time)
        end_datetime = datetime.combine(date.today(), self.end_time)
        duration = (end_datetime - start_datetime).total_seconds() / 3600
        self.duration_hours = round(duration, 2)
        self.save()
    
    @staticmethod
    def get_monthly_usage(employee, month_date):
        """
        حساب الاستخدام الشهري للأذونات - بدلاً من PermissionQuota Model
        
        Args:
            employee: الموظف
            month_date: تاريخ في الشهر المطلوب
        
        Returns:
            dict: إجمالي العدد والساعات
        """
        result = PermissionRequest.objects.filter(
            employee=employee,
            date__year=month_date.year,
            date__month=month_date.month,
            status='approved'
        ).aggregate(
            total_count=Count('id'),
            total_hours=Sum('duration_hours')
        )
        
        return {
            'total_count': result['total_count'] or 0,
            'total_hours': result['total_hours'] or 0
        }
