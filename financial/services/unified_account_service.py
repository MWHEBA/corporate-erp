"""
خدمة إنشاء الحسابات المحاسبية الموحدة
تتعامل مع إنشاء حسابات العملاء والموردين بطريقة موحدة
"""

from django.db import transaction
from django.contrib.auth.models import User
from typing import Optional
import logging

from financial.models import ChartOfAccounts

logger = logging.getLogger(__name__)


class UnifiedAccountService:
    """خدمة إنشاء الحسابات المحاسبية الموحدة"""
    
    @classmethod
    def create_parent_account(cls, parent, user: Optional[User] = None) -> Optional[ChartOfAccounts]:
        """
        إنشاء حساب محاسبي لالعميل
        
        Args:
            parent: نموذج العميل
            user: المستخدم الذي ينشئ الحساب
            
        Returns:
            ChartOfAccounts: الحساب المحاسبي الجديد أو None في حالة الفشل
        """
        try:
            with transaction.atomic():
                # التحقق من وجود حساب بالفعل
                if hasattr(parent, 'financial_account') and parent.financial_account:
                    logger.info(f"العميل {parent.name} لديه حساب محاسبي بالفعل: {parent.financial_account.code}")
                    return parent.financial_account
                
                # البحث عن الحساب الأساسي لالعملاء أو إنشاؤه
                parents_account = cls._get_or_create_parents_main_account(user)
                if not parents_account:
                    logger.error("فشل في الحصول على الحساب الأساسي لالعملاء")
                    return None
                
                # إنشاء كود فريد للحساب الجديد
                new_code = cls._generate_parent_account_code(parents_account)
                if not new_code:
                    logger.error("فشل في توليد كود فريد للحساب")
                    return None
                
                # إنشاء الحساب الجديد
                account_name = f"ولي أمر - {parent.name}"
                new_account = ChartOfAccounts.objects.create(
                    code=new_code,
                    name=account_name,
                    parent=parents_account,
                    account_type=parents_account.account_type,
                    is_active=True,
                    is_leaf=True,
                    description=f"حساب محاسبي لالعميل: {parent.name}",
                    created_by=user
                )
                
                # ربط العميل بالحساب الجديد
                parent.financial_account = new_account
                parent.save(update_fields=['financial_account'])
                
                logger.info(f"✅ تم إنشاء حساب محاسبي لالعميل: {new_account.code} - {new_account.name}")
                return new_account
                
        except Exception as e:
            logger.error(f"❌ فشل في إنشاء حساب محاسبي لالعميل {parent.name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    @classmethod
    def create_supplier_account(cls, supplier, user: Optional[User] = None) -> Optional[ChartOfAccounts]:
        """
        إنشاء حساب محاسبي للمورد
        
        Args:
            supplier: نموذج المورد
            user: المستخدم الذي ينشئ الحساب
            
        Returns:
            ChartOfAccounts: الحساب المحاسبي الجديد أو None في حالة الفشل
        """
        try:
            with transaction.atomic():
                # التحقق من وجود حساب بالفعل
                if hasattr(supplier, 'financial_account') and supplier.financial_account:
                    logger.info(f"المورد {supplier.name} لديه حساب محاسبي بالفعل: {supplier.financial_account.code}")
                    return supplier.financial_account
                
                # البحث عن الحساب الأساسي للموردين أو إنشاؤه
                suppliers_account = cls._get_or_create_suppliers_main_account(user)
                if not suppliers_account:
                    logger.error("فشل في الحصول على الحساب الأساسي للموردين")
                    return None
                
                # إنشاء كود فريد للحساب الجديد
                new_code = cls._generate_supplier_account_code(suppliers_account)
                if not new_code:
                    logger.error("فشل في توليد كود فريد للحساب")
                    return None
                
                # إنشاء الحساب الجديد
                account_name = f"مورد - {supplier.name}"
                new_account = ChartOfAccounts.objects.create(
                    code=new_code,
                    name=account_name,
                    parent=suppliers_account,
                    account_type=suppliers_account.account_type,
                    is_active=True,
                    is_leaf=True,
                    description=f"حساب محاسبي للمورد: {supplier.name}",
                    created_by=user
                )
                
                # ربط المورد بالحساب الجديد
                supplier.financial_account = new_account
                supplier.save(update_fields=['financial_account'])
                
                logger.info(f"✅ تم إنشاء حساب محاسبي للمورد: {new_account.code} - {new_account.name}")
                return new_account
                
        except Exception as e:
            logger.error(f"❌ فشل في إنشاء حساب محاسبي للمورد {supplier.name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    @classmethod
    def _get_or_create_parents_main_account(cls, user: Optional[User] = None) -> Optional[ChartOfAccounts]:
        """الحصول على الحساب الأساسي لالعملاء أو إنشاؤه"""
        try:
            # البحث عن الحساب الموجود
            parents_account = ChartOfAccounts.objects.filter(code="10300").first()
            
            if not parents_account:
                # البحث عن نوع الحساب المناسب (أصول - ذمم مدينة)
                from financial.models.chart_of_accounts import AccountType
                account_type = AccountType.objects.filter(
                    category="asset",
                    nature="debit"
                ).first()
                
                if not account_type:
                    # إنشاء نوع الحساب إذا لم يكن موجوداً
                    account_type = AccountType.objects.create(
                        code="RECEIVABLES",
                        name="ذمم مدينة",
                        name_en="Accounts Receivable",
                        category="asset",
                        nature="debit",
                        is_system_type=True,
                        created_by=user
                    )
                    logger.info("✅ تم إنشاء نوع حساب الذمم المدينة")
                
                # إنشاء الحساب الأساسي
                parents_account = ChartOfAccounts.objects.create(
                    code="10300",
                    name="العملاء",
                    account_type=account_type,
                    is_active=True,
                    is_leaf=False,  # حساب أساسي يحتوي على حسابات فرعية
                    description="الحساب الأساسي لجميع العملاء",
                    created_by=user
                )
                logger.info("✅ تم إنشاء الحساب الأساسي لالعملاء (10300)")
            
            return parents_account
            
        except Exception as e:
            logger.error(f"❌ فشل في الحصول على الحساب الأساسي لالعملاء: {e}")
            return None
    
    @classmethod
    def _get_or_create_suppliers_main_account(cls, user: Optional[User] = None) -> Optional[ChartOfAccounts]:
        """الحصول على الحساب الأساسي للموردين أو إنشاؤه"""
        try:
            # البحث عن الحساب الموجود
            suppliers_account = ChartOfAccounts.objects.filter(code="2101").first()
            
            if not suppliers_account:
                # البحث عن نوع الحساب المناسب (خصوم - دائنون)
                from financial.models.chart_of_accounts import AccountType
                account_type = AccountType.objects.filter(
                    category="liability",
                    nature="credit"
                ).first()
                
                if not account_type:
                    # إنشاء نوع الحساب إذا لم يكن موجوداً
                    account_type = AccountType.objects.create(
                        code="PAYABLES",
                        name="ذمم دائنة",
                        name_en="Accounts Payable",
                        category="liability",
                        nature="credit",
                        is_system_type=True,
                        created_by=user
                    )
                    logger.info("✅ تم إنشاء نوع حساب الذمم الدائنة")
                
                # إنشاء الحساب الأساسي
                suppliers_account = ChartOfAccounts.objects.create(
                    code="2101",
                    name="الموردون",
                    account_type=account_type,
                    is_active=True,
                    is_leaf=False,  # حساب أساسي يحتوي على حسابات فرعية
                    description="الحساب الأساسي لجميع الموردين",
                    created_by=user
                )
                logger.info("✅ تم إنشاء الحساب الأساسي للموردين (2101)")
            
            return suppliers_account
            
        except Exception as e:
            logger.error(f"❌ فشل في الحصول على الحساب الأساسي للموردين: {e}")
            return None
    
    @classmethod
    def _generate_parent_account_code(cls, parents_account: ChartOfAccounts) -> Optional[str]:
        """توليد كود فريد لحساب العميل"""
        try:
            # البحث عن آخر حساب فرعي
            last_account = ChartOfAccounts.objects.filter(
                parent=parents_account,
                code__startswith="10300"  # يبدأ بـ 10300
            ).order_by('-code').first()
            
            if last_account:
                try:
                    # استخراج الجزء الرقمي بعد 10300
                    code_suffix = last_account.code[5:]  # كل شيء بعد 10300
                    last_number = int(code_suffix)
                    new_number = last_number + 1
                except (ValueError, IndexError):
                    new_number = 1
            else:
                new_number = 1
            
            # تكوين الكود الجديد - استخدام 4 أرقام للسماح بأكثر من 999 حساب
            new_code = f"10300{new_number:04d}"
            
            # التأكد من عدم وجود الكود
            while ChartOfAccounts.objects.filter(code=new_code).exists():
                new_number += 1
                new_code = f"10300{new_number:04d}"
            
            return new_code
            
        except Exception as e:
            logger.error(f"❌ فشل في توليد كود حساب العميل: {e}")
            return None
    
    @classmethod
    def _generate_supplier_account_code(cls, suppliers_account: ChartOfAccounts) -> Optional[str]:
        """توليد كود فريد لحساب المورد"""
        try:
            # البحث عن آخر حساب فرعي
            last_account = ChartOfAccounts.objects.filter(
                parent=suppliers_account,
                code__regex=r'^2101\d{3}$'  # يبدأ بـ 2101 ويتبعه 3 أرقام
            ).order_by('-code').first()
            
            if last_account:
                try:
                    last_number = int(last_account.code[-3:])
                    new_number = last_number + 1
                except (ValueError, IndexError):
                    new_number = 1
            else:
                new_number = 1
            
            # تكوين الكود الجديد
            new_code = f"2101{new_number:03d}"
            
            # التأكد من عدم وجود الكود
            if ChartOfAccounts.objects.filter(code=new_code).exists():
                # في حالة التضارب، استخدم timestamp
                import time
                timestamp_suffix = str(int(time.time()))[-3:]
                new_code = f"2101{timestamp_suffix}"
            
            return new_code
            
        except Exception as e:
            logger.error(f"❌ فشل في توليد كود حساب المورد: {e}")
            return None