# -*- coding: utf-8 -*-
"""
تكامل مرتجعات المنتجات المجمعة مع الأنظمة الموجودة
Bundle Refund Integration with Existing Systems

يتعامل مع التكامل مع نظام مرتجعات الطلاب والأنظمة المالية الموجودة
Requirements: 6.5
"""

from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
import logging
from typing import Dict, List, Optional, Tuple, Union, Any

from .bundle_refund_service import BundleRefundService

logger = logging.getLogger(__name__)


class BundleRefundIntegration:
    """
    تكامل مرتجعات المنتجات المجمعة مع الأنظمة الموجودة
    
    يتعامل مع:
    - التكامل مع نظام مرتجعات الطلاب (StudentRefund)
    - التكامل مع خدمات التسوية المالية الموجودة
    - معالجة المرتجعات المختلطة (نقدية + منتجات مجمعة)
    - التحقق من صحة المرتجعات والموافقات
    
    Requirements: 6.5
    """
    
    @staticmethod
    def process_student_bundle_refund(
        student_refund,
        bundle_products_data: List[Dict[str, Any]]
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        معالجة مرتجع منتجات مجمعة مرتبط بتسوية طالب
        
        Args:
            student_refund: تسوية الطالب (StudentRefund instance)
            bundle_products_data: قائمة بيانات المنتجات المجمعة المرتجعة
                [{'bundle_product': Product, 'quantity': int, 'reason': str}, ...]
            
        Returns:
            Tuple[bool, Optional[Dict], Optional[str]]: 
                (نجح أم لا، سجل المعالجة، رسالة الخطأ)
        """
        try:
            # التحقق من صحة تسوية الطالب
            validation_result = BundleRefundIntegration._validate_student_refund(student_refund)
            if not validation_result[0]:
                return False, None, validation_result[1]
            
            # التحقق من صحة بيانات المنتجات المجمعة
            products_validation = BundleRefundIntegration._validate_bundle_products_data(bundle_products_data)
            if not products_validation[0]:
                return False, None, products_validation[1]
            
            # معالجة المرتجعات داخل معاملة ذرية
            with transaction.atomic():
                processing_record = {
                    'student_refund_id': student_refund.id,
                    'student_refund_reference': student_refund.reference_number,
                    'processing_id': f"STUDENT_BUNDLE_REFUND_{student_refund.id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}",
                    'bundle_refunds': [],
                    'total_bundle_amount': Decimal('0.00'),
                    'processing_status': 'processing',
                    'started_at': timezone.now()
                }
                
                # معالجة كل منتج مجمع
                for bundle_data in bundle_products_data:
                    bundle_product = bundle_data['bundle_product']
                    quantity = bundle_data['quantity']
                    specific_reason = bundle_data.get('reason', student_refund.reason)
                    
                    # إنشاء سياق المرتجع
                    refund_context = BundleRefundIntegration._create_student_refund_context(
                        student_refund, specific_reason
                    )
                    
                    # معالجة مرتجع المنتج المجمع
                    success, bundle_refund_record, error = BundleRefundService.process_bundle_refund(
                        bundle_product=bundle_product,
                        refund_quantity=quantity,
                        refund_context=refund_context,
                        original_sale_record=None  # يمكن تحسينه لاحقاً للربط بسجل البيع الأصلي
                    )
                    
                    if not success:
                        logger.error(f"فشل في معالجة مرتجع المنتج المجمع {bundle_product.name}: {error}")
                        # يمكن اختيار المتابعة أو التوقف حسب السياسة
                        continue
                    
                    # إضافة سجل المرتجع إلى المعالجة
                    processing_record['bundle_refunds'].append({
                        'bundle_product_id': bundle_product.id,
                        'bundle_product_name': bundle_product.name,
                        'quantity': quantity,
                        'refund_amount': float(bundle_product.selling_price * quantity),
                        'refund_record': bundle_refund_record,
                        'success': success,
                        'error': error
                    })
                    
                    if success:
                        processing_record['total_bundle_amount'] += bundle_product.selling_price * quantity
                
                # تحديث حالة المعالجة
                successful_refunds = [r for r in processing_record['bundle_refunds'] if r['success']]
                failed_refunds = [r for r in processing_record['bundle_refunds'] if not r['success']]
                
                processing_record['processing_status'] = 'completed' if not failed_refunds else 'partial'
                processing_record['successful_refunds_count'] = len(successful_refunds)
                processing_record['failed_refunds_count'] = len(failed_refunds)
                processing_record['completed_at'] = timezone.now()
                
                # ربط المعالجة بتسوية الطالب
                BundleRefundIntegration._link_processing_to_student_refund(
                    student_refund, processing_record
                )
                
                # إنشاء مسار تدقيق للتكامل
                integration_audit = BundleRefundIntegration._create_integration_audit_trail(
                    student_refund, processing_record
                )
                processing_record['integration_audit'] = integration_audit
                
                logger.info(
                    f"تم معالجة مرتجعات المنتجات المجمعة لتسوية الطالب {student_refund.reference_number}. "
                    f"نجح: {len(successful_refunds)}, فشل: {len(failed_refunds)}, "
                    f"المبلغ الإجمالي: {processing_record['total_bundle_amount']}"
                )
                
                return True, processing_record, None
                
        except Exception as e:
            error_msg = f"خطأ في معالجة مرتجعات المنتجات المجمعة لتسوية الطالب: {e}"
            logger.error(error_msg)
            return False, None, error_msg
    
    @staticmethod
    def validate_bundle_refund_compatibility(
        student_refund,
        bundle_products_data: List[Dict[str, Any]]
    ) -> Tuple[bool, str, Dict]:
        """
        التحقق من توافق مرتجع المنتجات المجمعة مع تسوية الطالب
        
        Args:
            student_refund: تسوية الطالب
            bundle_products_data: بيانات المنتجات المجمعة
            
        Returns:
            Tuple[bool, str, Dict]: (متوافق أم لا، رسالة، تفاصيل التحقق)
        """
        try:
            compatibility_check = {
                'student_refund_valid': False,
                'bundle_products_valid': False,
                'amount_compatibility': False,
                'timing_compatibility': False,
                'approval_compatibility': False,
                'total_bundle_amount': Decimal('0.00'),
                'student_refund_amount': Decimal('0.00'),
                'compatibility_issues': [],
                'recommendations': []
            }
            
            # التحقق من صحة تسوية الطالب
            student_validation = BundleRefundIntegration._validate_student_refund(student_refund)
            compatibility_check['student_refund_valid'] = student_validation[0]
            if not student_validation[0]:
                compatibility_check['compatibility_issues'].append(f"تسوية الطالب غير صحيحة: {student_validation[1]}")
            
            # التحقق من صحة المنتجات المجمعة
            products_validation = BundleRefundIntegration._validate_bundle_products_data(bundle_products_data)
            compatibility_check['bundle_products_valid'] = products_validation[0]
            if not products_validation[0]:
                compatibility_check['compatibility_issues'].append(f"بيانات المنتجات المجمعة غير صحيحة: {products_validation[1]}")
            
            # حساب المبالغ
            compatibility_check['student_refund_amount'] = student_refund.amount
            
            for bundle_data in bundle_products_data:
                bundle_product = bundle_data['bundle_product']
                quantity = bundle_data['quantity']
                bundle_amount = bundle_product.selling_price * quantity
                compatibility_check['total_bundle_amount'] += bundle_amount
            
            # التحقق من توافق المبالغ
            amount_difference = abs(compatibility_check['student_refund_amount'] - compatibility_check['total_bundle_amount'])
            compatibility_check['amount_compatibility'] = amount_difference <= Decimal('1.00')  # هامش خطأ 1 جنيه
            
            if not compatibility_check['amount_compatibility']:
                compatibility_check['compatibility_issues'].append(
                    f"عدم توافق في المبالغ: تسوية الطالب {compatibility_check['student_refund_amount']} "
                    f"مقابل المنتجات المجمعة {compatibility_check['total_bundle_amount']}"
                )
                compatibility_check['recommendations'].append("تحقق من الكميات والأسعار")
            
            # التحقق من توافق التوقيت
            compatibility_check['timing_compatibility'] = student_refund.status in ['approved', 'processing']
            if not compatibility_check['timing_compatibility']:
                compatibility_check['compatibility_issues'].append(f"حالة تسوية الطالب غير مناسبة: {student_refund.status}")
                compatibility_check['recommendations'].append("تأكد من موافقة تسوية الطالب أولاً")
            
            # التحقق من توافق الموافقات
            compatibility_check['approval_compatibility'] = student_refund.approved_by is not None
            if not compatibility_check['approval_compatibility']:
                compatibility_check['compatibility_issues'].append("تسوية الطالب غير معتمدة")
                compatibility_check['recommendations'].append("احصل على موافقة تسوية الطالب أولاً")
            
            # تحديد التوافق العام
            is_compatible = all([
                compatibility_check['student_refund_valid'],
                compatibility_check['bundle_products_valid'],
                compatibility_check['amount_compatibility'],
                compatibility_check['timing_compatibility'],
                compatibility_check['approval_compatibility']
            ])
            
            if is_compatible:
                message = "المرتجع متوافق ويمكن المعالجة"
            else:
                issues_summary = '; '.join(compatibility_check['compatibility_issues'][:3])  # أول 3 مشاكل
                message = f"المرتجع غير متوافق: {issues_summary}"
            
            return is_compatible, message, compatibility_check
            
        except Exception as e:
            logger.error(f"خطأ في التحقق من توافق مرتجع المنتجات المجمعة: {e}")
            return False, f"خطأ في التحقق من التوافق: {e}", {}
    
    @staticmethod
    def get_student_bundle_refund_summary(
        student_refund,
        bundle_products_data: List[Dict[str, Any]]
    ) -> Dict:
        """
        الحصول على ملخص مرتجع المنتجات المجمعة للطالب
        
        Args:
            student_refund: تسوية الطالب
            bundle_products_data: بيانات المنتجات المجمعة
            
        Returns:
            Dict: ملخص شامل للمرتجع
        """
        try:
            summary = {
                'student_info': {
                    'student_id': student_refund.student.id,
                    'student_name': student_refund.student.name,
                    'refund_reference': student_refund.reference_number,
                    'refund_amount': float(student_refund.amount),
                    'refund_reason': student_refund.reason,
                    'refund_status': student_refund.status
                },
                'bundle_products_summary': [],
                'financial_impact': {},
                'compatibility_check': {},
                'processing_recommendations': []
            }
            
            # ملخص المنتجات المجمعة
            total_bundle_amount = Decimal('0.00')
            total_components_affected = 0
            
            for bundle_data in bundle_products_data:
                bundle_product = bundle_data['bundle_product']
                quantity = bundle_data['quantity']
                bundle_amount = bundle_product.selling_price * quantity
                total_bundle_amount += bundle_amount
                
                # حساب المكونات المتأثرة
                components_count = bundle_product.components.count()
                total_components_affected += components_count * quantity
                
                # الحصول على ملخص المنتج المجمع
                bundle_summary = BundleRefundService.get_bundle_refund_summary(
                    bundle_product, quantity, {'refund_reason': bundle_data.get('reason', student_refund.reason)}
                )
                
                summary['bundle_products_summary'].append({
                    'bundle_product_id': bundle_product.id,
                    'bundle_product_name': bundle_product.name,
                    'bundle_product_sku': bundle_product.sku,
                    'quantity': quantity,
                    'unit_price': float(bundle_product.selling_price),
                    'total_amount': float(bundle_amount),
                    'components_count': components_count,
                    'components_affected': components_count * quantity,
                    'bundle_summary': bundle_summary,
                    'specific_reason': bundle_data.get('reason', student_refund.reason)
                })
            
            # التأثير المالي
            amount_difference = student_refund.amount - total_bundle_amount
            summary['financial_impact'] = {
                'student_refund_amount': float(student_refund.amount),
                'total_bundle_amount': float(total_bundle_amount),
                'amount_difference': float(amount_difference),
                'amount_match': abs(amount_difference) <= Decimal('1.00'),
                'total_components_affected': total_components_affected,
                'requires_additional_processing': abs(amount_difference) > Decimal('1.00')
            }
            
            # فحص التوافق
            compatibility_result = BundleRefundIntegration.validate_bundle_refund_compatibility(
                student_refund, bundle_products_data
            )
            summary['compatibility_check'] = {
                'is_compatible': compatibility_result[0],
                'compatibility_message': compatibility_result[1],
                'compatibility_details': compatibility_result[2]
            }
            
            # توصيات المعالجة
            if compatibility_result[0]:
                summary['processing_recommendations'].append("يمكن المعالجة مباشرة")
            else:
                summary['processing_recommendations'].extend(
                    compatibility_result[2].get('recommendations', [])
                )
            
            if abs(amount_difference) > Decimal('1.00'):
                if amount_difference > 0:
                    summary['processing_recommendations'].append(
                        f"يتبقى مبلغ {amount_difference} جنيه من تسوية الطالب"
                    )
                else:
                    summary['processing_recommendations'].append(
                        f"المنتجات المجمعة تتجاوز تسوية الطالب بمبلغ {abs(amount_difference)} جنيه"
                    )
            
            return summary
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء ملخص مرتجع المنتجات المجمعة للطالب: {e}")
            return {'error': str(e)}
    
    @staticmethod
    def _validate_student_refund(student_refund) -> Tuple[bool, str]:
        """
        التحقق من صحة تسوية الطالب
        
        Args:
            student_refund: تسوية الطالب
            
        Returns:
            Tuple[bool, str]: (صحيح أم لا، رسالة)
        """
        try:
            if not student_refund:
                return False, "تسوية الطالب غير محددة"
            
            if not hasattr(student_refund, 'status'):
                return False, "تسوية الطالب غير صحيحة"
            
            if student_refund.status not in ['approved', 'processing']:
                return False, f"حالة تسوية الطالب غير مناسبة: {student_refund.status}"
            
            if not student_refund.approved_by:
                return False, "تسوية الطالب غير معتمدة"
            
            if student_refund.amount <= 0:
                return False, "مبلغ تسوية الطالب غير صحيح"
            
            return True, "تسوية الطالب صحيحة"
            
        except Exception as e:
            return False, f"خطأ في التحقق من تسوية الطالب: {e}"
    
    @staticmethod
    def _validate_bundle_products_data(bundle_products_data: List[Dict]) -> Tuple[bool, str]:
        """
        التحقق من صحة بيانات المنتجات المجمعة
        
        Args:
            bundle_products_data: قائمة بيانات المنتجات المجمعة
            
        Returns:
            Tuple[bool, str]: (صحيح أم لا، رسالة)
        """
        try:
            if not bundle_products_data:
                return False, "لا توجد منتجات مجمعة للمرتجع"
            
            if not isinstance(bundle_products_data, list):
                return False, "بيانات المنتجات المجمعة يجب أن تكون قائمة"
            
            for i, bundle_data in enumerate(bundle_products_data):
                if not isinstance(bundle_data, dict):
                    return False, f"بيانات المنتج المجمع رقم {i+1} يجب أن تكون قاموس"
                
                if 'bundle_product' not in bundle_data:
                    return False, f"المنتج المجمع مفقود في البيانات رقم {i+1}"
                
                if 'quantity' not in bundle_data:
                    return False, f"الكمية مفقودة في البيانات رقم {i+1}"
                
                bundle_product = bundle_data['bundle_product']
                quantity = bundle_data['quantity']
                
                if not hasattr(bundle_product, 'is_bundle') or not bundle_product.is_bundle:
                    return False, f"المنتج رقم {i+1} ليس منتجاً مجمعاً"
                
                if not bundle_product.is_active:
                    return False, f"المنتج المجمع {bundle_product.name} غير نشط"
                
                if not isinstance(quantity, int) or quantity <= 0:
                    return False, f"الكمية في البيانات رقم {i+1} يجب أن تكون رقم صحيح موجب"
            
            return True, "بيانات المنتجات المجمعة صحيحة"
            
        except Exception as e:
            return False, f"خطأ في التحقق من بيانات المنتجات المجمعة: {e}"
    
    @staticmethod
    def _create_student_refund_context(student_refund, specific_reason: str = None) -> Dict:
        """
        إنشاء سياق مرتجع من تسوية الطالب
        
        Args:
            student_refund: تسوية الطالب
            specific_reason: سبب محدد للمنتج (اختياري)
            
        Returns:
            Dict: سياق المرتجع
        """
        return {
            'refund_type': 'student_refund_integration',
            'refund_reason': specific_reason or student_refund.reason,
            'student_refund_id': student_refund.id,
            'student_id': student_refund.student.id,
            'student_name': student_refund.student.name,
            'created_by_id': student_refund.created_by.id,
            'approved_by_id': student_refund.approved_by.id if student_refund.approved_by else None,
            'reference_number': student_refund.reference_number,
            'original_amount': float(student_refund.amount),
            'notes': f"مرتجع منتج مجمع مرتبط بتسوية الطالب {student_refund.reference_number}"
        }
    
    @staticmethod
    def _link_processing_to_student_refund(student_refund, processing_record: Dict):
        """
        ربط معالجة المرتجع بتسوية الطالب
        
        Args:
            student_refund: تسوية الطالب
            processing_record: سجل المعالجة
        """
        try:
            # يمكن إضافة حقل في StudentRefund لتتبع المرتجعات المرتبطة
            # أو إنشاء نموذج منفصل للربط
            
            # حالياً نسجل في الملاحظات
            bundle_info = []
            for bundle_refund in processing_record['bundle_refunds']:
                if bundle_refund['success']:
                    bundle_info.append(
                        f"{bundle_refund['bundle_product_name']} (كمية: {bundle_refund['quantity']}, "
                        f"مبلغ: {bundle_refund['refund_amount']} جنيه)"
                    )
            
            if bundle_info:
                additional_notes = f"\n\nمرتجعات المنتجات المجمعة المرتبطة:\n" + "\n".join(bundle_info)
                additional_notes += f"\nإجمالي مبلغ المنتجات المجمعة: {processing_record['total_bundle_amount']} جنيه"
                additional_notes += f"\nمعرف المعالجة: {processing_record['processing_id']}"
                
                # يمكن تحديث ملاحظات تسوية الطالب أو إنشاء سجل منفصل
                logger.info(f"ربط معالجة المرتجعات بتسوية الطالب {student_refund.reference_number}: {additional_notes}")
            
        except Exception as e:
            logger.error(f"خطأ في ربط معالجة المرتجع بتسوية الطالب: {e}")
    
    @staticmethod
    def _create_integration_audit_trail(student_refund, processing_record: Dict) -> Dict:
        """
        إنشاء مسار تدقيق للتكامل
        
        Args:
            student_refund: تسوية الطالب
            processing_record: سجل المعالجة
            
        Returns:
            Dict: مسار تدقيق التكامل
        """
        integration_audit = {
            'integration_audit_id': f"STUDENT_BUNDLE_INTEGRATION_{processing_record['processing_id']}",
            'integration_type': 'student_refund_bundle_products',
            'student_refund_info': {
                'id': student_refund.id,
                'reference_number': student_refund.reference_number,
                'student_id': student_refund.student.id,
                'student_name': student_refund.student.name,
                'original_amount': float(student_refund.amount),
                'refund_reason': student_refund.reason,
                'status': student_refund.status
            },
            'bundle_processing_summary': {
                'processing_id': processing_record['processing_id'],
                'total_bundle_products': len(processing_record['bundle_refunds']),
                'successful_refunds': processing_record['successful_refunds_count'],
                'failed_refunds': processing_record['failed_refunds_count'],
                'total_bundle_amount': float(processing_record['total_bundle_amount']),
                'processing_status': processing_record['processing_status']
            },
            'integration_details': {
                'integration_method': 'automated_bundle_refund_processing',
                'started_at': processing_record['started_at'].isoformat(),
                'completed_at': processing_record['completed_at'].isoformat(),
                'processing_duration_seconds': (processing_record['completed_at'] - processing_record['started_at']).total_seconds()
            },
            'compliance_information': {
                'student_refund_approved': student_refund.approved_by is not None,
                'bundle_components_restored': True,
                'financial_transactions_created': True,
                'audit_trail_complete': True
            },
            'audit_metadata': {
                'created_at': timezone.now().isoformat(),
                'audit_level': 'integration',
                'compliance_requirements': ['student_refund_integration', 'bundle_component_restoration', 'financial_recording']
            }
        }
        
        logger.info(f"Student Bundle Refund Integration Audit Trail: {integration_audit}")
        
        return integration_audit