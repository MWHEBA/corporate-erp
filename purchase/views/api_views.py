"""
Purchase API Views
API endpoints للمشتريات
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
import logging

from supplier.models import Supplier
from product.models import Product

logger = logging.getLogger(__name__)


@login_required
def get_supplier_type_api(request, supplier_id):
    """
    API للحصول على نوع المورد وفلترة المنتجات
    Get supplier type and filter products accordingly
    """
    try:
        supplier = Supplier.objects.select_related('primary_type', 'primary_type__settings').get(
            id=supplier_id, 
            is_active=True
        )
        
        # استخدام الـ method الموجود في الـ model - Single Source of Truth
        is_service = supplier.is_service_provider()
        
        # جلب المنتجات/الخدمات المناسبة
        products = Product.objects.filter(
            is_active=True,
            is_service=is_service
        ).values('id', 'name', 'sku', 'cost_price', 'selling_price')
        
        return JsonResponse({
            'success': True,
            'is_service_provider': is_service,
            'requires_warehouse': not is_service,
            'supplier_type_code': supplier.get_primary_type_code() or 'general',
            'products': list(products),
        })
    except Supplier.DoesNotExist:
        return JsonResponse({
            'success': False, 
            'message': 'المورد غير موجود'
        }, status=404)
    except Exception as e:
        logger.error(f"خطأ في API نوع المورد للمورد {supplier_id}: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'حدث خطأ في جلب بيانات المورد'
        }, status=500)
