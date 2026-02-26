"""
خدمة التكامل المحاسبي الشاملة
ربط المبيعات والمشتريات بالنظام المحاسبي الجديد
"""
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from datetime import date
import logging

from ..models.chart_of_accounts import ChartOfAccounts, AccountType
from ..models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod
from ..services.account_helper import AccountHelperService

# Import AccountingGateway for unified journal entry creation
from governance.services import AccountingGateway, JournalEntryLineData

logger = logging.getLogger(__name__)
User = get_user_model()


class AccountingIntegrationService:
    """
    خدمة التكامل المحاسبي الشاملة
    """

    # أكواد الحسابات الأساسية المطلوبة (حسب دليل الحسابات المعتمد)
    DEFAULT_ACCOUNTS = {
        "sales_revenue": "40100",  # إيرادات الرسوم الدراسية
        "cost_of_goods_sold": "50100",  # تكلفة الخدمات المقدمة
        "inventory": "10400",  # المخزون
        "accounts_receivable": "10300",  # مدينو أولياء الأمور
        "accounts_payable": "20100",  # الموردون
        "cash": "10100",  # الخزنة
        "bank": "10200",  # البنك
        "purchase_expense": "50100",  # تكلفة الخدمات المقدمة
    }

    @classmethod
    def create_sale_journal_entry(
        cls, sale, user: Optional[User] = None
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيود محاسبية منفصلة لفاتورة مبيعات حسب تصنيف المنتجات
        """
        try:
            with transaction.atomic():
                # الحصول على الحسابات المطلوبة
                accounts = cls._get_required_accounts_for_sale()
                if not accounts:
                    logger.error(
                        "لا يمكن العثور على الحسابات المحاسبية المطلوبة للمبيعات"
                    )
                    return None

                # تجميع بنود الفاتورة حسب التصنيف
                items_by_category = cls._group_sale_items_by_category(sale)
                
                if not items_by_category:
                    logger.warning(f"لا توجد بنود في الفاتورة {sale.number}")
                    return None

                # الحصول على معلومات العميل/ولي الأمر
                client_account, client_name = cls._get_client_info(sale, user)
                if not client_account:
                    return None

                created_entries = []
                
                # إنشاء قيد منفصل لكل تصنيف
                for category_name, category_items in items_by_category.items():
                    category_total = sum(item.total for item in category_items)
                    category_cost = sum(cls._get_item_cost(item) for item in category_items)
                    
                    # Prepare journal entry lines
                    lines = [
                        JournalEntryLineData(
                            account_code=client_account.code,
                            debit=category_total,
                            credit=Decimal("0.00"),
                            description=f"مبيعات {category_name} - {client_name} - فاتورة {sale.number}"
                        )
                    ]
                    
                    # قيد الإيرادات (دائن)
                    revenue_account = cls._get_category_revenue_account(category_name) or accounts["sales_revenue"]
                    lines.append(
                        JournalEntryLineData(
                            account_code=revenue_account.code,
                            debit=Decimal("0.00"),
                            credit=category_total,
                            description=f"إيرادات {category_name} - فاتورة {sale.number}"
                        )
                    )
                    
                    # قيد تكلفة البضاعة المباعة (إذا كانت متاحة)
                    if category_cost > 0:
                        lines.append(
                            JournalEntryLineData(
                                account_code=accounts["cost_of_goods_sold"].code,
                                debit=category_cost,
                                credit=Decimal("0.00"),
                                description=f"تكلفة {category_name} المباعة - فاتورة {sale.number}"
                            )
                        )
                        lines.append(
                            JournalEntryLineData(
                                account_code=accounts["inventory"].code,
                                debit=Decimal("0.00"),
                                credit=category_cost,
                                description=f"تخفيض مخزون {category_name} - فاتورة {sale.number}"
                            )
                        )
                    
                    # Create journal entry via AccountingGateway
                    gateway = AccountingGateway()
                    journal_entry = gateway.create_journal_entry(
                        source_module='sales',
                        source_model='Sale',
                        source_id=sale.id,
                        lines=lines,
                        idempotency_key=f"JE:sales:Sale:{sale.id}:{category_name[:3].upper()}:create",
                        user=user or sale.created_by,
                        entry_type='automatic',
                        description=f"مبيعات {category_name} لـ {client_name}",
                        reference=f"فاتورة مبيعات رقم {sale.number} - {category_name}",
                        date=sale.date
                    )

                    created_entries.append(journal_entry)
                    logger.info(f"تم إنشاء قيد محاسبي لـ {category_name}: {journal_entry.number}")

                # ربط أول قيد بالفاتورة (للمرجعية)
                if created_entries:
                    sale.journal_entry = created_entries[0]
                    sale.save(update_fields=["journal_entry"])

                logger.info(f"تم إنشاء {len(created_entries)} قيد محاسبي للمبيعات - فاتورة {sale.number}")
                return created_entries[0] if created_entries else None

        except Exception as e:
            logger.error(f"خطأ في إنشاء قيود المبيعات: {str(e)}")
            return None

    @classmethod
    def create_purchase_journal_entry(
        cls, purchase, user: Optional[User] = None
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد محاسبي لفاتورة مشتريات
        """
        try:
            with transaction.atomic():
                # الحصول على الحسابات المطلوبة
                accounts = cls._get_required_accounts_for_purchase()
                if not accounts:
                    logger.error(
                        "لا يمكن العثور على الحسابات المحاسبية المطلوبة للمشتريات"
                    )
                    return None

                # بناء وصف تفصيلي يتضمن المنتجات/الخدمات
                purchase_items = purchase.items.all()
                if purchase_items.exists():
                    # جمع أسماء المنتجات/الخدمات (أول 3 عناصر)
                    items_list = []
                    for item in purchase_items[:3]:
                        items_list.append(f"{item.product.name}")
                    
                    items_text = ", ".join(items_list)
                    if purchase_items.count() > 3:
                        items_text += f" وعناصر أخرى ({purchase_items.count() - 3})"
                    
                    description = f"مشتريات من \"{purchase.supplier.name}\" - {items_text}"
                else:
                    description = f"مشتريات من المورد {purchase.supplier.name}"
                
                # Prepare journal entry lines
                lines = []
                
                # قيد المخزون أو المصروفات (مدين)
                if purchase.is_service and purchase.financial_category:
                    expense_account = purchase.financial_category.default_expense_account
                    if not expense_account:
                        logger.error(
                            f"التصنيف المالي {purchase.financial_category.name} "
                            f"ليس له حساب مصروفات افتراضي"
                        )
                        return None
                    
                    lines.append(
                        JournalEntryLineData(
                            account_code=expense_account.code,
                            debit=purchase.total,
                            credit=Decimal("0.00"),
                            description=f"مصروفات {purchase.service_type_display} - فاتورة {purchase.number}"
                        )
                    )
                else:
                    # للمنتجات: استخدام حساب المخزون
                    lines.append(
                        JournalEntryLineData(
                            account_code=accounts["inventory"].code,
                            debit=purchase.total,
                            credit=Decimal("0.00"),
                            description=f"مشتريات مخزون - فاتورة {purchase.number}"
                        )
                    )

                # قيد المورد (دائن)
                supplier_account = cls._get_supplier_account(purchase.supplier)
                if not supplier_account:
                    logger.warning(f"⚠️ المورد {purchase.supplier.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                    supplier_account = cls._create_supplier_account(purchase.supplier, user or purchase.created_by)
                    
                    if not supplier_account:
                        error_msg = f"❌ فشل إنشاء حساب محاسبي للمورد {purchase.supplier.name}. يجب إنشاء حساب محاسبي للمورد أولاً."
                        logger.error(error_msg)
                        raise ValueError(error_msg)
                
                # بناء وصف تفصيلي لبند القيد
                if purchase_items.exists():
                    items_list = []
                    for item in purchase_items[:3]:
                        items_list.append(f"{item.product.name}")
                    
                    items_text = ", ".join(items_list)
                    if purchase_items.count() > 3:
                        items_text += f" وعناصر أخرى ({purchase_items.count() - 3})"
                    
                    line_description = f"مشتريات من \"{purchase.supplier.name}\" - {items_text}"
                else:
                    line_description = f"مشتريات - المورد {purchase.supplier.name} - فاتورة {purchase.number}"
                
                lines.append(
                    JournalEntryLineData(
                        account_code=supplier_account.code,
                        debit=Decimal("0.00"),
                        credit=purchase.total,
                        description=line_description
                    )
                )
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                journal_entry = gateway.create_journal_entry(
                    source_module='purchases',
                    source_model='Purchase',
                    source_id=purchase.id,
                    lines=lines,
                    idempotency_key=f"JE:purchases:Purchase:{purchase.id}:create",
                    user=user or purchase.created_by,
                    entry_type='automatic',
                    description=description,
                    reference=f"فاتورة مشتريات رقم {purchase.number}",
                    date=purchase.date
                )

                # ربط القيد بالفاتورة
                purchase.journal_entry = journal_entry
                purchase.save(update_fields=["journal_entry"])

                logger.info(f"تم إنشاء قيد محاسبي للمشتريات: {journal_entry.number}")
                return journal_entry

        except Exception as e:
            logger.error(f"خطأ في إنشاء قيد المشتريات: {str(e)}")
            return None

    @classmethod
    def create_return_journal_entry(
        cls, sale_return, user: Optional[User] = None
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد محاسبي لمرتجع مبيعات
        
        القيد المطلوب:
        من حـ/ إيرادات المبيعات (مدين)
            إلى حـ/ العملاء (دائن)
        
        من حـ/ المخزون (مدين)
            إلى حـ/ تكلفة البضاعة المباعة (دائن)
        """
        try:
            with transaction.atomic():
                # الحصول على الحسابات المطلوبة
                accounts = cls._get_required_accounts_for_sale()
                if not accounts:
                    logger.error("لا يمكن العثور على الحسابات المحاسبية المطلوبة للمرتجعات")
                    return None

                # حساب إجمالي المرتجع والتكلفة
                total_return = Decimal("0.00")
                total_cost = Decimal("0.00")
                
                for item in sale_return.items.all():
                    total_return += item.total
                    if hasattr(item.sale_item.product, "cost_price") and item.sale_item.product.cost_price:
                        total_cost += item.sale_item.product.cost_price * item.quantity

                # Prepare journal entry lines
                lines = []
                
                # قيد عكس الإيراد (مدين إيرادات)
                lines.append(
                    JournalEntryLineData(
                        account_code=accounts["sales_revenue"].code,
                        debit=total_return,
                        credit=Decimal("0.00"),
                        description=f"عكس إيرادات - مرتجع {sale_return.number}"
                    )
                )

                # استخدام حساب العميل/ولي الأمر المحدد
                client_account = None
                client_name = sale_return.sale.client_name
                
                if sale_return.sale.parent:
                    client_account = cls._get_parent_account(sale_return.sale.parent)
                    if not client_account:
                        logger.warning(f"⚠️ ولي الأمر {sale_return.sale.parent.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                        client_account = cls._create_parent_account(sale_return.sale.parent, user or sale_return.created_by)
                        if not client_account:
                            error_msg = f"❌ فشل إنشاء حساب محاسبي لولي الأمر {sale_return.sale.parent.name}. يجب إنشاء حساب محاسبي لولي الأمر أولاً."
                            logger.error(error_msg)
                            raise ValueError(error_msg)
                elif sale_return.sale.customer:
                    client_account = cls._get_customer_account(sale_return.sale.customer)
                    if not client_account:
                        logger.warning(f"⚠️ العميل {sale_return.sale.customer.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                        client_account = cls._create_customer_account(sale_return.sale.customer, user or sale_return.created_by)
                        if not client_account:
                            error_msg = f"❌ فشل إنشاء حساب محاسبي للعميل {sale_return.sale.customer.name}. يجب إنشاء حساب محاسبي للعميل أولاً."
                            logger.error(error_msg)
                            raise ValueError(error_msg)
                else:
                    error_msg = "❌ الفاتورة لا تحتوي على ولي أمر أو عميل"
                    logger.error(error_msg)
                    raise ValueError(error_msg)

                lines.append(
                    JournalEntryLineData(
                        account_code=client_account.code,
                        debit=Decimal("0.00"),
                        credit=total_return,
                        description=f"تخفيض ذمم {client_name} - مرتجع {sale_return.number}"
                    )
                )

                # قيد إرجاع المخزون (مدين مخزون، دائن تكلفة)
                if total_cost > 0:
                    lines.append(
                        JournalEntryLineData(
                            account_code=accounts["inventory"].code,
                            debit=total_cost,
                            credit=Decimal("0.00"),
                            description=f"إرجاع مخزون - مرتجع {sale_return.number}"
                        )
                    )
                    lines.append(
                        JournalEntryLineData(
                            account_code=accounts["cost_of_goods_sold"].code,
                            debit=Decimal("0.00"),
                            credit=total_cost,
                            description=f"عكس تكلفة البضاعة - مرتجع {sale_return.number}"
                        )
                    )
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                journal_entry = gateway.create_journal_entry(
                    source_module='sales',
                    source_model='SaleReturn',
                    source_id=sale_return.id,
                    lines=lines,
                    idempotency_key=f"JE:sales:SaleReturn:{sale_return.id}:create",
                    user=user or sale_return.created_by,
                    entry_type='automatic',
                    description=f"مرتجع من {sale_return.sale.client_name}",
                    reference=f"مرتجع مبيعات رقم {sale_return.number} - فاتورة {sale_return.sale.number}",
                    date=sale_return.date
                )

                # ربط القيد بالمرتجع
                sale_return.journal_entry = journal_entry
                sale_return.save(update_fields=["journal_entry"])

                logger.info(f"✅ تم إنشاء قيد محاسبي للمرتجع: {journal_entry.number}")
                return journal_entry

        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء قيد المرتجع: {str(e)}")
            return None

    @classmethod
    def create_payment_journal_entry(
        cls,
        payment,
        payment_type: str,  # 'sale_payment' or 'purchase_payment'
        user: Optional[User] = None,
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد محاسبي للمدفوعات
        """
        try:
            with transaction.atomic():
                accounts = cls._get_required_accounts_for_payment()
                if not accounts:
                    return None

                # تحديد نوع القيد
                if payment_type == "sale_payment":
                    # دفعة من عميل/ولي أمر
                    client_name = payment.sale.client_name
                    reference = f"دفعة من العميل - فاتورة {payment.sale.number}"
                    description = f"استلام دفعة من {client_name}"

                    # النظام الجديد: payment_method هو account code مباشرة
                    payment_method = payment.payment_method
                    try:
                        from financial.models import ChartOfAccounts
                        account_debit = ChartOfAccounts.objects.filter(
                            code=payment_method,
                            is_active=True
                        ).first()
                        
                        if not account_debit:
                            raise ValueError(f"الحساب المحاسبي {payment_method} غير موجود أو غير نشط")
                            
                    except Exception as e:
                        logger.error(f"فشل في الحصول على حساب الدفع {payment_method}: {str(e)}")
                        raise
                    
                    # دائن حساب العميل/ولي الأمر المحدد
                    client_account = None
                    
                    if payment.sale.parent:
                        # استخدام ولي الأمر (النظام الجديد)
                        client_account = cls._get_parent_account(payment.sale.parent)
                        
                        if not client_account:
                            # إنشاء حساب جديد لولي الأمر تلقائياً
                            logger.warning(f"⚠️ ولي الأمر {payment.sale.parent.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                            client_account = cls._create_parent_account(payment.sale.parent, user or payment.created_by)
                            
                            if not client_account:
                                # فشل إنشاء الحساب - إيقاف العملية
                                error_msg = f"❌ فشل إنشاء حساب محاسبي لولي الأمر {payment.sale.parent.name}. يجب إنشاء حساب محاسبي لولي الأمر أولاً."
                                logger.error(error_msg)
                                raise ValueError(error_msg)
                                
                    elif payment.sale.customer:
                        # استخدام العميل (النظام القديم - للتوافق المؤقت)
                        client_account = cls._get_customer_account(payment.sale.customer)
                        
                        if not client_account:
                            # إنشاء حساب جديد للعميل تلقائياً
                            logger.warning(f"⚠️ العميل {payment.sale.customer.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                            client_account = cls._create_customer_account(payment.sale.customer, user or payment.created_by)
                            
                            if not client_account:
                                # فشل إنشاء الحساب - إيقاف العملية
                                error_msg = f"❌ فشل إنشاء حساب محاسبي للعميل {payment.sale.customer.name}. يجب إنشاء حساب محاسبي للعميل أولاً."
                                logger.error(error_msg)
                                raise ValueError(error_msg)
                    else:
                        error_msg = "❌ الفاتورة لا تحتوي على ولي أمر أو عميل"
                        logger.error(error_msg)
                        raise ValueError(error_msg)
                    
                    account_credit = client_account

                # DEPRECATED: fee_payment type is no longer supported
                # This was part of the school management system
                elif payment_type == "fee_payment":
                    raise ValueError("fee_payment type is deprecated. Use client invoices instead.")

                elif payment_type == "purchase_payment":
                    # دفعة لمورد
                    # المرجع يبقى بسيط مع رقم الفاتورة
                    reference = f"دفعة للمورد - فاتورة {payment.purchase.number}"
                    
                    # الوصف يكون تفصيلي مع المنتجات/الخدمات
                    purchase_items = payment.purchase.items.all()
                    if purchase_items.exists():
                        # جمع أسماء المنتجات/الخدمات (أول 3 عناصر)
                        items_list = []
                        for item in purchase_items[:3]:
                            items_list.append(f"{item.product.name}")
                        
                        items_text = "، ".join(items_list)
                        if purchase_items.count() > 3:
                            items_text += f" وعناصر أخرى ({purchase_items.count() - 3})"
                        
                        description = f"دفع لـ \"{payment.purchase.supplier.name}\" مقابل {items_text}"
                    else:
                        description = f"دفع للمورد {payment.purchase.supplier.name}"

                    # مدين حساب المورد المحدد
                    supplier_account = cls._get_supplier_account(payment.purchase.supplier)
                    if not supplier_account:
                        # إنشاء حساب جديد للمورد تلقائياً
                        logger.warning(f"⚠️ المورد {payment.purchase.supplier.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                        supplier_account = cls._create_supplier_account(payment.purchase.supplier, user or payment.created_by)
                        
                        if not supplier_account:
                            # فشل إنشاء الحساب - إيقاف العملية
                            error_msg = f"❌ فشل إنشاء حساب محاسبي للمورد {payment.purchase.supplier.name}. يجب إنشاء حساب محاسبي للمورد أولاً."
                            logger.error(error_msg)
                            raise ValueError(error_msg)
                    
                    account_debit = supplier_account
                    
                    # النظام الجديد: payment_method هو account code مباشرة
                    payment_method = payment.payment_method
                    try:
                        from financial.models import ChartOfAccounts
                        account_credit = ChartOfAccounts.objects.filter(
                            code=payment_method,
                            is_active=True
                        ).first()
                        
                        if not account_credit:
                            raise ValueError(f"الحساب المحاسبي {payment_method} غير موجود أو غير نشط")
                            
                    except Exception as e:
                        logger.error(f"فشل في الحصول على حساب الدفع {payment_method}: {str(e)}")
                        raise

                else:
                    logger.error(f"نوع دفعة غير معروف: {payment_type}")
                    return None

                # تحديد نوع القيد الصحيح
                entry_type = "automatic"  # افتراضي
                
                if payment_type == "sale_payment":
                    entry_type = "parent_payment"
                elif payment_type == "fee_payment":
                    entry_type = "parent_payment"
                elif payment_type == "purchase_payment":
                    entry_type = "supplier_payment"

                # Prepare journal entry lines
                lines = [
                    JournalEntryLineData(
                        account_code=account_debit.code,
                        debit=payment.amount,
                        credit=Decimal("0.00"),
                        description=description
                    ),
                    JournalEntryLineData(
                        account_code=account_credit.code,
                        debit=Decimal("0.00"),
                        credit=payment.amount,
                        description=description
                    )
                ]
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                journal_entry = gateway.create_journal_entry(
                    source_module='sales' if payment_type in ['sale_payment', 'fee_payment'] else 'purchases',
                    source_model='Payment',
                    source_id=payment.id,
                    lines=lines,
                    idempotency_key=f"JE:payment:{payment_type}:{payment.id}:create",
                    user=user or payment.created_by,
                    entry_type=entry_type,
                    description=description,
                    reference=reference,
                    date=payment.payment_date
                )

                # ربط القيد بالدفعة
                payment.journal_entry = journal_entry
                payment.save(update_fields=["journal_entry"])

                logger.info(f"✅ تم إنشاء قيد محاسبي للدفعة: {journal_entry.number}")
                return journal_entry

        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء قيد الدفعة: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    # ==================== Helper Methods ====================

    @classmethod
    def _get_required_accounts_for_sale(cls) -> Optional[Dict[str, ChartOfAccounts]]:
        """الحصول على الحسابات المطلوبة لقيود المبيعات"""
        try:
            accounts = {}
            for key, code in cls.DEFAULT_ACCOUNTS.items():
                if key in ["sales_revenue", "cost_of_goods_sold", "inventory", "accounts_receivable"]:
                    account = ChartOfAccounts.objects.filter(code=code, is_active=True).first()
                    if not account:
                        logger.error(f"الحساب {key} ({code}) غير موجود أو غير نشط")
                        return None
                    accounts[key] = account
            return accounts
        except Exception as e:
            logger.error(f"خطأ في الحصول على حسابات المبيعات: {str(e)}")
            return None

    @classmethod
    def _get_required_accounts_for_purchase(cls) -> Optional[Dict[str, ChartOfAccounts]]:
        """الحصول على الحسابات المطلوبة لقيود المشتريات"""
        try:
            accounts = {}
            for key, code in cls.DEFAULT_ACCOUNTS.items():
                if key in ["inventory", "accounts_payable", "purchase_expense"]:
                    account = ChartOfAccounts.objects.filter(code=code, is_active=True).first()
                    if not account:
                        logger.error(f"الحساب {key} ({code}) غير موجود أو غير نشط")
                        return None
                    accounts[key] = account
            return accounts
        except Exception as e:
            logger.error(f"خطأ في الحصول على حسابات المشتريات: {str(e)}")
            return None

    @classmethod
    def _get_required_accounts_for_payment(cls) -> Optional[Dict[str, ChartOfAccounts]]:
        """الحصول على الحسابات المطلوبة لقيود الدفعات"""
        try:
            accounts = {}
            for key, code in cls.DEFAULT_ACCOUNTS.items():
                if key in ["cash", "bank", "accounts_receivable", "accounts_payable"]:
                    account = ChartOfAccounts.objects.filter(code=code, is_active=True).first()
                    if not account:
                        logger.error(f"الحساب {key} ({code}) غير موجود أو غير نشط")
                        return None
                    accounts[key] = account
            return accounts
        except Exception as e:
            logger.error(f"خطأ في الحصول على حسابات الدفعات: {str(e)}")
            return None

    @classmethod
    def _group_sale_items_by_category(cls, sale) -> Dict[str, List]:
        """تجميع بنود الفاتورة حسب التصنيف"""
        items_by_category = {}
        for item in sale.items.all():
            category_name = item.product.category.name if item.product.category else "غير مصنف"
            if category_name not in items_by_category:
                items_by_category[category_name] = []
            items_by_category[category_name].append(item)
        return items_by_category

    @classmethod
    def _get_item_cost(cls, item) -> Decimal:
        """الحصول على تكلفة البند"""
        if hasattr(item.product, "cost_price") and item.product.cost_price:
            return item.product.cost_price * item.quantity
        return Decimal("0.00")

    @classmethod
    def _get_category_revenue_account(cls, category_name: str) -> Optional[ChartOfAccounts]:
        """الحصول على حساب الإيرادات الخاص بالتصنيف"""
        try:
            # يمكن تخصيص هذه الدالة لربط كل تصنيف بحساب إيرادات محدد
            # حالياً نستخدم حساب الإيرادات الافتراضي
            return None
        except Exception as e:
            logger.error(f"خطأ في الحصول على حساب إيرادات التصنيف: {str(e)}")
            return None

    @classmethod
    def _get_client_info(cls, sale, user: Optional[User] = None) -> Tuple[Optional[ChartOfAccounts], str]:
        """الحصول على معلومات العميل/ولي الأمر"""
        try:
            client_account = None
            client_name = sale.client_name
            
            if sale.parent:
                client_account = cls._get_parent_account(sale.parent)
                if not client_account:
                    logger.warning(f"⚠️ ولي الأمر {sale.parent.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                    client_account = cls._create_parent_account(sale.parent, user or sale.created_by)
                    if not client_account:
                        error_msg = f"❌ فشل إنشاء حساب محاسبي لولي الأمر {sale.parent.name}"
                        logger.error(error_msg)
                        return None, client_name
            elif sale.customer:
                client_account = cls._get_customer_account(sale.customer)
                if not client_account:
                    logger.warning(f"⚠️ العميل {sale.customer.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                    client_account = cls._create_customer_account(sale.customer, user or sale.created_by)
                    if not client_account:
                        error_msg = f"❌ فشل إنشاء حساب محاسبي للعميل {sale.customer.name}"
                        logger.error(error_msg)
                        return None, client_name
            else:
                error_msg = "❌ الفاتورة لا تحتوي على ولي أمر أو عميل"
                logger.error(error_msg)
                return None, client_name
            
            return client_account, client_name
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على معلومات العميل: {str(e)}")
            return None, ""

    @classmethod
    def _calculate_sale_cost(cls, sale) -> Decimal:
        """حساب تكلفة فاتورة المبيعات"""
        total_cost = Decimal("0.00")
        for item in sale.items.all():
            total_cost += cls._get_item_cost(item)
        return total_cost

    @classmethod
    def _get_accounting_period(cls, date: date) -> Optional[AccountingPeriod]:
        """الحصول على الفترة المحاسبية للتاريخ المحدد"""
        try:
            return AccountingPeriod.objects.filter(
                start_date__lte=date,
                end_date__gte=date,
                is_active=True
            ).first()
        except Exception as e:
            logger.error(f"خطأ في الحصول على الفترة المحاسبية: {str(e)}")
            return None

    @classmethod
    def _generate_journal_number(cls, prefix: str, original_number: str) -> str:
        """توليد رقم قيد جديد"""
        try:
            timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
            return f"{prefix}-{original_number}-{timestamp}"
        except Exception as e:
            logger.error(f"خطأ في توليد رقم القيد: {str(e)}")
            return f"{prefix}-{original_number}"

    # ==================== Account Methods ====================

    @classmethod
    def _get_parent_account(cls, parent) -> Optional[ChartOfAccounts]:
        """الحصول على حساب ولي الأمر المحدد"""
        try:
            # أولاً: محاولة استخدام الحساب المالي المحدد لولي الأمر
            if parent.financial_account and parent.financial_account.is_active:
                logger.info(f"✅ استخدام حساب ولي الأمر المحدد: {parent.financial_account.code} - {parent.financial_account.name}")
                return parent.financial_account
            
            # ثانياً: البحث عن حساب فرعي لولي الأمر في شجرة الحسابات
            parent_sub_accounts = ChartOfAccounts.objects.filter(
                name__icontains=parent.name,
                is_active=True,
                is_leaf=True,  # حساب نهائي
                parent__code__startswith="103"  # تحت مجموعة أولياء الأمور
            )
            
            if parent_sub_accounts.exists():
                account = parent_sub_accounts.first()
                logger.info(f"✅ وُجد حساب فرعي لولي الأمر: {account.code} - {account.name}")
                return account
            
            # ثالثاً: إرجاع None للإنشاء التلقائي
            logger.warning(f"⚠️ لم يتم العثور على حساب محدد لولي الأمر {parent.name}")
            return None
            
        except Exception as e:
            logger.error(f"❌ خطأ في الحصول على حساب ولي الأمر: {e}")
            return None

    @classmethod
    def _get_supplier_account(cls, supplier) -> Optional[ChartOfAccounts]:
        """الحصول على حساب المورد المحدد"""
        try:
            # أولاً: محاولة استخدام الحساب المالي المحدد للمورد
            if supplier.financial_account and supplier.financial_account.is_active:
                logger.info(f"✅ استخدام حساب المورد المحدد: {supplier.financial_account.code} - {supplier.financial_account.name}")
                return supplier.financial_account
            
            # ثانياً: البحث عن حساب فرعي للمورد في شجرة الحسابات
            supplier_sub_accounts = ChartOfAccounts.objects.filter(
                name__icontains=supplier.name,
                is_active=True,
                is_leaf=True,  # حساب نهائي
                parent__code__startswith="201"  # تحت مجموعة الموردين
            )
            
            if supplier_sub_accounts.exists():
                account = supplier_sub_accounts.first()
                logger.info(f"✅ وُجد حساب فرعي للمورد: {account.code} - {account.name}")
                return account
            
            # ثالثاً: إرجاع None للإنشاء التلقائي
            logger.warning(f"⚠️ لم يتم العثور على حساب محدد للمورد {supplier.name}")
            return None
            
        except Exception as e:
            logger.error(f"❌ خطأ في الحصول على حساب المورد: {e}")
            return None

    @classmethod
    def _get_customer_account(cls, customer) -> Optional[ChartOfAccounts]:
        """الحصول على حساب العميل المحدد"""
        try:
            # أولاً: محاولة استخدام الحساب المالي المحدد للعميل
            if customer.financial_account and customer.financial_account.is_active:
                logger.info(f"✅ استخدام حساب العميل المحدد: {customer.financial_account.code} - {customer.financial_account.name}")
                return customer.financial_account
            
            # ثانياً: البحث عن حساب فرعي للعميل في شجرة الحسابات
            customer_sub_accounts = ChartOfAccounts.objects.filter(
                name__icontains=customer.name,
                is_active=True,
                is_leaf=True,  # حساب نهائي
                parent__code__startswith="103"  # تحت مجموعة العملاء
            )
            
            if customer_sub_accounts.exists():
                account = customer_sub_accounts.first()
                logger.info(f"✅ وُجد حساب فرعي للعميل: {account.code} - {account.name}")
                return account
            
            # ثالثاً: إرجاع None للإنشاء التلقائي
            logger.warning(f"⚠️ لم يتم العثور على حساب محدد للعميل {customer.name}")
            return None
            
        except Exception as e:
            logger.error(f"❌ خطأ في الحصول على حساب العميل: {e}")
            return None

    @classmethod
    def _create_parent_account(cls, parent, user: Optional[User] = None) -> Optional[ChartOfAccounts]:
        """
        إنشاء حساب محاسبي جديد لولي الأمر تلقائياً
        """
        try:
            # التحقق من أن ولي الأمر لا يملك حساب بالفعل
            if parent.financial_account:
                logger.warning(f"⚠️ ولي الأمر {parent.name} مربوط بالفعل بحساب محاسبي {parent.financial_account.code}")
                return parent.financial_account
            
            # البحث عن حساب العملاء/أولياء الأمور الرئيسي (10300) أو إنشاؤه
            parents_account = ChartOfAccounts.objects.filter(code="10300").first()
            
            if not parents_account:
                # محاولة إنشاء الحساب الأساسي
                try:
                    asset_type, _ = AccountType.objects.get_or_create(
                        category="asset",
                        defaults={
                            'code': 'ASSET',
                            'name': 'أصول',
                            'nature': 'debit',
                            'is_active': True
                        }
                    )
                    parents_account = ChartOfAccounts.objects.create(
                        code="10300",
                        name="أولياء الأمور",
                        account_type=asset_type,  # أصول (مدينون)
                        is_active=True,
                        is_leaf=False,  # حساب أساسي يحتوي على حسابات فرعية
                        description="الحساب الأساسي لجميع أولياء الأمور",
                        created_by=user
                    )
                    logger.info("✅ تم إنشاء الحساب الأساسي لأولياء الأمور (10300)")
                except Exception as e:
                    logger.error(f"❌ فشل في إنشاء الحساب الأساسي لأولياء الأمور: {e}")
                    return None
            
            # إنشاء كود فريد للحساب الجديد
            # البحث عن آخر حساب فرعي تحت حساب العملاء/أولياء الأمور
            # النمط المتوقع: 10300001, 10300002, 10300003...
            last_parent_account = ChartOfAccounts.objects.filter(
                parent=parents_account,
                code__regex=r'^10300\d{3}$'  # يبدأ بـ 10300 ويتبعه 3 أرقام بالضبط
            ).order_by('-code').first()
            
            if last_parent_account:
                # استخراج الرقم التسلسلي من آخر 3 أرقام
                try:
                    last_number = int(last_parent_account.code[-3:])
                    new_number = last_number + 1
                except (ValueError, IndexError):
                    new_number = 1
            else:
                new_number = 1
            
            # تكوين الكود الجديد: 10300 + رقم تسلسلي من 3 أرقام
            new_code = f"10300{new_number:03d}"
            
            # إنشاء اسم مناسب للحساب
            account_name = f"ولي أمر - {parent.name}"
            
            # إنشاء الحساب الجديد
            new_account = ChartOfAccounts.objects.create(
                code=new_code,
                name=account_name,
                parent=parents_account,
                account_type=parents_account.account_type,
                is_active=True,
                is_leaf=True,
                description=f"حساب محاسبي لولي الأمر: {parent.name} (الرقم القومي: {parent.national_id})",
                created_by=user
            )
            
            # ربط ولي الأمر بالحساب الجديد
            parent.financial_account = new_account
            parent.save(update_fields=['financial_account'])
            
            logger.info(f"✅ تم إنشاء حساب جديد لولي الأمر: {new_account.code} - {new_account.name}")
            return new_account
            
        except Exception as e:
            logger.error(f"❌ فشل في إنشاء حساب جديد لولي الأمر {parent.name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    @classmethod
    def _create_customer_account(cls, customer, user: Optional[User] = None) -> Optional[ChartOfAccounts]:
        """
        إنشاء حساب محاسبي جديد للعميل تلقائياً
        """
        try:
            # التحقق من أن العميل لا يملك حساب بالفعل
            if customer.financial_account:
                logger.warning(f"⚠️ العميل {customer.name} مربوط بالفعل بحساب محاسبي {customer.financial_account.code}")
                return customer.financial_account
            
            # البحث عن حساب العملاء الرئيسي (10300)
            customers_account = ChartOfAccounts.objects.filter(code="10300").first()
            
            if not customers_account:
                logger.error("❌ لا يمكن العثور على حساب أولياء الأمور الرئيسي (10300) في النظام")
                return None
            
            # إنشاء كود فريد للحساب الجديد
            # البحث عن آخر حساب فرعي تحت حساب العملاء
            # النمط المتوقع: 10300001, 10300002, 10300003...
            last_customer_account = ChartOfAccounts.objects.filter(
                parent=customers_account,
                code__regex=r'^10300\d{3}$'  # يبدأ بـ 10300 ويتبعه 3 أرقام
            ).order_by('-code').first()
            
            if last_customer_account:
                # استخراج الرقم التسلسلي من آخر 3 أرقام
                last_number = int(last_customer_account.code[-3:])
                new_number = last_number + 1
            else:
                new_number = 1
            
            # تكوين الكود الجديد: 10300 + رقم تسلسلي من 3 أرقام
            new_code = f"10300{new_number:03d}"
            
            # إنشاء اسم مناسب للحساب
            account_name = f"عميل - {customer.name}"
            
            # إنشاء الحساب الجديد
            new_account = ChartOfAccounts.objects.create(
                code=new_code,
                name=account_name,
                parent=customers_account,
                account_type=customers_account.account_type,
                is_active=True,
                is_leaf=True,
                description=f"حساب محاسبي للعميل: {customer.name} (كود العميل: {customer.code})",
                created_by=user if user else None
            )
            
            # ربط العميل بالحساب الجديد
            customer.financial_account = new_account
            customer.save(update_fields=['financial_account'])
            
            logger.info(f"✅ تم إنشاء حساب جديد للعميل: {new_account.code} - {new_account.name}")
            return new_account
            
        except Exception as e:
            logger.error(f"❌ فشل في إنشاء حساب جديد للعميل {customer.name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    @classmethod
    def _create_supplier_account(cls, supplier, user: Optional[User] = None) -> Optional[ChartOfAccounts]:
        """
        إنشاء حساب محاسبي جديد للمورد تلقائياً
        """
        try:
            # التحقق من أن المورد لا يملك حساب بالفعل
            if supplier.financial_account:
                logger.warning(f"⚠️ المورد {supplier.name} مربوط بالفعل بحساب محاسبي {supplier.financial_account.code}")
                return supplier.financial_account
            
            # البحث عن حساب الموردين الرئيسي (20100)
            suppliers_account = ChartOfAccounts.objects.filter(code="20100").first()
            
            if not suppliers_account:
                logger.error("❌ لا يمكن العثور على حساب الموردين الرئيسي (20100) في النظام")
                return None
            
            # إنشاء كود فريد للحساب الجديد
            # البحث عن آخر حساب فرعي تحت حساب الموردين
            # النمط المتوقع: 20100001, 20100002, 20100003...
            last_supplier_account = ChartOfAccounts.objects.filter(
                parent=suppliers_account,
                code__regex=r'^20100\d{3}$'  # يبدأ بـ 20100 ويتبعه 3 أرقام
            ).order_by('-code').first()
            
            if last_supplier_account:
                # استخراج الرقم التسلسلي من آخر 3 أرقام
                last_number = int(last_supplier_account.code[-3:])
                new_number = last_number + 1
            else:
                new_number = 1
            
            # تكوين الكود الجديد: 20100 + رقم تسلسلي من 3 أرقام
            new_code = f"20100{new_number:03d}"
            
            # إنشاء اسم مناسب للحساب
            account_name = f"مورد - {supplier.name}"
            
            # إنشاء الحساب الجديد
            new_account = ChartOfAccounts.objects.create(
                code=new_code,
                name=account_name,
                parent=suppliers_account,
                account_type=suppliers_account.account_type,
                is_active=True,
                is_leaf=True,
                description=f"حساب محاسبي للمورد: {supplier.name} (كود المورد: {supplier.code})",
                created_by=user if user else None
            )
            
            # ربط المورد بالحساب الجديد
            supplier.financial_account = new_account
            supplier.save(update_fields=['financial_account'])
            
            logger.info(f"✅ تم إنشاء حساب جديد للمورد: {new_account.code} - {new_account.name}")
            return new_account
            
        except Exception as e:
            logger.error(f"❌ فشل في إنشاء حساب جديد للمورد {supplier.name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    # ==================== Adjustment & Reversal Methods ====================

    @classmethod
    def create_sale_adjustment_entry(
        cls,
        sale,
        old_total: Decimal,
        old_cost: Decimal,
        user: Optional[User] = None,
        reason: str = ""
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد تصحيحي لتعديل فاتورة مبيعات مرحّلة
        
        يتم إنشاء قيد تصحيحي يُسجل الفرق بين القيم القديمة والجديدة
        مع الحفاظ على القيد الأصلي للأثر التدقيقي
        """
        try:
            with transaction.atomic():
                # حساب الفروقات
                new_total = sale.total
                new_cost = cls._calculate_sale_cost(sale)
                
                total_difference = new_total - old_total
                cost_difference = new_cost - old_cost
                
                # إذا لم يكن هناك فرق، لا حاجة لقيد تصحيحي
                if total_difference == 0 and cost_difference == 0:
                    logger.info(f"لا توجد فروقات تتطلب قيد تصحيحي للفاتورة {sale.number}")
                    return None
                
                # التحقق من إغلاق الفترة المحاسبية
                current_date = timezone.now().date()
                accounting_period = cls._get_accounting_period(current_date)
                
                if accounting_period and accounting_period.status == 'closed':
                    error_msg = f"لا يمكن إنشاء قيد تصحيحي - الفترة المحاسبية {accounting_period.name} مغلقة"
                    logger.error(error_msg)
                    raise ValidationError(error_msg)
                
                # الحصول على الحسابات المطلوبة
                accounts = cls._get_required_accounts_for_sale()
                if not accounts:
                    logger.error("لا يمكن العثور على الحسابات المحاسبية المطلوبة")
                    return None
                
                # Prepare journal entry lines
                lines = []
                
                # معالجة فرق الإجمالي (الإيرادات والعملاء/أولياء الأمور)
                if total_difference != 0:
                    client_account = None
                    client_name = sale.client_name
                    
                    if sale.parent:
                        client_account = cls._get_parent_account(sale.parent)
                        if not client_account:
                            logger.warning(f"⚠️ ولي الأمر {sale.parent.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                            client_account = cls._create_parent_account(sale.parent, user)
                            if not client_account:
                                error_msg = f"❌ فشل إنشاء حساب محاسبي لولي الأمر {sale.parent.name}"
                                logger.error(error_msg)
                                raise ValueError(error_msg)
                    elif sale.customer:
                        client_account = cls._get_customer_account(sale.customer)
                        if not client_account:
                            logger.warning(f"⚠️ العميل {sale.customer.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                            client_account = cls._create_customer_account(sale.customer, user)
                            if not client_account:
                                error_msg = f"❌ فشل إنشاء حساب محاسبي للعميل {sale.customer.name}"
                                logger.error(error_msg)
                                raise ValueError(error_msg)
                    else:
                        error_msg = "❌ الفاتورة لا تحتوي على ولي أمر أو عميل"
                        logger.error(error_msg)
                        raise ValueError(error_msg)
                    
                    if total_difference > 0:  # زيادة في الفاتورة
                        lines.append(JournalEntryLineData(
                            account_code=client_account.code,
                            debit=total_difference,
                            credit=Decimal("0.00"),
                            description=f"زيادة ذمة {client_name} - تصحيح فاتورة {sale.number}"
                        ))
                        lines.append(JournalEntryLineData(
                            account_code=accounts["sales_revenue"].code,
                            debit=Decimal("0.00"),
                            credit=total_difference,
                            description=f"زيادة إيرادات - تصحيح فاتورة {sale.number}"
                        ))
                    else:  # نقص في الفاتورة
                        abs_diff = abs(total_difference)
                        lines.append(JournalEntryLineData(
                            account_code=client_account.code,
                            debit=Decimal("0.00"),
                            credit=abs_diff,
                            description=f"تخفيض ذمة {client_name} - تصحيح فاتورة {sale.number}"
                        ))
                        lines.append(JournalEntryLineData(
                            account_code=accounts["sales_revenue"].code,
                            debit=abs_diff,
                            credit=Decimal("0.00"),
                            description=f"تخفيض إيرادات - تصحيح فاتورة {sale.number}"
                        ))
                
                # معالجة فرق التكلفة (تكلفة البضاعة والمخزون)
                if cost_difference != 0:
                    if cost_difference > 0:  # زيادة في التكلفة
                        lines.append(JournalEntryLineData(
                            account_code=accounts["cost_of_goods_sold"].code,
                            debit=cost_difference,
                            credit=Decimal("0.00"),
                            description=f"زيادة تكلفة البضاعة - تصحيح فاتورة {sale.number}"
                        ))
                        lines.append(JournalEntryLineData(
                            account_code=accounts["inventory"].code,
                            debit=Decimal("0.00"),
                            credit=cost_difference,
                            description=f"تخفيض المخزون - تصحيح فاتورة {sale.number}"
                        ))
                    else:  # نقص في التكلفة
                        abs_cost_diff = abs(cost_difference)
                        lines.append(JournalEntryLineData(
                            account_code=accounts["cost_of_goods_sold"].code,
                            debit=Decimal("0.00"),
                            credit=abs_cost_diff,
                            description=f"تخفيض تكلفة البضاعة - تصحيح فاتورة {sale.number}"
                        ))
                        lines.append(JournalEntryLineData(
                            account_code=accounts["inventory"].code,
                            debit=abs_cost_diff,
                            credit=Decimal("0.00"),
                            description=f"زيادة المخزون - تصحيح فاتورة {sale.number}"
                        ))
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                adjustment_entry = gateway.create_journal_entry(
                    source_module='sales',
                    source_model='Sale',
                    source_id=sale.id,
                    lines=lines,
                    idempotency_key=f"JE:sales:Sale:{sale.id}:adjustment:{current_date.strftime('%Y%m%d')}",
                    user=user,
                    entry_type='adjustment',
                    description=f"تصحيح بسبب تعديل الفاتورة - الفرق: {total_difference} ج.م",
                    reference=f"تصحيح فاتورة مبيعات {sale.number}",
                    date=current_date
                )
                
                # إنشاء سجل تدقيق مفصل
                from financial.models import InvoiceAuditLog
                
                audit_log = InvoiceAuditLog.objects.create(
                    invoice_type="sale",
                    invoice_id=sale.id,
                    invoice_number=sale.number,
                    action_type="adjustment",
                    old_total=old_total,
                    old_cost=old_cost,
                    new_total=new_total,
                    new_cost=new_cost,
                    total_difference=total_difference,
                    cost_difference=cost_difference,
                    adjustment_entry=adjustment_entry,
                    reason=reason,
                    notes=f"تم إنشاء قيد تصحيحي {adjustment_entry.number}",
                    created_by=user,
                )
                
                logger.info(
                    f"✅ تم إنشاء قيد تصحيحي للمبيعات: {adjustment_entry.number} - "
                    f"فاتورة {sale.number} (فرق الإجمالي: {total_difference}, فرق التكلفة: {cost_difference}) - "
                    f"سجل تدقيق: {audit_log.id}"
                )
                return adjustment_entry
                
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء قيد تصحيحي للمبيعات: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    @classmethod
    def create_purchase_adjustment_entry(
        cls,
        purchase,
        old_total: Decimal,
        user: Optional[User] = None,
        reason: str = ""
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد تصحيحي لتعديل فاتورة مشتريات مرحّلة
        """
        try:
            with transaction.atomic():
                # حساب الفرق
                new_total = purchase.total
                total_difference = new_total - old_total
                
                # إذا لم يكن هناك فرق، لا حاجة لقيد تصحيحي
                if total_difference == 0:
                    logger.info(f"لا توجد فروقات تتطلب قيد تصحيحي للفاتورة {purchase.number}")
                    return None
                
                # التحقق من إغلاق الفترة المحاسبية
                current_date = timezone.now().date()
                accounting_period = cls._get_accounting_period(current_date)
                
                if accounting_period and accounting_period.status == 'closed':
                    error_msg = f"لا يمكن إنشاء قيد تصحيحي - الفترة المحاسبية {accounting_period.name} مغلقة"
                    logger.error(error_msg)
                    raise ValidationError(error_msg)
                
                # الحصول على الحسابات المطلوبة
                accounts = cls._get_required_accounts_for_purchase()
                if not accounts:
                    logger.error("لا يمكن العثور على الحسابات المحاسبية المطلوبة")
                    return None
                
                # Prepare journal entry lines
                lines = []
                
                # معالجة الفرق
                supplier_account = cls._get_supplier_account(purchase.supplier)
                if not supplier_account:
                    logger.warning(f"⚠️ المورد {purchase.supplier.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                    supplier_account = cls._create_supplier_account(purchase.supplier, user)
                    if not supplier_account:
                        error_msg = f"❌ فشل إنشاء حساب محاسبي للمورد {purchase.supplier.name}"
                        logger.error(error_msg)
                        raise ValueError(error_msg)
                
                if total_difference > 0:  # زيادة في الفاتورة
                    lines.append(JournalEntryLineData(
                        account_code=accounts["inventory"].code,
                        debit=total_difference,
                        credit=Decimal("0.00"),
                        description=f"زيادة مخزون - تصحيح فاتورة {purchase.number}"
                    ))
                    lines.append(JournalEntryLineData(
                        account_code=supplier_account.code,
                        debit=Decimal("0.00"),
                        credit=total_difference,
                        description=f"زيادة مديونية المورد {purchase.supplier.name} - تصحيح فاتورة {purchase.number}"
                    ))
                else:  # نقص في الفاتورة
                    abs_diff = abs(total_difference)
                    lines.append(JournalEntryLineData(
                        account_code=accounts["inventory"].code,
                        debit=Decimal("0.00"),
                        credit=abs_diff,
                        description=f"تخفيض مخزون - تصحيح فاتورة {purchase.number}"
                    ))
                    lines.append(JournalEntryLineData(
                        account_code=supplier_account.code,
                        debit=abs_diff,
                        credit=Decimal("0.00"),
                        description=f"تخفيض مديونية المورد {purchase.supplier.name} - تصحيح فاتورة {purchase.number}"
                    ))
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                adjustment_entry = gateway.create_journal_entry(
                    source_module='purchases',
                    source_model='Purchase',
                    source_id=purchase.id,
                    lines=lines,
                    idempotency_key=f"JE:purchases:Purchase:{purchase.id}:adjustment:{current_date.strftime('%Y%m%d')}",
                    user=user,
                    entry_type='adjustment',
                    description=f"تصحيح بسبب تعديل الفاتورة - الفرق: {total_difference} ج.م",
                    reference=f"تصحيح فاتورة مشتريات {purchase.number}",
                    date=current_date
                )
                
                # إنشاء سجل تدقيق مفصل
                from financial.models import InvoiceAuditLog
                
                audit_log = InvoiceAuditLog.objects.create(
                    invoice_type="purchase",
                    invoice_id=purchase.id,
                    invoice_number=purchase.number,
                    action_type="adjustment",
                    old_total=old_total,
                    new_total=new_total,
                    total_difference=total_difference,
                    adjustment_entry=adjustment_entry,
                    reason=reason,
                    notes=f"تم إنشاء قيد تصحيحي {adjustment_entry.number}",
                    created_by=user,
                )
                
                logger.info(
                    f"✅ تم إنشاء قيد تصحيحي للمشتريات: {adjustment_entry.number} - "
                    f"فاتورة {purchase.number} (فرق الإجمالي: {total_difference}) - "
                    f"سجل تدقيق: {audit_log.id}"
                )
                return adjustment_entry
                
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء قيد تصحيحي للمشتريات: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    @classmethod
    def create_reversal_entry(
        cls, 
        original_entry: JournalEntry, 
        refund_amount: Decimal, 
        reason: str,
        user: Optional[User] = None
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد عكسي للتسوية المالية
        
        المبدأ المحاسبي الصحيح:
        - إذا كان البند الأصلي: من حـ/أ (مدين 100) إلى حـ/ب (دائن 100)
        - فالقيد العكسي يكون: من حـ/ب (مدين 100) إلى حـ/أ (دائن 100)
        """
        try:
            with transaction.atomic():
                # التحقق من صحة القيد الأصلي
                if not original_entry or not original_entry.is_posted:
                    logger.error("القيد الأصلي غير موجود أو غير مرحل")
                    return None
                
                # التحقق من صحة مبلغ الاسترداد
                if refund_amount <= 0:
                    logger.error("مبلغ الاسترداد يجب أن يكون أكبر من صفر")
                    return None
                
                # حساب المبلغ الإجمالي للقيد الأصلي
                original_total = max(original_entry.total_debit, original_entry.total_credit)
                
                if refund_amount > original_total:
                    logger.error(f"مبلغ الاسترداد ({refund_amount}) لا يمكن أن يكون أكبر من مبلغ القيد الأصلي ({original_total})")
                    return None
                
                # الحصول على الفترة المحاسبية
                try:
                    accounting_period = cls._get_accounting_period(timezone.now().date())
                    if not accounting_period:
                        logger.error("لا توجد فترة محاسبية مفتوحة للتاريخ الحالي")
                        return None
                except Exception as e:
                    logger.error(f"فشل في الحصول على الفترة المحاسبية: {e}")
                    return None
                
                # حساب نسبة الاسترداد
                refund_ratio = refund_amount / original_total
                
                # Prepare journal entry lines (reverse of original)
                lines = []
                for original_line in original_entry.lines.all():
                    # حساب المبلغ المتناسب للبند
                    line_debit = original_line.debit * refund_ratio
                    line_credit = original_line.credit * refund_ratio
                    
                    # تجاهل البنود التي مبلغها صفر
                    if line_debit == 0 and line_credit == 0:
                        continue
                    
                    # إنشاء البند العكسي - عكس الجهات تماماً
                    lines.append(JournalEntryLineData(
                        account_code=original_line.account.code,
                        debit=line_credit,   # الدائن الأصلي يصبح مدين في العكسي
                        credit=line_debit,   # المدين الأصلي يصبح دائن في العكسي
                        description=f"عكس: {original_line.description}",
                        cost_center=original_line.cost_center.code if original_line.cost_center else None,
                        project=original_line.project.code if original_line.project else None
                    ))
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                reversal_entry = gateway.create_journal_entry(
                    source_module='financial',
                    source_model='JournalEntry',
                    source_id=original_entry.id,
                    lines=lines,
                    idempotency_key=f"JE:financial:JournalEntry:{original_entry.id}:reversal:{timezone.now().timestamp()}",
                    user=user,
                    entry_type='reversal',
                    description=f"قيد عكسي - {reason}",
                    reference=f"قيد عكسي للقيد {original_entry.number}",
                    date=timezone.now().date()
                )
                
                logger.info(f"✅ تم إنشاء قيد عكسي صحيح: {reversal_entry.number} بمبلغ {refund_amount}")
                
                # إضافة سجل تدقيق للقيد العكسي
                try:
                    cls._log_reversal_entry(original_entry, reversal_entry, refund_amount, reason, user)
                except Exception as e:
                    logger.warning(f"⚠️ فشل في تسجيل القيد العكسي في سجل التدقيق: {e}")
                
                return reversal_entry
                
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء القيد العكسي: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    @classmethod
    def _log_reversal_entry(cls, original_entry, reversal_entry, amount, reason, user):
        """تسجيل عملية القيد العكسي في سجل التدقيق"""
        # SettlementAuditLog removed - students module no longer used
        # Use general audit logging instead
        try:
            logger.info(
                f"Reversal entry created: {reversal_entry.number} for original {original_entry.number}. "
                f"Amount: {amount}, Reason: {reason}"
            )
        except Exception as e:
            logger.warning(f"⚠️ فشل في تسجيل القيد العكسي: {e}")
    
    @classmethod
    def validate_reversal_entry(cls, original_entry: JournalEntry, reversal_entry: JournalEntry) -> bool:
        """
        التحقق من صحة القيد العكسي محاسبياً
        """
        try:
            original_lines = {line.account_id: line for line in original_entry.lines.all()}
            reversal_lines = {line.account_id: line for line in reversal_entry.lines.all()}
            
            # التحقق من أن نفس الحسابات موجودة
            if set(original_lines.keys()) != set(reversal_lines.keys()):
                logger.error("الحسابات في القيد العكسي لا تطابق الحسابات في القيد الأصلي")
                return False
            
            # التحقق من عكس المبالغ لكل حساب
            for account_id in original_lines.keys():
                orig_line = original_lines[account_id]
                rev_line = reversal_lines[account_id]
                
                # المدين الأصلي يجب أن يساوي الدائن العكسي
                if orig_line.debit != rev_line.credit:
                    logger.error(f"خطأ في الحساب {account_id}: المدين الأصلي ({orig_line.debit}) لا يساوي الدائن العكسي ({rev_line.credit})")
                    return False
                
                # الدائن الأصلي يجب أن يساوي المدين العكسي
                if orig_line.credit != rev_line.debit:
                    logger.error(f"خطأ في الحساب {account_id}: الدائن الأصلي ({orig_line.credit}) لا يساوي المدين العكسي ({rev_line.debit})")
                    return False
            
            logger.info("✅ تم التحقق من صحة القيد العكسي محاسبياً")
            return True
            
        except Exception as e:
            logger.error(f"❌ خطأ في التحقق من صحة القيد العكسي: {e}")
            return False

    # ==================== DEPRECATED: Student Account Methods ====================
    # These methods are deprecated and should not be used in Corporate ERP
    # They were part of the school management system and have been removed.
    # Use client/customer account methods instead.

    @classmethod
    def generate_financial_report(
        cls,
        date_from: date,
        date_to: date,
        report_type: str = "settlements",
        filters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        إنتاج تقرير مالي للتسويات والمرتجعات
        """
        try:
            filters = filters or {}
            
            # إعداد التقرير الأساسي
            report_data = {
                "report_info": {
                    "type": report_type,
                    "date_from": date_from,
                    "date_to": date_to,
                    "generated_at": timezone.now(),
                    "filters": filters
                },
                "summary": {
                    "total_settlements": 0,
                    "total_amount": Decimal("0.00"),
                    "by_type": {},
                    "by_status": {}
                },
                "details": [],
                "accounting_entries": [],
                "errors": []
            }
            
            # الحصول على التسويات في الفترة المحددة
            from students.models import StudentRefund
            
            settlements_query = StudentRefund.objects.filter(
                created_at__date__gte=date_from,
                created_at__date__lte=date_to
            ).select_related(
                'student', 'student__parent', 'created_by', 'approved_by', 'journal_entry'
            ).prefetch_related('audit_logs')
            
            # تطبيق الفلاتر الإضافية
            if filters.get('refund_type'):
                settlements_query = settlements_query.filter(refund_type=filters['refund_type'])
            
            if filters.get('status'):
                settlements_query = settlements_query.filter(status=filters['status'])
            
            if filters.get('student_id'):
                settlements_query = settlements_query.filter(student_id=filters['student_id'])
            
            settlements = settlements_query.order_by('-created_at')
            
            # معالجة البيانات
            for settlement in settlements:
                # تحديث الملخص
                report_data["summary"]["total_settlements"] += 1
                report_data["summary"]["total_amount"] += settlement.amount
                
                # تجميع حسب النوع
                refund_type = settlement.get_refund_type_display()
                if refund_type not in report_data["summary"]["by_type"]:
                    report_data["summary"]["by_type"][refund_type] = {
                        "count": 0,
                        "amount": Decimal("0.00")
                    }
                report_data["summary"]["by_type"][refund_type]["count"] += 1
                report_data["summary"]["by_type"][refund_type]["amount"] += settlement.amount
                
                # تجميع حسب الحالة
                status = settlement.get_status_display()
                if status not in report_data["summary"]["by_status"]:
                    report_data["summary"]["by_status"][status] = {
                        "count": 0,
                        "amount": Decimal("0.00")
                    }
                report_data["summary"]["by_status"][status]["count"] += 1
                report_data["summary"]["by_status"][status]["amount"] += settlement.amount
                
                # إضافة التفاصيل
                settlement_detail = {
                    "id": settlement.id,
                    "reference_number": settlement.reference_number,
                    "student": {
                        "id": settlement.student.id,
                        "name": settlement.student.name,
                        "parent_name": settlement.student.parent.name if settlement.student.parent else "غير محدد"
                    },
                    "refund_type": refund_type,
                    "amount": settlement.amount,
                    "status": status,
                    "reason": settlement.reason,
                    "created_at": settlement.created_at,
                    "created_by": settlement.created_by.get_full_name() if settlement.created_by else "غير محدد",
                    "approved_at": settlement.approved_at,
                    "approved_by": settlement.approved_by.get_full_name() if settlement.approved_by else None,
                    "journal_entry": {
                        "number": settlement.journal_entry.number if settlement.journal_entry else None,
                        "amount": settlement.journal_entry.total_amount if settlement.journal_entry else None,
                        "status": settlement.journal_entry.get_status_display() if settlement.journal_entry else None
                    } if settlement.journal_entry else None,
                    "failure_info": {
                        "reason": settlement.failure_reason,
                        "retry_count": settlement.retry_count,
                        "last_retry": settlement.last_retry_at
                    } if settlement.failure_reason else None
                }
                
                report_data["details"].append(settlement_detail)
                
                # إضافة القيود المحاسبية المرتبطة
                if settlement.journal_entry:
                    journal_lines = []
                    for line in settlement.journal_entry.lines.all():
                        journal_lines.append({
                            "account_code": line.account.code,
                            "account_name": line.account.name,
                            "debit": line.debit,
                            "credit": line.credit,
                            "description": line.description
                        })
                    
                    report_data["accounting_entries"].append({
                        "settlement_id": settlement.id,
                        "reference_number": settlement.reference_number,
                        "journal_number": settlement.journal_entry.number,
                        "journal_date": settlement.journal_entry.date,
                        "total_amount": settlement.journal_entry.total_amount,
                        "lines": journal_lines
                    })
            
            # إضافة إحصائيات إضافية
            if report_data["summary"]["total_settlements"] > 0:
                report_data["summary"]["average_amount"] = (
                    report_data["summary"]["total_amount"] / report_data["summary"]["total_settlements"]
                )
            else:
                report_data["summary"]["average_amount"] = Decimal("0.00")
            
            # تحويل Decimal إلى string للتسلسل
            def convert_decimals(obj):
                if isinstance(obj, dict):
                    return {k: convert_decimals(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_decimals(item) for item in obj]
                elif isinstance(obj, Decimal):
                    return str(obj)
                else:
                    return obj
            
            report_data = convert_decimals(report_data)
            
            logger.info(
                f"✅ تم إنتاج تقرير مالي: {report_type} "
                f"من {date_from} إلى {date_to} "
                f"({report_data['summary']['total_settlements']} تسوية)"
            )
            
            return report_data
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنتاج التقرير المالي: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
            return {
                "report_info": {
                    "type": report_type,
                    "date_from": date_from,
                    "date_to": date_to,
                    "generated_at": timezone.now(),
                    "filters": filters
                },
                "summary": {
                    "total_settlements": 0,
                    "total_amount": "0.00",
                    "by_type": {},
                    "by_status": {}
                },
                "details": [],
                "accounting_entries": [],
                "errors": [f"خطأ في إنتاج التقرير: {str(e)}"]
            }

    # DEPRECATED: Student fee methods removed
    # These methods were part of the school management system
    # Use client/customer invoice methods instead
