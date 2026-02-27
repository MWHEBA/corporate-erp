"""
خدمة إدارة حسابات الموردين والعملاء في دليل الحسابات

⚠️ DEPRECATED: This service is deprecated and should not be used for new code.

For suppliers, use: supplier.services.supplier_service.SupplierService
For customers, use: client.services.CustomerService

This service is kept for backward compatibility with parent accounts only.
"""
import logging
import warnings
from django.db import transaction
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class SupplierParentAccountService:
    """
    خدمة مركزية لإدارة ربط الموردين والعملاء بدليل الحسابات
    
    ⚠️ DEPRECATED: Use unified services instead:
    - For suppliers: SupplierService.create_financial_account_for_supplier()
    - For customers: CustomerService.create_financial_account_for_customer()
    """

    @staticmethod
    def create_supplier_account(supplier, user=None):
        """
        إنشاء حساب محاسبي للمورد
        
        ⚠️ DEPRECATED: Use SupplierService.create_financial_account_for_supplier() instead

        Args:
            supplier: كائن المورد
            user: المستخدم الذي ينشئ الحساب (اختياري)

        Returns:
            ChartOfAccounts: الحساب المحاسبي المنشأ
        """
        warnings.warn(
            "SupplierParentAccountService.create_supplier_account() is deprecated. "
            "Use SupplierService.create_financial_account_for_supplier() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        # Redirect to unified service
        from supplier.services.supplier_service import SupplierService
        return SupplierService.create_financial_account_for_supplier(
            supplier=supplier,
            user=user
        )

    @staticmethod
    def create_parent_account(parent, user=None):
        """
        إنشاء حساب محاسبي لالعميل

        Args:
            parent: كائن العميل
            user: المستخدم الذي ينشئ الحساب (اختياري)

        Returns:
            ChartOfAccounts: الحساب المحاسبي المنشأ
        """
        from financial.models import ChartOfAccounts, AccountType

        try:
            with transaction.atomic():
                # البحث عن الحساب الرئيسي للعملاء
                receivables_type = AccountType.objects.filter(
                    code="RECEIVABLES"
                ).first()
                if not receivables_type:
                    raise ValueError("نوع حساب RECEIVABLES غير موجود")

                parent_account = ChartOfAccounts.objects.filter(
                    account_type=receivables_type, parent__isnull=True, is_active=True
                ).first()

                if not parent_account:
                    # إنشاء الحساب الرئيسي إذا لم يكن موجوداً
                    parent_account = ChartOfAccounts.objects.create(
                        code="10300",
                        name="العملاء",
                        account_type=receivables_type,
                        is_active=True,
                        is_leaf=False,
                        is_control_account=True,
                        created_by=user,
                    )

                # توليد كود فريد للحساب الفرعي
                code = f"1030{parent.id:03d}"  # مثال: 10300001

                # التحقق من عدم وجود الكود
                if ChartOfAccounts.objects.filter(code=code).exists():
                    # إذا كان موجوداً، نستخدم timestamp
                    import time

                    code = f"1103{int(time.time()) % 1000:03d}"

                # حساب الرصيد الافتتاحي من طلبات المنتجات المُسلمة
                from student_products.models import ProductRequest
                from decimal import Decimal
                
                # إجمالي طلبات المنتجات المُسلمة لأبناء العميل
                opening_balance = Decimal('0')
                for student in parent.students.all():
                    student_debt = ProductRequest.objects.filter(
                        student=student,
                        status='delivered'
                    ).aggregate(
                        total=Sum('outstanding_amount')
                    )['total'] or Decimal('0')
                    
                    opening_balance += student_debt

                # إنشاء الحساب الفرعي
                account = ChartOfAccounts.objects.create(
                    code=code,
                    name=f"ولي أمر - {parent.name}",
                    parent=parent_account,
                    account_type=receivables_type,
                    is_active=True,
                    is_leaf=True,
                    opening_balance=opening_balance,
                    description=f"حساب العميل: {parent.name} (كود: {parent.id})",
                    created_by=user,
                )

                # ربط الحساب بالعميل
                parent.financial_account = account
                parent.save(update_fields=["financial_account"])

                logger.info(
                    f"تم إنشاء حساب محاسبي {account.code} لالعميل {parent.name}"
                )
                return account

        except Exception as e:
            logger.error(f"فشل إنشاء حساب لالعميل {parent.name}: {e}")
            raise

    @staticmethod
    def get_or_create_supplier_account(supplier, user=None):
        """
        الحصول على الحساب المحاسبي للمورد أو إنشاؤه إذا لم يكن موجوداً
        
        ⚠️ DEPRECATED: Use SupplierService.create_financial_account_for_supplier() instead

        Args:
            supplier: كائن المورد
            user: المستخدم (اختياري)

        Returns:
            ChartOfAccounts: الحساب المحاسبي
        """
        warnings.warn(
            "SupplierParentAccountService.get_or_create_supplier_account() is deprecated. "
            "Use SupplierService.create_financial_account_for_supplier() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        if supplier.financial_account:
            return supplier.financial_account
        
        from supplier.services.supplier_service import SupplierService
        return SupplierService.create_financial_account_for_supplier(
            supplier=supplier,
            user=user
        )

    @staticmethod
    def get_or_create_parent_account(parent, user=None):
        """
        الحصول على الحساب المحاسبي لالعميل أو إنشاؤه إذا لم يكن موجوداً

        Args:
            parent: كائن العميل
            user: المستخدم (اختياري)

        Returns:
            ChartOfAccounts: الحساب المحاسبي
        """
        if parent.financial_account:
            return parent.financial_account
        return SupplierParentAccountService.create_parent_account(parent, user)

    @staticmethod
    def sync_balance(entity):
        """
        مزامنة الرصيد بين المورد/العميل والحساب المحاسبي

        Args:
            entity: المورد أو العميل
        """
        if not entity.financial_account:
            return

        try:
            # تحديث الرصيد في الحساب المحاسبي
            current_balance = entity.financial_account.get_balance()
            actual_balance = entity.actual_balance

            if current_balance != actual_balance:
                logger.warning(
                    f"تباين في الرصيد: {entity.__class__.__name__} {entity.name} - "
                    f"الحساب المحاسبي: {current_balance}, الرصيد الفعلي: {actual_balance}"
                )
        except Exception as e:
            logger.error(f"فشل مزامنة الرصيد لـ {entity.name}: {e}")
