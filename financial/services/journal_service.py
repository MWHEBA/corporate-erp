"""
خدمة إنشاء القيود المحاسبية للرسوم المدرسية
"""
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from decimal import Decimal
from typing import Optional
import logging

from ..models.chart_of_accounts import ChartOfAccounts
from ..models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod

# Import AccountingGateway for unified journal entry creation
from governance.services import AccountingGateway, JournalEntryLineData

logger = logging.getLogger(__name__)
User = get_user_model()


class JournalEntryService:
    """
    خدمة إنشاء القيود المحاسبية للرسوم المدرسية
    """
    
    # أكواد الحسابات المطلوبة للرسوم المدرسية (mapped to existing accounts in fixtures)
    SCHOOL_ACCOUNTS = {
        "tuition_revenue": "40100",      # إيرادات الرسوم الدراسية (pk 8)
        "bus_revenue": "40300",          # إيرادات رسوم الباص/النقل (pk 37)
        "activity_revenue": "40320",     # إيرادات الأنشطة (pk 44)
        "application_revenue": "40200",  # إيرادات رسوم التقديم (pk 9)
        "other_revenue": "40400",        # إيرادات أخرى (pk 35)
        "parents_receivable": "10300",   # مدينو أولياء الأمور (pk 3)
        "cash": "10100",                 # الخزنة (pk 1)
        "bank": "10200",                 # البنك (pk 2)
    }
    
    def create_student_fee_entry(self, student_fee) -> Optional[JournalEntry]:
        """
        إنشاء قيد محاسبي لرسوم طالب جديدة
        
        القيد:
        من حـ/ ذمم أولياء الأمور (مدين)
            إلى حـ/ إيرادات الرسوم (دائن)
        """
        try:
            with transaction.atomic():
                # الحصول على الحسابات المطلوبة
                accounts = self._get_school_accounts()
                if not accounts:
                    logger.error("لا يمكن العثور على الحسابات المحاسبية المطلوبة للرسوم")
                    return None
                
                # تحديد حساب الإيراد حسب نوع الرسوم
                revenue_account = self._get_revenue_account_for_fee_type(
                    student_fee.fee_type.category, accounts
                )
                
                # الحصول على حساب ولي الأمر
                parent_account = self._get_or_create_parent_account(
                    student_fee.student.parent
                )
                if not parent_account:
                    logger.error(f"فشل في الحصول على حساب ولي الأمر {student_fee.student.parent.name}")
                    return None
                
                # جلب التصنيف المالي من FeeType
                financial_category = student_fee.fee_type.financial_category if student_fee.fee_type else None
                
                # Prepare journal entry lines
                lines = [
                    JournalEntryLineData(
                        account_code=parent_account.code,
                        debit=student_fee.total_amount,
                        credit=Decimal("0.00"),
                        description=f"رسوم {student_fee.fee_type.name} - {student_fee.student.name}"
                    ),
                    JournalEntryLineData(
                        account_code=revenue_account.code,
                        debit=Decimal("0.00"),
                        credit=student_fee.total_amount,
                        description=f"إيرادات {student_fee.fee_type.name} - {student_fee.student.name}"
                    )
                ]
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                journal_entry = gateway.create_journal_entry(
                    source_module='students',
                    source_model='StudentFee',
                    source_id=student_fee.id,
                    lines=lines,
                    idempotency_key=f"JE:students:StudentFee:{student_fee.id}:create",
                    user=student_fee.created_by,
                    entry_type='automatic',
                    description=f"رسوم {student_fee.fee_type.name} للطالب {student_fee.student.name}",
                    reference=f"رسوم طالب - {student_fee.fee_type.name}",
                    date=student_fee.due_date,
                    financial_category=financial_category
                )
                
                logger.info(f"تم إنشاء قيد محاسبي للرسوم: {journal_entry.number}")
                return journal_entry
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء قيد الرسوم: {str(e)}")
            return None
    
    def create_payment_entry(self, fee_payment, user=None) -> Optional[JournalEntry]:
        """
        إنشاء قيد محاسبي لدفعة رسوم (alias للتوافق مع النظام)
        
        Args:
            fee_payment: سجل الدفعة
            user: المستخدم الذي يقوم بالعملية
            
        Returns:
            JournalEntry: القيد المحاسبي المنشأ
        """
        return self.create_fee_payment_entry(fee_payment)
    
    def create_payment_reversal_entry(self, fee_payment, reason: str, user=None) -> Optional[JournalEntry]:
        """
        إنشاء قيد محاسبي عكسي لإلغاء دفعة
        
        Args:
            fee_payment: سجل الدفعة المراد إلغاؤها
            reason: سبب الإلغاء
            user: المستخدم الذي يقوم بالعملية
            
        Returns:
            JournalEntry: القيد العكسي المنشأ
        """
        try:
            with transaction.atomic():
                # الحصول على الحسابات المطلوبة
                accounts = self._get_school_accounts()
                if not accounts:
                    logger.error("لا يمكن العثور على الحسابات المحاسبية المطلوبة للإلغاء")
                    return None
                
                # تحديد حساب الاستلام حسب طريقة الدفع
                receiving_account = self._get_receiving_account_for_payment_method(
                    fee_payment.payment_method, accounts
                )
                
                # الحصول على حساب ولي الأمر
                parent_account = self._get_or_create_parent_account(
                    fee_payment.student_fee.student.parent
                )
                if not parent_account:
                    logger.error(f"فشل في الحصول على حساب ولي الأمر {fee_payment.student_fee.student.parent.name}")
                    return None
                
                # Prepare journal entry lines
                lines = [
                    JournalEntryLineData(
                        account_code=parent_account.code,
                        debit=fee_payment.amount,
                        credit=Decimal("0.00"),
                        description=f"إلغاء دفعة - {reason}"
                    ),
                    JournalEntryLineData(
                        account_code=receiving_account.code,
                        debit=Decimal("0.00"),
                        credit=fee_payment.amount,
                        description=f"إلغاء استلام {fee_payment.get_payment_method_display()} - {reason}"
                    )
                ]
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                journal_entry = gateway.create_journal_entry(
                    source_module='students',
                    source_model='FeePayment',
                    source_id=fee_payment.id,
                    lines=lines,
                    idempotency_key=f"JE:students:FeePayment:{fee_payment.id}:reversal",
                    user=user or fee_payment.created_by,
                    entry_type='reversal',
                    description=f"إلغاء دفعة {fee_payment.student_fee.student.parent.name} - السبب: {reason}",
                    reference=f"إلغاء دفعة - {fee_payment.reference_number or 'نقدي'}",
                    date=timezone.now().date()
                )
                
                logger.info(f"تم إنشاء قيد عكسي للدفعة: {journal_entry.number}")
                return journal_entry
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء القيد العكسي: {str(e)}")
            return None
    
    def create_fee_refund_entry(self, fee_payment) -> Optional[JournalEntry]:
        """
        إنشاء قيد محاسبي لمرجع رسوم
        
        القيد:
        من حـ/ ذمم أولياء الأمور (مدين) - تقليل الذمة
            إلى حـ/ الصندوق/البنك (دائن) - إخراج النقدية
        """
        try:
            with transaction.atomic():
                # الحصول على الحسابات المطلوبة
                accounts = self._get_school_accounts()
                if not accounts:
                    logger.error("لا يمكن العثور على الحسابات المحاسبية المطلوبة للمرجعات")
                    return None
                
                # تحديد حساب الإخراج حسب طريقة المرجع
                refund_account = self._get_receiving_account_for_payment_method(
                    fee_payment.payment_method, accounts
                )
                
                # الحصول على حساب ولي الأمر
                parent_account = self._get_or_create_parent_account(
                    fee_payment.student_fee.student.parent
                )
                if not parent_account:
                    logger.error(f"فشل في الحصول على حساب ولي الأمر {fee_payment.student_fee.student.parent.name}")
                    return None
                
                # المبلغ الموجب للمرجع
                refund_amount = abs(fee_payment.amount)
                
                # Get financial category from fee type
                financial_category = fee_payment.student_fee.fee_type.financial_category if fee_payment.student_fee.fee_type else None
                financial_subcategory = fee_payment.student_fee.fee_type.financial_subcategory if fee_payment.student_fee.fee_type else None
                
                # Prepare journal entry lines
                lines = [
                    JournalEntryLineData(
                        account_code=parent_account.code,
                        debit=refund_amount,
                        credit=Decimal("0.00"),
                        description=f"مرجع رسوم {fee_payment.student_fee.fee_type.name} - {fee_payment.student_fee.student.name}"
                    ),
                    JournalEntryLineData(
                        account_code=refund_account.code,
                        debit=Decimal("0.00"),
                        credit=refund_amount,
                        description=f"مرجع {fee_payment.get_payment_method_display()} - {fee_payment.student_fee.student.name}"
                    )
                ]
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                journal_entry = gateway.create_journal_entry(
                    source_module='students',
                    source_model='FeePayment',
                    source_id=fee_payment.id,
                    lines=lines,
                    idempotency_key=f"JE:students:FeePayment:{fee_payment.id}:refund",
                    user=fee_payment.created_by,
                    entry_type='refund',
                    description=f"مرجع رسوم {fee_payment.student_fee.fee_type.name} للطالب {fee_payment.student_fee.student.name}",
                    reference=f"مرجع رسوم - {fee_payment.reference_number or 'نقدي'}",
                    date=fee_payment.payment_date,
                    financial_category=financial_category,
                    financial_subcategory=financial_subcategory
                )
                
                logger.info(f"تم إنشاء قيد محاسبي للمرجع: {journal_entry.number}")
                return journal_entry
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء قيد المرجع: {str(e)}")
            return None
    
    def create_fee_payment_entry(self, fee_payment) -> Optional[JournalEntry]:
        """
        إنشاء قيد محاسبي لدفعة رسوم
        
        القيد:
        من حـ/ الصندوق/البنك (مدين)
            إلى حـ/ ذمم أولياء الأمور (دائن)
        """
        try:
            # Check if journal entry already exists for this payment
            existing_entry = JournalEntry.objects.filter(
                source_module='students',
                source_model='FeePayment',
                source_id=fee_payment.id
            ).first()
            
            if existing_entry:
                logger.info(f"القيد المحاسبي موجود بالفعل للدفعة {fee_payment.id}: {existing_entry.number}")
                return existing_entry
            
            with transaction.atomic():
                # الحصول على الحسابات المطلوبة
                accounts = self._get_school_accounts()
                if not accounts:
                    logger.error("لا يمكن العثور على الحسابات المحاسبية المطلوبة للمدفوعات")
                    return None
                
                # تحديد حساب الاستلام حسب طريقة الدفع
                receiving_account = self._get_receiving_account_for_payment_method(
                    fee_payment.payment_method, accounts
                )
                
                # الحصول على حساب ولي الأمر
                parent_account = self._get_or_create_parent_account(
                    fee_payment.student_fee.student.parent
                )
                if not parent_account:
                    logger.error(f"فشل في الحصول على حساب ولي الأمر {fee_payment.student_fee.student.parent.name}")
                    return None
                
                # إنشاء وصف مفصل يتضمن المنتجات الإضافية
                description = self._create_detailed_payment_description(fee_payment)
                
                # جلب التصنيف المالي من FeeType
                financial_category = fee_payment.student_fee.fee_type.financial_category if fee_payment.student_fee.fee_type else None
                
                # إنشاء وصف مفصل لبنود القيد
                debit_description = self._create_debit_line_description(fee_payment)
                credit_description = self._create_credit_line_description(fee_payment)
                
                # Prepare journal entry lines
                lines = [
                    JournalEntryLineData(
                        account_code=receiving_account.code,
                        debit=fee_payment.amount,
                        credit=Decimal("0.00"),
                        description=debit_description
                    ),
                    JournalEntryLineData(
                        account_code=parent_account.code,
                        debit=Decimal("0.00"),
                        credit=fee_payment.amount,
                        description=credit_description
                    )
                ]
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                
                try:
                    journal_entry = gateway.create_journal_entry(
                        source_module='students',
                        source_model='FeePayment',
                        source_id=fee_payment.id,
                        lines=lines,
                        idempotency_key=f"JE:students:FeePayment:{fee_payment.id}:payment",
                        user=fee_payment.created_by,
                        entry_type='automatic',
                        description=description,
                        reference=f"دفعة رسوم - {fee_payment.reference_number or 'نقدي'}",
                        date=fee_payment.payment_date,
                        financial_category=financial_category
                    )
                    
                    logger.info(f"تم إنشاء قيد محاسبي للدفعة: {journal_entry.number}")
                    return journal_entry
                    
                except Exception as gateway_error:
                    # Check if it's an idempotency error - the entry might already exist
                    error_msg = str(gateway_error)
                    if 'IdempotencyError' in str(type(gateway_error).__name__) or 'already exists' in error_msg:
                        logger.warning(f"Idempotency conflict for payment {fee_payment.id}, checking for existing entry")
                        # Try to find the existing entry
                        existing = JournalEntry.objects.filter(
                            source_module='students',
                            source_model='FeePayment',
                            source_id=fee_payment.id
                        ).first()
                        if existing:
                            logger.info(f"Found existing journal entry: {existing.number}")
                            return existing
                        else:
                            # Idempotency record exists but journal entry doesn't
                            # This indicates a previous failure in AccountingGateway
                            logger.error(f"Idempotency record exists but journal entry not found for payment {fee_payment.id}")
                            # Return None - admin needs to investigate and clear orphaned idempotency records
                            return None
                    # Re-raise if it's not an idempotency error
                    raise
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء قيد الدفعة: {str(e)}", exc_info=True)
            return None
    
    def _create_detailed_payment_description(self, fee_payment) -> str:
        """
        إنشاء وصف مفصل للقيد المحاسبي يتضمن تفاصيل المنتجات الإضافية
        
        Args:
            fee_payment: سجل الدفعة
            
        Returns:
            str: الوصف المفصل للقيد
        """
        try:
            # الوصف الأساسي
            base_description = f"دفعة رسوم {fee_payment.student_fee.fee_type.name} للطالب {fee_payment.student_fee.student.name}"
            
            # البحث عن المنتجات المرتبطة بهذه الدفعة
            product_payments = fee_payment.product_payments.select_related(
                'product_request__product'
            ).all()
            
            if not product_payments.exists():
                return base_description
            
            # إضافة تفاصيل المنتجات
            products_details = []
            total_products_amount = Decimal('0')
            
            for product_payment in product_payments:
                product_request = product_payment.product_request
                product_name = product_request.product.name
                quantity = product_request.quantity
                unit_price = product_request.unit_price
                allocated_amount = product_payment.allocated_amount
                
                # تفاصيل المنتج
                product_detail = f"{product_name}"
                if quantity > 1:
                    product_detail += f" (الكمية: {quantity})"
                
                product_detail += f" - {allocated_amount} ج.م"
                products_details.append(product_detail)
                total_products_amount += allocated_amount
            
            # تجميع الوصف النهائي
            detailed_description = f"{base_description}"
            
            if products_details:
                detailed_description += f" | المنتجات المدفوعة: {', '.join(products_details)}"
                detailed_description += f" | إجمالي المنتجات: {total_products_amount} ج.م"
            
            # إضافة معلومات طريقة الدفع إذا كانت متوفرة
            if fee_payment.payment_method != 'cash':
                detailed_description += f" | طريقة الدفع: {fee_payment.get_payment_method_display()}"
            
            if fee_payment.reference_number:
                detailed_description += f" | المرجع: {fee_payment.reference_number}"
            
            return detailed_description
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء الوصف المفصل: {str(e)}")
            # العودة للوصف الأساسي في حالة الخطأ
            return f"دفعة رسوم {fee_payment.student_fee.fee_type.name} للطالب {fee_payment.student_fee.student.name}"
    
    def _create_debit_line_description(self, fee_payment) -> str:
        """
        إنشاء وصف مفصل لبند المدين (الصندوق/البنك)
        
        Args:
            fee_payment: سجل الدفعة
            
        Returns:
            str: وصف بند المدين
        """
        try:
            # الوصف الأساسي
            payment_method_display = fee_payment.get_payment_method_display()
            base_description = f"استلام {payment_method_display} من {fee_payment.student_fee.student.parent.name}"
            
            # إضافة تفاصيل المنتجات المدفوعة
            product_payments = fee_payment.product_payments.select_related(
                'product_request__product'
            ).all()
            
            if product_payments.exists():
                product_names = []
                for product_payment in product_payments:
                    product_name = product_payment.product_request.product.name
                    quantity = product_payment.product_request.quantity
                    
                    if quantity > 1:
                        product_names.append(f"{product_name} ({quantity})")
                    else:
                        product_names.append(product_name)
                
                if product_names:
                    base_description += f" | المنتجات: {', '.join(product_names)}"
            
            # إضافة رقم المرجع إذا كان متوفراً
            if fee_payment.reference_number:
                base_description += f" | رقم المرجع: {fee_payment.reference_number}"
            
            return base_description
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء وصف بند المدين: {str(e)}")
            return f"استلام {fee_payment.get_payment_method_display()} - {fee_payment.student_fee.student.name}"
    
    def _create_credit_line_description(self, fee_payment) -> str:
        """
        إنشاء وصف مفصل لبند الدائن (ذمم أولياء الأمور)
        
        Args:
            fee_payment: سجل الدفعة
            
        Returns:
            str: وصف بند الدائن
        """
        try:
            # الوصف الأساسي
            base_description = f"دفعة مالية -  {fee_payment.student_fee.student.parent.name}"
            
            # إضافة تفاصيل المنتجات المدفوعة
            product_payments = fee_payment.product_payments.select_related(
                'product_request__product'
            ).all()
            
            if product_payments.exists():
                # حساب إجمالي المنتجات وعددها
                total_products = product_payments.count()
                total_amount = sum(pp.allocated_amount for pp in product_payments)
                
                if total_products == 1:
                    # منتج واحد - اذكر اسمه
                    product_payment = product_payments.first()
                    product_name = product_payment.product_request.product.name
                    quantity = product_payment.product_request.quantity
                    
                    if quantity > 1:
                        base_description += f" | {product_name} ({quantity} قطعة)"
                    else:
                        base_description += f" | {product_name}"
                else:
                    # منتجات متعددة - اذكر العدد والإجمالي
                    base_description += f" | {total_products} منتجات بقيمة {total_amount} ج.م"
            
            # إضافة نوع الرسوم
            base_description += f" | {fee_payment.student_fee.fee_type.name}"
            
            return base_description
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء وصف بند الدائن: {str(e)}")
            return f"تخفيض ذمة {fee_payment.student_fee.student.parent.name} - {fee_payment.student_fee.fee_type.name}"
    
    def create_application_fee_entry(
        self,
        application,
        amount: Decimal,
        payment_method: str = 'cash',
        reference_number: str = '',
        payment_date = None,
        user: Optional[User] = None
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد محاسبي لرسوم التقديم
        
        القيد:
        من حـ/ الصندوق/البنك (مدين)
            إلى حـ/ إيرادات رسوم التقديم (دائن)
        """
        try:
            with transaction.atomic():
                # الحصول على الحسابات المطلوبة
                accounts = self._get_school_accounts()
                if not accounts:
                    logger.error("لا يمكن العثور على الحسابات المحاسبية المطلوبة لرسوم التقديم")
                    return None
                
                # تحديد حساب الاستلام حسب طريقة الدفع
                receiving_account = self._get_receiving_account_for_payment_method(
                    payment_method, accounts
                )
                
                # حساب إيرادات رسوم التقديم
                application_revenue_account = accounts.get('application_revenue')
                if not application_revenue_account:
                    logger.error("لا يمكن العثور على حساب إيرادات رسوم التقديم")
                    return None
                
                # تحديد تاريخ القيد
                if payment_date is None:
                    payment_date = timezone.now().date()
                
                # Prepare journal entry lines
                lines = [
                    JournalEntryLineData(
                        account_code=receiving_account.code,
                        debit=amount,
                        credit=Decimal("0.00"),
                        description=f"استلام رسوم تقديم {payment_method} - {application.student_name}"
                    ),
                    JournalEntryLineData(
                        account_code=application_revenue_account.code,
                        debit=Decimal("0.00"),
                        credit=amount,
                        description=f"إيرادات رسوم تقديم - {application.student_name}"
                    )
                ]
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                journal_entry = gateway.create_journal_entry(
                    source_module='students',
                    source_model='Application',
                    source_id=application.id,
                    lines=lines,
                    idempotency_key=f"JE:students:Application:{application.id}:fee",
                    user=user,
                    entry_type='automatic',
                    description=f"رسوم تقديم طلب {application.student_name} - ولي الأمر: {application.parent_name}",
                    reference=f"رسوم تقديم - {reference_number or 'نقدي'}",
                    date=payment_date
                )
                
                logger.info(f"تم إنشاء قيد محاسبي لرسوم التقديم: {journal_entry.number}")
                return journal_entry
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء قيد رسوم التقديم: {str(e)}")
            return None
    
    def create_fee_adjustment_entry(
        self, 
        student_fee, 
        old_amount: Decimal, 
        adjustment_reason: str = "",
        user: Optional[User] = None
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد تصحيحي لتعديل رسوم
        """
        try:
            with transaction.atomic():
                new_amount = student_fee.total_amount
                difference = new_amount - old_amount
                
                if difference == 0:
                    logger.info("لا توجد فروقات تتطلب قيد تصحيحي")
                    return None
                
                # الحصول على الحسابات المطلوبة
                accounts = self._get_school_accounts()
                if not accounts:
                    return None
                
                revenue_account = self._get_revenue_account_for_fee_type(
                    student_fee.fee_type.category, accounts
                )
                
                parent_account = self._get_or_create_parent_account(
                    student_fee.student.parent
                )
                if not parent_account:
                    return None
                
                # Prepare journal entry lines based on difference
                if difference > 0:  # زيادة في الرسوم
                    lines = [
                        JournalEntryLineData(
                            account_code=parent_account.code,
                            debit=difference,
                            credit=Decimal("0.00"),
                            description=f"زيادة رسوم - {adjustment_reason}"
                        ),
                        JournalEntryLineData(
                            account_code=revenue_account.code,
                            debit=Decimal("0.00"),
                            credit=difference,
                            description=f"زيادة إيرادات - {adjustment_reason}"
                        )
                    ]
                else:  # نقص في الرسوم
                    abs_diff = abs(difference)
                    lines = [
                        JournalEntryLineData(
                            account_code=parent_account.code,
                            debit=Decimal("0.00"),
                            credit=abs_diff,
                            description=f"تخفيض رسوم - {adjustment_reason}"
                        ),
                        JournalEntryLineData(
                            account_code=revenue_account.code,
                            debit=abs_diff,
                            credit=Decimal("0.00"),
                            description=f"تخفيض إيرادات - {adjustment_reason}"
                        )
                    ]
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                journal_entry = gateway.create_journal_entry(
                    source_module='students',
                    source_model='StudentFee',
                    source_id=student_fee.id,
                    lines=lines,
                    idempotency_key=f"JE:students:StudentFee:{student_fee.id}:adjustment:{timezone.now().timestamp()}",
                    user=user or student_fee.created_by,
                    entry_type='adjustment',
                    description=f"تصحيح رسوم {student_fee.student.name} - الفرق: {difference}",
                    reference=f"تصحيح رسوم - {student_fee.fee_type.name}",
                    date=timezone.now().date()
                )
                
                logger.info(f"تم إنشاء قيد تصحيحي للرسوم: {journal_entry.number}")
                return journal_entry
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء قيد التصحيح: {str(e)}")
            return None
    
    def _get_school_accounts(self) -> dict:
        """الحصول على الحسابات المطلوبة للرسوم المدرسية"""
        try:
            accounts = {}
            for account_key, code in self.SCHOOL_ACCOUNTS.items():
                account = ChartOfAccounts.objects.filter(
                    code=code, is_active=True
                ).first()
                if account:
                    accounts[account_key] = account
                else:
                    logger.warning(f"لا يمكن العثور على الحساب: {code}")
            
            return accounts if len(accounts) >= 4 else None
        except Exception as e:
            logger.error(f"خطأ في الحصول على حسابات الرسوم: {str(e)}")
            return None
    
    def _get_revenue_account_for_fee_type(self, fee_category: str, accounts: dict) -> ChartOfAccounts:
        """تحديد حساب الإيراد حسب نوع الرسوم"""
        revenue_mapping = {
            'tuition': 'tuition_revenue',
            'bus': 'bus_revenue',
            'summer': 'activity_revenue',
            'activity': 'activity_revenue',
            'application': 'application_revenue',
        }
        
        account_key = revenue_mapping.get(fee_category, 'other_revenue')
        return accounts.get(account_key, accounts.get('tuition_revenue'))
    
    def _get_receiving_account_for_payment_method(self, payment_method: str, accounts: dict) -> ChartOfAccounts:
        """تحديد حساب الاستلام حسب طريقة الدفع - النظام الجديد فقط"""
        # payment_method هو account code مباشرة (مثل 10100، 10200، 10500)
        try:
            account = ChartOfAccounts.objects.filter(
                code=payment_method,
                is_active=True
            ).first()
            
            if not account:
                raise ValueError(f"الحساب المحاسبي {payment_method} غير موجود أو غير نشط")
            
            return account
            
        except Exception as e:
            logger.error(f"فشل في الحصول على الحساب بالكود {payment_method}: {str(e)}")
            raise
    
    def _get_or_create_parent_account(self, parent) -> Optional[ChartOfAccounts]:
        """الحصول على حساب ولي الأمر أو إنشاؤه"""
        try:
            # التحقق من وجود حساب مرتبط
            if parent.financial_account and parent.financial_account.is_active:
                return parent.financial_account
            
            # إنشاء حساب جديد
            from financial.services.accounting_integration_service import AccountingIntegrationService
            return AccountingIntegrationService._create_parent_account(parent)
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على حساب ولي الأمر: {str(e)}")
            return None
    
    def _generate_journal_number(self, prefix: str, reference_id: int) -> str:
        """
        توليد رقم القيد مع دعم التسميات العربية الموحدة
        
        Args:
            prefix: بادئة القيد (مثل: تسليم-منتجات، رسوم-مكملة، رسوم-طالب)
            reference_id: معرف المرجع
            
        Returns:
            str: رقم القيد المُولد (مثل: تسليم-منتجات-0001)
        """
        # قاموس البادئات الإنجليزية (أرقام القيود يجب أن تكون بالإنجليزية فقط)
        prefix_mapping = {
            # البادئات العربية القديمة → البادئات الإنجليزية الجديدة
            "رسوم": "FEE",               # Fee (البادئة العامة للرسوم)
            "رسوم-طالب": "TF",           # Tuition Fee
            "دفع-رسوم": "PP",             # Parent Payment
            "استرداد-رسوم": "RF",         # Refund
            "عكس-رسوم": "RV",             # Reversal
            "تعديل-رسوم": "ADJ",          # Adjustment
            "رسوم-تقديم": "APP",          # Application Fee
            "تسليم-منتجات": "PD",         # Product Delivery
            "رسوم-مكملة": "CF",           # Complementary Fee
            "رسوم-تسليم": "DF",           # Delivery Fee
            # البادئات الإنجليزية (تبقى كما هي)
            "SALE": "SALE",
            "PURCHASE": "PURCH", 
            "RETURN": "RET",
            "PAYMENT": "PAY",
            "ADJ-SALE": "ADJ-SALE",
            "ADJ-PURCHASE": "ADJ-PURCH",
            "REV": "REV",
            "JE": "JE"
        }
        
        # استخدام البادئة المترجمة إذا كانت متوفرة
        normalized_prefix = prefix_mapping.get(prefix, prefix)
        
        # البحث عن أعلى رقم للبادئة المحددة
        existing_entries = JournalEntry.objects.filter(
            number__startswith=f"{normalized_prefix}-"
        ).order_by('-id')
        
        max_number = 0
        for entry in existing_entries:
            try:
                # استخراج الرقم من نهاية اسم القيد
                parts = entry.number.split("-")
                if len(parts) >= 2:
                    # أخذ آخر جزء كرقم
                    number_part = parts[-1]
                    current_number = int(number_part)
                    if current_number > max_number:
                        max_number = current_number
            except (ValueError, IndexError):
                continue
        
        new_number = max_number + 1
        return f"{normalized_prefix}-{new_number:04d}"
    
    def _get_accounting_period(self, date) -> Optional[AccountingPeriod]:
        """الحصول على الفترة المحاسبية للتاريخ"""
        try:
            return AccountingPeriod.get_period_for_date(date)
        except Exception:
            return None
    
    @classmethod
    def create_simple_entry(
        cls,
        date,
        debit_account: str,
        credit_account: str,
        amount: Decimal,
        description: str = "",
        reference: str = "",
        user: Optional[User] = None,
        financial_category=None,
        financial_subcategory=None,
        entry_type: str = "manual"
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد محاسبي بسيط (مدين واحد ودائن واحد)
        
        Args:
            date: تاريخ القيد
            debit_account: كود الحساب المدين
            credit_account: كود الحساب الدائن
            amount: المبلغ
            description: وصف القيد
            reference: مرجع القيد
            user: المستخدم المنشئ للقيد
            financial_category: التصنيف المالي الأساسي (اختياري)
            financial_subcategory: التصنيف الفرعي (اختياري)
            entry_type: نوع القيد (manual, cash_payment, cash_receipt, إلخ)
            
        Returns:
            JournalEntry: القيد المحاسبي المنشأ أو None في حالة الخطأ
        """
        try:
            with transaction.atomic():
                # الحصول على الحسابات
                debit_acc = ChartOfAccounts.objects.filter(
                    code=debit_account, is_active=True
                ).first()
                credit_acc = ChartOfAccounts.objects.filter(
                    code=credit_account, is_active=True
                ).first()
                
                if not debit_acc:
                    logger.error(f"لا يمكن العثور على الحساب المدين: {debit_account}")
                    return None
                    
                if not credit_acc:
                    logger.error(f"لا يمكن العثور على الحساب الدائن: {credit_account}")
                    return None
                
                # التعامل مع التصنيفات - لو تم تمرير FinancialSubcategory
                from financial.models import FinancialSubcategory
                if isinstance(financial_category, FinancialSubcategory):
                    # لو تم تمرير subcategory في مكان category، نصلحه
                    financial_subcategory = financial_category
                    financial_category = financial_subcategory.parent_category
                
                # Prepare journal entry lines
                lines = [
                    JournalEntryLineData(
                        account_code=debit_acc.code,
                        debit=amount,
                        credit=Decimal("0.00"),
                        description=description
                    ),
                    JournalEntryLineData(
                        account_code=credit_acc.code,
                        debit=Decimal("0.00"),
                        credit=amount,
                        description=description
                    )
                ]
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                
                # تحديد source_id و source_model الصحيح
                # لو في reference بيبدأ بـ ACT_EXP_ يبقى ده مصروف نشاط
                source_module_to_use = 'financial'
                source_model_to_use = 'ManualEntry'
                source_id_to_use = 0
                
                if reference and reference.startswith('ACT_EXP_'):
                    # استخراج الـ ID من الـ reference
                    try:
                        expense_id = int(reference.split('_')[-1])
                        source_module_to_use = 'activities'
                        source_model_to_use = 'ActivityExpense'
                        source_id_to_use = expense_id
                    except (ValueError, IndexError):
                        logger.warning(f"Could not parse expense_id from reference: {reference}")
                
                journal_entry = gateway.create_journal_entry(
                    source_module=source_module_to_use,
                    source_model=source_model_to_use,
                    source_id=source_id_to_use,
                    lines=lines,
                    idempotency_key=f"JE:{source_module_to_use}:{source_model_to_use}:{reference or timezone.now().timestamp()}:create",
                    user=user,
                    entry_type=entry_type,
                    description=description,
                    reference=reference,
                    date=date,
                    financial_category=financial_category,
                    financial_subcategory=financial_subcategory
                )
                
                if journal_entry:
                    logger.info(f"تم إنشاء قيد محاسبي بسيط: {journal_entry.number}")
                else:
                    logger.error("فشل في إنشاء القيد المحاسبي")
                
                return journal_entry
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء القيد البسيط: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    @classmethod
    def create_compound_entry(
        cls,
        date,
        lines: list,
        description: str = "",
        reference: str = "",
        user: Optional[User] = None,
        financial_category=None
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد محاسبي مركب (متعدد الخطوط)
        
        Args:
            date: تاريخ القيد
            lines: قائمة بخطوط القيد [{'account': 'code', 'debit': amount, 'credit': amount, 'description': 'desc'}]
            description: وصف القيد
            reference: مرجع القيد
            user: المستخدم المنشئ للقيد
            financial_category: التصنيف المالي (اختياري)
            
        Returns:
            JournalEntry: القيد المحاسبي المنشأ أو None في حالة الخطأ
        """
        try:
            with transaction.atomic():
                # التحقق من توازن القيد
                total_debit = sum(Decimal(str(line.get('debit', 0))) for line in lines)
                total_credit = sum(Decimal(str(line.get('credit', 0))) for line in lines)
                
                if total_debit != total_credit:
                    logger.error(f"القيد غير متوازن: مدين {total_debit} != دائن {total_credit}")
                    return None
                
                # Prepare journal entry lines
                prepared_lines = []
                for line in lines:
                    account = ChartOfAccounts.objects.filter(
                        code=line['account'], is_active=True
                    ).first()
                    
                    if not account:
                        logger.error(f"لا يمكن العثور على الحساب: {line['account']}")
                        raise Exception(f"حساب غير موجود: {line['account']}")
                    
                    prepared_lines.append(
                        JournalEntryLineData(
                            account_code=account.code,
                            debit=Decimal(str(line.get('debit', 0))),
                            credit=Decimal(str(line.get('credit', 0))),
                            description=line.get('description', description)
                        )
                    )
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                journal_entry = gateway.create_journal_entry(
                    source_module='financial',
                    source_model='CompoundEntry',
                    source_id=0,
                    lines=prepared_lines,
                    idempotency_key=f"JE:financial:CompoundEntry:{reference or timezone.now().timestamp()}:create",
                    user=user,
                    entry_type='manual',
                    description=description,
                    reference=reference,
                    date=date,
                    financial_category=financial_category
                )
                
                logger.info(f"تم إنشاء قيد محاسبي مركب: {journal_entry.number}")
                return journal_entry
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء القيد المركب: {str(e)}")
            return None
    
    @classmethod
    def post_entry(cls, journal_entry: JournalEntry) -> bool:
        """
        ترحيل القيد المحاسبي (تحديث أرصدة الحسابات)
        
        Args:
            journal_entry: القيد المراد ترحيله
            
        Returns:
            bool: True إذا تم الترحيل بنجاح، False في حالة الخطأ
        """
        try:
            with transaction.atomic():
                if journal_entry.status == 'posted':
                    logger.info(f"القيد {journal_entry.number} مرحل مسبقاً")
                    return True
                
                # ترحيل خطوط القيد
                for line in journal_entry.lines.all():
                    account = line.account
                    
                    # تحديث رصيد الحساب
                    if line.debit > 0:
                        account.balance += line.debit
                    if line.credit > 0:
                        account.balance -= line.credit
                    
                    account.save()
                
                # تحديث حالة القيد
                journal_entry.status = 'posted'
                journal_entry.save()
                
                logger.info(f"تم ترحيل القيد: {journal_entry.number}")
                return True
                
        except Exception as e:
            logger.error(f"خطأ في ترحيل القيد: {str(e)}")
            return False
    
    @staticmethod
    def _generate_journal_number_static(prefix: str, reference_id: int) -> str:
        """نسخة ثابتة من توليد رقم القيد"""
        # البحث عن أعلى رقم للبادئة المحددة
        existing_entries = JournalEntry.objects.filter(
            number__startswith=f"{prefix}-"
        ).order_by('-id')
        
        max_number = 0
        for entry in existing_entries:
            try:
                # استخراج الرقم من نهاية اسم القيد
                parts = entry.number.split("-")
                if len(parts) >= 2:
                    number_part = parts[1]
                    current_number = int(number_part)
                    if current_number > max_number:
                        max_number = current_number
            except (ValueError, IndexError):
                continue
        
        new_number = max_number + 1
        return f"{prefix}-{new_number:04d}"
    
    @staticmethod
    def _get_accounting_period_static(date) -> Optional[AccountingPeriod]:
        """نسخة ثابتة من الحصول على الفترة المحاسبية"""
        try:
            return AccountingPeriod.get_period_for_date(date)
        except Exception:
            return None

    @classmethod
    def setup_school_accounts(cls) -> bool:
        """إعداد الحسابات الأساسية للرسوم المدرسية"""
        try:
            with transaction.atomic():
                accounts_created = 0
                
                # بيانات الحسابات المطلوبة
                school_accounts_data = {
                    "41020": {
                        "name": "إيرادات الرسوم الدراسية",
                        "name_en": "Tuition Revenue",
                        "type": "revenue",
                        "description": "إيرادات من الرسوم الدراسية للطلاب",
                    },
                    "41021": {
                        "name": "إيرادات رسوم الباص",
                        "name_en": "Bus Fees Revenue",
                        "type": "revenue",
                        "description": "إيرادات من رسوم النقل المدرسي",
                    },
                    "41022": {
                        "name": "إيرادات الأنشطة",
                        "name_en": "Activities Revenue",
                        "type": "revenue",
                        "description": "إيرادات من الأنشطة والبرامج الصيفية",
                    },
                    "41023": {
                        "name": "إيرادات رسوم التقديم",
                        "name_en": "Application Fees Revenue",
                        "type": "revenue",
                        "description": "إيرادات من رسوم تقديم الطلبات",
                    },
                    "41029": {
                        "name": "إيرادات أخرى",
                        "name_en": "Other Revenue",
                        "type": "revenue",
                        "description": "إيرادات متنوعة أخرى",
                    },
                    "10301": {
                        "name": "ذمم أولياء الأمور",
                        "name_en": "Parents Receivable",
                        "type": "asset",
                        "description": "المبالغ المستحقة من أولياء الأمور",
                    },
                }
                
                for code, data in school_accounts_data.items():
                    if not ChartOfAccounts.objects.filter(code=code).exists():
                        # البحث عن الحساب الأب
                        parent_code = code[:3] + "0" if len(code) == 5 else code[:2] + "00"
                        parent_account = ChartOfAccounts.objects.filter(code=parent_code).first()
                        
                        ChartOfAccounts.objects.create(
                            code=code,
                            name=data["name"],
                            name_en=data.get("name_en"),
                            parent=parent_account,
                            account_type=data["type"],
                            is_leaf=True,
                            is_active=True,
                            description=data.get("description", ""),
                        )
                        accounts_created += 1
                
                logger.info(f"تم إنشاء {accounts_created} حساب محاسبي للرسوم المدرسية")
                return True
                
        except Exception as e:
            logger.error(f"خطأ في إعداد حسابات الرسوم المدرسية: {str(e)}")
            return False