"""
Signals للموردين
Integrated with Governance System for monitoring and control
"""
import logging
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.conf import settings
from django.utils import timezone

# Governance integration
from governance.services import signal_router, governance_switchboard
from governance.services.audit_service import AuditService
from governance.services.monitoring_service import monitoring_service
from governance.models import GovernanceContext

from .models import Supplier, MonthlyDriverInvoice

logger = logging.getLogger(__name__)


from governance.signal_integration import governed_signal_handler

@governed_signal_handler(
    signal_name="supplier_account_creation",
    critical=True,
    description="إنشاء حساب محاسبي تلقائياً عند إضافة مورد جديد"
)
@receiver(post_save, sender=Supplier)
def create_supplier_account_signal(sender, instance, created, **kwargs):
    """
    إنشاء حساب محاسبي تلقائياً عند إضافة مورد جديد
    
    ✅ Single Source of Truth for supplier financial account creation
    
    This signal is the ONLY place where supplier financial accounts are created.
    All supplier creation flows (views, services, admin, scripts) rely on this signal.
    
    Integrated with Governance: audit_logging workflow
    """
    from django.db import transaction
    
    # التحقق من وجود primary_type قبل أي شيء
    if not instance.primary_type:
        logger.debug(f"تخطي إنشاء حساب للمورد {instance.name} - لا يوجد نوع محدد")
        return
    
    # Route through governance signal_router
    routing_result = signal_router.route_signal(
        signal_name='supplier_account_creation',
        sender=sender,
        instance=instance,
        critical=False,  # Non-critical audit signal
        created=created,
        **kwargs
    )
    
    # Check if governance allows this operation
    if not governance_switchboard.is_workflow_enabled('audit_logging'):
        logger.debug("Supplier account creation audit disabled - skipping")
        return
    
    # التحقق من تفعيل الميزة في الإعدادات
    if not getattr(settings, "AUTO_CREATE_SUPPLIER_ACCOUNTS", True):
        return

    # إنشاء حساب فقط إذا لم يكن موجوداً
    if instance.financial_account:
        return
    
    try:
        # ✅ استخدام SupplierService الموحد بدلاً من SupplierParentAccountService
        from supplier.services.supplier_service import SupplierService
        
        account = SupplierService.create_financial_account_for_supplier(
            supplier=instance,
            user=instance.created_by
        )
        
        # Update supplier with financial account using update() to avoid triggering signal again
        Supplier.objects.filter(pk=instance.pk).update(financial_account=account)
        instance.financial_account = account  # Update in-memory instance
        
        # Log successful account creation to governance audit service
        AuditService.log_signal_operation(
            signal_name='supplier_account_creation',
            sender_model='Supplier',
            sender_id=instance.id,
            operation='ACCOUNT_CREATED',
            user=GovernanceContext.get_current_user(),
            supplier_name=instance.name,
            account_code=account.code,
            supplier_type=instance.primary_type.code if instance.primary_type else 'unknown'
        )
        
        action = "created" if created else "recovered"
        logger.info(
            f"✅ Financial account {account.code} {action} for supplier {instance.name} "
            f"automatically via post_save signal"
        )
        
    except Exception as e:
        # Log account creation failure
        try:
            AuditService.log_signal_operation(
                signal_name='supplier_account_creation',
                sender_model='Supplier',
                sender_id=instance.id,
                operation='ACCOUNT_CREATION_FAILED',
                user=GovernanceContext.get_current_user(),
                supplier_name=instance.name,
                error=str(e)
            )
            
            # Record violation in monitoring service
            monitoring_service.record_violation(
                violation_type='supplier_account_creation_failure',
                component='supplier',
                details={
                    'supplier_id': instance.id,
                    'supplier_name': instance.name,
                    'error': str(e)
                },
                user=GovernanceContext.get_current_user()
            )
        except Exception:
            pass  # تجنب أخطاء إضافية في الـ logging
        
        # نسجل الخطأ لكن لا نوقف العملية
        logger.error(f"❌ Failed to create financial account for supplier {instance.name}: {e}")


@governed_signal_handler(
    signal_name="delete_supplier_account",
    critical=True,
    description="حذف حساب المورد المحاسبي عند حذف المورد"
)
@receiver(post_delete, sender=Supplier)
def delete_supplier_account_signal(sender, instance, **kwargs):
    """
    حذف الحساب المحاسبي عند حذف المورد (اختياري)
    """
    if instance.financial_account:
        try:
            account_code = instance.financial_account.code
            instance.financial_account.delete()
            logger.info(f"تم حذف الحساب المحاسبي {account_code} للمورد {instance.name}")
        except Exception as e:
            logger.error(f"فشل حذف الحساب المحاسبي للمورد {instance.name}: {e}")


@governed_signal_handler(
    signal_name="supplier_invoice_balance_link",
    critical=True,
    description="ربط فاتورة السائق الشهرية برصيد المورد"
)
@receiver(post_save, sender=MonthlyDriverInvoice)
def link_invoice_to_supplier_balance(sender, instance, created, **kwargs):
    """
    ربط الفاتورة برصيد المورد وتحديث الرصيد
    Requirements: 6.4, 6.5 - Invoice-supplier linkage and balance tracking
    
    ملاحظة: التحقق من المعاملة المالية يتم في MonthlyDriverInvoice.save()
    هذا الـ signal فقط للتسجيل والمراقبة
    """
    from django.db import transaction
    
    if created:
        def update_balance():
            try:
                # تحديث رصيد المورد
                supplier = instance.driver_supplier
                old_balance = supplier.balance
                supplier.balance += instance.total_amount
                supplier.save(update_fields=['balance'])
                
                logger.info(
                    f'تم ربط فاتورة {instance.id} برصيد المورد {supplier.name}: '
                    f'{old_balance} + {instance.total_amount} = {supplier.balance}'
                )
                
            except Exception as e:
                logger.error(f'فشل في ربط الفاتورة {instance.id} برصيد المورد: {str(e)}')
        
        transaction.on_commit(update_balance)


@governed_signal_handler(
    signal_name="supplier_driver_balance_update",
    critical=True,
    description="تحديث رصيد السائق عند إضافة دفعة شراء"
)
@receiver(post_save, sender='purchase.PurchasePayment')
def update_driver_balance_on_payment(sender, instance, created, **kwargs):
    """
    تحديث رصيد السائق عند دفع فاتورة مشتريات
    Requirements: 6.5 - Driver balance tracking
    """
    from django.db import transaction
    
    if created and instance.purchase and instance.purchase.supplier:
        def update_balance():
            try:
                supplier = instance.purchase.supplier
                
                # التحقق من أن المورد سائق
                if supplier.is_driver():
                    # التحقق من المعاملة المالية قبل تحديث الرصيد
                    from financial.services.validation_service import FinancialValidationService
                    from financial.exceptions import FinancialValidationError
                    
                    try:
                        validation_result = FinancialValidationService.validate_transaction(
                            entity=supplier,
                            transaction_date=instance.payment_date,
                            entity_type='supplier',
                            transaction_type='payment',
                            transaction_amount=instance.amount,
                            user=instance.created_by if hasattr(instance, 'created_by') else None,
                            module='supplier',
                            view_name='update_driver_balance_on_payment',
                            raise_exception=True,
                            log_failures=True
                        )
                        
                        # تقليل الرصيد بمبلغ الدفعة
                        old_balance = supplier.balance
                        supplier.balance -= instance.amount
                        supplier.save(update_fields=['balance'])
                        
                        logger.info(
                            f'تم تحديث رصيد السائق {supplier.name} بعد الدفع: '
                            f'{old_balance} - {instance.amount} = {supplier.balance}'
                        )
                        
                    except FinancialValidationError as e:
                        logger.error(
                            f'فشل التحقق من المعاملة المالية لدفعة السائق {supplier.name}: {str(e)}'
                        )
                        # لا نرفع الاستثناء هنا لأننا في signal، فقط نسجل الخطأ
                        
            except Exception as e:
                logger.error(f'فشل في تحديث رصيد السائق بعد الدفع: {str(e)}')
        
        transaction.on_commit(update_balance)


@governed_signal_handler(
    signal_name="track_driver_pricing_changes",
    critical=True,
    description="تتبع تغييرات أسعار السائق"
)
@receiver(pre_save, sender=Supplier)
def track_driver_pricing_changes(sender, instance, **kwargs):
    """
    تتبع تغييرات تسعيرة السائقين - محدث للنظام الجديد
    """
    if instance.pk and instance.is_driver():
        try:
            old_instance = Supplier.objects.get(pk=instance.pk)
            # حساب التكلفة القديمة من الباصات
            instance._old_monthly_cost = old_instance.calculate_monthly_cost_per_student()
        except Supplier.DoesNotExist:
            instance._old_monthly_cost = None


@governed_signal_handler(
    signal_name="supplier_pricing_history",
    critical=False,
    description="إنشاء سجل تاريخ الأسعار عند تغيير بيانات المورد"
)
@receiver(post_save, sender=Supplier)
def create_pricing_history_on_change(sender, instance, created, **kwargs):
    """
    إنشاء سجل تاريخ التسعير عند تغيير تسعيرة السائق - محدث للنظام الجديد
    """
    if not created and instance.is_driver() and hasattr(instance, '_old_monthly_cost'):
        old_cost = instance._old_monthly_cost
        # حساب التكلفة الجديدة من الباصات
        new_cost = instance.calculate_monthly_cost_per_student()
        
        if old_cost != new_cost and (old_cost is not None or new_cost is not None):
            try:
                # تسجيل التغيير في الـ logs بدلاً من إنشاء سجل منفصل
                logger.info(
                    f'تم تحديث تسعيرة السائق {instance.name}: '
                    f'{old_cost or "غير محدد"} ← {new_cost or "غير محدد"}'
                )
                
            except Exception as e:
                logger.error(f'فشل في تسجيل تغيير التسعيرة: {str(e)}')

