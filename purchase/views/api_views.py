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
        
        # جلب التصنيفات المالية المناسبة لنوع المورد
        financial_categories = []
        try:
            from financial.models import FinancialCategory
            if is_service:
                # موردين خدميين: خدمات + مصروفات إدارية + تسويق + رواتب + متنوعة
                service_codes = ['services', 'administrative', 'marketing', 'salaries', 'insurance', 'taxes', 'other_expense']
                cats = FinancialCategory.objects.filter(
                    is_active=True,
                    default_expense_account__isnull=False,
                    code__in=service_codes
                ).order_by('display_order', 'name')
            else:
                # موردين منتجات: منتجات فقط
                cats = FinancialCategory.objects.filter(
                    is_active=True,
                    default_expense_account__isnull=False,
                    code='products'
                ).order_by('display_order', 'name')
            
            for cat in cats:
                financial_categories.append({'value': f'cat_{cat.pk}', 'label': f'📁 {cat.name}'})
                for subcat in cat.subcategories.filter(is_active=True).order_by('display_order', 'name'):
                    financial_categories.append({'value': f'sub_{subcat.pk}', 'label': f'   ↳ {subcat.name}'})
        except Exception:
            pass

        return JsonResponse({
            'success': True,
            'is_service_provider': is_service,
            'requires_warehouse': not is_service,
            'supplier_type_code': supplier.get_primary_type_code() or 'general',
            'products': list(products),
            'financial_categories': financial_categories,
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
