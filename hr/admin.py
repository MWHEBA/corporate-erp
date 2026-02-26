"""
إعدادات Admin لوحدة الموارد البشرية
"""
from django.contrib import admin
from .models import (
    Employee, Department, JobTitle,
    Shift, Attendance,
    LeaveType, LeaveBalance, Leave,
    PermissionType, PermissionRequest,
    Payroll, Advance, AdvanceInstallment,
    SalaryComponent, SalaryComponentTemplate, PayrollLine,
    ContractSalaryComponent  # TEMP: سيتم إزالته لاحقاً
)
from .models.contract import Contract, ContractAmendment, ContractDocument, ContractIncrease
from .models.payroll_payment import PayrollPayment


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['code', 'name_ar', 'parent', 'manager', 'employees_count', 'is_active']
    list_filter = ['is_active', 'parent']
    search_fields = ['code', 'name_ar', 'name_en']
    ordering = ['code']


@admin.register(JobTitle)
class JobTitleAdmin(admin.ModelAdmin):
    list_display = ['code', 'title_ar', 'department', 'is_active']
    list_filter = ['is_active', 'department']
    search_fields = ['code', 'title_ar', 'title_en']
    ordering = ['code']


class SalaryComponentInline(admin.TabularInline):
    """Inline لعرض بنود الراتب في صفحة الموظف"""
    model = SalaryComponent
    extra = 0
    fields = ['code', 'name', 'component_type', 'calculation_method', 'amount', 'percentage', 'is_active', 'effective_from', 'effective_to']
    readonly_fields = ['created_at']
    ordering = ['component_type', 'order']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('template', 'contract')


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['employee_number', 'get_full_name_ar', 'department', 'job_title', 'status', 'hire_date']
    list_filter = ['status', 'department', 'employment_type', 'gender']
    search_fields = ['employee_number', 'name', 'national_id', 'work_email']
    ordering = ['employee_number']
    date_hierarchy = 'hire_date'
    inlines = [SalaryComponentInline]
    
    fieldsets = (
        ('معلومات المستخدم', {
            'fields': ('user', 'employee_number', 'created_by')
        }),
        ('المعلومات الشخصية', {
            'fields': (
                'name',
                'national_id', 'birth_date', 'gender',
                'nationality', 'marital_status', 'military_status'
            )
        }),
        ('معلومات الاتصال', {
            'fields': (
                ('personal_email', 'work_email'),
                ('mobile_phone', 'home_phone'),
                'address', ('city', 'postal_code')
            )
        }),
        ('جهة اتصال الطوارئ', {
            'fields': ('emergency_contact_name', 'emergency_contact_relation', 'emergency_contact_phone')
        }),
        ('المعلومات الوظيفية', {
            'fields': (
                'department', 'job_title', 'direct_manager',
                'hire_date', 'employment_type'
            )
        }),
        ('الحالة', {
            'fields': ('status', 'termination_date', 'termination_reason')
        }),
        ('الصورة', {
            'fields': ('photo',)
        }),
    )


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ['name', 'shift_type', 'start_time', 'end_time', 'work_hours', 'is_active']
    list_filter = ['shift_type', 'is_active']
    search_fields = ['name']


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['employee', 'date', 'check_in', 'check_out', 'work_hours', 'late_minutes', 'status']
    list_filter = ['status', 'date', 'shift']
    search_fields = ['employee__name', 'employee__employee_number']
    date_hierarchy = 'date'
    ordering = ['-date']


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ['code', 'name_ar', 'max_days_per_year', 'is_paid', 'requires_approval', 'is_active']
    list_filter = ['is_paid', 'requires_approval', 'is_active']
    search_fields = ['code', 'name_ar', 'name_en']


@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ['employee', 'leave_type', 'year', 'total_days', 'used_days', 'remaining_days']
    list_filter = ['year', 'leave_type']
    search_fields = ['employee__name']


@admin.register(Leave)
class LeaveAdmin(admin.ModelAdmin):
    list_display = ['employee', 'leave_type', 'start_date', 'end_date', 'days_count', 'status']
    date_hierarchy = 'start_date'
    ordering = ['-start_date']


class PayrollLineInline(admin.TabularInline):
    """
    Secure inline for PayrollLine with authority boundary enforcement.
    
    This inline prevents unauthorized modifications to payroll line items
    and provides read-only access for viewing detailed salary breakdowns.
    """
    model = PayrollLine
    extra = 0
    
    # Make all fields read-only to prevent unauthorized modifications
    fields = ['code', 'name', 'component_type', 'quantity', 'rate', 'amount', 'description', 'order']
    readonly_fields = ['code', 'name', 'component_type', 'quantity', 'rate', 'amount', 
                      'description', 'calculation_details', 'order', 'created_at']
    ordering = ['component_type', 'order']
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        """Prevent adding new payroll lines through admin."""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Prevent changing payroll lines through admin."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deleting payroll lines through admin."""
        return False


@admin.register(Payroll)
class PayrollAdmin(admin.ModelAdmin):
    """
    Secure admin for Payroll model with authority boundary enforcement.
    
    This admin class implements comprehensive security controls for payroll records:
    - Read-only mode to prevent unauthorized modifications
    - Authority boundary enforcement through PayrollGateway
    - Comprehensive audit logging for all access attempts
    - Warnings for operations affecting payroll integrity
    - Redirect to business interface for safe operations
    """
    
    # Security configuration
    is_high_risk_model = True
    read_only_mode = True
    allow_bulk_actions = False
    allow_inline_edits = False
    require_special_permission = True
    authoritative_service = "PayrollGateway"
    business_interface_url = "/hr/payroll/"
    
    list_display = ['employee', 'month', 'gross_salary', 'total_deductions', 'net_salary', 'status', 'security_status']
    list_filter = ['status', 'month', 'payment_method', 'processed_by']
    search_fields = ['employee__name', 'employee__employee_number']
    date_hierarchy = 'month'
    ordering = ['-month']
    
    # Make all fields read-only to prevent unauthorized modifications
    readonly_fields = [
        'employee', 'month', 'contract', 'basic_salary', 'allowances',
        'overtime_hours', 'overtime_rate', 'overtime_amount', 'bonus',
        'social_insurance', 'tax', 'absence_days', 'absence_deduction',
        'late_deduction', 'advance_deduction', 'other_deductions',
        'gross_salary', 'total_additions', 'total_deductions', 'net_salary',
        'status', 'payment_method', 'payment_date', 'payment_reference',
        'journal_entry', 'notes', 'created_at', 'updated_at', 'processed_at',
        'processed_by', 'approved_by', 'approved_at', 'paid_by', 'paid_at',
        'payment_account'
    ]
    
    fieldsets = (
        ('⚠️ تحذير أمني', {
            'description': 'هذا السجل محمي ولا يمكن تعديله مباشرة. استخدم PayrollGateway للعمليات الآمنة.',
            'fields': (),
            'classes': ('collapse',)
        }),
        ('معلومات أساسية', {
            'fields': ('employee', 'month', 'contract', 'processed_by')
        }),
        ('مكونات الراتب', {
            'fields': ('basic_salary', 'allowances', 'overtime_hours', 'overtime_rate', 'overtime_amount', 'bonus')
        }),
        ('الخصومات', {
            'fields': ('social_insurance', 'tax', 'absence_days', 'absence_deduction', 
                      'late_deduction', 'advance_deduction', 'other_deductions')
        }),
        ('الإجماليات', {
            'fields': ('gross_salary', 'total_additions', 'total_deductions', 'net_salary')
        }),
        ('الحالة والدفع', {
            'fields': ('status', 'payment_method', 'payment_date', 'payment_reference', 'payment_account')
        }),
        ('القيد المحاسبي', {
            'fields': ('journal_entry',),
            'classes': ('collapse',)
        }),
        ('معلومات الاعتماد والدفع', {
            'fields': ('approved_by', 'approved_at', 'paid_by', 'paid_at'),
            'classes': ('collapse',)
        }),
        ('ملاحظات', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at', 'processed_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """Override queryset to add security logging."""
        queryset = super().get_queryset(request)
        
        # Log queryset access for audit trail
        self._log_admin_access_attempt(
            request,
            'queryset_access',
            'allowed',
            additional_context={
                'queryset_count': queryset.count()
            }
        )
        
        return queryset.select_related('employee', 'contract', 'processed_by', 'approved_by', 'paid_by', 'journal_entry')
    
    def security_status(self, obj):
        """Display security status indicator."""
        from django.utils.html import format_html
        
        if obj.journal_entry:
            return format_html(
                '<span style="color: green;">🔒 محمي - مرتبط بقيد محاسبي</span>'
            )
        else:
            return format_html(
                '<span style="color: orange;">⚠️ غير مرتبط بقيد محاسبي</span>'
            )
    security_status.short_description = 'حالة الأمان'
    
    def has_add_permission(self, request):
        """Prevent adding new payroll records through admin."""
        self._log_admin_access_attempt(request, 'add_attempt', 'blocked')
        return False
    
    def has_change_permission(self, request, obj=None):
        """Allow viewing but prevent changing payroll records."""
        if obj:
            self._log_admin_access_attempt(
                request, 
                'change_attempt', 
                'view_only',
                additional_context={'payroll_id': obj.id, 'employee': str(obj.employee)}
            )
        return super().has_view_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of payroll records."""
        if obj:
            self._log_admin_access_attempt(
                request,
                'delete_attempt',
                'blocked',
                additional_context={'payroll_id': obj.id, 'employee': str(obj.employee)}
            )
        return False
    
    def save_model(self, request, obj, form, change):
        """Override save_model to detect bypass attempts."""
        from governance.exceptions import AuthorityViolationError
        from django.contrib import messages
        
        # Log bypass attempt
        self._log_admin_access_attempt(
            request,
            'save_model_bypass_attempt',
            'blocked',
            additional_context={
                'payroll_id': getattr(obj, 'pk', None),
                'employee': str(obj.employee) if obj.employee else None,
                'change': change,
                'form_data': form.cleaned_data if hasattr(form, 'cleaned_data') else None
            }
        )
        
        # Show error message
        messages.error(
            request,
            "❌ محاولة تجاوز أمني محظورة: لا يمكن حفظ التغييرات على قسائم الرواتب. "
            "استخدم PayrollGateway للعمليات الآمنة."
        )
        
        # Raise governance error
        raise AuthorityViolationError(
            f"Admin save_model bypass attempt blocked for Payroll",
            error_code="ADMIN_PAYROLL_SAVE_BYPASS_BLOCKED",
            context={
                'model': 'hr.Payroll',
                'user': request.user.username,
                'payroll_id': getattr(obj, 'pk', None)
            }
        )
    
    def delete_model(self, request, obj):
        """Override delete_model to prevent unauthorized deletions."""
        from governance.exceptions import AuthorityViolationError
        from django.contrib import messages
        
        self._log_admin_access_attempt(
            request,
            'delete_model_bypass_attempt',
            'blocked',
            additional_context={
                'payroll_id': obj.pk,
                'employee': str(obj.employee)
            }
        )
        
        messages.error(
            request,
            "❌ محاولة حذف محظورة: لا يمكن حذف قسائم الرواتب للحفاظ على سلامة البيانات."
        )
        
        raise AuthorityViolationError(
            f"Admin delete_model bypass attempt blocked for Payroll",
            error_code="ADMIN_PAYROLL_DELETE_BYPASS_BLOCKED",
            context={
                'model': 'hr.Payroll',
                'user': request.user.username,
                'payroll_id': obj.pk
            }
        )
    
    def changelist_view(self, request, extra_context=None):
        """Override changelist view to show security warnings."""
        from django.contrib import messages
        
        extra_context = extra_context or {}
        
        # Add security warning
        messages.warning(
            request,
            "⚠️ تحذير أمني: قسائم الرواتب محمية ولا يمكن تعديلها مباشرة. "
            "استخدم PayrollGateway للإنشاء والتعديل الآمن."
        )
        
        # Add governance status
        extra_context['governance_status'] = {
            'is_high_risk_model': True,
            'read_only_mode': True,
            'authoritative_service': 'PayrollGateway',
            'business_interface_url': self.business_interface_url
        }
        
        return super().changelist_view(request, extra_context)
    
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        """Override changeform view to show security warnings and controls."""
        from django.contrib import messages
        
        extra_context = extra_context or {}
        
        # Add security warning for edit attempts
        if object_id:
            messages.warning(
                request,
                "🔒 وضع القراءة فقط: هذه القسيمة محمية ولا يمكن تعديلها مباشرة. "
                "استخدم PayrollGateway للعمليات الآمنة."
            )
        
        # Add governance information
        extra_context['governance_info'] = {
            'is_high_risk_model': True,
            'read_only_mode': True,
            'authoritative_service': 'PayrollGateway',
            'business_interface_url': self.business_interface_url,
            'security_warning': 'قسائم الرواتب محمية ولا يمكن تعديلها مباشرة'
        }
        
        return super().changeform_view(request, object_id, form_url, extra_context)
    
    def response_change(self, request, obj):
        """Override response to redirect to business interface."""
        from django.contrib import messages
        from django.utils.html import format_html
        
        if self.business_interface_url:
            messages.info(
                request,
                format_html(
                    'للتعديل الآمن، استخدم <a href="{}" target="_blank">واجهة الرواتب المخصصة</a>',
                    self.business_interface_url
                )
            )
        
        return super().response_change(request, obj)
    
    def _log_admin_access_attempt(self, request, action_type: str, result: str, 
                                  additional_context: dict = None):
        """Log all admin access attempts for audit trail."""
        import logging
        from django.utils import timezone
        
        logger = logging.getLogger('governance.admin_security')
        
        try:
            context = {
                'model': 'hr.Payroll',
                'action_type': action_type,
                'result': result,
                'user': request.user.username,
                'user_id': request.user.id,
                'ip_address': self._get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'timestamp': timezone.now().isoformat(),
                'session_key': request.session.session_key,
                'path': request.path,
                'method': request.method
            }
            
            if additional_context:
                context.update(additional_context)
            
            # Log to security logger
            logger.warning(
                f"Payroll admin access attempt: {action_type} by {request.user.username} - Result: {result}",
                extra=context
            )
            
        except Exception as e:
            # Don't let audit logging failures break the admin
            logger.error(f"Failed to log payroll admin access attempt: {e}")
    
    def _get_client_ip(self, request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def get_actions(self, request):
        """Override to add secure payroll approval actions."""
        actions = super().get_actions(request)
        
        # Remove default delete action for security
        if 'delete_selected' in actions:
            del actions['delete_selected']
        
        # Add secure approval actions with proper authority checks
        if request.user.has_perm('hr.can_approve_payroll'):
            actions['approve_selected_payrolls'] = (
                self.approve_selected_payrolls,
                'approve_selected_payrolls',
                'اعتماد قسائم الرواتب المحددة (يتطلب صلاحية خاصة)'
            )
        
        if request.user.has_perm('hr.can_pay_payroll'):
            actions['mark_as_paid'] = (
                self.mark_as_paid,
                'mark_as_paid',
                'تعيين كمدفوعة (يتطلب صلاحية خاصة)'
            )
        
        return actions
    
    def approve_selected_payrolls(self, request, queryset):
        """
        Secure action to approve selected payrolls with authority validation.
        
        This action implements payroll approval workflow authority by:
        - Validating user has approval permissions
        - Logging all approval attempts
        - Enforcing business rules for approval
        - Creating comprehensive audit trail
        """
        from django.contrib import messages
        from django.utils import timezone
        
        # Validate authority for approval
        if not request.user.has_perm('hr.can_approve_payroll'):
            self._log_admin_access_attempt(
                request,
                'bulk_approve_attempt',
                'permission_denied',
                additional_context={
                    'queryset_count': queryset.count(),
                    'queryset_ids': list(queryset.values_list('pk', flat=True))
                }
            )
            messages.error(
                request,
                "❌ ليس لديك صلاحية اعتماد قسائم الرواتب. "
                "يتطلب صلاحية 'can_approve_payroll'."
            )
            return
        
        # Filter payrolls that can be approved
        approvable_payrolls = queryset.filter(status='calculated')
        non_approvable_count = queryset.count() - approvable_payrolls.count()
        
        if non_approvable_count > 0:
            messages.warning(
                request,
                f"⚠️ تم تجاهل {non_approvable_count} قسيمة راتب لأنها ليست في حالة 'محسوب'."
            )
        
        if not approvable_payrolls.exists():
            messages.error(
                request,
                "❌ لا توجد قسائم رواتب قابلة للاعتماد في التحديد."
            )
            return
        
        # Perform approval with audit logging
        approved_count = 0
        approval_time = timezone.now()
        
        for payroll in approvable_payrolls:
            try:
                # Update payroll status
                payroll.status = 'approved'
                payroll.approved_by = request.user
                payroll.approved_at = approval_time
                payroll.save(update_fields=['status', 'approved_by', 'approved_at'])
                
                # Log individual approval
                self._log_admin_access_attempt(
                    request,
                    'payroll_approved',
                    'success',
                    additional_context={
                        'payroll_id': payroll.id,
                        'employee_id': payroll.employee.id,
                        'employee_name': payroll.employee.get_full_name_ar(),
                        'month': payroll.month.isoformat(),
                        'net_salary': str(payroll.net_salary),
                        'approval_time': approval_time.isoformat()
                    }
                )
                
                approved_count += 1
                
            except Exception as e:
                # Log approval failure
                self._log_admin_access_attempt(
                    request,
                    'payroll_approval_failed',
                    'error',
                    additional_context={
                        'payroll_id': payroll.id,
                        'employee_name': payroll.employee.get_full_name_ar(),
                        'error': str(e)
                    }
                )
        
        # Show success message
        if approved_count > 0:
            messages.success(
                request,
                f"✅ تم اعتماد {approved_count} قسيمة راتب بنجاح."
            )
            
            # Log bulk approval summary
            self._log_admin_access_attempt(
                request,
                'bulk_payroll_approval',
                'success',
                additional_context={
                    'total_selected': queryset.count(),
                    'approved_count': approved_count,
                    'non_approvable_count': non_approvable_count,
                    'approval_time': approval_time.isoformat()
                }
            )
    
    approve_selected_payrolls.short_description = "اعتماد قسائم الرواتب المحددة"
    
    def mark_as_paid(self, request, queryset):
        """
        Secure action to mark selected payrolls as paid with authority validation.
        
        This action implements payroll payment workflow authority by:
        - Validating user has payment permissions
        - Logging all payment attempts
        - Enforcing business rules for payment
        - Creating comprehensive audit trail
        """
        from django.contrib import messages
        from django.utils import timezone
        
        # Validate authority for payment
        if not request.user.has_perm('hr.can_pay_payroll'):
            self._log_admin_access_attempt(
                request,
                'bulk_payment_attempt',
                'permission_denied',
                additional_context={
                    'queryset_count': queryset.count(),
                    'queryset_ids': list(queryset.values_list('pk', flat=True))
                }
            )
            messages.error(
                request,
                "❌ ليس لديك صلاحية تعيين قسائم الرواتب كمدفوعة. "
                "يتطلب صلاحية 'can_pay_payroll'."
            )
            return
        
        # Filter payrolls that can be marked as paid
        payable_payrolls = queryset.filter(status='approved')
        non_payable_count = queryset.count() - payable_payrolls.count()
        
        if non_payable_count > 0:
            messages.warning(
                request,
                f"⚠️ تم تجاهل {non_payable_count} قسيمة راتب لأنها ليست في حالة 'معتمد'."
            )
        
        if not payable_payrolls.exists():
            messages.error(
                request,
                "❌ لا توجد قسائم رواتب قابلة للدفع في التحديد."
            )
            return
        
        # Perform payment marking with audit logging
        paid_count = 0
        payment_time = timezone.now()
        
        for payroll in payable_payrolls:
            try:
                # Update payroll status
                payroll.status = 'paid'
                payroll.paid_by = request.user
                payroll.paid_at = payment_time
                payroll.payment_date = payment_time.date()
                payroll.save(update_fields=['status', 'paid_by', 'paid_at', 'payment_date'])
                
                # Log individual payment
                self._log_admin_access_attempt(
                    request,
                    'payroll_marked_paid',
                    'success',
                    additional_context={
                        'payroll_id': payroll.id,
                        'employee_id': payroll.employee.id,
                        'employee_name': payroll.employee.get_full_name_ar(),
                        'month': payroll.month.isoformat(),
                        'net_salary': str(payroll.net_salary),
                        'payment_time': payment_time.isoformat()
                    }
                )
                
                paid_count += 1
                
            except Exception as e:
                # Log payment failure
                self._log_admin_access_attempt(
                    request,
                    'payroll_payment_failed',
                    'error',
                    additional_context={
                        'payroll_id': payroll.id,
                        'employee_name': payroll.employee.get_full_name_ar(),
                        'error': str(e)
                    }
                )
        
        # Show success message
        if paid_count > 0:
            messages.success(
                request,
                f"✅ تم تعيين {paid_count} قسيمة راتب كمدفوعة بنجاح."
            )
            
            # Log bulk payment summary
            self._log_admin_access_attempt(
                request,
                'bulk_payroll_payment',
                'success',
                additional_context={
                    'total_selected': queryset.count(),
                    'paid_count': paid_count,
                    'non_payable_count': non_payable_count,
                    'payment_time': payment_time.isoformat()
                }
            )
    
    mark_as_paid.short_description = "تعيين كمدفوعة"


@admin.register(Advance)
class AdvanceAdmin(admin.ModelAdmin):
    list_display = [
        'employee', 'amount', 'installments_count', 'installment_amount',
        'paid_installments', 'remaining_amount', 'status', 'requested_at'
    ]
    list_filter = ['status', 'deduction_start_month']
    search_fields = ['employee__name', 'reason']
    date_hierarchy = 'requested_at'
    ordering = ['-requested_at']
    readonly_fields = ['installment_amount', 'remaining_amount', 'paid_installments']
    
    fieldsets = (
        ('معلومات السلفة', {
            'fields': ('employee', 'amount', 'reason')
        }),
        ('نظام الأقساط', {
            'fields': (
                'installments_count', 'installment_amount', 
                'deduction_start_month', 'paid_installments', 'remaining_amount'
            )
        }),
        ('الحالة والاعتماد', {
            'fields': ('status', 'approved_by', 'approved_at', 'payment_date', 'completed_at')
        }),
        ('ملاحظات', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )


@admin.register(AdvanceInstallment)
class AdvanceInstallmentAdmin(admin.ModelAdmin):
    list_display = [
        'advance', 'installment_number', 'month', 'amount', 'payroll', 'created_at'
    ]
    list_filter = ['month', 'created_at']
    search_fields = ['advance__employee__name']
    date_hierarchy = 'month'
    ordering = ['-month', 'advance']
    readonly_fields = ['created_at']


@admin.register(SalaryComponentTemplate)
class SalaryComponentTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'component_type', 'formula', 'default_amount', 'order', 'is_active']
    list_filter = ['component_type', 'is_active']
    search_fields = ['name', 'description']
    ordering = ['component_type', 'order', 'name']
    list_editable = ['order', 'is_active']


@admin.register(SalaryComponent)
class SalaryComponentAdmin(admin.ModelAdmin):
    """
    Secure admin for SalaryComponent model with authority boundary enforcement.
    
    This admin class implements security controls for salary components to prevent
    unauthorized modifications that could affect payroll integrity:
    - Special permissions required for modifications
    - Comprehensive audit logging for all changes
    - Warnings for operations affecting payroll calculations
    - Authority boundary enforcement
    """
    
    # Security configuration
    require_special_permission = True
    authoritative_service = "PayrollGateway"
    
    list_display = ['employee', 'code', 'name', 'component_type', 'calculation_method', 'get_amount_display', 'is_active', 'effective_from', 'security_status']
    list_filter = ['component_type', 'calculation_method', 'is_active', 'is_basic', 'is_taxable', 'is_fixed']
    search_fields = ['code', 'name', 'employee__name', 'employee__employee_number', 'notes']
    ordering = ['employee', 'component_type', 'order']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'
    list_editable = ['is_active']
    
    fieldsets = (
        ('⚠️ تحذير أمني', {
            'description': 'تعديل بنود الراتب يؤثر على حسابات الرواتب المستقبلية. تأكد من صحة البيانات.',
            'fields': (),
            'classes': ('collapse',)
        }),
        ('معلومات أساسية', {
            'fields': ('employee', 'contract', 'template', 'code', 'name', 'component_type')
        }),
        ('طريقة الحساب', {
            'fields': ('calculation_method', 'amount', 'percentage', 'formula')
        }),
        ('الإعدادات', {
            'fields': ('is_basic', 'is_taxable', 'is_fixed', 'affects_overtime', 'show_in_payslip', 'order')
        }),
        ('الفترة الزمنية', {
            'fields': ('is_active', 'effective_from', 'effective_to')
        }),
        ('ملاحظات', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_amount_display(self, obj):
        """عرض المبلغ حسب طريقة الحساب"""
        if obj.calculation_method == 'fixed':
            return f"{obj.amount} ج.م"
        elif obj.calculation_method == 'percentage':
            return f"{obj.percentage}%"
        elif obj.calculation_method == 'formula':
            return f"صيغة: {obj.formula[:30]}..."
        return '-'
    get_amount_display.short_description = 'القيمة'
    
    def security_status(self, obj):
        """Display security status indicator."""
        from django.utils.html import format_html
        
        if obj.is_basic:
            return format_html(
                '<span style="color: red;">🔴 راتب أساسي - حساس جداً</span>'
            )
        elif obj.component_type == 'deduction':
            return format_html(
                '<span style="color: orange;">⚠️ خصم - يؤثر على الراتب</span>'
            )
        elif obj.affects_overtime:
            return format_html(
                '<span style="color: blue;">⏰ يؤثر على العمل الإضافي</span>'
            )
        else:
            return format_html(
                '<span style="color: green;">✅ بند عادي</span>'
            )
    security_status.short_description = 'حالة الأمان'
    
    def get_queryset(self, request):
        """Override queryset to add security logging."""
        queryset = super().get_queryset(request)
        
        # Log queryset access for audit trail
        self._log_admin_access_attempt(
            request,
            'queryset_access',
            'allowed',
            additional_context={
                'queryset_count': queryset.count()
            }
        )
        
        return queryset.select_related('employee', 'contract', 'template')
    
    def has_add_permission(self, request):
        """Check special permission for adding salary components."""
        has_permission = request.user.has_perm('hr.add_salarycomponent')
        if not has_permission:
            self._log_admin_access_attempt(request, 'add_attempt', 'permission_denied')
        else:
            self._log_admin_access_attempt(request, 'add_attempt', 'allowed')
        return has_permission
    
    def has_change_permission(self, request, obj=None):
        """Check special permission for changing salary components."""
        has_permission = request.user.has_perm('hr.change_salarycomponent')
        
        if obj:
            self._log_admin_access_attempt(
                request, 
                'change_attempt', 
                'allowed' if has_permission else 'permission_denied',
                additional_context={
                    'component_id': obj.id, 
                    'code': obj.code,
                    'employee_id': obj.employee.id if obj.employee else None,
                    'is_basic': obj.is_basic,
                    'component_type': obj.component_type
                }
            )
        
        return has_permission
    
    def has_delete_permission(self, request, obj=None):
        """Check special permission for deleting salary components."""
        has_permission = request.user.has_perm('hr.delete_salarycomponent')
        
        if obj:
            self._log_admin_access_attempt(
                request,
                'delete_attempt',
                'allowed' if has_permission else 'permission_denied',
                additional_context={
                    'component_id': obj.id,
                    'code': obj.code,
                    'is_basic': obj.is_basic,
                    'amount': str(obj.amount)
                }
            )
        
        return has_permission
    
    def save_model(self, request, obj, form, change):
        """Override save_model to add security logging and validation."""
        from django.contrib import messages
        
        # Log the save attempt with detailed context
        self._log_admin_access_attempt(
            request,
            'save_model',
            'allowed',
            additional_context={
                'component_id': getattr(obj, 'pk', None),
                'code': obj.code if hasattr(obj, 'code') else None,
                'employee_id': obj.employee.id if hasattr(obj, 'employee') and obj.employee else None,
                'change': change,
                'is_basic': getattr(obj, 'is_basic', False),
                'component_type': getattr(obj, 'component_type', None),
                'amount': str(getattr(obj, 'amount', 0)),
                'form_changed_data': form.changed_data if hasattr(form, 'changed_data') else []
            }
        )
        
        # Add warning for critical changes
        if obj.is_basic or obj.component_type == 'deduction':
            messages.warning(
                request,
                f"⚠️ تحذير: تم تعديل بند حساس ({obj.name}). "
                "هذا التغيير سيؤثر على حسابات الرواتب المستقبلية."
            )
        
        # Add info message for successful save
        if change:
            messages.info(
                request,
                f"✅ تم تحديث بند الراتب: {obj.name} للموظف {obj.employee.get_full_name_ar()}"
            )
        else:
            messages.success(
                request,
                f"✅ تم إنشاء بند راتب جديد: {obj.name} للموظف {obj.employee.get_full_name_ar()}"
            )
        
        super().save_model(request, obj, form, change)
    
    def delete_model(self, request, obj):
        """Override delete_model to add security logging and warnings."""
        from django.contrib import messages
        
        self._log_admin_access_attempt(
            request,
            'delete_model',
            'allowed',
            additional_context={
                'component_id': obj.pk,
                'code': obj.code,
                'employee_id': obj.employee.id if obj.employee else None,
                'is_basic': obj.is_basic,
                'component_type': obj.component_type,
                'amount': str(obj.amount)
            }
        )
        
        # Add warning for critical deletions
        if obj.is_basic:
            messages.error(
                request,
                f"⚠️ تحذير خطير: تم حذف بند راتب أساسي ({obj.name}) "
                f"للموظف {obj.employee.get_full_name_ar()}. "
                "هذا قد يؤثر على حسابات الرواتب."
            )
        else:
            messages.warning(
                request,
                f"تم حذف بند الراتب: {obj.name} للموظف {obj.employee.get_full_name_ar()}"
            )
        
        super().delete_model(request, obj)
    
    def changelist_view(self, request, extra_context=None):
        """Override changelist view to show security warnings."""
        from django.contrib import messages
        
        extra_context = extra_context or {}
        
        # Add security warning
        messages.info(
            request,
            "ℹ️ بنود الرواتب تؤثر على حسابات الرواتب المستقبلية. "
            "تأكد من صحة البيانات قبل التعديل."
        )
        
        # Add governance status
        extra_context['governance_status'] = {
            'require_special_permission': True,
            'authoritative_service': 'PayrollGateway',
            'affects_payroll_calculations': True
        }
        
        return super().changelist_view(request, extra_context)
    
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        """Override changeform view to show security warnings and controls."""
        from django.contrib import messages
        
        extra_context = extra_context or {}
        
        # Add security warning for edit attempts
        if object_id:
            try:
                obj = self.get_object(request, object_id)
                if obj and obj.is_basic:
                    messages.warning(
                        request,
                        "⚠️ تحذير: هذا بند راتب أساسي. التعديل سيؤثر على جميع حسابات الرواتب المستقبلية."
                    )
                elif obj and obj.component_type == 'deduction':
                    messages.info(
                        request,
                        "ℹ️ ملاحظة: هذا بند خصم. تأكد من صحة المبلغ والنسبة."
                    )
            except:
                pass
        
        # Add governance information
        extra_context['governance_info'] = {
            'require_special_permission': True,
            'authoritative_service': 'PayrollGateway',
            'affects_payroll_calculations': True,
            'security_warning': 'بنود الرواتب تؤثر على حسابات الرواتب'
        }
        
        return super().changeform_view(request, object_id, form_url, extra_context)
    
    def _log_admin_access_attempt(self, request, action_type: str, result: str, 
                                  additional_context: dict = None):
        """Log all admin access attempts for audit trail."""
        import logging
        from django.utils import timezone
        
        logger = logging.getLogger('governance.admin_security')
        
        try:
            context = {
                'model': 'hr.SalaryComponent',
                'action_type': action_type,
                'result': result,
                'user': request.user.username,
                'user_id': request.user.id,
                'ip_address': self._get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'timestamp': timezone.now().isoformat(),
                'session_key': request.session.session_key,
                'path': request.path,
                'method': request.method
            }
            
            if additional_context:
                context.update(additional_context)
            
            # Log to security logger
            logger.info(
                f"SalaryComponent admin access: {action_type} by {request.user.username} - Result: {result}",
                extra=context
            )
            
        except Exception as e:
            # Don't let audit logging failures break the admin
            logger.error(f"Failed to log salary component admin access attempt: {e}")
    
    def _get_client_ip(self, request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


@admin.register(PayrollLine)
class PayrollLineAdmin(admin.ModelAdmin):
    """
    Secure admin for PayrollLine model with authority boundary enforcement.
    
    This admin class implements comprehensive security controls for payroll line items:
    - Read-only mode to prevent unauthorized modifications
    - Authority boundary enforcement through PayrollGateway
    - Comprehensive audit logging for all access attempts
    - Prevention of salary component manipulation
    """
    
    # Security configuration
    is_high_risk_model = True
    read_only_mode = True
    allow_bulk_actions = False
    allow_inline_edits = False
    require_special_permission = True
    authoritative_service = "PayrollGateway"
    business_interface_url = "/hr/payroll/"
    
    list_display = ['payroll_employee', 'payroll_month', 'code', 'name', 'component_type', 'amount', 'security_status']
    list_filter = ['component_type', 'source', 'payroll__status', 'payroll__month']
    search_fields = ['code', 'name', 'payroll__employee__name']
    date_hierarchy = 'created_at'
    ordering = ['-payroll__month', 'payroll__employee', 'component_type', 'order']
    
    # Make all fields read-only to prevent unauthorized modifications
    readonly_fields = [
        'payroll', 'code', 'name', 'component_type', 'source', 'quantity', 'rate', 'amount',
        'salary_component', 'attendance_record', 'leave_record', 'advance_installment',
        'description', 'calculation_details', 'order', 'created_at'
    ]
    
    fieldsets = (
        ('⚠️ تحذير أمني', {
            'description': 'هذا البند محمي ولا يمكن تعديله مباشرة. استخدم PayrollGateway للعمليات الآمنة.',
            'fields': (),
            'classes': ('collapse',)
        }),
        ('معلومات البند', {
            'fields': ('payroll', 'code', 'name', 'component_type', 'source')
        }),
        ('القيم والحسابات', {
            'fields': ('quantity', 'rate', 'amount', 'calculation_details')
        }),
        ('الربط بالمصادر', {
            'fields': ('salary_component', 'attendance_record', 'leave_record', 'advance_installment'),
            'classes': ('collapse',)
        }),
        ('معلومات إضافية', {
            'fields': ('description', 'order', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def payroll_employee(self, obj):
        """Display employee name from related payroll."""
        return obj.payroll.employee.get_full_name_ar() if obj.payroll and obj.payroll.employee else '-'
    payroll_employee.short_description = 'الموظف'
    payroll_employee.admin_order_field = 'payroll__employee__name'
    
    def payroll_month(self, obj):
        """Display payroll month."""
        return obj.payroll.month.strftime('%Y-%m') if obj.payroll else '-'
    payroll_month.short_description = 'الشهر'
    payroll_month.admin_order_field = 'payroll__month'
    
    def security_status(self, obj):
        """Display security status indicator."""
        from django.utils.html import format_html
        
        if obj.salary_component:
            return format_html(
                '<span style="color: green;">🔒 مرتبط ببند راتب</span>'
            )
        elif obj.advance_installment:
            return format_html(
                '<span style="color: blue;">💰 قسط سلفة</span>'
            )
        else:
            return format_html(
                '<span style="color: orange;">⚠️ بند يدوي</span>'
            )
    security_status.short_description = 'حالة الأمان'
    
    def get_queryset(self, request):
        """Override queryset to add security logging and optimize queries."""
        queryset = super().get_queryset(request)
        
        # Log queryset access for audit trail
        self._log_admin_access_attempt(
            request,
            'queryset_access',
            'allowed',
            additional_context={
                'queryset_count': queryset.count()
            }
        )
        
        return queryset.select_related(
            'payroll', 'payroll__employee', 'salary_component', 
            'attendance_record', 'leave_record', 'advance_installment'
        )
    
    def has_add_permission(self, request):
        """Prevent adding new payroll line records through admin."""
        self._log_admin_access_attempt(request, 'add_attempt', 'blocked')
        return False
    
    def has_change_permission(self, request, obj=None):
        """Allow viewing but prevent changing payroll line records."""
        if obj:
            self._log_admin_access_attempt(
                request, 
                'change_attempt', 
                'view_only',
                additional_context={
                    'payroll_line_id': obj.id, 
                    'code': obj.code,
                    'payroll_id': obj.payroll.id if obj.payroll else None
                }
            )
        return super().has_view_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of payroll line records."""
        if obj:
            self._log_admin_access_attempt(
                request,
                'delete_attempt',
                'blocked',
                additional_context={
                    'payroll_line_id': obj.id,
                    'code': obj.code,
                    'amount': str(obj.amount)
                }
            )
        return False
    
    def save_model(self, request, obj, form, change):
        """Override save_model to detect bypass attempts."""
        from governance.exceptions import AuthorityViolationError
        from django.contrib import messages
        
        # Log bypass attempt
        self._log_admin_access_attempt(
            request,
            'save_model_bypass_attempt',
            'blocked',
            additional_context={
                'payroll_line_id': getattr(obj, 'pk', None),
                'code': obj.code if hasattr(obj, 'code') else None,
                'change': change,
                'form_data': form.cleaned_data if hasattr(form, 'cleaned_data') else None
            }
        )
        
        # Show error message
        messages.error(
            request,
            "❌ محاولة تجاوز أمني محظورة: لا يمكن حفظ التغييرات على بنود الرواتب. "
            "استخدم PayrollGateway للعمليات الآمنة."
        )
        
        # Raise governance error
        raise AuthorityViolationError(
            f"Admin save_model bypass attempt blocked for PayrollLine",
            error_code="ADMIN_PAYROLL_LINE_SAVE_BYPASS_BLOCKED",
            context={
                'model': 'hr.PayrollLine',
                'user': request.user.username,
                'payroll_line_id': getattr(obj, 'pk', None)
            }
        )
    
    def changelist_view(self, request, extra_context=None):
        """Override changelist view to show security warnings."""
        from django.contrib import messages
        
        extra_context = extra_context or {}
        
        # Add security warning
        messages.warning(
            request,
            "⚠️ تحذير أمني: بنود الرواتب محمية ولا يمكن تعديلها مباشرة. "
            "يتم إنشاؤها تلقائياً من خلال PayrollGateway."
        )
        
        # Add governance status
        extra_context['governance_status'] = {
            'is_high_risk_model': True,
            'read_only_mode': True,
            'authoritative_service': 'PayrollGateway',
            'business_interface_url': self.business_interface_url
        }
        
        return super().changelist_view(request, extra_context)
    
    def _log_admin_access_attempt(self, request, action_type: str, result: str, 
                                  additional_context: dict = None):
        """Log all admin access attempts for audit trail."""
        import logging
        from django.utils import timezone
        
        logger = logging.getLogger('governance.admin_security')
        
        try:
            context = {
                'model': 'hr.PayrollLine',
                'action_type': action_type,
                'result': result,
                'user': request.user.username,
                'user_id': request.user.id,
                'ip_address': self._get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'timestamp': timezone.now().isoformat(),
                'session_key': request.session.session_key,
                'path': request.path,
                'method': request.method
            }
            
            if additional_context:
                context.update(additional_context)
            
            # Log to security logger
            logger.warning(
                f"PayrollLine admin access attempt: {action_type} by {request.user.username} - Result: {result}",
                extra=context
            )
            
        except Exception as e:
            # Don't let audit logging failures break the admin
            logger.error(f"Failed to log payroll line admin access attempt: {e}")
    
    def _get_client_ip(self, request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def get_queryset(self, request):
        """Override queryset to add security logging and optimize queries."""
        queryset = super().get_queryset(request)
        
        # Log queryset access for audit trail
        self._log_admin_access_attempt(
            request,
            'queryset_access',
            'allowed',
            additional_context={
                'queryset_count': queryset.count()
            }
        )
        
        return queryset.select_related(
            'payroll', 'payroll__employee', 'salary_component', 
            'attendance_record', 'leave_record', 'advance_installment'
        )
    
    def has_add_permission(self, request):
        """Prevent adding new payroll line records through admin."""
        self._log_admin_access_attempt(request, 'add_attempt', 'blocked')
        return False
    
    def has_change_permission(self, request, obj=None):
        """Allow viewing but prevent changing payroll line records."""
        if obj:
            self._log_admin_access_attempt(
                request, 
                'change_attempt', 
                'view_only',
                additional_context={
                    'payroll_line_id': obj.id, 
                    'code': obj.code,
                    'payroll_id': obj.payroll.id if obj.payroll else None
                }
            )
        return super().has_view_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of payroll line records."""
        if obj:
            self._log_admin_access_attempt(
                request,
                'delete_attempt',
                'blocked',
                additional_context={
                    'payroll_line_id': obj.id,
                    'code': obj.code,
                    'amount': str(obj.amount)
                }
            )
        return False
    
    def save_model(self, request, obj, form, change):
        """Override save_model to detect bypass attempts."""
        from governance.exceptions import AuthorityViolationError
        from django.contrib import messages
        
        # Log bypass attempt
        self._log_admin_access_attempt(
            request,
            'save_model_bypass_attempt',
            'blocked',
            additional_context={
                'payroll_line_id': getattr(obj, 'pk', None),
                'code': obj.code if hasattr(obj, 'code') else None,
                'change': change,
                'form_data': form.cleaned_data if hasattr(form, 'cleaned_data') else None
            }
        )
        
        # Show error message
        messages.error(
            request,
            "❌ محاولة تجاوز أمني محظورة: لا يمكن حفظ التغييرات على بنود الرواتب. "
            "استخدم PayrollGateway للعمليات الآمنة."
        )
        
        # Raise governance error
        raise AuthorityViolationError(
            f"Admin save_model bypass attempt blocked for PayrollLine",
            error_code="ADMIN_PAYROLL_LINE_SAVE_BYPASS_BLOCKED",
            context={
                'model': 'hr.PayrollLine',
                'user': request.user.username,
                'payroll_line_id': getattr(obj, 'pk', None)
            }
        )
    
    def changelist_view(self, request, extra_context=None):
        """Override changelist view to show security warnings."""
        from django.contrib import messages
        
        extra_context = extra_context or {}
        
        # Add security warning
        messages.warning(
            request,
            "⚠️ تحذير أمني: بنود الرواتب محمية ولا يمكن تعديلها مباشرة. "
            "يتم إنشاؤها تلقائياً من خلال PayrollGateway."
        )
        
        # Add governance status
        extra_context['governance_status'] = {
            'is_high_risk_model': True,
            'read_only_mode': True,
            'authoritative_service': 'PayrollGateway',
            'business_interface_url': self.business_interface_url
        }
        
        return super().changelist_view(request, extra_context)
    
    def _log_admin_access_attempt(self, request, action_type: str, result: str, 
                                  additional_context: dict = None):
        """Log all admin access attempts for audit trail."""
        import logging
        from django.utils import timezone
        
        logger = logging.getLogger('governance.admin_security')
        
        try:
            context = {
                'model': 'hr.PayrollLine',
                'action_type': action_type,
                'result': result,
                'user': request.user.username,
                'user_id': request.user.id,
                'ip_address': self._get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'timestamp': timezone.now().isoformat(),
                'session_key': request.session.session_key,
                'path': request.path,
                'method': request.method
            }
            
            if additional_context:
                context.update(additional_context)
            
            # Log to security logger
            logger.warning(
                f"PayrollLine admin access attempt: {action_type} by {request.user.username} - Result: {result}",
                extra=context
            )
            
        except Exception as e:
            # Don't let audit logging failures break the admin
            logger.error(f"Failed to log payroll line admin access attempt: {e}")
    
    def _get_client_ip(self, request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class ContractDocumentInline(admin.TabularInline):
    model = ContractDocument
    extra = 0
    fields = ['document_type', 'title', 'file', 'uploaded_by', 'uploaded_at']
    readonly_fields = ['uploaded_by', 'uploaded_at']


class ContractAmendmentInline(admin.TabularInline):
    model = ContractAmendment
    extra = 0
    fields = ['amendment_number', 'amendment_type', 'effective_date', 'description']
    readonly_fields = ['amendment_number', 'created_at', 'created_by']


class ContractSalaryComponentInline(admin.TabularInline):
    """Inline لعرض بنود الراتب في صفحة العقد"""
    model = ContractSalaryComponent
    extra = 0
    fields = ['code', 'name', 'component_type', 'calculation_method', 'amount', 'percentage', 'is_basic', 'order']
    ordering = ['component_type', 'order']


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ['contract_number', 'employee', 'contract_type', 'status', 'start_date', 'end_date', 'basic_salary', 'has_annual_increase', 'next_increase_date']
    list_filter = ['status', 'contract_type', 'has_annual_increase', 'increase_frequency', 'start_date']
    search_fields = ['contract_number', 'employee__name']
    ordering = ['-start_date']
    inlines = [ContractSalaryComponentInline, ContractDocumentInline, ContractAmendmentInline]
    readonly_fields = ['created_at', 'created_by']
    
    fieldsets = (
        ('معلومات العقد الأساسية', {
            'fields': ('contract_number', 'employee', 'contract_type', 'status')
        }),
        ('التواريخ', {
            'fields': ('start_date', 'end_date', 'probation_period_months', 'probation_end_date')
        }),
        ('الراتب', {
            'fields': ('basic_salary',)
        }),
        ('الزيادة السنوية التلقائية', {
            'fields': (
                'has_annual_increase',
                'annual_increase_percentage',
                'increase_frequency',
                'increase_start_reference',
                'next_increase_date',
            ),
            'description': 'إعدادات الزيادة السنوية التلقائية - سيتم إنشاء زيادات تلقائياً حسب الجدول المحدد'
        }),
        ('البنود والشروط', {
            'fields': ('terms_and_conditions', 'notes', 'auto_renew')
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ContractSalaryComponent)
class ContractSalaryComponentAdmin(admin.ModelAdmin):
    """إدارة بنود الراتب في العقود"""
    list_display = ['contract', 'code', 'name', 'component_type', 'calculation_method', 'amount', 'is_basic', 'order']
    list_filter = ['component_type', 'calculation_method', 'is_basic', 'is_taxable']
    search_fields = ['code', 'name', 'contract__contract_number', 'contract__employee__name']
    ordering = ['contract', 'component_type', 'order']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('معلومات البند', {
            'fields': ('contract', 'template', 'code', 'name', 'component_type')
        }),
        ('طريقة الحساب', {
            'fields': ('calculation_method', 'amount', 'percentage', 'formula')
        }),
        ('الخصائص', {
            'fields': ('is_basic', 'is_taxable', 'is_fixed', 'affects_overtime', 'show_in_payslip', 'order')
        }),
        ('ملاحظات', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ContractDocument)
class ContractDocumentAdmin(admin.ModelAdmin):
    list_display = ['contract', 'document_type', 'title', 'file_size_mb', 'uploaded_at', 'uploaded_by']
    list_filter = ['document_type', 'uploaded_at']
    search_fields = ['title', 'contract__contract_number']
    ordering = ['-uploaded_at']
    readonly_fields = ['uploaded_at', 'uploaded_by', 'file_size_mb']


@admin.register(ContractAmendment)
class ContractAmendmentAdmin(admin.ModelAdmin):
    list_display = ['amendment_number', 'contract', 'amendment_type', 'effective_date', 'created_by']
    list_filter = ['amendment_type', 'effective_date']
    search_fields = ['amendment_number', 'contract__contract_number', 'description']
    ordering = ['-effective_date']
    readonly_fields = ['created_at', 'created_by']


@admin.register(ContractIncrease)
class ContractIncreaseAdmin(admin.ModelAdmin):
    list_display = ['contract', 'increase_number', 'increase_type', 'get_increase_value', 'scheduled_date', 'status', 'applied_date']
    list_filter = ['status', 'increase_type', 'scheduled_date']
    search_fields = ['contract__contract_number', 'contract__employee__name']
    ordering = ['contract', 'increase_number']
    readonly_fields = ['created_at', 'created_by', 'updated_at', 'applied_date', 'applied_amount']
    
    fieldsets = (
        ('معلومات الزيادة', {
            'fields': ('contract', 'increase_number', 'increase_type')
        }),
        ('قيمة الزيادة', {
            'fields': ('increase_percentage', 'increase_amount')
        }),
        ('الجدولة', {
            'fields': ('months_from_start', 'scheduled_date')
        }),
        ('الحالة', {
            'fields': ('status', 'applied_date', 'applied_amount', 'amendment')
        }),
        ('ملاحظات', {
            'fields': ('notes',)
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'created_by', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_increase_value(self, obj):
        """عرض قيمة الزيادة"""
        if obj.increase_type == 'percentage':
            return f"{obj.increase_percentage}%"
        else:
            return f"{obj.increase_amount} جنيه"
    get_increase_value.short_description = 'قيمة الزيادة'


# تم حذف نظام الخطط - النظام الآن تلقائي في Contract


@admin.register(PayrollPayment)
class PayrollPaymentAdmin(admin.ModelAdmin):
    """
    Secure admin for PayrollPayment model with authority boundary enforcement.
    
    This admin class implements comprehensive security controls for payroll payments:
    - Read-only mode to prevent unauthorized modifications
    - Authority boundary enforcement through PayrollGateway
    - Comprehensive audit logging for all access attempts
    - Prevention of payment manipulation that could affect payroll integrity
    - Warnings for operations affecting financial data
    """
    
    # Security configuration
    is_high_risk_model = True
    read_only_mode = True
    allow_bulk_actions = False
    allow_inline_edits = False
    require_special_permission = True
    authoritative_service = "PayrollGateway"
    business_interface_url = "/hr/payroll-payments/"
    
    list_display = [
        'payment_reference', 'payment_type', 'total_amount', 'net_amount', 
        'payment_date', 'status', 'payment_method', 'security_status'
    ]
    list_filter = ['status', 'payment_type', 'payment_method', 'payment_date', 'created_at']
    search_fields = ['payment_reference', 'description', 'bank_reference']
    date_hierarchy = 'payment_date'
    ordering = ['-payment_date', '-created_at']
    
    # Make all fields read-only to prevent unauthorized modifications
    readonly_fields = [
        'payment_reference', 'payment_type', 'payment_method', 'status',
        'total_amount', 'net_amount', 'fees_amount', 'payment_account',
        'journal_entry', 'payment_date', 'due_date', 'processed_at',
        'created_by', 'processed_by', 'approved_by', 'description',
        'bank_reference', 'notes', 'created_at', 'updated_at'
    ]
    
    fieldsets = (
        ('⚠️ تحذير أمني', {
            'description': 'هذه الدفعة محمية ولا يمكن تعديلها مباشرة. استخدم PayrollGateway للعمليات الآمنة.',
            'fields': (),
            'classes': ('collapse',)
        }),
        ('معلومات الدفعة الأساسية', {
            'fields': ('payment_reference', 'payment_type', 'payment_method', 'status')
        }),
        ('المبالغ المالية', {
            'fields': ('total_amount', 'net_amount', 'fees_amount')
        }),
        ('الحساب المحاسبي', {
            'fields': ('payment_account', 'journal_entry'),
            'classes': ('collapse',)
        }),
        ('معلومات التوقيت', {
            'fields': ('payment_date', 'due_date', 'processed_at')
        }),
        ('معلومات المستخدمين', {
            'fields': ('created_by', 'processed_by', 'approved_by'),
            'classes': ('collapse',)
        }),
        ('معلومات إضافية', {
            'fields': ('description', 'bank_reference', 'notes'),
            'classes': ('collapse',)
        }),
        ('معلومات النظام', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def security_status(self, obj):
        """Display security status indicator."""
        from django.utils.html import format_html
        
        if obj.journal_entry:
            return format_html(
                '<span style="color: green;">🔒 محمي - مرتبط بقيد محاسبي</span>'
            )
        elif obj.status == 'completed':
            return format_html(
                '<span style="color: orange;">⚠️ مكتمل بدون قيد محاسبي</span>'
            )
        else:
            return format_html(
                '<span style="color: blue;">📋 {}</span>',
                obj.get_status_display()
            )
    security_status.short_description = 'حالة الأمان'
    
    def get_queryset(self, request):
        """Override queryset to add security logging and optimize queries."""
        queryset = super().get_queryset(request)
        
        # Log queryset access for audit trail
        self._log_admin_access_attempt(
            request,
            'queryset_access',
            'allowed',
            additional_context={
                'queryset_count': queryset.count()
            }
        )
        
        return queryset.select_related(
            'payment_account', 'journal_entry', 'created_by', 'processed_by', 'approved_by'
        )
    
    def has_add_permission(self, request):
        """Prevent adding new payroll payment records through admin."""
        self._log_admin_access_attempt(request, 'add_attempt', 'blocked')
        return False
    
    def has_change_permission(self, request, obj=None):
        """Allow viewing but prevent changing payroll payment records."""
        if obj:
            self._log_admin_access_attempt(
                request, 
                'change_attempt', 
                'view_only',
                additional_context={
                    'payment_id': obj.id, 
                    'payment_reference': obj.payment_reference,
                    'total_amount': str(obj.total_amount),
                    'status': obj.status
                }
            )
        return super().has_view_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of payroll payment records."""
        if obj:
            self._log_admin_access_attempt(
                request,
                'delete_attempt',
                'blocked',
                additional_context={
                    'payment_id': obj.id,
                    'payment_reference': obj.payment_reference,
                    'total_amount': str(obj.total_amount),
                    'status': obj.status
                }
            )
        return False
    
    def save_model(self, request, obj, form, change):
        """Override save_model to detect bypass attempts."""
        from governance.exceptions import AuthorityViolationError
        from django.contrib import messages
        
        # Log bypass attempt
        self._log_admin_access_attempt(
            request,
            'save_model_bypass_attempt',
            'blocked',
            additional_context={
                'payment_id': getattr(obj, 'pk', None),
                'payment_reference': getattr(obj, 'payment_reference', None),
                'change': change,
                'form_data': form.cleaned_data if hasattr(form, 'cleaned_data') else None
            }
        )
        
        # Show error message
        messages.error(
            request,
            "❌ محاولة تجاوز أمني محظورة: لا يمكن حفظ التغييرات على دفعات الرواتب. "
            "استخدم PayrollGateway للعمليات الآمنة."
        )
        
        # Raise governance error
        raise AuthorityViolationError(
            f"Admin save_model bypass attempt blocked for PayrollPayment",
            error_code="ADMIN_PAYROLL_PAYMENT_SAVE_BYPASS_BLOCKED",
            context={
                'model': 'hr.PayrollPayment',
                'user': request.user.username,
                'payment_id': getattr(obj, 'pk', None)
            }
        )
    
    def delete_model(self, request, obj):
        """Override delete_model to prevent unauthorized deletions."""
        from governance.exceptions import AuthorityViolationError
        from django.contrib import messages
        
        self._log_admin_access_attempt(
            request,
            'delete_model_bypass_attempt',
            'blocked',
            additional_context={
                'payment_id': obj.pk,
                'payment_reference': obj.payment_reference,
                'total_amount': str(obj.total_amount)
            }
        )
        
        messages.error(
            request,
            "❌ محاولة حذف محظورة: لا يمكن حذف دفعات الرواتب للحفاظ على سلامة البيانات المالية."
        )
        
        raise AuthorityViolationError(
            f"Admin delete_model bypass attempt blocked for PayrollPayment",
            error_code="ADMIN_PAYROLL_PAYMENT_DELETE_BYPASS_BLOCKED",
            context={
                'model': 'hr.PayrollPayment',
                'user': request.user.username,
                'payment_id': obj.pk
            }
        )
    
    def changelist_view(self, request, extra_context=None):
        """Override changelist view to show security warnings."""
        from django.contrib import messages
        
        extra_context = extra_context or {}
        
        # Add security warning
        messages.warning(
            request,
            "⚠️ تحذير أمني: دفعات الرواتب محمية ولا يمكن تعديلها مباشرة. "
            "استخدم PayrollGateway للإنشاء والمعالجة الآمنة."
        )
        
        # Add governance status
        extra_context['governance_status'] = {
            'is_high_risk_model': True,
            'read_only_mode': True,
            'authoritative_service': 'PayrollGateway',
            'business_interface_url': self.business_interface_url
        }
        
        return super().changelist_view(request, extra_context)
    
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        """Override changeform view to show security warnings and controls."""
        from django.contrib import messages
        
        extra_context = extra_context or {}
        
        # Add security warning for edit attempts
        if object_id:
            messages.warning(
                request,
                "🔒 وضع القراءة فقط: هذه الدفعة محمية ولا يمكن تعديلها مباشرة. "
                "استخدم PayrollGateway للعمليات الآمنة."
            )
        
        # Add governance information
        extra_context['governance_info'] = {
            'is_high_risk_model': True,
            'read_only_mode': True,
            'authoritative_service': 'PayrollGateway',
            'business_interface_url': self.business_interface_url,
            'security_warning': 'دفعات الرواتب محمية ولا يمكن تعديلها مباشرة'
        }
        
        return super().changeform_view(request, object_id, form_url, extra_context)
    
    def response_change(self, request, obj):
        """Override response to redirect to business interface."""
        from django.contrib import messages
        from django.utils.html import format_html
        
        if self.business_interface_url:
            messages.info(
                request,
                format_html(
                    'للتعديل الآمن، استخدم <a href="{}" target="_blank">واجهة دفعات الرواتب المخصصة</a>',
                    self.business_interface_url
                )
            )
        
        return super().response_change(request, obj)
    
    def _log_admin_access_attempt(self, request, action_type: str, result: str, 
                                  additional_context: dict = None):
        """Log all admin access attempts for audit trail."""
        import logging
        from django.utils import timezone
        
        logger = logging.getLogger('governance.admin_security')
        
        try:
            context = {
                'model': 'hr.PayrollPayment',
                'action_type': action_type,
                'result': result,
                'user': request.user.username,
                'user_id': request.user.id,
                'ip_address': self._get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'timestamp': timezone.now().isoformat(),
                'session_key': request.session.session_key,
                'path': request.path,
                'method': request.method
            }
            
            if additional_context:
                context.update(additional_context)
            
            # Log to security logger
            logger.warning(
                f"PayrollPayment admin access attempt: {action_type} by {request.user.username} - Result: {result}",
                extra=context
            )
            
        except Exception as e:
            # Don't let audit logging failures break the admin
            logger.error(f"Failed to log payroll payment admin access attempt: {e}")
    
    def _get_client_ip(self, request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


# Import PayrollPayment model for admin registration



@admin.register(PermissionType)
class PermissionTypeAdmin(admin.ModelAdmin):
    list_display = ['code', 'name_ar', 'name_en', 'max_hours_per_request', 'requires_advance_request', 'affects_salary', 'is_active']
    list_filter = ['is_active', 'requires_advance_request', 'affects_salary']
    search_fields = ['code', 'name_ar', 'name_en']
    ordering = ['code']


@admin.register(PermissionRequest)
class PermissionRequestAdmin(admin.ModelAdmin):
    list_display = ['employee', 'permission_type', 'date', 'start_time', 'end_time', 'duration_hours', 'status', 'requested_at']
    list_filter = ['status', 'permission_type', 'date', 'is_emergency']
    search_fields = ['employee__name', 'employee__employee_number', 'reason']
    readonly_fields = ['requested_at', 'reviewed_at', 'approved_at', 'duration_hours']
    ordering = ['-requested_at']
    
    fieldsets = (
        ('معلومات الإذن', {
            'fields': ('employee', 'permission_type', 'date', 'start_time', 'end_time', 'duration_hours', 'reason', 'is_emergency')
        }),
        ('سير العمل', {
            'fields': ('status', 'requested_at', 'requested_by')
        }),
        ('المراجعة', {
            'fields': ('reviewed_by', 'reviewed_at', 'review_notes')
        }),
        ('الاعتماد', {
            'fields': ('approved_by', 'approved_at')
        }),
        ('التكامل', {
            'fields': ('attendance',)
        }),
    )
