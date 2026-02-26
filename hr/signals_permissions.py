"""
إشارات الأذونات
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import PermissionRequest
from django.contrib.auth import get_user_model

User = get_user_model()


@receiver(post_save, sender=PermissionRequest)
def send_permission_notifications(sender, instance, created, **kwargs):
    """
    إرسال إشعارات الأذونات - نفس نمط leave notifications
    للإدارة فقط (لا يتم إرسال إشعارات للموظفين)
    """
    try:
        from core.models import Notification
        
        if created and instance.status == 'pending':
            # إشعار للمدير المباشر
            if hasattr(instance.employee, 'direct_manager') and instance.employee.direct_manager:
                if hasattr(instance.employee.direct_manager, 'user') and instance.employee.direct_manager.user:
                    Notification.objects.create(
                        user=instance.employee.direct_manager.user,
                        title='طلب إذن جديد يحتاج موافقة',
                        message=f'إذن للموظف {instance.employee.get_full_name_ar()} - {instance.permission_type.name_ar}',
                        notification_type='permission_pending',
                        link=f'/hr/permissions/{instance.pk}/'
                    )
            
            # إشعار لمجموعة HR
            hr_users = User.objects.filter(groups__name__in=['HR', 'HR Manager'])
            for hr_user in hr_users:
                Notification.objects.create(
                    user=hr_user,
                    title='طلب إذن جديد',
                    message=f'تم تسجيل إذن للموظف {instance.employee.get_full_name_ar()}',
                    notification_type='permission_created',
                    link=f'/hr/permissions/{instance.pk}/'
                )
        
        elif instance.status == 'approved':
            # إشعار للـ HR بالاعتماد
            hr_users = User.objects.filter(groups__name__in=['HR', 'HR Manager'])
            for hr_user in hr_users:
                Notification.objects.create(
                    user=hr_user,
                    title='تم اعتماد إذن',
                    message=f'تم اعتماد إذن {instance.permission_type.name_ar} للموظف {instance.employee.get_full_name_ar()}',
                    notification_type='permission_approved',
                    link=f'/hr/permissions/{instance.pk}/'
                )
        
        elif instance.status == 'rejected':
            # إشعار للـ HR بالرفض
            hr_users = User.objects.filter(groups__name__in=['HR', 'HR Manager'])
            for hr_user in hr_users:
                Notification.objects.create(
                    user=hr_user,
                    title='تم رفض إذن',
                    message=f'تم رفض إذن {instance.permission_type.name_ar} للموظف {instance.employee.get_full_name_ar()}',
                    notification_type='permission_rejected',
                    link=f'/hr/permissions/{instance.pk}/'
                )
    
    except Exception:
        # تجاهل الأخطاء في الإشعارات - لا نريد أن تؤثر على العملية الأساسية
        pass
