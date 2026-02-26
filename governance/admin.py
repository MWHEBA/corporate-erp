from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils import timezone
from .models import IdempotencyRecord, AuditTrail, QuarantineRecord, AuthorityDelegation
import json


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(admin.ModelAdmin):
    list_display = [
        'operation_type', 
        'idempotency_key', 
        'created_by', 
        'created_at', 
        'expires_at',
        'is_expired_display'
    ]
    list_filter = [
        'operation_type', 
        'created_at', 
        'expires_at',
        'created_by'
    ]
    search_fields = [
        'operation_type', 
        'idempotency_key',
        'created_by__username'
    ]
    readonly_fields = [
        'created_at', 
        'result_data_display',
        'is_expired_display'
    ]
    ordering = ['-created_at']
    
    def is_expired_display(self, obj):
        if obj.is_expired():
            return format_html('<span style="color: red;">منتهي الصلاحية</span>')
        return format_html('<span style="color: green;">صالح</span>')
    is_expired_display.short_description = 'الحالة'
    
    def result_data_display(self, obj):
        if obj.result_data:
            formatted_json = json.dumps(obj.result_data, indent=2, ensure_ascii=False)
            return format_html('<pre>{}</pre>', formatted_json)
        return 'لا توجد بيانات'
    result_data_display.short_description = 'بيانات النتيجة'
    
    def has_delete_permission(self, request, obj=None):
        # Only allow deletion of expired records
        if obj and not obj.is_expired():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(AuditTrail)
class AuditTrailAdmin(admin.ModelAdmin):
    list_display = [
        'model_name',
        'object_id', 
        'operation',
        'user',
        'source_service',
        'timestamp',
        'has_changes_display'
    ]
    list_filter = [
        'model_name',
        'operation',
        'source_service',
        'timestamp',
        'user'
    ]
    search_fields = [
        'model_name',
        'object_id',
        'user__username',
        'source_service'
    ]
    readonly_fields = [
        'timestamp',
        'before_data_display',
        'after_data_display',
        'additional_context_display',
        'changes_summary'
    ]
    ordering = ['-timestamp']
    date_hierarchy = 'timestamp'
    
    def has_changes_display(self, obj):
        if obj.before_data or obj.after_data:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: gray;">-</span>')
    has_changes_display.short_description = 'تغييرات'
    
    def before_data_display(self, obj):
        if obj.before_data:
            formatted_json = json.dumps(obj.before_data, indent=2, ensure_ascii=False)
            return format_html('<pre>{}</pre>', formatted_json)
        return 'لا توجد بيانات'
    before_data_display.short_description = 'البيانات السابقة'
    
    def after_data_display(self, obj):
        if obj.after_data:
            formatted_json = json.dumps(obj.after_data, indent=2, ensure_ascii=False)
            return format_html('<pre>{}</pre>', formatted_json)
        return 'لا توجد بيانات'
    after_data_display.short_description = 'البيانات الجديدة'
    
    def additional_context_display(self, obj):
        if obj.additional_context:
            formatted_json = json.dumps(obj.additional_context, indent=2, ensure_ascii=False)
            return format_html('<pre>{}</pre>', formatted_json)
        return 'لا توجد بيانات إضافية'
    additional_context_display.short_description = 'السياق الإضافي'
    
    def changes_summary(self, obj):
        if obj.before_data and obj.after_data:
            changes = []
            for key in set(list(obj.before_data.keys()) + list(obj.after_data.keys())):
                old_val = obj.before_data.get(key, 'غير موجود')
                new_val = obj.after_data.get(key, 'محذوف')
                if old_val != new_val:
                    changes.append(f"{key}: {old_val} → {new_val}")
            
            if changes:
                return format_html('<br>'.join(changes))
        return 'لا توجد تغييرات'
    changes_summary.short_description = 'ملخص التغييرات'
    
    def has_add_permission(self, request):
        # Audit trails should only be created programmatically
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Audit trails should be immutable
        return False


@admin.register(QuarantineRecord)
class QuarantineRecordAdmin(admin.ModelAdmin):
    list_display = [
        'model_name',
        'object_id',
        'corruption_type',
        'status',
        'quarantined_by',
        'quarantined_at',
        'resolved_by',
        'resolved_at'
    ]
    list_filter = [
        'model_name',
        'corruption_type',
        'status',
        'quarantined_at',
        'resolved_at'
    ]
    search_fields = [
        'model_name',
        'object_id',
        'quarantine_reason',
        'quarantined_by__username'
    ]
    readonly_fields = [
        'quarantined_at',
        'original_data_display',
        'quarantine_reason_display'
    ]
    ordering = ['-quarantined_at']
    date_hierarchy = 'quarantined_at'
    
    fieldsets = (
        ('معلومات الحجر الصحي', {
            'fields': (
                'model_name',
                'object_id', 
                'corruption_type',
                'quarantine_reason_display',
                'quarantined_by',
                'quarantined_at'
            )
        }),
        ('البيانات الأصلية', {
            'fields': ('original_data_display',),
            'classes': ('collapse',)
        }),
        ('حالة الحل', {
            'fields': (
                'status',
                'resolution_notes',
                'resolved_by',
                'resolved_at'
            )
        })
    )
    
    def original_data_display(self, obj):
        if obj.original_data:
            formatted_json = json.dumps(obj.original_data, indent=2, ensure_ascii=False)
            return format_html('<pre>{}</pre>', formatted_json)
        return 'لا توجد بيانات'
    original_data_display.short_description = 'البيانات الأصلية'
    
    def quarantine_reason_display(self, obj):
        return format_html('<div style="max-width: 400px; word-wrap: break-word;">{}</div>', obj.quarantine_reason)
    quarantine_reason_display.short_description = 'سبب الحجر الصحي'
    
    def save_model(self, request, obj, form, change):
        if change and obj.status == 'RESOLVED' and not obj.resolved_by:
            obj.resolved_by = request.user
            obj.resolved_at = timezone.now()
        super().save_model(request, obj, form, change)


@admin.register(AuthorityDelegation)
class AuthorityDelegationAdmin(admin.ModelAdmin):
    list_display = [
        'from_service',
        'to_service',
        'model_name',
        'granted_by',
        'granted_at',
        'expires_at',
        'is_active',
        'status_display'
    ]
    list_filter = [
        'from_service',
        'to_service',
        'model_name',
        'is_active',
        'granted_at',
        'expires_at'
    ]
    search_fields = [
        'from_service',
        'to_service',
        'model_name',
        'reason',
        'granted_by__username'
    ]
    readonly_fields = [
        'granted_at',
        'is_expired_display',
        'is_valid_display',
        'time_remaining'
    ]
    ordering = ['-granted_at']
    date_hierarchy = 'granted_at'
    
    fieldsets = (
        ('معلومات التفويض', {
            'fields': (
                'from_service',
                'to_service',
                'model_name',
                'reason'
            )
        }),
        ('التوقيت', {
            'fields': (
                'granted_at',
                'expires_at',
                'time_remaining',
                'is_expired_display'
            )
        }),
        ('الحالة', {
            'fields': (
                'is_active',
                'is_valid_display',
                'granted_by'
            )
        }),
        ('الإلغاء', {
            'fields': (
                'revoked_at',
                'revoked_by'
            ),
            'classes': ('collapse',)
        })
    )
    
    def status_display(self, obj):
        if obj.is_valid():
            return format_html('<span style="color: green;">صالح</span>')
        elif obj.is_expired():
            return format_html('<span style="color: red;">منتهي الصلاحية</span>')
        elif obj.revoked_at:
            return format_html('<span style="color: orange;">ملغي</span>')
        else:
            return format_html('<span style="color: gray;">غير نشط</span>')
    status_display.short_description = 'الحالة'
    
    def is_expired_display(self, obj):
        if obj.is_expired():
            return format_html('<span style="color: red;">منتهي الصلاحية</span>')
        return format_html('<span style="color: green;">صالح</span>')
    is_expired_display.short_description = 'انتهاء الصلاحية'
    
    def is_valid_display(self, obj):
        if obj.is_valid():
            return format_html('<span style="color: green;">✓ صالح</span>')
        return format_html('<span style="color: red;">✗ غير صالح</span>')
    is_valid_display.short_description = 'صالح للاستخدام'
    
    def time_remaining(self, obj):
        from django.utils import timezone
        if obj.is_expired():
            return 'منتهي الصلاحية'
        
        remaining = obj.expires_at - timezone.now()
        hours = remaining.total_seconds() / 3600
        
        if hours < 1:
            minutes = remaining.total_seconds() / 60
            return f'{int(minutes)} دقيقة'
        elif hours < 24:
            return f'{int(hours)} ساعة'
        else:
            days = hours / 24
            return f'{int(days)} يوم'
    time_remaining.short_description = 'الوقت المتبقي'
    
    def save_model(self, request, obj, form, change):
        if not change:  # New delegation
            obj.granted_by = request.user
        super().save_model(request, obj, form, change)
    
    actions = ['revoke_delegations']
    
    def revoke_delegations(self, request, queryset):
        count = 0
        for delegation in queryset.filter(is_active=True, revoked_at__isnull=True):
            delegation.revoke(request.user, "إلغاء من لوحة الإدارة")
            count += 1
        
        self.message_user(request, f'تم إلغاء {count} تفويض بنجاح.')
    revoke_delegations.short_description = 'إلغاء التفويضات المحددة'
