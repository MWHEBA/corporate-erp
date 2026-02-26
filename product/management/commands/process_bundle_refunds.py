# -*- coding: utf-8 -*-
"""
أمر إدارة لمعالجة مرتجعات المنتجات المجمعة
Management Command for Processing Bundle Refunds

Requirements: 6.5
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from decimal import Decimal
import json
import logging

from product.models import Product
from product.services.bundle_refund_service import BundleRefundService
from product.services.bundle_refund_integration import BundleRefundIntegration

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    أمر إدارة لمعالجة مرتجعات المنتجات المجمعة
    
    الاستخدام:
    python manage.py process_bundle_refunds --bundle-id 123 --quantity 2 --reason "منتج معيب" --user-id 1
    python manage.py process_bundle_refunds --student-refund-id 456 --bundle-data '[{"bundle_id": 123, "quantity": 2}]'
    python manage.py process_bundle_refunds --preview --bundle-id 123 --quantity 2
    """
    
    help = 'معالجة مرتجعات المنتجات المجمعة'
    
    def add_arguments(self, parser):
        """إضافة معاملات الأمر"""
        
        # معاملات المرتجع المباشر
        parser.add_argument(
            '--bundle-id',
            type=int,
            help='معرف المنتج المجمع للمرتجع'
        )
        
        parser.add_argument(
            '--quantity',
            type=int,
            help='الكمية المرتجعة'
        )
        
        parser.add_argument(
            '--reason',
            type=str,
            help='سبب المرتجع'
        )
        
        parser.add_argument(
            '--user-id',
            type=int,
            help='معرف المستخدم المنشئ للمرتجع'
        )
        
        # معاملات التكامل مع تسوية الطالب
        parser.add_argument(
            '--student-refund-id',
            type=int,
            help='معرف تسوية الطالب للتكامل'
        )
        
        parser.add_argument(
            '--bundle-data',
            type=str,
            help='بيانات المنتجات المجمعة بصيغة JSON: [{"bundle_id": 123, "quantity": 2, "reason": "سبب"}]'
        )
        
        # معاملات إضافية
        parser.add_argument(
            '--preview',
            action='store_true',
            help='معاينة المرتجع بدون تنفيذ'
        )
        
        parser.add_argument(
            '--refund-type',
            type=str,
            choices=['full_refund', 'partial_refund', 'defective_return', 'customer_return'],
            default='full_refund',
            help='نوع المرتجع'
        )
        
        parser.add_argument(
            '--customer-name',
            type=str,
            help='اسم العميل'
        )
        
        parser.add_argument(
            '--notes',
            type=str,
            help='ملاحظات إضافية'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='فرض المعالجة حتى لو كانت هناك تحذيرات'
        )
    
    def handle(self, *args, **options):
        """تنفيذ الأمر"""
        try:
            # تحديد نوع المعالجة
            if options.get('student_refund_id') and options.get('bundle_data'):
                return self._handle_student_refund_integration(options)
            elif options.get('bundle_id') and options.get('quantity'):
                return self._handle_direct_bundle_refund(options)
            else:
                raise CommandError(
                    'يجب تحديد إما (bundle-id و quantity) للمرتجع المباشر '
                    'أو (student-refund-id و bundle-data) للتكامل مع تسوية الطالب'
                )
                
        except Exception as e:
            logger.error(f"خطأ في تنفيذ أمر معالجة مرتجعات المنتجات المجمعة: {e}")
            raise CommandError(f"فشل في معالجة المرتجع: {e}")
    
    def _handle_direct_bundle_refund(self, options):
        """معالجة مرتجع مباشر للمنتج المجمع"""
        bundle_id = options['bundle_id']
        quantity = options['quantity']
        reason = options.get('reason', 'مرتجع من أمر الإدارة')
        user_id = options.get('user_id')
        preview = options.get('preview', False)
        
        # التحقق من المعاملات المطلوبة
        if not user_id and not preview:
            raise CommandError('معرف المستخدم مطلوب للمعالجة الفعلية (استخدم --user-id)')
        
        # الحصول على المنتج المجمع
        try:
            bundle_product = Product.objects.get(id=bundle_id, is_bundle=True)
        except Product.DoesNotExist:
            raise CommandError(f'المنتج المجمع بالمعرف {bundle_id} غير موجود')
        
        self.stdout.write(f"معالجة مرتجع المنتج المجمع: {bundle_product.name}")
        self.stdout.write(f"الكمية: {quantity}")
        self.stdout.write(f"السبب: {reason}")
        
        # إنشاء سياق المرتجع
        refund_context = {
            'refund_reason': reason,
            'refund_type': options.get('refund_type', 'full_refund'),
            'customer_name': options.get('customer_name', ''),
            'notes': options.get('notes', 'مرتجع من أمر الإدارة'),
        }
        
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                refund_context['created_by_id'] = user.id
            except User.DoesNotExist:
                raise CommandError(f'المستخدم بالمعرف {user_id} غير موجود')
        
        # معاينة أو تنفيذ المرتجع
        if preview:
            return self._preview_bundle_refund(bundle_product, quantity, refund_context)
        else:
            return self._execute_bundle_refund(bundle_product, quantity, refund_context, options)
    
    def _handle_student_refund_integration(self, options):
        """معالجة التكامل مع تسوية الطالب"""
        student_refund_id = options['student_refund_id']
        bundle_data_json = options['bundle_data']
        preview = options.get('preview', False)
        
        # الحصول على التسوية
        try:
            from client.models import CustomerRefund
            customer_refund = CustomerRefund.objects.get(id=student_refund_id)
        except Exception:
            raise CommandError(f'التسوية بالمعرف {student_refund_id} غير موجودة')
        
        # تحليل بيانات المنتجات المجمعة
        try:
            bundle_data_list = json.loads(bundle_data_json)
        except json.JSONDecodeError:
            raise CommandError('بيانات المنتجات المجمعة يجب أن تكون بصيغة JSON صحيحة')
        
        # تحويل بيانات المنتجات المجمعة
        bundle_products_data = []
        for item in bundle_data_list:
            try:
                bundle_product = Product.objects.get(id=item['bundle_id'], is_bundle=True)
                bundle_products_data.append({
                    'bundle_product': bundle_product,
                    'quantity': item['quantity'],
                    'reason': item.get('reason', student_refund.reason)
                })
            except Product.DoesNotExist:
                raise CommandError(f'المنتج المجمع بالمعرف {item["bundle_id"]} غير موجود')
            except KeyError as e:
                raise CommandError(f'بيانات المنتج المجمع ناقصة: {e}')
        
        self.stdout.write(f"معالجة تكامل مع تسوية الطالب: {student_refund.reference_number}")
        self.stdout.write(f"الطالب: {student_refund.student.name}")
        self.stdout.write(f"عدد المنتجات المجمعة: {len(bundle_products_data)}")
        
        # معاينة أو تنفيذ التكامل
        if preview:
            return self._preview_student_integration(student_refund, bundle_products_data)
        else:
            return self._execute_student_integration(student_refund, bundle_products_data, options)
    
    def _preview_bundle_refund(self, bundle_product, quantity, refund_context):
        """معاينة مرتجع المنتج المجمع"""
        self.stdout.write(self.style.WARNING("وضع المعاينة - لن يتم تنفيذ المرتجع فعلياً"))
        
        # الحصول على ملخص المرتجع
        summary = BundleRefundService.get_bundle_refund_summary(
            bundle_product, quantity, refund_context
        )
        
        # عرض معلومات المنتج المجمع
        bundle_info = summary['bundle_info']
        self.stdout.write("\n=== معلومات المنتج المجمع ===")
        self.stdout.write(f"الاسم: {bundle_info['name']}")
        self.stdout.write(f"الرمز: {bundle_info['sku']}")
        self.stdout.write(f"سعر الوحدة: {bundle_info['unit_price']} جنيه")
        self.stdout.write(f"الكمية المرتجعة: {bundle_info['refund_quantity']}")
        self.stdout.write(f"إجمالي المبلغ: {bundle_info['total_refund_amount']} جنيه")
        
        # عرض تفاصيل استعادة المكونات
        self.stdout.write("\n=== تفاصيل استعادة المكونات ===")
        for component in summary['components_restoration']:
            self.stdout.write(
                f"- {component['component_name']} ({component['component_sku']}): "
                f"استعادة {component['total_restoration']} وحدة "
                f"(من {component['current_stock']} إلى {component['stock_after_restoration']})"
            )
        
        # عرض فحص الأهلية
        eligibility = summary['eligibility_check']
        if eligibility['eligible']:
            self.stdout.write(self.style.SUCCESS(f"\n✓ {eligibility['message']}"))
        else:
            self.stdout.write(self.style.ERROR(f"\n✗ {eligibility['message']}"))
        
        # عرض التأثير المالي
        financial_impact = summary['financial_impact']
        self.stdout.write("\n=== التأثير المالي ===")
        self.stdout.write(f"مبلغ المرتجع: {financial_impact['refund_amount']} جنيه")
        self.stdout.write(f"نوع المرتجع: {financial_impact['refund_type']}")
        if financial_impact['requires_financial_approval']:
            self.stdout.write(self.style.WARNING("⚠ يتطلب موافقة مالية"))
    
    def _preview_student_integration(self, student_refund, bundle_products_data):
        """معاينة التكامل مع تسوية الطالب"""
        self.stdout.write(self.style.WARNING("وضع المعاينة - لن يتم تنفيذ التكامل فعلياً"))
        
        # الحصول على ملخص التكامل
        summary = BundleRefundIntegration.get_student_bundle_refund_summary(
            student_refund, bundle_products_data
        )
        
        # عرض معلومات الطالب
        student_info = summary['student_info']
        self.stdout.write("\n=== معلومات تسوية الطالب ===")
        self.stdout.write(f"الطالب: {student_info['student_name']}")
        self.stdout.write(f"رقم التسوية: {student_info['refund_reference']}")
        self.stdout.write(f"مبلغ التسوية: {student_info['refund_amount']} جنيه")
        self.stdout.write(f"السبب: {student_info['refund_reason']}")
        self.stdout.write(f"الحالة: {student_info['refund_status']}")
        
        # عرض ملخص المنتجات المجمعة
        self.stdout.write("\n=== ملخص المنتجات المجمعة ===")
        for bundle_summary in summary['bundle_products_summary']:
            self.stdout.write(
                f"- {bundle_summary['bundle_product_name']}: "
                f"{bundle_summary['quantity']} وحدة × {bundle_summary['unit_price']} = "
                f"{bundle_summary['total_amount']} جنيه"
            )
            self.stdout.write(f"  المكونات المتأثرة: {bundle_summary['components_affected']}")
        
        # عرض التأثير المالي
        financial_impact = summary['financial_impact']
        self.stdout.write("\n=== التأثير المالي ===")
        self.stdout.write(f"مبلغ تسوية الطالب: {financial_impact['student_refund_amount']} جنيه")
        self.stdout.write(f"إجمالي المنتجات المجمعة: {financial_impact['total_bundle_amount']} جنيه")
        self.stdout.write(f"الفرق: {financial_impact['amount_difference']} جنيه")
        
        if financial_impact['amount_match']:
            self.stdout.write(self.style.SUCCESS("✓ المبالغ متطابقة"))
        else:
            self.stdout.write(self.style.WARNING("⚠ المبالغ غير متطابقة"))
        
        # عرض فحص التوافق
        compatibility = summary['compatibility_check']
        if compatibility['is_compatible']:
            self.stdout.write(self.style.SUCCESS(f"\n✓ {compatibility['compatibility_message']}"))
        else:
            self.stdout.write(self.style.ERROR(f"\n✗ {compatibility['compatibility_message']}"))
        
        # عرض التوصيات
        if summary['processing_recommendations']:
            self.stdout.write("\n=== توصيات المعالجة ===")
            for recommendation in summary['processing_recommendations']:
                self.stdout.write(f"- {recommendation}")
    
    def _execute_bundle_refund(self, bundle_product, quantity, refund_context, options):
        """تنفيذ مرتجع المنتج المجمع"""
        force = options.get('force', False)
        
        # التحقق من الأهلية إذا لم يكن فرض
        if not force:
            is_eligible, message = BundleRefundService.validate_bundle_refund_eligibility(
                bundle_product, quantity, refund_context
            )
            if not is_eligible:
                raise CommandError(f"المرتجع غير مؤهل: {message}")
        
        self.stdout.write("تنفيذ مرتجع المنتج المجمع...")
        
        # تنفيذ المرتجع
        with transaction.atomic():
            success, refund_record, error = BundleRefundService.process_bundle_refund(
                bundle_product, quantity, refund_context
            )
        
        if success:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ تم تنفيذ المرتجع بنجاح\n"
                    f"رقم المرتجع: {refund_record['refund_id']}\n"
                    f"المبلغ: {refund_record['total_refund_amount']} جنيه\n"
                    f"المكونات المستعادة: {len(refund_record['component_restorations'])}"
                )
            )
            
            # عرض تفاصيل المكونات المستعادة
            self.stdout.write("\nتفاصيل استعادة المكونات:")
            for restoration in refund_record['component_restorations']:
                self.stdout.write(
                    f"- {restoration['component_name']}: "
                    f"استعادة {restoration['restored_quantity']} وحدة"
                )
        else:
            raise CommandError(f"فشل في تنفيذ المرتجع: {error}")
    
    def _execute_student_integration(self, student_refund, bundle_products_data, options):
        """تنفيذ التكامل مع تسوية الطالب"""
        force = options.get('force', False)
        
        # التحقق من التوافق إذا لم يكن فرض
        if not force:
            is_compatible, message, _ = BundleRefundIntegration.validate_bundle_refund_compatibility(
                student_refund, bundle_products_data
            )
            if not is_compatible:
                raise CommandError(f"التكامل غير متوافق: {message}")
        
        self.stdout.write("تنفيذ التكامل مع تسوية الطالب...")
        
        # تنفيذ التكامل
        with transaction.atomic():
            success, processing_record, error = BundleRefundIntegration.process_student_bundle_refund(
                student_refund, bundle_products_data
            )
        
        if success:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ تم تنفيذ التكامل بنجاح\n"
                    f"معرف المعالجة: {processing_record['processing_id']}\n"
                    f"المرتجعات الناجحة: {processing_record['successful_refunds_count']}\n"
                    f"المرتجعات الفاشلة: {processing_record['failed_refunds_count']}\n"
                    f"إجمالي المبلغ: {processing_record['total_bundle_amount']} جنيه"
                )
            )
            
            # عرض تفاصيل المرتجعات
            self.stdout.write("\nتفاصيل المرتجعات:")
            for bundle_refund in processing_record['bundle_refunds']:
                status_icon = "✓" if bundle_refund['success'] else "✗"
                self.stdout.write(
                    f"{status_icon} {bundle_refund['bundle_product_name']}: "
                    f"{bundle_refund['quantity']} وحدة - {bundle_refund['refund_amount']} جنيه"
                )
                if not bundle_refund['success']:
                    self.stdout.write(f"   خطأ: {bundle_refund['error']}")
        else:
            raise CommandError(f"فشل في تنفيذ التكامل: {error}")