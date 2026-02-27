"""
Product Signal Handlers - DISABLED FOR SINGLE ENTRY POINT

⚠️⚠️⚠️ ALL STOCK-RELATED SIGNALS DISABLED ⚠️⚠️⚠️

REASON: Violates Single Entry Point principle
All stock operations MUST go through MovementService directly.

CORRECT PATTERN:
View/Service → MovementService.process_movement() → Stock Update

WRONG PATTERN (this file):
View → Signal → StockMovement → Stock Update
                    ↓
              Duplicate updates!

See: STOCK_MOVEMENT_UNIFICATION_PLAN.md
See: governance/services/movement_service.py

DO NOT RE-ENABLE THESE SIGNALS.

Migration Status: Phase 1 - Signals Disabled ✅
Date: 25 February 2026
"""

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.db import transaction
from django.utils.text import slugify
from django.utils import timezone
from decimal import Decimal
import logging

from governance.signal_integration import governed_signal_handler, side_effect_handler
from governance.services.audit_service import AuditService
from governance.models import GovernanceContext

from .models import StockMovement, Stock, Product, ProductImage
from purchase.models import Purchase

logger = logging.getLogger(__name__)

# Safe imports for enhanced models
try:
    from .models.inventory_movement import InventoryMovement
    from .services.inventory_service import InventoryService
    from core.services.notification_service import NotificationService
except ImportError:
    InventoryMovement = InventoryService = NotificationService = None


# ============================================================================
# NON-STOCK SIGNALS (ACTIVE)
# ============================================================================

@governed_signal_handler(
    "product_sku_generation",
    critical=False,
    description="Generate unique SKU for products automatically"
)
@receiver(pre_save, sender=Product)
def ensure_unique_sku(sender, instance, **kwargs):
    """
    التأكد من أن الـ كود المنتج فريد وإنشاءه تلقائيًا إذا لم يتم توفيره
    ✅ ACTIVE - Not related to stock movements
    """
    if not instance.sku:
        timestamp = timezone.now().strftime("%y%m%d%H%M")
        base_slug = slugify(instance.name)[:10]
        instance.sku = f"{base_slug}-{timestamp}"
        logger.info(f"Generated unique SKU '{instance.sku}' for product '{instance.name}'")


@governed_signal_handler(
    "product_image_primary_management",
    critical=False,
    description="Manage primary product image constraints"
)
@receiver(post_save, sender=ProductImage)
def ensure_single_primary_image(sender, instance, created, **kwargs):
    """
    التأكد من وجود صورة رئيسية واحدة فقط لكل منتج
    ✅ ACTIVE - Not related to stock movements
    """
    if instance.is_primary:
        ProductImage.objects.filter(product=instance.product, is_primary=True).exclude(
            pk=instance.pk
        ).update(is_primary=False)
        logger.info(f"Set primary image for product '{instance.product.name}' (image ID: {instance.id})")
    else:
        if not ProductImage.objects.filter(
            product=instance.product, is_primary=True
        ).exists():
            instance.is_primary = True
            instance.save()
            logger.info(f"Auto-set primary image for product '{instance.product.name}' (image ID: {instance.id})")


@side_effect_handler(
    "purchase_deletion_cleanup",
    "Handle purchase deletion cleanup"
)
@receiver(post_delete, sender=Purchase)
def handle_purchase_delete(sender, instance, **kwargs):
    """
    معالجة حذف فاتورة المشتريات
    ✅ ACTIVE - Not related to stock movements
    """
    logger.info(f"Purchase {instance.id} deleted - no sequential number reset")


# ============================================================================
# STOCK-RELATED SIGNALS (DISABLED)
# ============================================================================

# ❌ DISABLED: update_stock_on_movement
# Reason: Violates Single Entry Point - MovementService handles this
# Original location: Line 154
# Migration: Use MovementService.process_movement() instead

# ❌ DISABLED: revert_stock_on_movement_delete
# Reason: Violates Single Entry Point - MovementService handles this
# Original location: Line 358
# Migration: Use MovementService.process_movement() with negative quantity

# ❌ DISABLED: handle_stock_movement_delete
# Reason: Not needed - MovementService handles cleanup
# Original location: Line 737
# Migration: MovementService handles all cleanup automatically


# ============================================================================
# HELPER FUNCTIONS (KEPT FOR REFERENCE)
# ============================================================================

def _create_low_stock_alert(product, stock):
    """
    إنشاء تنبيه مخزون منخفض للنظام المحسن
    ✅ ACTIVE - Used by other parts of the system
    """
    if not NotificationService:
        return

    try:
        from django.contrib.auth import get_user_model
        from django.db import models

        User = get_user_model()

        authorized_users = User.objects.filter(
            models.Q(groups__name__in=["مدير مخزون", "مدير", "Admin"])
            | models.Q(is_superuser=True),
            is_active=True,
        ).distinct()

        if hasattr(stock, 'is_out_of_stock') and stock.is_out_of_stock:
            alert_type = "نفد"
            notification_type = "danger"
        else:
            alert_type = "منخفض"
            notification_type = "warning"

        title = f"تنبيه مخزون {alert_type}: {product.name}"
        message = (
            f"المنتج '{product.name}' في المخزن '{stock.warehouse.name}' {alert_type}.\n"
            f"الكمية الحالية: {stock.quantity} {product.unit.symbol}\n"
            f"الحد الأدنى: {stock.min_stock_level} {product.unit.symbol}\n"
            f"يُرجى إعادة التزويد فوراً."
        )

        for user in authorized_users:
            NotificationService.create_notification(
                user=user,
                title=title,
                message=message,
                notification_type=notification_type,
                related_model="Product",
                related_id=product.id,
                link_url=f"/products/{product.id}/"
            )

        AuditService.create_audit_record(
            model_name='Product',
            object_id=product.id,
            operation='LOW_STOCK_ALERT_CREATED',
            user=GovernanceContext.get_current_user(),
            source_service='ProductSignals',
            additional_context={
                'alert_type': alert_type,
                'current_quantity': str(stock.quantity),
                'min_stock_level': str(stock.min_stock_level),
                'warehouse': stock.warehouse.name,
                'notification_count': authorized_users.count()
            }
        )
        
        logger.info(f"Created {alert_type} stock alert for product {product.name}")

    except Exception as e:
        logger.error(f"Error creating enhanced low stock alert for product {product.name}: {e}")


def _create_legacy_low_stock_alert(product, stock):
    """
    إنشاء تنبيه مخزون منخفض للنظام القديم
    ✅ ACTIVE - Used by other parts of the system
    """
    try:
        from django.contrib.auth import get_user_model
        from django.db import models
        from core.models import Notification

        User = get_user_model()

        authorized_users = User.objects.filter(
            models.Q(groups__name__in=["مدير مخزون", "مدير", "Admin"])
            | models.Q(is_superuser=True),
            is_active=True,
        ).distinct()

        if stock.quantity == 0:
            alert_type = "نفد"
            notification_type = "danger"
        else:
            alert_type = "منخفض"
            notification_type = "warning"

        title = f"تنبيه مخزون {alert_type}: {product.name}"
        message = (
            f"المنتج '{product.name}' {alert_type} في المخزون.\n"
            f"الكمية الحالية: {stock.quantity} {product.unit.symbol}\n"
            f"الحد الأدنى: {product.min_stock} {product.unit.symbol}\n"
            f"يُرجى إعادة التزويد فوراً."
        )

        for user in authorized_users:
            Notification.objects.create(
                user=user, title=title, message=message, type=notification_type
            )

        AuditService.create_audit_record(
            model_name='Product',
            object_id=product.id,
            operation='LEGACY_LOW_STOCK_ALERT_CREATED',
            user=GovernanceContext.get_current_user(),
            source_service='ProductSignals',
            additional_context={
                'alert_type': alert_type,
                'current_quantity': str(stock.quantity),
                'min_stock': str(product.min_stock),
                'notification_count': authorized_users.count()
            }
        )
        
        logger.info(f"Created legacy {alert_type} stock alert for product {product.name}")

    except Exception as e:
        logger.error(f"Error creating legacy low stock alert for product {product.name}: {e}")


# ============================================================================
# ENHANCED INVENTORY MOVEMENT (ACTIVE)
# ============================================================================

if InventoryMovement:
    @governed_signal_handler(
        signal_name="handle_enhanced_inventory_movement",
        critical=False,
        description="معالجة حركات المخزون المحسنة مع تنبيهات فورية"
    )
    @receiver(post_save, sender=InventoryMovement)
    def handle_enhanced_inventory_movement(sender, instance, created, **kwargs):
        """
        معالجة حركات المخزون المحسنة مع تنبيهات فورية
        ✅ ACTIVE - Enhanced inventory system
        ✅ UNIFIED: Uses MovementService for Single Entry Point
        
        NOTE: This signal is DISABLED for InventoryMovement because it has its own
        approve() method that handles stock updates directly.
        """
        # تجاهل InventoryMovement - له approve() method خاص
        return
        
        if not instance.is_approved:
            return
        
        try:
            from governance.services import MovementService
            from decimal import Decimal
            
            # ✅ استخدام MovementService بدلاً من الإنشاء المباشر
            movement_service = MovementService()
            
            # تحديد quantity_change حسب نوع الحركة
            quantity_change = Decimal(str(instance.quantity))
            if instance.movement_type in ['out', 'return_out']:
                quantity_change = -quantity_change
            
            movement = movement_service.process_movement(
                product_id=instance.product.id,
                quantity_change=quantity_change,
                movement_type=instance.movement_type,
                source_reference=instance.movement_number,
                idempotency_key=f"inventory_movement_{instance.id}",
                user=instance.approved_by,
                unit_cost=instance.unit_cost,
                document_number=instance.movement_number,
                notes=f'{instance.get_voucher_type_display()} - {instance.get_purpose_type_display() if instance.purpose_type else ""}'
            )
            
            logger.info(
                f"✅ تم إنشاء حركة مخزون عبر MovementService: {movement.id} - "
                f"InventoryMovement {instance.id} - {instance.movement_number}"
            )
            
        except Exception as e:
            logger.error(
                f"❌ خطأ في إنشاء حركة المخزون عبر MovementService: {str(e)} - "
                f"InventoryMovement {instance.id}"
            )
            raise
