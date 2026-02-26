"""
Sale Service - خدمة موحدة لإدارة المبيعات

هذه الخدمة تستخدم:
- AccountingGateway للقيود المحاسبية (مع الحوكمة الكاملة)
- MovementService لحركات المخزون (مع الحوكمة الكاملة)
- CustomerService للتعامل مع العملاء

الهدف: ضمان الالتزام الكامل بمعايير الحوكمة والتدقيق
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
import logging

from sale.models import Sale, SaleItem, SalePayment, SaleReturn, SaleReturnItem
from governance.services.accounting_gateway import AccountingGateway
from governance.services.movement_service import MovementService
from client.services.customer_service import CustomerService

User = get_user_model()
logger = logging.getLogger(__name__)


class SaleService:
    """
    خدمة موحدة لإدارة المبيعات مع الالتزام الكامل بالحوكمة
    """

    @staticmethod
    @transaction.atomic
    def create_sale(data, user):
        """
        إنشاء فاتورة مبيعات جديدة مع القيود المحاسبية وحركات المخزون
        
        Args:
            data: dict يحتوي على بيانات الفاتورة والبنود
            user: المستخدم الذي ينشئ الفاتورة
            
        Returns:
            Sale: الفاتورة المنشأة
            
        Raises:
            Exception: في حالة فشل أي عملية
        """
        try:
            # 1. إنشاء الفاتورة
            sale = Sale.objects.create(
                date=data.get('date', timezone.now().date()),
                customer_id=data['customer_id'],
                warehouse_id=data['warehouse_id'],
                payment_method=data.get('payment_method', 'credit'),
                subtotal=Decimal('0'),
                discount=Decimal(data.get('discount', 0)),
                tax=Decimal(data.get('tax', 0)),
                total=Decimal('0'),
                notes=data.get('notes', ''),
                status='confirmed',
                created_by=user
            )
            
            logger.info(f"✅ تم إنشاء فاتورة المبيعات: {sale.number}")
            
            # 2. إضافة البنود
            items_data = data.get('items', [])
            for item_data in items_data:
                SaleService._add_sale_item(sale, item_data, user)
            
            # 3. حساب الإجماليات
            sale.refresh_from_db()
            SaleService._calculate_totals(sale)
            
            # 4. إنشاء القيد المحاسبي عبر AccountingGateway
            journal_entry = SaleService._create_sale_journal_entry(sale, user)
            if journal_entry:
                sale.journal_entry = journal_entry
                sale.save(update_fields=['journal_entry'])
                logger.info(f"✅ تم ربط القيد المحاسبي: {journal_entry.number} بالفاتورة: {sale.number}")
            
            # 5. إنشاء حركات المخزون عبر MovementService
            SaleService._create_stock_movements(sale, user)
            
            logger.info(f"✅ تم إنشاء فاتورة المبيعات بنجاح: {sale.number}")
            return sale
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء فاتورة المبيعات: {str(e)}")
            raise

    @staticmethod
    def _add_sale_item(sale, item_data, user):
        """
        إضافة بند لفاتورة المبيعات
        """
        item = SaleItem.objects.create(
            sale=sale,
            product_id=item_data['product_id'],
            quantity=Decimal(item_data['quantity']),
            unit_price=Decimal(item_data['unit_price']),
            discount=Decimal(item_data.get('discount', 0)),
            total=Decimal(item_data['quantity']) * Decimal(item_data['unit_price']) - Decimal(item_data.get('discount', 0))
        )
        logger.info(f"✅ تم إضافة بند: {item.product.name} للفاتورة: {sale.number}")
        return item

    @staticmethod
    def _calculate_totals(sale):
        """
        حساب إجماليات الفاتورة
        """
        items = sale.items.all()
        subtotal = sum(item.total for item in items)
        
        sale.subtotal = subtotal
        sale.total = subtotal - sale.discount + sale.tax
        sale.save(update_fields=['subtotal', 'total'])
        
        logger.info(f"✅ تم حساب إجماليات الفاتورة: {sale.number} - الإجمالي: {sale.total}")

    @staticmethod
    def _create_sale_journal_entry(sale, user):
        """
        إنشاء القيد المحاسبي للفاتورة عبر AccountingGateway
        
        القيد:
        - مدين: العملاء (أو الخزينة/البنك إذا نقدي)
        - دائن: إيرادات المبيعات
        - مدين: تكلفة البضاعة المباعة
        - دائن: المخزون
        """
        try:
            from governance.services.accounting_gateway import JournalEntryLineData
            from financial.models import ChartOfAccounts
            
            # تحديد حساب المدين حسب طريقة الدفع
            if sale.payment_method == 'cash':
                debit_account = ChartOfAccounts.objects.get(code='10100')  # الخزينة
            elif sale.payment_method == 'bank_transfer':
                debit_account = ChartOfAccounts.objects.get(code='10200')  # البنك
            else:  # credit
                # حساب العميل - التأكد من وجود الحساب المحاسبي
                if not sale.customer.financial_account:
                    # استدعاء الـ signal لإنشاء الحساب (Single Source of Truth)
                    logger.warning(
                        f"العميل '{sale.customer.name}' ليس لديه حساب محاسبي. "
                        f"سيتم إنشاؤه تلقائياً عبر signal."
                    )
                    sale.customer.save()  # Trigger post_save signal
                    sale.customer.refresh_from_db()
                    
                    # التحقق من نجاح الإنشاء
                    if not sale.customer.financial_account:
                        raise ValidationError(
                            f"فشل إنشاء حساب محاسبي للعميل '{sale.customer.name}'. "
                            f"يرجى التواصل مع الدعم الفني."
                        )
                
                debit_account = sale.customer.financial_account
            
            # حساب تكلفة البضاعة المباعة
            cost_of_goods_sold = sum(
                item.product.cost_price * item.quantity 
                for item in sale.items.all()
            )
            
            # الحصول على الحسابات
            sales_revenue_account = ChartOfAccounts.objects.get(code='40100')  # إيرادات المبيعات
            cogs_account = ChartOfAccounts.objects.get(code='50100')  # تكلفة البضاعة المباعة
            inventory_account = ChartOfAccounts.objects.get(code='10300')  # المخزون
            
            # إعداد بيانات القيد باستخدام JournalEntryLineData
            lines = [
                # مدين: العملاء/الخزينة/البنك
                JournalEntryLineData(
                    account_code=debit_account.code,
                    debit=sale.total,
                    credit=Decimal('0'),
                    description=f'مبيعات - فاتورة {sale.number}'
                ),
                # دائن: إيرادات المبيعات
                JournalEntryLineData(
                    account_code=sales_revenue_account.code,
                    debit=Decimal('0'),
                    credit=sale.total,
                    description=f'مبيعات - فاتورة {sale.number}'
                ),
                # مدين: تكلفة البضاعة المباعة
                JournalEntryLineData(
                    account_code=cogs_account.code,
                    debit=cost_of_goods_sold,
                    credit=Decimal('0'),
                    description=f'تكلفة مبيعات - فاتورة {sale.number}'
                ),
                # دائن: المخزون
                JournalEntryLineData(
                    account_code=inventory_account.code,
                    debit=Decimal('0'),
                    credit=cost_of_goods_sold,
                    description=f'تكلفة مبيعات - فاتورة {sale.number}'
                )
            ]
            
            # إنشاء القيد عبر AccountingGateway (مع الحوكمة الكاملة)
            gateway = AccountingGateway()
            journal_entry = gateway.create_journal_entry(
                source_module='sale',
                source_model='Sale',
                source_id=sale.id,
                lines=lines,
                idempotency_key=f'sale_{sale.id}_journal_entry',
                user=user,
                entry_type='automatic',
                description=f'فاتورة مبيعات رقم {sale.number} - {sale.customer.name}',
                reference=sale.number,
                date=sale.date
            )
            
            logger.info(f"✅ تم إنشاء القيد المحاسبي: {journal_entry.number} للفاتورة: {sale.number}")
            return journal_entry
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء القيد المحاسبي للفاتورة {sale.number}: {str(e)}")
            raise

    @staticmethod
    def _create_stock_movements(sale, user):
        """
        إنشاء حركات المخزون للفاتورة عبر MovementService
        """
        try:
            movement_service = MovementService()
            
            for item in sale.items.all():
                # إنشاء الحركة عبر MovementService (مع الحوكمة الكاملة)
                movement = movement_service.process_movement(
                    product_id=item.product.id,
                    quantity_change=-item.quantity,  # Negative for outbound
                    movement_type='out',
                    source_reference=f"SALE-{sale.number}-ITEM-{item.id}",
                    idempotency_key=f'sale_{sale.id}_item_{item.id}_movement',
                    user=user,
                    unit_cost=item.product.cost_price,
                    document_number=sale.number,
                    notes=f'مبيعات - فاتورة رقم {sale.number}',
                    movement_date=sale.date
                )
                
                logger.info(f"✅ تم إنشاء حركة مخزون: {movement.id} للبند: {item.product.name}")
                
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء حركات المخزون للفاتورة {sale.number}: {str(e)}")
            raise

    @staticmethod
    @transaction.atomic
    def process_payment(sale, payment_data, user):
        """
        معالجة دفعة على فاتورة مبيعات
        
        Args:
            sale: الفاتورة
            payment_data: بيانات الدفعة
            user: المستخدم
            
        Returns:
            SalePayment: الدفعة المنشأة
        """
        try:
            # 1. إنشاء الدفعة
            payment = SalePayment.objects.create(
                sale=sale,
                amount=Decimal(payment_data['amount']),
                payment_method=payment_data.get('payment_method', 'cash'),
                payment_date=payment_data.get('payment_date', timezone.now().date()),
                notes=payment_data.get('notes', ''),
                status='draft',
                created_by=user
            )
            
            logger.info(f"✅ تم إنشاء دفعة: {payment.id} للفاتورة: {sale.number}")
            
            # 2. إنشاء القيد المحاسبي للدفعة عبر AccountingGateway
            journal_entry = SaleService._create_payment_journal_entry(payment, user)
            if journal_entry:
                payment.financial_transaction = journal_entry
                payment.status = 'posted'
                payment.save(update_fields=['financial_transaction', 'status'])
                logger.info(f"✅ تم ترحيل الدفعة: {payment.id}")
            
            # 3. تحديث حالة الدفع للفاتورة
            sale.update_payment_status()
            
            return payment
            
        except Exception as e:
            logger.error(f"❌ خطأ في معالجة الدفعة للفاتورة {sale.number}: {str(e)}")
            raise

    @staticmethod
    def _create_payment_journal_entry(payment, user):
        """
        إنشاء القيد المحاسبي للدفعة عبر AccountingGateway
        
        القيد:
        - مدين: الخزينة/البنك
        - دائن: العملاء
        """
        try:
            from governance.services.accounting_gateway import JournalEntryLineData
            
            # تحديد حساب المدين حسب طريقة الدفع
            # payment_method هنا ممكن يكون account code (مثل '10100') أو قيمة قديمة (مثل 'cash')
            payment_method = payment.payment_method
            
            if payment_method == 'cash' or payment_method == '10100':
                debit_account_code = '10100'  # الخزينة
            elif payment_method == 'bank_transfer' or payment_method == '10200':
                debit_account_code = '10200'  # البنك
            elif payment_method and payment_method.isdigit():
                # إذا كان account code مباشرة
                debit_account_code = payment_method
            else:
                debit_account_code = '10100'  # افتراضي: الخزينة
            
            # حساب العميل - التأكد من وجود الحساب المحاسبي
            if not payment.sale.customer.financial_account:
                # استدعاء الـ signal لإنشاء الحساب (Single Source of Truth)
                logger.warning(
                    f"العميل '{payment.sale.customer.name}' ليس لديه حساب محاسبي. "
                    f"سيتم إنشاؤه تلقائياً عبر signal."
                )
                payment.sale.customer.save()  # Trigger post_save signal
                payment.sale.customer.refresh_from_db()
                
                # التحقق من نجاح الإنشاء
                if not payment.sale.customer.financial_account:
                    raise ValidationError(
                        f"فشل إنشاء حساب محاسبي للعميل '{payment.sale.customer.name}'. "
                        f"يرجى التواصل مع الدعم الفني."
                    )
            
            credit_account_code = payment.sale.customer.financial_account.code
            
            # إعداد بيانات القيد باستخدام JournalEntryLineData
            lines = [
                # مدين: الخزينة/البنك
                JournalEntryLineData(
                    account_code=debit_account_code,
                    debit=payment.amount,
                    credit=Decimal('0'),
                    description=f'دفعة - فاتورة {payment.sale.number}'
                ),
                # دائن: العملاء
                JournalEntryLineData(
                    account_code=credit_account_code,
                    debit=Decimal('0'),
                    credit=payment.amount,
                    description=f'دفعة - فاتورة {payment.sale.number}'
                )
            ]
            
            # إنشاء القيد عبر AccountingGateway
            gateway = AccountingGateway()
            journal_entry = gateway.create_journal_entry(
                source_module='sale',
                source_model='SalePayment',
                source_id=payment.id,
                lines=lines,
                idempotency_key=f'sale_payment_{payment.id}_journal_entry',
                user=user,
                entry_type='automatic',
                description=f'دفعة على فاتورة {payment.sale.number} - {payment.sale.customer.name}',
                reference=f'PAY-{payment.sale.number}',
                date=payment.payment_date
            )
            
            logger.info(f"✅ تم إنشاء القيد المحاسبي: {journal_entry.number} للدفعة: {payment.id}")
            return journal_entry
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء القيد المحاسبي للدفعة {payment.id}: {str(e)}")
            raise

    @staticmethod
    @transaction.atomic
    def create_return(sale, return_data, user):
        """
        إنشاء مرتجع مبيعات
        
        Args:
            sale: الفاتورة الأصلية
            return_data: بيانات المرتجع
            user: المستخدم
            
        Returns:
            SaleReturn: المرتجع المنشأ
        """
        try:
            # 1. إنشاء المرتجع
            sale_return = SaleReturn.objects.create(
                sale=sale,
                date=return_data.get('return_date', timezone.now().date()),
                warehouse=sale.warehouse,
                subtotal=Decimal('0'),
                discount=Decimal('0'),
                tax=Decimal('0'),
                total=Decimal('0'),
                status='confirmed',
                notes=return_data.get('notes', ''),
                created_by=user
            )
            
            logger.info(f"✅ تم إنشاء مرتجع: {sale_return.number} للفاتورة: {sale.number}")
            
            # 2. إضافة بنود المرتجع
            items_data = return_data.get('items', [])
            for item_data in items_data:
                SaleService._add_return_item(sale_return, item_data, user)
            
            # 3. حساب الإجمالي
            sale_return.refresh_from_db()
            total = sum(item.total for item in sale_return.items.all())
            sale_return.total = total
            sale_return.subtotal = total
            sale_return.save(update_fields=['total', 'subtotal'])
            
            # 4. إنشاء القيد المحاسبي للمرتجع
            journal_entry = SaleService._create_return_journal_entry(sale_return, user)
            if journal_entry:
                sale_return.journal_entry = journal_entry
                sale_return.save(update_fields=['journal_entry'])
            
            # 5. إنشاء حركات المخزون (إرجاع)
            SaleService._create_return_stock_movements(sale_return, user)
            
            # 6. تحديث حالة الدفع للفاتورة
            sale.update_payment_status()
            
            logger.info(f"✅ تم إنشاء المرتجع بنجاح: {sale_return.number}")
            return sale_return
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء المرتجع للفاتورة {sale.number}: {str(e)}")
            raise

    @staticmethod
    def _add_return_item(sale_return, item_data, user):
        """
        إضافة بند للمرتجع
        """
        from sale.models import SaleItem
        
        sale_item = SaleItem.objects.get(id=item_data['sale_item_id'])
        
        item = SaleReturnItem.objects.create(
            sale_return=sale_return,
            sale_item=sale_item,
            product=sale_item.product,
            quantity=Decimal(item_data['quantity']),
            unit_price=Decimal(item_data['unit_price']),
            discount=Decimal(item_data.get('discount', 0)),
            total=Decimal(item_data['quantity']) * Decimal(item_data['unit_price']) - Decimal(item_data.get('discount', 0)),
            reason=item_data.get('reason', 'مرتجع')
        )
        logger.info(f"✅ تم إضافة بند مرتجع: {item.product.name}")
        return item

    @staticmethod
    def _create_return_journal_entry(sale_return, user):
        """
        إنشاء القيد المحاسبي للمرتجع (عكس قيد المبيعات)
        """
        try:
            from governance.services.accounting_gateway import JournalEntryLineData
            from financial.models import ChartOfAccounts
            
            sale = sale_return.sale
            
            # تحديد حساب الدائن حسب طريقة الدفع الأصلية
            if sale.payment_method == 'cash':
                credit_account_code = '10100'
            elif sale.payment_method == 'bank_transfer':
                credit_account_code = '10200'
            else:
                # حساب العميل - التأكد من وجود الحساب المحاسبي
                if not sale.customer.financial_account:
                    # استدعاء الـ signal لإنشاء الحساب (Single Source of Truth)
                    logger.warning(
                        f"العميل '{sale.customer.name}' ليس لديه حساب محاسبي. "
                        f"سيتم إنشاؤه تلقائياً عبر signal."
                    )
                    sale.customer.save()  # Trigger post_save signal
                    sale.customer.refresh_from_db()
                    
                    # التحقق من نجاح الإنشاء
                    if not sale.customer.financial_account:
                        raise ValidationError(
                            f"فشل إنشاء حساب محاسبي للعميل '{sale.customer.name}'. "
                            f"يرجى التواصل مع الدعم الفني."
                        )
                
                if sale.customer.financial_account:
                    credit_account_code = sale.customer.financial_account.code
                else:
                    credit_account_code = '11030'  # حساب العملاء الرئيسي
                    logger.warning(f"استخدام حساب العملاء الرئيسي للعميل {sale.customer.name}")
            
            # حساب تكلفة البضاعة المرتجعة
            cost_of_goods_returned = sum(
                item.product.cost_price * item.quantity
                for item in sale_return.items.all()
            )
            
            # إعداد بيانات القيد باستخدام JournalEntryLineData
            lines = [
                # مدين: إيرادات المبيعات (عكس)
                JournalEntryLineData(
                    account_code='40100',
                    debit=sale_return.total,
                    credit=Decimal('0'),
                    description=f'مرتجع - فاتورة {sale.number}'
                ),
                # دائن: العملاء/الخزينة/البنك (عكس)
                JournalEntryLineData(
                    account_code=credit_account_code,
                    debit=Decimal('0'),
                    credit=sale_return.total,
                    description=f'مرتجع - فاتورة {sale.number}'
                ),
                # مدين: المخزون (إرجاع)
                JournalEntryLineData(
                    account_code='10300',
                    debit=cost_of_goods_returned,
                    credit=Decimal('0'),
                    description=f'مرتجع - فاتورة {sale.number}'
                ),
                # دائن: تكلفة البضاعة المباعة (عكس)
                JournalEntryLineData(
                    account_code='50100',
                    debit=Decimal('0'),
                    credit=cost_of_goods_returned,
                    description=f'مرتجع - فاتورة {sale.number}'
                )
            ]
            
            # إنشاء القيد عبر AccountingGateway
            gateway = AccountingGateway()
            journal_entry = gateway.create_journal_entry(
                source_module='sale',
                source_model='SaleReturn',
                source_id=sale_return.id,
                lines=lines,
                idempotency_key=f'sale_return_{sale_return.id}_journal_entry',
                user=user,
                entry_type='automatic',
                description=f'مرتجع مبيعات رقم {sale_return.number} - فاتورة {sale.number}',
                reference=sale_return.number,
                date=sale_return.date
            )
            
            logger.info(f"✅ تم إنشاء القيد المحاسبي: {journal_entry.number} للمرتجع: {sale_return.number}")
            return journal_entry
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء القيد المحاسبي للمرتجع {sale_return.number}: {str(e)}")
            raise

    @staticmethod
    def _create_return_stock_movements(sale_return, user):
        """
        إنشاء حركات المخزون للمرتجع (إرجاع للمخزن)
        """
        try:
            movement_service = MovementService()
            
            for item in sale_return.items.all():
                # إنشاء الحركة عبر MovementService (مع الحوكمة الكاملة)
                movement = movement_service.process_movement(
                    product_id=item.product.id,
                    quantity_change=item.quantity,  # Positive for inbound
                    movement_type='in',
                    source_reference=f"RETURN-{sale_return.number}-ITEM-{item.id}",
                    idempotency_key=f'sale_return_{sale_return.id}_item_{item.id}_movement',
                    user=user,
                    unit_cost=item.product.cost_price,
                    document_number=sale_return.number,
                    notes=f'مرتجع مبيعات - فاتورة {sale_return.sale.number}',
                    movement_date=sale_return.date
                )
                
                logger.info(f"✅ تم إنشاء حركة مخزون (إرجاع): {movement.id}")
                
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء حركات المخزون للمرتجع {sale_return.number}: {str(e)}")
            raise

    @staticmethod
    @transaction.atomic
    def delete_sale(sale, user):
        """
        حذف فاتورة مبيعات مع التراجع عن جميع العمليات
        
        Args:
            sale: الفاتورة المراد حذفها
            user: المستخدم
        """
        try:
            # 1. حذف القيد المحاسبي
            if sale.journal_entry:
                try:
                    # فك قفل القيد وتغيير الحالة قبل الحذف
                    journal_entry = sale.journal_entry
                    journal_entry.is_locked = False
                    journal_entry.status = 'draft'  # تغيير الحالة من posted إلى draft
                    journal_entry.save(update_fields=['is_locked', 'status'])
                    journal_entry.delete()
                    logger.info(f"✅ تم حذف القيد المحاسبي للفاتورة: {sale.number}")
                except Exception as e:
                    logger.warning(f"فشل حذف القيد المحاسبي: {str(e)}")
            
            # 2. حذف حركات المخزون
            from product.models import StockMovement
            movements = StockMovement.objects.filter(
                reference_number__contains=f'SALE-{sale.number}'
            )
            movements_count = movements.count()
            movements.delete()
            
            if movements_count > 0:
                logger.info(f"✅ تم حذف {movements_count} حركة مخزون للفاتورة: {sale.number}")
            
            # 3. تحديث رصيد العميل
            if sale.payment_method == 'credit':
                customer = sale.customer
                customer.balance -= sale.total
                customer.save(update_fields=['balance'])
                logger.info(f"✅ تم تحديث رصيد العميل: {customer.name}")
            
            # 4. حذف الفاتورة
            sale_number = sale.number
            sale.delete()
            
            logger.info(f"✅ تم حذف الفاتورة بنجاح: {sale_number}")
            
        except Exception as e:
            logger.error(f"❌ خطأ في حذف الفاتورة {sale.number}: {str(e)}")
            raise
            
            # 3. تحديث رصيد العميل
            if sale.payment_method == 'credit':
                customer = sale.customer
                customer.balance -= sale.total
                customer.save(update_fields=['balance'])
                logger.info(f"✅ تم تحديث رصيد العميل: {customer.name}")
            
            # 4. حذف الفاتورة
            sale_number = sale.number
            sale.delete()
            
            logger.info(f"✅ تم حذف الفاتورة بنجاح: {sale_number}")
            
        except Exception as e:
            logger.error(f"❌ خطأ في حذف الفاتورة {sale.number}: {str(e)}")
            raise

    @staticmethod
    def get_sale_statistics(sale):
        """
        الحصول على إحصائيات الفاتورة
        """
        return {
            'total': sale.total,
            'amount_paid': sale.amount_paid,
            'amount_due': sale.amount_due,
            'is_fully_paid': sale.is_fully_paid,
            'payment_status': sale.get_payment_status_display(),
            'items_count': sale.items.count(),
            'returns_count': sale.returns.filter(status='confirmed').count(),
            'is_returned': sale.is_returned,
            'return_status': sale.return_status,
        }
