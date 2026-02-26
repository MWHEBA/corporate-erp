# -*- coding: utf-8 -*-
"""
خدمة معالجة مرتجعات المنتجات المجمعة - محدثة للعمل مع AccountingGateway
Bundle Refund Processing Service

يتعامل مع معالجة مرتجعات المنتجات المجمعة واستعادة كميات المكونات عبر AccountingGateway
Requirements: 6.5
"""

from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
import logging
from typing import Dict, List, Optional, Tuple, Union, Any

logger = logging.getLogger(__name__)


class BundleRefundService:
    """
    خدمة معالجة مرتجعات المنتجات المجمعة
    
    يتعامل مع:
    - معالجة مرتجعات المنتجات المجمعة الكاملة والجزئية
    - استعادة كميات المكونات إلى المخزون
    - التكامل مع النظام المالي الموجود
    - التحقق من صحة المرتجعات وتوفر المكونات
    - إنشاء مسار تدقيق شامل للمرتجعات
    
    Requirements: 6.5
    """
    
    @staticmethod
    def process_bundle_refund(
        bundle_product,
        refund_quantity: int,
        refund_context: Dict[str, Any],
        original_sale_record: Optional[Dict] = None
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        معالجة مرتجع منتج مجمع مع استعادة كميات المكونات
        
        Args:
            bundle_product: المنتج المجمع
            refund_quantity: الكمية المرتجعة
            refund_context: سياق المرتجع (معلومات إضافية مثل المستخدم، سبب المرتجع، إلخ)
            original_sale_record: سجل البيع الأصلي (اختياري)
            
        Returns:
            Tuple[bool, Optional[Dict], Optional[str]]: 
                (نجح أم لا، سجل المرتجع، رسالة الخطأ)
                
        Requirements: 6.5
        """
        try:
            # التحقق من صحة المدخلات
            validation_result = BundleRefundService._validate_refund_inputs(
                bundle_product, refund_quantity, refund_context
            )
            if not validation_result[0]:
                return False, None, validation_result[1]
            
            # التحقق من إمكانية المرتجع
            refund_validation = BundleRefundService.validate_bundle_refund_eligibility(
                bundle_product, refund_quantity, refund_context, original_sale_record
            )
            if not refund_validation[0]:
                return False, None, refund_validation[1]
            
            # معالجة المرتجع داخل معاملة ذرية
            with transaction.atomic():
                # إنشاء سجل المرتجع
                refund_record = BundleRefundService._create_refund_record(
                    bundle_product, refund_quantity, refund_context, original_sale_record
                )
                
                # استعادة كميات المكونات
                component_restorations = BundleRefundService._restore_component_quantities(
                    bundle_product, refund_quantity, refund_record
                )
                
                # إنشاء المعاملة المالية للمرتجع
                financial_success, financial_record, financial_error = BundleRefundService._create_bundle_refund_financial_transaction(
                    bundle_product, refund_quantity, refund_context, component_restorations, original_sale_record
                )
                
                if not financial_success:
                    logger.error(f"فشل في إنشاء المعاملة المالية للمرتجع: {financial_error}")
                    # يمكن المتابعة حتى لو فشلت المعاملة المالية، لكن نسجل التحذير
                
                # تحديث سجل المرتجع بتفاصيل المكونات والمعاملة المالية
                refund_record['component_restorations'] = component_restorations
                refund_record['financial_record'] = financial_record
                refund_record['status'] = 'completed'
                refund_record['completed_at'] = timezone.now()
                
                # إنشاء مسار التدقيق
                audit_record = BundleRefundService._create_refund_audit_trail(
                    refund_record, bundle_product, refund_quantity, 
                    refund_context, component_restorations, financial_record
                )
                refund_record['audit_record'] = audit_record
                
                logger.info(
                    f"تم معالجة مرتجع {refund_quantity} وحدة من المنتج المجمع {bundle_product.name} بنجاح. "
                    f"رقم المرتجع: {refund_record.get('refund_id')}, "
                    f"المعاملة المالية: {financial_record.get('financial_transaction_id') if financial_record else 'غير متاح'}"
                )
                
                return True, refund_record, None
                
        except Exception as e:
            error_msg = f"خطأ في معالجة مرتجع المنتج المجمع {bundle_product.name}: {e}"
            logger.error(error_msg)
            return False, None, error_msg
    
    @staticmethod
    def validate_bundle_refund_eligibility(
        bundle_product, 
        refund_quantity: int, 
        refund_context: Dict[str, Any],
        original_sale_record: Optional[Dict] = None
    ) -> Tuple[bool, str]:
        """
        التحقق من أهلية مرتجع المنتج المجمع
        
        Args:
            bundle_product: المنتج المجمع
            refund_quantity: الكمية المرتجعة
            refund_context: سياق المرتجع
            original_sale_record: سجل البيع الأصلي (اختياري)
            
        Returns:
            Tuple[bool, str]: (مؤهل أم لا، رسالة توضيحية)
        """
        try:
            # التحقق من أن المنتج مجمع ونشط
            if not bundle_product.is_bundle:
                return False, _("المنتج المحدد ليس منتجاً مجمعاً")
            
            if not bundle_product.is_active:
                return False, _("المنتج المجمع غير نشط")
            
            if refund_quantity <= 0:
                return False, _("الكمية المرتجعة يجب أن تكون أكبر من صفر")
            
            # التحقق من وجود مكونات
            components = bundle_product.components.select_related('component_product').all()
            if not components.exists():
                return False, _("المنتج المجمع لا يحتوي على مكونات")
            
            # التحقق من نشاط المكونات
            inactive_components = []
            for component in components:
                if not component.component_product.is_active:
                    inactive_components.append(component.component_product.name)
            
            if inactive_components:
                return False, _("المكونات التالية غير نشطة: {}").format(', '.join(inactive_components))
            
            # التحقق من الكمية المرتجعة مقابل البيع الأصلي (إذا توفر)
            if original_sale_record:
                original_quantity = original_sale_record.get('quantity_sold', 0)
                if refund_quantity > original_quantity:
                    return False, _("الكمية المرتجعة ({}) أكبر من الكمية المباعة الأصلية ({})").format(
                        refund_quantity, original_quantity
                    )
            
            # التحقق من نوع المرتجع
            refund_type = refund_context.get('refund_type', 'full_refund')
            if refund_type not in ['full_refund', 'partial_refund', 'defective_return', 'customer_return']:
                return False, _("نوع المرتجع غير صحيح: {}").format(refund_type)
            
            # التحقق من سبب المرتجع
            refund_reason = refund_context.get('refund_reason', '')
            if not refund_reason or len(refund_reason.strip()) < 5:
                return False, _("سبب المرتجع مطلوب ويجب أن يكون واضحاً")
            
            return True, _("المرتجع مؤهل للمعالجة")
            
        except Exception as e:
            logger.error(f"خطأ في التحقق من أهلية مرتجع المنتج المجمع {bundle_product.name}: {e}")
            return False, _("خطأ في التحقق من أهلية المرتجع")
    
    @staticmethod
    def create_bundle_refund_from_student_refund(
        student_refund,
        bundle_product,
        refund_quantity: int
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        إنشاء مرتجع منتج مجمع من تسوية طالب موجودة
        
        Args:
            student_refund: تسوية الطالب (StudentRefund instance)
            bundle_product: المنتج المجمع
            refund_quantity: الكمية المرتجعة
            
        Returns:
            Tuple[bool, Optional[Dict], Optional[str]]: 
                (نجح أم لا، سجل المرتجع، رسالة الخطأ)
        """
        try:
            # إنشاء سياق المرتجع من تسوية الطالب
            refund_context = {
                'refund_type': 'student_refund_integration',
                'refund_reason': student_refund.reason,
                'student_refund_id': student_refund.id,
                'student_id': student_refund.student.id,
                'student_name': student_refund.student.name,
                'created_by_id': student_refund.created_by.id,
                'approved_by_id': student_refund.approved_by.id if student_refund.approved_by else None,
                'reference_number': student_refund.reference_number,
                'original_amount': float(student_refund.amount),
                'notes': f"مرتجع منتج مجمع مرتبط بتسوية الطالب {student_refund.reference_number}"
            }
            
            # معالجة المرتجع
            success, refund_record, error = BundleRefundService.process_bundle_refund(
                bundle_product=bundle_product,
                refund_quantity=refund_quantity,
                refund_context=refund_context
            )
            
            if success and refund_record:
                # ربط المرتجع بتسوية الطالب
                refund_record['student_refund_integration'] = {
                    'student_refund_id': student_refund.id,
                    'student_refund_reference': student_refund.reference_number,
                    'integration_status': 'completed',
                    'integration_timestamp': timezone.now().isoformat()
                }
                
                logger.info(
                    f"تم إنشاء مرتجع منتج مجمع من تسوية الطالب {student_refund.reference_number}. "
                    f"المنتج: {bundle_product.name}, الكمية: {refund_quantity}"
                )
            
            return success, refund_record, error
            
        except Exception as e:
            error_msg = f"خطأ في إنشاء مرتجع منتج مجمع من تسوية الطالب: {e}"
            logger.error(error_msg)
            return False, None, error_msg
    
    @staticmethod
    def get_bundle_refund_summary(
        bundle_product, 
        refund_quantity: int,
        refund_context: Dict[str, Any] = None
    ) -> Dict:
        """
        الحصول على ملخص مرتجع المنتج المجمع قبل التنفيذ
        
        Args:
            bundle_product: المنتج المجمع
            refund_quantity: الكمية المرتجعة
            refund_context: سياق المرتجع (اختياري)
            
        Returns:
            Dict: ملخص المرتجع المتوقع
        """
        try:
            summary = {
                'bundle_info': {
                    'name': bundle_product.name,
                    'sku': bundle_product.sku,
                    'unit_price': float(bundle_product.selling_price),
                    'refund_quantity': refund_quantity,
                    'total_refund_amount': float(bundle_product.selling_price * refund_quantity)
                },
                'components_restoration': [],
                'eligibility_check': None,
                'can_proceed': False,
                'financial_impact': {}
            }
            
            # التحقق من الأهلية
            eligibility = BundleRefundService.validate_bundle_refund_eligibility(
                bundle_product, refund_quantity, refund_context or {}
            )
            summary['eligibility_check'] = {
                'eligible': eligibility[0],
                'message': eligibility[1]
            }
            summary['can_proceed'] = eligibility[0]
            
            # تفاصيل استعادة المكونات
            components = bundle_product.components.select_related('component_product').all()
            
            for component in components:
                component_product = component.component_product
                restoration_quantity = component.required_quantity * refund_quantity
                
                summary['components_restoration'].append({
                    'component_name': component_product.name,
                    'component_sku': component_product.sku,
                    'required_per_unit': component.required_quantity,
                    'total_restoration': restoration_quantity,
                    'current_stock': component_product.current_stock,
                    'stock_after_restoration': component_product.current_stock + restoration_quantity
                })
            
            # التأثير المالي
            refund_amount = bundle_product.selling_price * refund_quantity
            summary['financial_impact'] = {
                'refund_amount': float(refund_amount),
                'refund_type': refund_context.get('refund_type', 'full_refund') if refund_context else 'full_refund',
                'requires_financial_approval': refund_amount > Decimal('1000.00'),
                'estimated_processing_time': '5-10 دقائق'
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء ملخص مرتجع المنتج المجمع: {e}")
            return {'error': str(e)}
    
    @staticmethod
    def _validate_refund_inputs(
        bundle_product, 
        refund_quantity: int, 
        refund_context: Dict
    ) -> Tuple[bool, Optional[str]]:
        """
        التحقق من صحة مدخلات المرتجع
        
        Args:
            bundle_product: المنتج المجمع
            refund_quantity: الكمية المرتجعة
            refund_context: سياق المرتجع
            
        Returns:
            Tuple[bool, Optional[str]]: (صحيح أم لا، رسالة الخطأ)
        """
        if bundle_product is None:
            return False, _("المنتج المجمع غير محدد")
        
        if not hasattr(bundle_product, 'is_bundle') or not bundle_product.is_bundle:
            return False, _("المنتج المحدد ليس منتجاً مجمعاً")
        
        if refund_quantity <= 0:
            return False, _("الكمية المرتجعة يجب أن تكون أكبر من صفر")
        
        if not isinstance(refund_context, dict):
            return False, _("سياق المرتجع يجب أن يكون قاموس")
        
        # التحقق من وجود المعلومات المطلوبة في سياق المرتجع
        required_fields = ['created_by_id', 'refund_reason']
        for field in required_fields:
            if field not in refund_context:
                return False, _("معلومة مطلوبة مفقودة في سياق المرتجع: {}").format(field)
        
        return True, None
    
    @staticmethod
    def _create_refund_record(
        bundle_product, 
        refund_quantity: int, 
        refund_context: Dict,
        original_sale_record: Optional[Dict] = None
    ) -> Dict:
        """
        إنشاء سجل المرتجع
        
        Args:
            bundle_product: المنتج المجمع
            refund_quantity: الكمية المرتجعة
            refund_context: سياق المرتجع
            original_sale_record: سجل البيع الأصلي (اختياري)
            
        Returns:
            Dict: سجل المرتجع
        """
        from django.utils.crypto import get_random_string
        
        refund_id = f"BUNDLE_REFUND_{timezone.now().strftime('%Y%m%d_%H%M%S')}_{get_random_string(6)}"
        
        return {
            'refund_id': refund_id,
            'refund_type': 'bundle_refund',
            'bundle_product_id': bundle_product.id,
            'bundle_product_name': bundle_product.name,
            'bundle_product_sku': bundle_product.sku,
            'refund_quantity': refund_quantity,
            'unit_price': bundle_product.selling_price,
            'total_refund_amount': bundle_product.selling_price * refund_quantity,
            'refund_reason': refund_context.get('refund_reason'),
            'refund_category': refund_context.get('refund_type', 'full_refund'),
            'status': 'processing',
            'created_at': timezone.now(),
            'created_by_id': refund_context.get('created_by_id'),
            'approved_by_id': refund_context.get('approved_by_id'),
            'customer_id': refund_context.get('customer_id'),
            'student_id': refund_context.get('student_id'),
            'reference_number': refund_context.get('reference_number'),
            'original_sale_record': original_sale_record,
            'notes': refund_context.get('notes', ''),
            'processed': False
        }
    
    @staticmethod
    def _restore_component_quantities(
        bundle_product, 
        refund_quantity: int, 
        refund_record: Dict
    ) -> List[Dict]:
        """
        استعادة كميات المكونات إلى المخزون
        
        Args:
            bundle_product: المنتج المجمع
            refund_quantity: الكمية المرتجعة
            refund_record: سجل المرتجع
            
        Returns:
            List[Dict]: قائمة بتفاصيل استعادة المكونات
        """
        component_restorations = []
        components = bundle_product.components.select_related('component_product').all()
        
        for component in components:
            component_product = component.component_product
            required_quantity = component.required_quantity
            total_restoration = required_quantity * refund_quantity
            
            # إنشاء حركة مخزون للاستعادة
            BundleRefundService._create_stock_movement(
                product_id=component_product.id,
                quantity=total_restoration,
                movement_type='return_in',
                reference_number=refund_record['refund_id'],
                notes=f"استعادة مكون من مرتجع المنتج المجمع {bundle_product.name}",
                created_by_id=refund_record['created_by_id']
            )
            
            component_restorations.append({
                'component_id': component_product.id,
                'component_name': component_product.name,
                'component_sku': component_product.sku,
                'required_per_unit': required_quantity,
                'units_refunded': refund_quantity,
                'restored_quantity': total_restoration,
                'stock_before_restoration': component_product.current_stock,
                'stock_after_restoration': component_product.current_stock + total_restoration,
                'restored_at': timezone.now()
            })
            
            logger.debug(
                f"استعادة {total_restoration} وحدة إلى المكون {component_product.name} "
                f"من مرتجع {refund_quantity} وحدة من المنتج المجمع {bundle_product.name}"
            )
        
        return component_restorations
    
    @staticmethod
    def _create_bundle_refund_financial_transaction(
        bundle_product,
        refund_quantity: int,
        refund_context: Dict[str, Any],
        component_restorations: List[Dict],
        original_sale_record: Optional[Dict] = None
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        إنشاء معاملة مالية لمرتجع المنتج المجمع
        
        Args:
            bundle_product: المنتج المجمع
            refund_quantity: الكمية المرتجعة
            refund_context: سياق المرتجع
            component_restorations: تفاصيل استعادة المكونات
            original_sale_record: سجل البيع الأصلي (اختياري)
            
        Returns:
            Tuple[bool, Optional[Dict], Optional[str]]: 
                (نجح أم لا، سجل المعاملة المالية، رسالة الخطأ)
        """
        try:
            # التحقق من وجود تكامل مع النظام المالي للطلاب
            if refund_context.get('student_refund_id'):
                return BundleRefundService._integrate_with_student_refund_system(
                    bundle_product, refund_quantity, refund_context, component_restorations
                )
            
            # إنشاء معاملة مالية عامة للمرتجع
            return BundleRefundService._create_general_refund_financial_transaction(
                bundle_product, refund_quantity, refund_context, component_restorations, original_sale_record
            )
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء المعاملة المالية لمرتجع المنتج المجمع: {e}")
            return False, None, str(e)
    
    @staticmethod
    def _integrate_with_student_refund_system(
        bundle_product,
        refund_quantity: int,
        refund_context: Dict[str, Any],
        component_restorations: List[Dict]
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        التكامل مع نظام مرتجعات الطلاب الموجود
        
        Args:
            bundle_product: المنتج المجمع
            refund_quantity: الكمية المرتجعة
            refund_context: سياق المرتجع
            component_restorations: تفاصيل استعادة المكونات
            
        Returns:
            Tuple[bool, Optional[Dict], Optional[str]]: 
                (نجح أم لا، سجل القيد المحاسبي، رسالة الخطأ)
        """
        # Student refund integration removed - no longer applicable for ERP system
        try:
            # Create financial record for bundle refund
            financial_record = {
                'financial_transaction_type': 'bundle_refund',
                'bundle_refund_amount': float(bundle_product.selling_price * refund_quantity),
                'integration_method': 'bundle_component_restoration',
                'journal_entry_number': student_refund.journal_entry.number if student_refund.journal_entry else None,
                'component_restorations': component_restorations,
                'integration_status': 'completed',
                'integration_timestamp': timezone.now().isoformat(),
                'notes': f"مرتجع منتج مجمع مرتبط بتسوية الطالب {student_refund.reference_number}"
            }
            
            logger.info(
                f"تم التكامل مع نظام مرتجعات الطلاب. "
                f"تسوية الطالب: {student_refund.reference_number}, "
                f"المنتج المجمع: {bundle_product.name}"
            )
            
            return True, financial_record, None
            
        except Exception as e:
            logger.error(f"خطأ في التكامل مع نظام مرتجعات الطلاب: {e}")
            return False, None, str(e)
    
    @staticmethod
    def _create_general_refund_financial_transaction(
        bundle_product,
        refund_quantity: int,
        refund_context: Dict[str, Any],
        component_restorations: List[Dict],
        original_sale_record: Optional[Dict] = None
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        إنشاء قيد محاسبي عام للمرتجع عبر AccountingGateway
        
        Args:
            bundle_product: المنتج المجمع
            refund_quantity: الكمية المرتجعة
            refund_context: سياق المرتجع
            component_restorations: تفاصيل استعادة المكونات
            original_sale_record: سجل البيع الأصلي (اختياري)
            
        Returns:
            Tuple[bool, Optional[Dict], Optional[str]]: 
                (نجح أم لا، سجل القيد المحاسبي، رسالة الخطأ)
        """
        try:
            from governance.services import AccountingGateway, JournalEntryLineData
            from financial.models.chart_of_accounts import ChartOfAccounts
            from django.contrib.auth import get_user_model
            
            User = get_user_model()
            
            # الحصول على المستخدم
            created_by = User.objects.get(id=refund_context['created_by_id'])
            
            # حساب المبلغ الإجمالي للمرتجع
            total_refund_amount = bundle_product.selling_price * refund_quantity
            
            # تحديد الحسابات المحاسبية
            # 40500 - إيرادات مبيعات المنتجات (عكس الإيراد)
            # 10100 - الخزينة (إخراج النقدية) - أو حسب payment_method
            revenue_account_code = "40500"  # إيرادات مبيعات المنتجات
            
            # تحديد حساب الإخراج حسب طريقة المرتجع
            payment_method = refund_context.get('payment_method', 'cash')
            if payment_method == 'cash' or payment_method == '10100':
                refund_account_code = "10100"  # الخزينة
            elif payment_method == 'bank_transfer' or payment_method == '10200':
                refund_account_code = "10200"  # البنك
            else:
                # إذا كان account code مباشرة
                refund_account_code = payment_method if payment_method.isdigit() else "10100"
            
            # التحقق من وجود الحسابات
            revenue_account = ChartOfAccounts.objects.filter(code=revenue_account_code, is_active=True).first()
            refund_account = ChartOfAccounts.objects.filter(code=refund_account_code, is_active=True).first()
            
            if not revenue_account or not refund_account:
                logger.error(f"الحسابات المحاسبية غير موجودة: revenue={revenue_account_code}, refund={refund_account_code}")
                raise ValueError("الحسابات المحاسبية المطلوبة غير موجودة")
            
            # إعداد بنود القيد المحاسبي
            description = f'مرتجع {refund_quantity} وحدة من المنتج المجمع {bundle_product.name} (SKU: {bundle_product.sku})\nسبب المرتجع: {refund_context.get("refund_reason", "")}'
            
            # إضافة تفاصيل المكونات المستعادة
            if component_restorations:
                component_details = []
                for restoration in component_restorations:
                    component_details.append(
                        f"- {restoration['component_name']} (SKU: {restoration['component_sku']}): "
                        f"استعادة {restoration['restored_quantity']} وحدة"
                    )
                description += f"\n\nتفاصيل استعادة المكونات:\n" + "\n".join(component_details)
            
            lines = [
                JournalEntryLineData(
                    account_code=revenue_account_code,
                    debit=total_refund_amount,
                    credit=Decimal('0.00'),
                    description=f"عكس إيرادات بيع منتج مجمع - {bundle_product.name}"
                ),
                JournalEntryLineData(
                    account_code=refund_account_code,
                    debit=Decimal('0.00'),
                    credit=total_refund_amount,
                    description=f"إخراج مرتجع منتج مجمع - {bundle_product.name}"
                )
            ]
            
            # إنشاء القيد المحاسبي عبر Gateway
            gateway = AccountingGateway()
            reference_number = refund_context.get('reference_number', f'BUNDLE-REFUND-{bundle_product.id}-{timezone.now().strftime("%Y%m%d%H%M%S")}')
            
            journal_entry = gateway.create_journal_entry(
                source_module='product',
                source_model='BundleRefund',
                source_id=bundle_product.id,
                lines=lines,
                idempotency_key=f"JE:product:BundleRefund:{bundle_product.id}:{reference_number}",
                user=created_by,
                entry_type='refund',
                description=description,
                reference=reference_number,
                date=timezone.now().date(),
                financial_category=bundle_product.financial_category if hasattr(bundle_product, 'financial_category') else None,
                financial_subcategory=bundle_product.financial_subcategory if hasattr(bundle_product, 'financial_subcategory') else None
            )
            
            # إنشاء سجل القيد المحاسبي
            financial_record = {
                'journal_entry_id': journal_entry.id,
                'journal_entry': journal_entry,
                'journal_entry_number': journal_entry.number,
                'refund_amount': float(total_refund_amount),
                'transaction_type': 'bundle_refund',
                'component_restorations': component_restorations,
                'created_at': timezone.now().isoformat()
            }
            
            logger.info(
                f"تم إنشاء قيد محاسبي لمرتجع المنتج المجمع {bundle_product.name}. "
                f"القيد المحاسبي: {journal_entry.number}, "
                f"المبلغ: {total_refund_amount}"
            )
            
            return True, financial_record, None
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء القيد المحاسبي العام للمرتجع: {e}")
            return False, None, str(e)
    
    @staticmethod
    def _create_stock_movement(
        product_id: int,
        quantity: int,
        movement_type: str,
        reference_number: str,
        notes: str,
        created_by_id: int
    ) -> None:
        """
        إنشاء حركة مخزون لاستعادة المكونات
        
        Args:
            product_id: معرف المنتج
            quantity: الكمية المستعادة
            movement_type: نوع الحركة (return_in)
            reference_number: رقم المرجع
            notes: ملاحظات
            created_by_id: معرف المستخدم المنشئ
        """
        try:
            from ..models import StockMovement, Product, Warehouse, Stock
            from django.contrib.auth import get_user_model
            
            User = get_user_model()
            
            # الحصول على المنتج
            product = Product.objects.get(id=product_id)
            
            # الحصول على المخزن الافتراضي (أول مخزن نشط)
            warehouse = Warehouse.objects.filter(is_active=True).first()
            if not warehouse:
                raise ValidationError(_("لا يوجد مخزن نشط لإنشاء حركة المخزون"))
            
            # الحصول على المستخدم
            created_by = User.objects.get(id=created_by_id)
            
            # ✅ استخدام MovementService بدلاً من التحديث المباشر
            from governance.services import MovementService
            from decimal import Decimal
            
            movement_service = MovementService()
            
            # إنشاء حركة المخزون عبر MovementService (استعادة = إضافة)
            stock_movement = movement_service.process_movement(
                product_id=product.id,
                quantity_change=Decimal(str(quantity)),
                movement_type='return_in',
                source_reference=reference_number,
                idempotency_key=f"bundle_refund_{product.id}_{reference_number}_{timezone.now().timestamp()}",
                user=created_by,
                document_number=reference_number,
                notes=notes
            )
            
            logger.debug(f"تم إنشاء حركة مخزون للاستعادة عبر MovementService: {stock_movement}")
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء حركة المخزون للاستعادة: {e}")
            raise
    
    @staticmethod
    def _create_refund_audit_trail(
        refund_record: Dict,
        bundle_product,
        refund_quantity: int,
        refund_context: Dict[str, Any],
        component_restorations: List[Dict],
        financial_record: Optional[Dict] = None
    ) -> Dict:
        """
        إنشاء مسار تدقيق شامل لمرتجع المنتج المجمع
        
        Args:
            refund_record: سجل المرتجع
            bundle_product: المنتج المجمع
            refund_quantity: الكمية المرتجعة
            refund_context: سياق المرتجع
            component_restorations: تفاصيل استعادة المكونات
            financial_record: سجل المعاملة المالية (اختياري)
            
        Returns:
            Dict: سجل مسار التدقيق
        """
        audit_record = {
            'audit_id': f"BUNDLE_REFUND_AUDIT_{refund_record['refund_id']}_{timezone.now().strftime('%Y%m%d%H%M%S')}",
            'transaction_type': 'bundle_refund_processing',
            'refund_id': refund_record['refund_id'],
            'bundle_product_info': {
                'id': bundle_product.id,
                'name': bundle_product.name,
                'sku': bundle_product.sku,
                'selling_price': float(bundle_product.selling_price),
                'cost_price': float(bundle_product.cost_price)
            },
            'refund_details': {
                'refund_quantity': refund_quantity,
                'unit_price': float(bundle_product.selling_price),
                'total_refund_amount': float(refund_record['total_refund_amount']),
                'refund_reason': refund_context.get('refund_reason'),
                'refund_type': refund_context.get('refund_type', 'full_refund'),
                'refund_date': refund_record['created_at'].isoformat(),
                'reference_number': refund_record.get('reference_number')
            },
            'component_restorations': component_restorations,
            'financial_processing': {
                'financial_integration': financial_record is not None,
                'journal_entry_id': financial_record.get('journal_entry_id') if financial_record else None,
                'journal_entry_number': financial_record.get('journal_entry_number') if financial_record else None,
                'refund_amount_recorded': float(financial_record.get('refund_amount', 0)) if financial_record else 0,
                'via_gateway': True
            },
            'refund_context': {
                'created_by_id': refund_context.get('created_by_id'),
                'approved_by_id': refund_context.get('approved_by_id'),
                'customer_id': refund_context.get('customer_id'),
                'student_id': refund_context.get('student_id'),
                'student_refund_id': refund_context.get('student_refund_id'),
                'notes': refund_context.get('notes', '')
            },
            'audit_metadata': {
                'created_at': timezone.now().isoformat(),
                'audit_level': 'detailed',
                'compliance_requirements': ['component_restoration', 'financial_recording', 'audit_trail'],
                'processing_method': 'automated_bundle_refund_engine'
            }
        }
        
        # حفظ مسار التدقيق
        logger.info(f"Bundle Refund Audit Trail: {audit_record}")
        
        return audit_record
    
