"""
خدمة الربط المحاسبي لأذون الصرف والاستلام
Voucher Accounting Service
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntry, JournalEntryLine
from product.models.inventory_movement import InventoryMovement


# خريطة ربط الأغراض بالحسابات المحاسبية
CONTRA_ACCOUNTS_MAP = {
    # أغراض الاستلام
    'supplies_gifts': '40410',  # سبلايز وهدايا
    'inventory_gain': '59000',  # أرباح وخسائر جرد
    
    # أغراض الصرف
    'office_supplies': '50310',  # مستلزمات إدارية
    'educational_supplies': '50351',  # أدوات ومستلزمات تعليمية
    'activity_materials': '50352',  # خامات أنشطة
    'office_equipment': '50353',  # تجهيزات مكتبية
    'maintenance': '50341',  # صيانة دورية
    'cleaning': '50342',  # خدمات نظافة
    'samples': '50610',  # عينات مجانية
    'exhibition': '50620',  # معارض وفعاليات
    'advertising': '50630',  # إعلانات
    'gifts': '50760',  # هدايا وضيافة
    'charity': '50770',  # تبرعات خيرية
    'damage': '50810',  # خسائر تلف بضاعة
    'expired': '50820',  # خسائر منتهية الصلاحية
    'theft': '50830',  # خسائر سرقة وفقدان
    'inventory_loss': '59000',  # أرباح وخسائر جرد
}


def get_inventory_account(product):
    """الحصول على حساب المخزون للمنتج"""
    # حساب المخزون الرئيسي
    try:
        return ChartOfAccounts.objects.get(code='10400')
    except ChartOfAccounts.DoesNotExist:
        raise ValueError('حساب المخزون (10400) غير موجود')


def get_contra_account(purpose_type):
    """الحصول على الحساب المقابل حسب الغرض"""
    if not purpose_type or purpose_type not in CONTRA_ACCOUNTS_MAP:
        raise ValueError(f'غرض غير صحيح: {purpose_type}')
    
    account_code = CONTRA_ACCOUNTS_MAP[purpose_type]
    try:
        return ChartOfAccounts.objects.get(code=account_code)
    except ChartOfAccounts.DoesNotExist:
        raise ValueError(f'الحساب المقابل ({account_code}) غير موجود')


@transaction.atomic
def create_receipt_voucher_entry(voucher):
    """
    إنشاء قيد محاسبي لإذن استلام
    
    القيد:
    مدين: المخزون (حساب المنتج)
    دائن: حساب مقابل حسب نوع الاستلام
    """
    if not voucher.is_approved:
        raise ValueError('لا يمكن إنشاء قيد لإذن غير معتمد')
    
    if voucher.journal_entry:
        return voucher.journal_entry  # القيد موجود مسبقاً
    
    # الحصول على الحسابات
    inventory_account = get_inventory_account(voucher.product)
    contra_account = voucher.contra_account or get_contra_account(voucher.purpose_type)
    
    # استخدام AccountingGateway
    from governance.services import AccountingGateway, JournalEntryLineData
    
    gateway = AccountingGateway()
    lines = [
        JournalEntryLineData(
            account_code=inventory_account.code,
            debit=voucher.total_cost,
            credit=Decimal('0.00'),
            description=f'{voucher.product.name} - {voucher.quantity} وحدة'
        ),
        JournalEntryLineData(
            account_code=contra_account.code,
            debit=Decimal('0.00'),
            credit=voucher.total_cost,
            description=f'{voucher.get_purpose_type_display()}'
        )
    ]
    
    entry = gateway.create_journal_entry(
        source_module='product',
        source_model='InventoryMovement',
        source_id=voucher.id,
        lines=lines,
        idempotency_key=f'JE:product:InventoryMovement:{voucher.id}:receipt',
        user=voucher.approved_by,
        date=voucher.movement_date.date() if hasattr(voucher.movement_date, 'date') else voucher.movement_date,
        description=f'إذن استلام - {voucher.product.name} - {voucher.get_purpose_type_display()}',
        reference=voucher.movement_number,
        entry_type='inventory',
        auto_post=True
    )
    
    # ربط القيد بالحركة (استخدام update لتجنب validation)
    InventoryMovement.objects.filter(pk=voucher.pk).update(journal_entry=entry)
    
    return entry

@transaction.atomic
def create_issue_voucher_entry(voucher):
    """
    إنشاء قيد محاسبي لإذن صرف
    
    القيد:
    مدين: حساب مقابل حسب نوع الصرف
    دائن: المخزون (حساب المنتج)
    """
    if not voucher.is_approved:
        raise ValueError('لا يمكن إنشاء قيد لإذن غير معتمد')
    
    if voucher.journal_entry:
        return voucher.journal_entry  # القيد موجود مسبقاً
    
    # الحصول على الحسابات
    inventory_account = get_inventory_account(voucher.product)
    contra_account = voucher.contra_account or get_contra_account(voucher.purpose_type)
    
    # استخدام AccountingGateway
    from governance.services import AccountingGateway, JournalEntryLineData
    
    gateway = AccountingGateway()
    lines = [
        JournalEntryLineData(
            account_code=contra_account.code,
            debit=voucher.total_cost,
            credit=Decimal('0.00'),
            description=f'{voucher.get_purpose_type_display()}'
        ),
        JournalEntryLineData(
            account_code=inventory_account.code,
            debit=Decimal('0.00'),
            credit=voucher.total_cost,
            description=f'{voucher.product.name} - {voucher.quantity} وحدة'
        )
    ]
    
    entry = gateway.create_journal_entry(
        source_module='product',
        source_model='InventoryMovement',
        source_id=voucher.id,
        lines=lines,
        idempotency_key=f'JE:product:InventoryMovement:{voucher.id}:issue',
        user=voucher.approved_by,
        date=voucher.movement_date.date() if hasattr(voucher.movement_date, 'date') else voucher.movement_date,
        description=f'إذن صرف - {voucher.product.name} - {voucher.get_purpose_type_display()}',
        reference=voucher.movement_number,
        entry_type='inventory',
        auto_post=True
    )
    
    # ربط القيد بالحركة (استخدام update لتجنب validation)
    InventoryMovement.objects.filter(pk=voucher.pk).update(journal_entry=entry)
    
    return entry
