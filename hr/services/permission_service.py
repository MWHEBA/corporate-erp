"""
خدمة إدارة الأذونات
"""
from django.db import transaction
from django.utils import timezone
from datetime import datetime, date
from ..models import PermissionRequest, PermissionType, Attendance


class PermissionService:
    """خدمة إدارة الأذونات - نفس نمط LeaveService"""
    
    @staticmethod
    @transaction.atomic
    def request_permission(employee, permission_data, requested_by=None):
        """
        طلب إذن جديد
        
        Args:
            employee: الموظف
            permission_data: بيانات الإذن
            requested_by: من طلب الإذن (HR)
        
        Returns:
            PermissionRequest: طلب الإذن
        """
        permission_type = permission_data['permission_type']
        perm_date = permission_data['date']
        start_time = permission_data['start_time']
        end_time = permission_data['end_time']
        
        # حساب المدة
        duration = PermissionService._calculate_duration(start_time, end_time)
        
        # التحقق من الحصة (on-the-fly بدون model منفصل)
        if not PermissionService._check_monthly_quota(employee, perm_date, duration):
            raise ValueError('تجاوزت الحد الأقصى للأذونات الشهرية')
        
        # إنشاء الطلب
        permission = PermissionRequest.objects.create(
            employee=employee,
            permission_type=permission_type,
            date=perm_date,
            start_time=start_time,
            end_time=end_time,
            duration_hours=duration,
            reason=permission_data['reason'],
            is_emergency=permission_data.get('is_emergency', False),
            status='pending',
            requested_by=requested_by
        )
        
        return permission
    
    @staticmethod
    def _calculate_duration(start_time, end_time):
        """حساب المدة بالساعات"""
        start_datetime = datetime.combine(date.today(), start_time)
        end_datetime = datetime.combine(date.today(), end_time)
        duration = (end_datetime - start_datetime).total_seconds() / 3600
        return round(duration, 2)
    
    @staticmethod
    def _check_monthly_quota(employee, perm_date, duration):
        """
        التحقق من الحصة - بدون model منفصل
        
        Args:
            employee: الموظف
            perm_date: تاريخ الإذن
            duration: المدة بالساعات
        
        Returns:
            bool: هل يمكن طلب الإذن
        """
        usage = PermissionRequest.get_monthly_usage(employee, perm_date)
        
        # الحد الأقصى للأذونات الشهرية (4 أذونات)
        max_count = 4
        # الحد الأقصى لساعات الأذونات الشهرية (12 ساعة)
        max_hours = 12
        
        return (usage['total_count'] < max_count and 
                (usage['total_hours'] + duration) <= max_hours)
    
    @staticmethod
    @transaction.atomic
    def approve_permission(permission, approver, review_notes=None):
        """
        اعتماد الإذن
        
        Args:
            permission: الإذن
            approver: المعتمد
            review_notes: ملاحظات المراجعة (اختياري)
        
        Returns:
            PermissionRequest: الإذن المعتمد
        """
        permission.status = 'approved'
        permission.approved_by = approver
        permission.approved_at = timezone.now()
        if review_notes:
            permission.review_notes = review_notes
        permission.save()
        
        # تحديث سجل الحضور
        PermissionService._update_attendance(permission)
        
        return permission
    
    @staticmethod
    def _update_attendance(permission):
        """
        تحديث سجل الحضور عند اعتماد الإذن
        
        Args:
            permission: الإذن المعتمد
        """
        try:
            attendance = Attendance.objects.get(
                employee=permission.employee,
                date=permission.date
            )
            
            # ربط الإذن بالحضور
            permission.attendance = attendance
            
            # تعديل التأخير/الانصراف المبكر حسب نوع الإذن
            if permission.permission_type.code == 'LATE_ARRIVAL':
                # إلغاء التأخير
                attendance.late_minutes = 0
                attendance.notes = f"إذن معتمد: {permission.permission_type.name_ar}"
            elif permission.permission_type.code == 'EARLY_LEAVE':
                # إلغاء الانصراف المبكر
                attendance.early_leave_minutes = 0
                attendance.notes = f"إذن معتمد: {permission.permission_type.name_ar}"
            else:
                # أنواع أخرى - إضافة ملاحظة فقط
                if attendance.notes:
                    attendance.notes += f" | إذن: {permission.permission_type.name_ar}"
                else:
                    attendance.notes = f"إذن معتمد: {permission.permission_type.name_ar}"
            
            attendance.save()
            permission.save()
            
        except Attendance.DoesNotExist:
            # لم يتم تسجيل حضور بعد - لا مشكلة
            pass
    
    @staticmethod
    @transaction.atomic
    def reject_permission(permission, reviewer, notes):
        """
        رفض الإذن
        
        Args:
            permission: الإذن
            reviewer: المراجع
            notes: ملاحظات الرفض
        
        Returns:
            PermissionRequest: الإذن المرفوض
        """
        permission.status = 'rejected'
        permission.reviewed_by = reviewer
        permission.reviewed_at = timezone.now()
        permission.review_notes = notes
        permission.save()
        
        return permission
    
    @staticmethod
    def get_monthly_quota_info(employee, month_date):
        """
        الحصول على معلومات الحصة الشهرية
        
        Args:
            employee: الموظف
            month_date: تاريخ في الشهر المطلوب
        
        Returns:
            dict: معلومات الحصة
        """
        usage = PermissionRequest.get_monthly_usage(employee, month_date)
        
        return {
            'used_count': usage['total_count'],
            'max_count': 4,
            'remaining_count': 4 - usage['total_count'],
            'used_hours': float(usage['total_hours']),
            'max_hours': 12,
            'remaining_hours': 12 - float(usage['total_hours']),
        }
