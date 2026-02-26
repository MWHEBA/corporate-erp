from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from core.models import SystemSetting
from .models import (
    AccountType,
    ChartOfAccounts,
    AccountingPeriod,
    JournalEntry,
    JournalEntryLine,
    PaymentSyncOperation,
    PaymentSyncLog,
    PartnerTransaction,
    PartnerBalance,
    InvoiceAuditLog,
    FinancialCategory,
    FinancialSubcategory,
)
from .models.validation_audit_log import ValidationAuditLog

# Import governance security controls
from governance.admin_security import (
    SecureJournalEntryAdmin,
    ReadOnlyModelAdmin,
    RestrictedModelAdmin
)


class JournalEntryLineInline(admin.TabularInline):
    """
    عرض بنود القيد المحاسبي ضمن صفحة القيد
    SECURITY: Read-only inline for high-risk model
    """

    model = JournalEntryLine
    extra = 0  # No extra forms for security
    max_num = 0  # Prevent adding new lines
    can_delete = False  # Prevent deletion
    
    # Make all fields read-only
    readonly_fields = ("account", "debit", "credit", "description")
    fields = ("account", "debit", "credit", "description")

    def has_add_permission(self, request, obj=None):
        """Prevent adding new journal entry lines through admin."""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Prevent changing journal entry lines through admin."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deleting journal entry lines through admin."""
        return False


@admin.register(AccountType)
class AccountTypeAdmin(admin.ModelAdmin):
    """
    إدارة أنواع الحسابات
    """

    list_display = ("name", "nature", "is_active")
    list_filter = ("nature", "is_active")
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ChartOfAccounts)
class ChartOfAccountsAdmin(admin.ModelAdmin):
    """
    إدارة دليل الحسابات
    """

    list_display = (
        "name",
        "code",
        "account_type",
        "parent",
        "opening_balance",
        "is_active",
    )
    list_filter = ("account_type", "is_active", "is_cash_account", "is_bank_account")
    search_fields = ("name", "code", "description")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("name", "code", "account_type", "parent")}),
        (
            _("الرصيد الافتتاحي"),
            {"fields": ("opening_balance", "opening_balance_date")},
        ),
        (
            _("خصائص الحساب"),
            {"fields": ("is_cash_account", "is_bank_account", "is_active")},
        ),
        (_("معلومات إضافية"), {"fields": ("description",)}),
        (_("معلومات النظام"), {"fields": ("created_at", "updated_at")}),
    )


@admin.register(AccountingPeriod)
class AccountingPeriodAdmin(admin.ModelAdmin):
    """
    إدارة الفترات المحاسبية
    """

    list_display = ("name", "start_date", "end_date", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("name",)
    readonly_fields = ("created_at",)


@admin.register(JournalEntry)
class JournalEntryAdmin(SecureJournalEntryAdmin):
    """
    إدارة القيود المحاسبية - محمية بنظام الحوكمة
    SECURITY: High-risk model - read-only with comprehensive audit logging
    """

    # Security configuration
    authoritative_service = "AccountingGateway"
    business_interface_url = "/financial/journal-entries/"
    security_warning_message = _(
        "⚠️ تحذير أمني: القيود المحاسبية محمية ولا يمكن تعديلها مباشرة. "
        "استخدم AccountingGateway للإنشاء والتعديل الآمن."
    )

    list_display = ("id", "number", "date", "entry_type", "status", "reference", "financial_category", "security_status")
    list_filter = ("entry_type", "status", "date", "accounting_period", "financial_category")
    search_fields = ("number", "reference", "description")
    readonly_fields = ("number", "created_at", "created_by", "security_info")
    inlines = [JournalEntryLineInline]
    
    fieldsets = (
        (
            _("معلومات القيد"),
            {
                "fields": (
                    "number",
                    "date",
                    "entry_type",
                    "accounting_period",
                    "reference",
                )
            },
        ),
        (_("معلومات إضافية"), {"fields": ("description", "status")}),
        (_("معلومات النظام"), {"fields": ("created_at", "created_by")}),
        (_("معلومات الأمان"), {
            "fields": ("security_info",),
            "classes": ("collapse",),
            "description": "معلومات الحماية والحوكمة للقيد المحاسبي"
        }),
    )

    def security_status(self, obj):
        """عرض حالة الأمان للقيد."""
        return format_html(
            '<span style="color: green; font-weight: bold;">🔒 محمي</span>'
        )
    security_status.short_description = _("حالة الأمان")
    
    def security_info(self, obj):
        """عرض معلومات الأمان والحوكمة."""
        return format_html(
            '<div style="background: #f8f9fa; padding: 10px; border-radius: 5px;">'
            '<strong>نظام الحوكمة:</strong><br>'
            '• الخدمة المخولة: AccountingGateway<br>'
            '• وضع القراءة فقط: نشط<br>'
            '• التدقيق الشامل: مفعل<br>'
            '• آخر تعديل: {}<br>'
            '</div>',
            obj.created_at.strftime('%Y-%m-%d %H:%M:%S') if obj.created_at else 'غير محدد'
        )
    security_info.short_description = _("معلومات الأمان")

    def save_model(self, request, obj, form, change):
        """Override to enforce governance controls."""
        # This will be blocked by SecureJournalEntryAdmin
        super().save_model(request, obj, form, change)


@admin.register(JournalEntryLine)
class JournalEntryLineAdmin(ReadOnlyModelAdmin):
    """
    إدارة بنود القيود المحاسبية - محمية بنظام الحوكمة
    SECURITY: High-risk model - read-only access only
    """

    # Security configuration
    authoritative_service = "AccountingGateway"
    business_interface_url = "/financial/journal-entries/"
    security_warning_message = _(
        "⚠️ بنود القيود المحاسبية محمية ولا يمكن تعديلها مباشرة."
    )

    list_display = ("journal_entry", "account", "debit", "credit", "description", "security_status")
    list_filter = ("journal_entry__date", "account__account_type")
    search_fields = ("journal_entry__reference", "account__name", "description")
    readonly_fields = ("created_at", "security_info")
    
    fieldsets = (
        (None, {"fields": ("journal_entry", "account")}),
        (_("المبالغ"), {"fields": ("debit", "credit")}),
        (_("معلومات إضافية"), {"fields": ("description", "cost_center", "project")}),
        (_("معلومات النظام"), {"fields": ("created_at",)}),
        (_("معلومات الأمان"), {
            "fields": ("security_info",),
            "classes": ("collapse",)
        }),
    )
    
    def security_status(self, obj):
        """عرض حالة الأمان."""
        return format_html(
            '<span style="color: green; font-weight: bold;">🔒 محمي</span>'
        )
    security_status.short_description = _("حالة الأمان")
    
    def security_info(self, obj):
        """عرض معلومات الأمان."""
        return format_html(
            '<div style="background: #f8f9fa; padding: 10px; border-radius: 5px;">'
            '<strong>نظام الحوكمة:</strong><br>'
            '• نموذج عالي المخاطر<br>'
            '• وضع القراءة فقط: نشط<br>'
            '• مرتبط بالقيد: {}<br>'
            '</div>',
            obj.journal_entry.number if obj.journal_entry else 'غير محدد'
        )
    security_info.short_description = _("معلومات الأمان")


@admin.register(PaymentSyncOperation)
class PaymentSyncOperationAdmin(admin.ModelAdmin):
    """
    إدارة عمليات تزامن المدفوعات
    """

    list_display = ("operation_id", "operation_type", "status", "created_at")
    list_filter = ("operation_type", "status", "created_at")
    search_fields = ("operation_id", "source_model", "target_model")
    readonly_fields = ("operation_id", "created_at", "completed_at")


@admin.register(PaymentSyncLog)
class PaymentSyncLogAdmin(admin.ModelAdmin):
    """
    إدارة سجلات تزامن المدفوعات
    """

    list_display = (
        "sync_operation",
        "action",
        "target_model",
        "success",
        "executed_at",
    )
    list_filter = ("action", "success", "executed_at")
    search_fields = ("target_model", "error_message")
    readonly_fields = ("executed_at", "execution_time")


# إدارة معاملات الشريك
@admin.register(PartnerTransaction)
class PartnerTransactionAdmin(admin.ModelAdmin):
    """
    إدارة معاملات الشريك في Django Admin
    """
    
    list_display = [
        'id', 'transaction_type_display', 'partner_name', 
        'amount_display', 'transaction_date', 'status_display', 
        'created_by', 'created_at'
    ]
    
    list_filter = [
        'transaction_type', 'status', 'transaction_date', 
        'contribution_type', 'withdrawal_type', 'created_at'
    ]
    
    search_fields = [
        'description', 'partner_account__name', 'cash_account__name',
        'created_by__username', 'created_by__first_name', 'created_by__last_name'
    ]
    
    readonly_fields = [
        'created_at', 'updated_at', 'approved_at', 'journal_entry_link'
    ]
    
    fieldsets = (
        (_('معلومات المعاملة'), {
            'fields': (
                'transaction_type', 'partner_account', 'cash_account', 
                'amount', 'transaction_date'
            )
        }),
        (_('تفاصيل المعاملة'), {
            'fields': (
                'contribution_type', 'withdrawal_type', 
                'description', 'notes'
            )
        }),
        (_('الحالة والموافقات'), {
            'fields': (
                'status', 'created_by', 'approved_by', 
                'approved_at'
            )
        }),
        (_('القيد المحاسبي'), {
            'fields': ('journal_entry_link',),
            'classes': ('collapse',)
        }),
        (_('معلومات التدقيق'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    date_hierarchy = 'transaction_date'
    ordering = ['-transaction_date', '-created_at']
    
    def transaction_type_display(self, obj):
        """عرض نوع المعاملة مع أيقونة"""
        if obj.transaction_type == 'contribution':
            return format_html(
                '<span style="color: green;"><i class="fas fa-plus-circle"></i> {}</span>',
                obj.get_transaction_type_display()
            )
        else:
            return format_html(
                '<span style="color: orange;"><i class="fas fa-minus-circle"></i> {}</span>',
                obj.get_transaction_type_display()
            )
    transaction_type_display.short_description = _('نوع المعاملة')
    transaction_type_display.admin_order_field = 'transaction_type'
    
    def partner_name(self, obj):
        """اسم الشريك"""
        return obj.partner_account.name if obj.partner_account else '-'
    partner_name.short_description = _('الشريك')
    partner_name.admin_order_field = 'partner_account__name'
    
    def amount_display(self, obj):
        """عرض المبلغ مع تنسيق"""
        currency = SystemSetting.get_currency_symbol()
        color = 'green' if obj.transaction_type == 'contribution' else 'orange'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}</span>',
            color, obj.amount, currency
        )
    amount_display.short_description = _('المبلغ')
    amount_display.admin_order_field = 'amount'
    
    def status_display(self, obj):
        """عرض الحالة مع ألوان"""
        colors = {
            'pending': '#ffc107',
            'approved': '#17a2b8',
            'completed': '#28a745',
            'cancelled': '#dc3545'
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 10px; font-size: 0.8em;">{}</span>',
            color, obj.get_status_display()
        )
    status_display.short_description = _('الحالة')
    status_display.admin_order_field = 'status'
    
    def journal_entry_link(self, obj):
        """رابط للقيد المحاسبي"""
        if obj.journal_entry:
            url = reverse('financial:journal_entries_detail', kwargs={'pk': obj.journal_entry.id})
            return format_html(
                '<a href="{}" target="_blank">القيد رقم {} <i class="fas fa-external-link-alt"></i></a>',
                url, obj.journal_entry.number
            )
        return '-'
    journal_entry_link.short_description = _('القيد المحاسبي')
    
    def get_queryset(self, request):
        """تحسين الاستعلام"""
        return super().get_queryset(request).select_related(
            'partner_account', 'cash_account', 'created_by', 
            'approved_by', 'journal_entry'
        )
    
    def save_model(self, request, obj, form, change):
        """حفظ النموذج مع تحديث المنشئ"""
        if not change:  # إنشاء جديد
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PartnerBalance)
class PartnerBalanceAdmin(admin.ModelAdmin):
    """
    إدارة أرصدة الشركاء في Django Admin
    """
    
    list_display = [
        'partner_name', 'total_contributions_display', 
        'total_withdrawals_display', 'current_balance_display',
        'last_transaction_date', 'updated_at'
    ]
    
    readonly_fields = [
        'total_contributions', 'total_withdrawals', 'current_balance',
        'last_transaction_date', 'updated_at'
    ]
    
    search_fields = ['partner_account__name']
    
    def partner_name(self, obj):
        """اسم الشريك"""
        return obj.partner_account.name if obj.partner_account else '-'
    partner_name.short_description = _('الشريك')
    partner_name.admin_order_field = 'partner_account__name'
    
    def total_contributions_display(self, obj):
        """عرض إجمالي المساهمات"""
        currency = SystemSetting.get_currency_symbol()
        return format_html(
            '<span style="color: green; font-weight: bold;">{} {}</span>',
            obj.total_contributions, currency
        )
    total_contributions_display.short_description = _('إجمالي المساهمات')
    total_contributions_display.admin_order_field = 'total_contributions'
    
    def total_withdrawals_display(self, obj):
        """عرض إجمالي السحوبات"""
        currency = SystemSetting.get_currency_symbol()
        return format_html(
            '<span style="color: orange; font-weight: bold;">{} {}</span>',
            obj.total_withdrawals, currency
        )
    total_withdrawals_display.short_description = _('إجمالي السحوبات')
    total_withdrawals_display.admin_order_field = 'total_withdrawals'
    
    def current_balance_display(self, obj):
        """عرض الرصيد الحالي"""
        currency = SystemSetting.get_currency_symbol()
        color = 'green' if obj.current_balance >= 0 else 'red'
        return format_html(
            '<span style="color: {}; font-weight: bold; font-size: 1.1em;">{} {}</span>',
            color, obj.current_balance, currency
        )
    current_balance_display.short_description = _('الرصيد الحالي')
    current_balance_display.admin_order_field = 'current_balance'
    
    def get_queryset(self, request):
        """تحسين الاستعلام"""
        return super().get_queryset(request).select_related('partner_account')
    
    def has_add_permission(self, request):
        """منع الإضافة اليدوية - يتم الإنشاء تلقائياً"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """منع الحذف"""
        return False
    
    actions = ['update_balances']
    
    def update_balances(self, request, queryset):
        """إجراء لتحديث الأرصدة"""
        updated_count = 0
        for balance in queryset:
            balance.update_balance()
            updated_count += 1
        
        self.message_user(
            request,
            f'تم تحديث {updated_count} رصيد بنجاح.'
        )
    update_balances.short_description = _('تحديث الأرصدة المحددة')


@admin.register(InvoiceAuditLog)
class InvoiceAuditLogAdmin(admin.ModelAdmin):
    """
    واجهة إدارة سجلات تدقيق الفواتير
    """

    list_display = [
        "id",
        "invoice_display",
        "action_type_display",
        "difference_display",
        "adjustment_entry_link",
        "created_by",
        "created_at",
    ]

    list_filter = [
        "invoice_type",
        "action_type",
        "created_at",
    ]

    search_fields = [
        "invoice_number",
        "reason",
        "notes",
    ]

    readonly_fields = [
        "invoice_type",
        "invoice_id",
        "invoice_number",
        "action_type",
        "old_total",
        "old_cost",
        "new_total",
        "new_cost",
        "total_difference",
        "cost_difference",
        "adjustment_entry",
        "created_at",
        "created_by",
    ]

    fieldsets = (
        (
            _("معلومات الفاتورة"),
            {
                "fields": (
                    "invoice_type",
                    "invoice_id",
                    "invoice_number",
                    "action_type",
                )
            },
        ),
        (
            _("القيم القديمة"),
            {
                "fields": (
                    "old_total",
                    "old_cost",
                )
            },
        ),
        (
            _("القيم الجديدة"),
            {
                "fields": (
                    "new_total",
                    "new_cost",
                )
            },
        ),
        (
            _("الفروقات"),
            {
                "fields": (
                    "total_difference",
                    "cost_difference",
                )
            },
        ),
        (
            _("القيد التصحيحي"),
            {
                "fields": ("adjustment_entry",)
            },
        ),
        (
            _("التفاصيل"),
            {
                "fields": (
                    "reason",
                    "notes",
                )
            },
        ),
        (
            _("معلومات التتبع"),
            {
                "fields": (
                    "created_at",
                    "created_by",
                )
            },
        ),
    )

    def invoice_display(self, obj):
        """عرض معلومات الفاتورة"""
        return f"{obj.get_invoice_type_display()} - {obj.invoice_number}"

    invoice_display.short_description = _("الفاتورة")

    def action_type_display(self, obj):
        """عرض نوع الإجراء مع أيقونة"""
        if obj.action_type == "adjustment":
            return format_html(
                '<span style="color: #ff9800;">⚙️ {}</span>',
                obj.get_action_type_display(),
            )
        return obj.get_action_type_display()

    action_type_display.short_description = _("نوع الإجراء")

    def difference_display(self, obj):
        """عرض الفرق مع لون حسب الاتجاه"""
        if obj.total_difference > 0:
            color = "#4caf50"  # أخضر للزيادة
            icon = "↑"
        elif obj.total_difference < 0:
            color = "#f44336"  # أحمر للنقص
            icon = "="
        else:
            color = "#9e9e9e"  # رمادي لعدم التغيير
            icon = "="

        currency = SystemSetting.get_currency_symbol()
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {} {}</span>',
            color,
            icon,
            abs(obj.total_difference),
            currency
        )

    difference_display.short_description = _("الفرق")

    def adjustment_entry_link(self, obj):
        """رابط للقيد التصحيحي"""
        if obj.adjustment_entry:
            url = reverse(
                "financial:journal_entries_detail",
                kwargs={'pk': obj.adjustment_entry.id},
            )
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                url,
                obj.adjustment_entry.number,
            )
        return "-"

    adjustment_entry_link.short_description = _("القيد التصحيحي")

    def has_add_permission(self, request):
        """منع الإضافة اليدوية - يتم الإنشاء تلقائياً"""
        return False

    def has_delete_permission(self, request, obj=None):
        """منع الحذف - للحفاظ على الأثر التدقيقي"""
        return False


@admin.register(ValidationAuditLog)
class ValidationAuditLogAdmin(admin.ModelAdmin):
    """
    واجهة إدارة سجلات تدقيق التحقق من المعاملات المالية
    
    عرض للقراءة فقط لجميع محاولات التحقق المرفوضة
    """
    
    list_display = [
        'id',
        'timestamp_display',
        'user_display',
        'entity_display',
        'validation_type_display',
        'module_display',
        'transaction_info_display',
        'is_bypass_display',
    ]
    
    list_filter = [
        'entity_type',
        'validation_type',
        'module',
        'timestamp',
        'is_bypass_attempt',
        'transaction_type',
    ]
    
    search_fields = [
        'entity_name',
        'user__username',
        'user__first_name',
        'user__last_name',
        'failure_reason',
        'error_message',
        'view_name',
        'request_path',
    ]
    
    readonly_fields = [
        'timestamp',
        'user',
        'entity_type',
        'entity_id',
        'entity_name',
        'transaction_type',
        'transaction_date',
        'transaction_amount',
        'validation_type',
        'failure_reason',
        'error_message',
        'module',
        'view_name',
        'request_path',
        'is_bypass_attempt',
        'bypass_reason',
        'ip_address',
        'user_agent',
    ]
    
    fieldsets = (
        (_('معلومات المحاولة'), {
            'fields': (
                'timestamp',
                'user',
                'ip_address',
            )
        }),
        (_('معلومات الكيان'), {
            'fields': (
                'entity_type',
                'entity_id',
                'entity_name',
            )
        }),
        (_('معلومات المعاملة'), {
            'fields': (
                'transaction_type',
                'transaction_date',
                'transaction_amount',
            )
        }),
        (_('معلومات الفشل'), {
            'fields': (
                'validation_type',
                'failure_reason',
                'error_message',
            )
        }),
        (_('معلومات النظام'), {
            'fields': (
                'module',
                'view_name',
                'request_path',
            )
        }),
        (_('محاولة التجاوز'), {
            'fields': (
                'is_bypass_attempt',
                'bypass_reason',
            ),
            'classes': ('collapse',)
        }),
        (_('معلومات تقنية'), {
            'fields': (
                'user_agent',
            ),
            'classes': ('collapse',)
        }),
    )
    
    date_hierarchy = 'timestamp'
    ordering = ['-timestamp']
    
    def timestamp_display(self, obj):
        """عرض الوقت مع تنسيق"""
        from django.utils.formats import date_format
        return date_format(obj.timestamp, 'SHORT_DATETIME_FORMAT')
    timestamp_display.short_description = _('وقت المحاولة')
    timestamp_display.admin_order_field = 'timestamp'
    
    def user_display(self, obj):
        """عرض المستخدم"""
        if obj.user:
            return format_html(
                '<span title="{}">{}</span>',
                obj.user.username,
                obj.user.get_full_name() or obj.user.username
            )
        return '-'
    user_display.short_description = _('المستخدم')
    user_display.admin_order_field = 'user__username'
    
    def entity_display(self, obj):
        """عرض معلومات الكيان"""
        entity_type_color = {
            'student': '#2196F3',
            'supplier': '#FF9800',
            'employee': '#4CAF50',
            'activity': '#9C27B0',
            'transportation_route': '#00BCD4',
            'product': '#795548',
            'sale': '#8BC34A',
            'purchase': '#FFC107',
            'other': '#9E9E9E',
        }
        color = entity_type_color.get(obj.entity_type, '#9E9E9E')
        
        return format_html(
            '<div style="line-height: 1.4;">'
            '<span style="background-color: {}; color: white; padding: 2px 6px; '
            'border-radius: 3px; font-size: 0.75em; display: inline-block; margin-bottom: 2px;">{}</span><br>'
            '<strong>{}</strong>'
            '</div>',
            color,
            obj.get_entity_type_display(),
            obj.entity_name
        )
    entity_display.short_description = _('الكيان')
    entity_display.admin_order_field = 'entity_type'
    
    def validation_type_display(self, obj):
        """عرض نوع التحقق مع أيقونة"""
        validation_icons = {
            'chart_of_accounts': '💼',
            'accounting_period': '📅',
            'both': '⚠️',
        }
        icon = validation_icons.get(obj.validation_type, '❓')
        
        validation_colors = {
            'chart_of_accounts': '#FF5722',
            'accounting_period': '#3F51B5',
            'both': '#F44336',
        }
        color = validation_colors.get(obj.validation_type, '#9E9E9E')
        
        return format_html(
            '<span style="color: {}; font-weight: bold;" title="{}">{} {}</span>',
            color,
            obj.failure_reason,
            icon,
            obj.get_validation_type_display()
        )
    validation_type_display.short_description = _('نوع التحقق')
    validation_type_display.admin_order_field = 'validation_type'
    
    def module_display(self, obj):
        """عرض الوحدة"""
        module_colors = {
            'students': '#2196F3',
            'financial': '#4CAF50',
            'activities': '#9C27B0',
            'transportation': '#00BCD4',
            'product': '#795548',
            'sale': '#8BC34A',
            'purchase': '#FFC107',
            'supplier': '#FF9800',
            'hr': '#E91E63',
            'other': '#9E9E9E',
        }
        color = module_colors.get(obj.module, '#9E9E9E')
        
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 10px; font-size: 0.8em;">{}</span>',
            color,
            obj.get_module_display()
        )
    module_display.short_description = _('الوحدة')
    module_display.admin_order_field = 'module'
    
    def transaction_info_display(self, obj):
        """عرض معلومات المعاملة"""
        if obj.transaction_type or obj.transaction_date or obj.transaction_amount:
            info_parts = []
            
            if obj.transaction_type:
                info_parts.append(f'<strong>{obj.transaction_type}</strong>')
            
            if obj.transaction_date:
                from django.utils.formats import date_format
                info_parts.append(date_format(obj.transaction_date, 'SHORT_DATE_FORMAT'))
            
            if obj.transaction_amount:
                currency = SystemSetting.get_currency_symbol()
                info_parts.append(f'{obj.transaction_amount} {currency}')
            
            return format_html('<div style="line-height: 1.4;">{}</div>', '<br>'.join(info_parts))
        return '-'
    transaction_info_display.short_description = _('معلومات المعاملة')
    
    def is_bypass_display(self, obj):
        """عرض حالة التجاوز"""
        if obj.is_bypass_attempt:
            return format_html(
                '<span style="background-color: #FF9800; color: white; padding: 3px 8px; '
                'border-radius: 10px; font-size: 0.75em;" title="{}">⚠️ تجاوز</span>',
                obj.bypass_reason or 'لا يوجد سبب'
            )
        return '-'
    is_bypass_display.short_description = _('تجاوز')
    is_bypass_display.admin_order_field = 'is_bypass_attempt'
    
    def get_queryset(self, request):
        """تحسين الاستعلام"""
        return super().get_queryset(request).select_related('user')
    
    def has_add_permission(self, request):
        """منع الإضافة اليدوية - يتم الإنشاء تلقائياً من النظام"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """منع الحذف - للحفاظ على الأثر التدقيقي"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """منع التعديل - للقراءة فقط"""
        return False
    
    # إضافة إجراءات مخصصة
    actions = ['export_to_csv']
    
    def export_to_csv(self, request, queryset):
        """تصدير السجلات المحددة إلى CSV"""
        import csv
        from django.http import HttpResponse
        from django.utils import timezone
        
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = f'attachment; filename="validation_audit_log_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        # إضافة BOM لدعم العربية في Excel
        response.write('\ufeff')
        
        writer = csv.writer(response)
        writer.writerow([
            'الوقت',
            'المستخدم',
            'نوع الكيان',
            'اسم الكيان',
            'نوع التحقق',
            'سبب الفشل',
            'رسالة الخطأ',
            'الوحدة',
            'نوع المعاملة',
            'تاريخ المعاملة',
            'مبلغ المعاملة',
            'محاولة تجاوز',
        ])
        
        for obj in queryset:
            writer.writerow([
                obj.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                obj.user.get_full_name() if obj.user else '-',
                obj.get_entity_type_display(),
                obj.entity_name,
                obj.get_validation_type_display(),
                obj.failure_reason,
                obj.error_message,
                obj.get_module_display(),
                obj.transaction_type or '-',
                obj.transaction_date.strftime('%Y-%m-%d') if obj.transaction_date else '-',
                str(obj.transaction_amount) if obj.transaction_amount else '-',
                'نعم' if obj.is_bypass_attempt else 'لا',
            ])
        
        self.message_user(
            request,
            f'تم تصدير {queryset.count()} سجل بنجاح.'
        )
        
        return response
    export_to_csv.short_description = _('تصدير السجلات المحددة إلى CSV')


@admin.register(FinancialCategory)
class FinancialCategoryAdmin(admin.ModelAdmin):
    """
    إدارة التصنيفات المالية
    """
    
    list_display = (
        'code',
        'name',
        'revenue_account_display',
        'expense_account_display',
        'is_active',
        'display_order',
    )
    
    list_filter = ('is_active',)
    
    search_fields = ('code', 'name', 'description')
    
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (_('المعلومات الأساسية'), {
            'fields': ('code', 'name', 'description')
        }),
        (_('الحسابات المحاسبية'), {
            'fields': ('default_revenue_account', 'default_expense_account')
        }),
        (_('الإعدادات'), {
            'fields': ('is_active', 'display_order')
        }),
        (_('معلومات النظام'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    ordering = ('display_order', 'name')
    
    def revenue_account_display(self, obj):
        if obj.default_revenue_account:
            return f"{obj.default_revenue_account.code} - {obj.default_revenue_account.name}"
        return "-"
    revenue_account_display.short_description = _("حساب الإيرادات")
    
    def expense_account_display(self, obj):
        if obj.default_expense_account:
            return f"{obj.default_expense_account.code} - {obj.default_expense_account.name}"
        return "-"
    expense_account_display.short_description = _("حساب المصروفات")


@admin.register(FinancialSubcategory)
class FinancialSubcategoryAdmin(admin.ModelAdmin):
    """
    إدارة التصنيفات المالية الفرعية
    """
    
    list_display = (
        'code',
        'name',
        'parent_category',
        'is_active',
        'display_order',
    )
    
    list_filter = ('is_active', 'parent_category')
    
    search_fields = ('code', 'name', 'parent_category__name')
    
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (_('المعلومات الأساسية'), {
            'fields': ('parent_category', 'code', 'name')
        }),
        (_('الإعدادات'), {
            'fields': ('is_active', 'display_order')
        }),
        (_('معلومات النظام'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    ordering = ('parent_category', 'display_order', 'name')

    def revenue_account_display(self, obj):
        """عرض حساب الإيرادات"""
        if obj.default_revenue_account:
            return format_html(
                '<span style="color: #4CAF50;">{} - {}</span>',
                obj.default_revenue_account.code,
                obj.default_revenue_account.name
            )
        return format_html('<span style="color: #9E9E9E;">-</span>')
    revenue_account_display.short_description = _('حساب الإيرادات')
    
    def expense_account_display(self, obj):
        """عرض حساب المصروفات"""
        if obj.default_expense_account:
            return format_html(
                '<span style="color: #FF5722;">{} - {}</span>',
                obj.default_expense_account.code,
                obj.default_expense_account.name
            )
        return format_html('<span style="color: #9E9E9E;">-</span>')
    expense_account_display.short_description = _('حساب المصروفات')
