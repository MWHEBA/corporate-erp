"""
Views إدارة الأذونات
"""
from .base_imports import *
from ..models import PermissionRequest, PermissionType, Employee
from ..forms.permission_forms import PermissionRequestForm
from ..services.permission_service import PermissionService
from ..decorators import require_hr, can_approve_permissions
from django.core.paginator import Paginator
from datetime import date
import logging

logger = logging.getLogger(__name__)

__all__ = [
    'permission_list',
    'permission_request',
    'permission_detail',
    'permission_approve',
    'permission_reject',
    'permission_type_list',
    'permission_type_form',
    'permission_type_delete',
]


@login_required
def permission_list(request):
    """قائمة الأذونات - نسخة من leave_list"""
    # Query Optimization
    permissions = PermissionRequest.objects.select_related(
        'employee',
        'employee__department',
        'permission_type',
        'approved_by'
    ).all()
    
    # الإحصائيات
    total_permissions = permissions.count()
    pending_permissions = permissions.filter(status='pending').count()
    approved_permissions = permissions.filter(status='approved').count()
    rejected_permissions = permissions.filter(status='rejected').count()
    
    # جلب الموظفين وأنواع الأذونات للفلاتر
    employees = Employee.objects.filter(status='active')
    permission_types = PermissionType.objects.filter(is_active=True)
    
    # Pagination - 30 إذن لكل صفحة
    paginator = Paginator(permissions, 30)
    page = request.GET.get('page', 1)
    permissions_page = paginator.get_page(page)
    
    context = {
        'permissions': permissions_page,
        'employees': employees,
        'permission_types': permission_types,
        'total_permissions': total_permissions,
        'pending_permissions': pending_permissions,
        'approved_permissions': approved_permissions,
        'rejected_permissions': rejected_permissions,
        'show_stats': True,
        
        # بيانات الهيدر
        'page_title': 'قائمة الأذونات',
        'page_subtitle': 'إدارة ومتابعة طلبات الأذونات للموظفين',
        'page_icon': 'fas fa-clock',
        
        # أزرار الهيدر
        'header_buttons': [
            {
                'url': reverse('hr:permission_type_list'),
                'icon': 'fa-tags',
                'text': 'أنواع الأذونات',
                'class': 'btn-info',
            },
            {
                'url': reverse('hr:permission_request'),
                'icon': 'fa-plus',
                'text': 'تسجيل إذن جديد',
                'class': 'btn-primary',
            },
        ],
        
        # البريدكرمب
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'قائمة الأذونات', 'active': True},
        ],
    }
    
    return render(request, 'hr/permission/list.html', context)


@login_required
@require_hr
def permission_request(request):
    """تسجيل إذن جديد - نسخة من leave_request مع تعديلات للـ HR"""
    
    current_month = date.today()
    
    if request.method == 'POST':
        form = PermissionRequestForm(request.POST)
        if form.is_valid():
            try:
                employee = form.cleaned_data['employee']
                permission_type = form.cleaned_data['permission_type']
                perm_date = form.cleaned_data['date']
                start_time = form.cleaned_data['start_time']
                end_time = form.cleaned_data['end_time']
                reason = form.cleaned_data['reason']
                is_emergency = form.cleaned_data.get('is_emergency', False)
                
                logger.info(
                    f"طلب إذن جديد من HR للموظف {employee.get_full_name_ar()} - "
                    f"النوع: {permission_type.name_ar}"
                )
                
                # استخدام الخدمة لإنشاء الإذن
                permission = PermissionService.request_permission(
                    employee=employee,
                    permission_data={
                        'permission_type': permission_type,
                        'date': perm_date,
                        'start_time': start_time,
                        'end_time': end_time,
                        'reason': reason,
                        'is_emergency': is_emergency,
                    },
                    requested_by=request.user
                )
                
                logger.info(f"تم حفظ طلب الإذن #{permission.pk} بنجاح")
                messages.success(request, 'تم تسجيل الإذن بنجاح')
                return redirect('hr:permission_detail', pk=permission.pk)
                    
            except ValueError as e:
                logger.error(f"خطأ في البيانات عند طلب إذن: {str(e)}")
                messages.error(request, f'خطأ في البيانات: {str(e)}')
            except Exception as e:
                logger.exception(f"خطأ غير متوقع عند طلب إذن: {str(e)}")
                messages.error(request, f'حدث خطأ غير متوقع: {str(e)}')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = PermissionRequestForm()
    
    context = {
        'form': form,
        'current_month': current_month,
        'page_title': 'تسجيل إذن جديد',
        'page_subtitle': 'تسجيل طلب إذن جديد للموظف',
        'page_icon': 'fas fa-clock',
        'header_buttons': [
            {
                'url': reverse('hr:permission_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'الأذونات', 'url': reverse('hr:permission_list'), 'icon': 'fas fa-clock'},
            {'title': 'تسجيل إذن', 'active': True},
        ],
    }
    return render(request, 'hr/permission/request.html', context)


@login_required
def permission_detail(request, pk):
    """تفاصيل الإذن - نسخة من leave_detail"""
    permission = get_object_or_404(PermissionRequest, pk=pk)
    
    # تحديد الأزرار حسب حالة الإذن
    header_buttons = []
    if permission.status == 'pending':
        header_buttons.extend([
            {
                'url': reverse('hr:permission_approve', args=[permission.pk]),
                'icon': 'fa-check',
                'text': 'اعتماد',
                'class': 'btn-success',
            },
            {
                'url': reverse('hr:permission_reject', args=[permission.pk]),
                'icon': 'fa-times',
                'text': 'رفض',
                'class': 'btn-danger',
            },
        ])
    header_buttons.append({
        'url': reverse('hr:permission_list'),
        'icon': 'fa-arrow-right',
        'text': 'رجوع',
        'class': 'btn-secondary',
    })
    
    context = {
        'permission': permission,
        'page_title': 'تفاصيل الإذن',
        'page_subtitle': f'{permission.employee.get_full_name_ar()} - {permission.permission_type.name_ar}',
        'page_icon': 'fas fa-clock',
        'header_buttons': header_buttons,
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'الأذونات', 'url': reverse('hr:permission_list'), 'icon': 'fas fa-clock'},
            {'title': 'تفاصيل الإذن', 'active': True},
        ],
    }
    return render(request, 'hr/permission/detail.html', context)


@login_required
@can_approve_permissions
def permission_approve(request, pk):
    """اعتماد الإذن - نسخة من leave_approve"""
    permission = get_object_or_404(PermissionRequest, pk=pk)
    
    if permission.status != 'pending':
        messages.warning(request, 'هذا الإذن تمت معالجته بالفعل')
        return redirect('hr:permission_detail', pk=pk)
    
    if request.method == 'POST':
        review_notes = request.POST.get('review_notes', '')
        try:
            PermissionService.approve_permission(permission, request.user, review_notes)
            messages.success(request, 'تم اعتماد الإذن بنجاح')
            return redirect('hr:permission_detail', pk=pk)
        except Exception as e:
            logger.exception(f"خطأ عند اعتماد الإذن: {str(e)}")
            messages.error(request, f'خطأ: {str(e)}')
    
    context = {
        'permission': permission,
        'page_title': 'اعتماد طلب إذن',
        'page_subtitle': 'مراجعة واعتماد طلب الإذن',
        'page_icon': 'fas fa-check-circle',
        'header_buttons': [
            {
                'url': reverse('hr:permission_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users'},
            {'title': 'الأذونات', 'url': reverse('hr:permission_list'), 'icon': 'fas fa-clock'},
            {'title': 'اعتماد إذن', 'active': True},
        ],
    }
    return render(request, 'hr/permission/approve.html', context)


@login_required
@can_approve_permissions
def permission_reject(request, pk):
    """رفض الإذن - نسخة من leave_reject"""
    permission = get_object_or_404(PermissionRequest, pk=pk)
    
    if permission.status != 'pending':
        messages.warning(request, 'هذا الإذن تمت معالجته بالفعل')
        return redirect('hr:permission_detail', pk=pk)
    
    if request.method == 'POST':
        review_notes = request.POST.get('review_notes', '')
        if not review_notes:
            messages.error(request, 'يجب إدخال سبب الرفض')
        else:
            try:
                PermissionService.reject_permission(permission, request.user, review_notes)
                messages.success(request, 'تم رفض الإذن')
                return redirect('hr:permission_detail', pk=pk)
            except Exception as e:
                logger.exception(f"خطأ عند رفض الإذن: {str(e)}")
                messages.error(request, f'خطأ: {str(e)}')
    
    context = {
        'permission': permission,
        'page_title': 'رفض طلب إذن',
        'page_subtitle': 'مراجعة ورفض طلب الإذن',
        'page_icon': 'fas fa-times-circle',
        'header_buttons': [
            {
                'url': reverse('hr:permission_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users'},
            {'title': 'الأذونات', 'url': reverse('hr:permission_list'), 'icon': 'fas fa-clock'},
            {'title': 'رفض إذن', 'active': True},
        ],
    }
    return render(request, 'hr/permission/reject.html', context)



@login_required
@require_hr
def permission_type_list(request):
    """قائمة أنواع الأذونات - للإدارة فقط"""
    permission_types = PermissionType.objects.all().order_by('code')
    
    context = {
        'permission_types': permission_types,
        'page_title': 'أنواع الأذونات',
        'page_subtitle': 'إدارة أنواع الأذونات المتاحة',
        'page_icon': 'fas fa-tags',
        'header_buttons': [
            {
                'url': reverse('hr:permission_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'الأذونات', 'url': reverse('hr:permission_list'), 'icon': 'fas fa-clock'},
            {'title': 'أنواع الأذونات', 'active': True},
        ],
    }
    return render(request, 'hr/permission/type_list.html', context)


@login_required
@require_hr
def permission_type_form(request, pk=None):
    """إضافة أو تعديل نوع إذن"""
    from ..forms.permission_forms import PermissionTypeForm
    
    if pk:
        permission_type = get_object_or_404(PermissionType, pk=pk)
        title = 'تعديل نوع الإذن'
    else:
        permission_type = None
        title = 'إضافة نوع إذن جديد'
    
    if request.method == 'POST':
        form = PermissionTypeForm(request.POST, instance=permission_type)
        if form.is_valid():
            permission_type = form.save()
            messages.success(request, 'تم حفظ نوع الإذن بنجاح')
            return redirect('hr:permission_type_list')
    else:
        form = PermissionTypeForm(instance=permission_type)
    
    context = {
        'form': form,
        'permission_type': permission_type,
        'page_title': title,
        'page_icon': 'fas fa-tag',
        'header_buttons': [
            {
                'url': reverse('hr:permission_type_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'أنواع الأذونات', 'url': reverse('hr:permission_type_list'), 'icon': 'fas fa-tags'},
            {'title': title, 'active': True},
        ],
    }
    return render(request, 'hr/permission/type_form.html', context)


@login_required
@require_hr
def permission_type_delete(request, pk):
    """حذف نوع إذن"""
    permission_type = get_object_or_404(PermissionType, pk=pk)
    
    if request.method == 'POST':
        try:
            permission_type.delete()
            messages.success(request, 'تم حذف نوع الإذن بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ في الحذف: {str(e)}')
        return redirect('hr:permission_type_list')
    
    context = {
        'permission_type': permission_type,
        'page_title': 'حذف نوع الإذن',
        'page_icon': 'fas fa-trash',
    }
    return render(request, 'hr/permission/type_confirm_delete.html', context)
