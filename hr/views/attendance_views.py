"""
Views إدارة الحضور
"""
from .base_imports import *
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import permission_required
from ..models import Employee, Department, Shift, BiometricLog, AttendanceSummary, Attendance
from ..services.attendance_service import AttendanceService
from ..services.attendance_summary_service import AttendanceSummaryService

__all__ = [
    'attendance_list',
    'attendance_check_in',
    'attendance_check_out',
    'attendance_summary_list',
    'attendance_summary_detail',  # Re-added with Smart Auto-recalculate
    'approve_attendance_summary',
    'recalculate_attendance_summary',
    'calculate_attendance_summaries',  # Moved from integrated_payroll_views
]


@login_required
def attendance_list(request):
    """قائمة الحضور - من سجلات Attendance المعالجة"""
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    
    # الفلاتر
    # التاريخ - افتراضي الشهر الحالي
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if not date_from:
        # أول يوم في الشهر الحالي
        date_from = date.today().replace(day=1).strftime('%Y-%m-%d')
    if not date_to:
        # اليوم الحالي
        date_to = date.today().strftime('%Y-%m-%d')
    
    date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
    date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
    
    # فلتر القسم
    department_id = request.GET.get('department')
    
    # فلتر الموظف
    employee_id = request.GET.get('employee')
    
    # جلب سجلات الحضور المعالجة
    attendances = Attendance.objects.filter(
        date__gte=date_from_obj,
        date__lte=date_to_obj
    ).select_related('employee', 'employee__department', 'shift')
    
    # تطبيق فلتر القسم
    if department_id:
        attendances = attendances.filter(employee__department_id=department_id)
    
    # تطبيق فلتر الموظف
    if employee_id:
        attendances = attendances.filter(employee_id=employee_id)
    
    attendances = attendances.order_by('-date', 'employee__name')
    
    # Pagination - 50 سجل في الصفحة
    paginator = Paginator(attendances, 50)
    page = request.GET.get('page', 1)
    
    try:
        attendances_page = paginator.page(page)
    except PageNotAnInteger:
        attendances_page = paginator.page(1)
    except EmptyPage:
        attendances_page = paginator.page(paginator.num_pages)
    
    # تحضير البيانات للعرض - فقط للصفحة الحالية
    attendance_data = []
    
    for attendance in attendances_page:
        # حساب الانصراف المبكر
        early_leave_minutes = attendance.early_leave_minutes if attendance.early_leave_minutes else 0
        
        # جلب حركات البصمة المرتبطة
        biometric_logs = attendance.biometric_logs.all().order_by('timestamp')
        movements = [log.timestamp for log in biometric_logs]
        
        # الحصول على الملخص الشهري
        summary, _ = AttendanceSummary.objects.get_or_create(
            employee=attendance.employee,
            month=attendance.date.replace(day=1)
        )
        
        attendance_data.append({
            'employee': attendance.employee,
            'date': attendance.date,
            'check_in': attendance.check_in,
            'check_out': attendance.check_out,
            'work_hours': float(attendance.work_hours) if attendance.work_hours else 0,
            'late_minutes': attendance.late_minutes,
            'early_leave_minutes': early_leave_minutes,
            'status': attendance.status,
            'total_movements': len(movements),
            'movements': movements,
            'summary_id': summary.id,
            'overtime_hours': float(attendance.overtime_hours) if attendance.overtime_hours else 0,
        })
    
    # حساب الإحصائيات
    present_count = sum(1 for a in attendance_data if a['status'] == 'present')
    late_count = sum(1 for a in attendance_data if a['status'] == 'late')
    absent_count = 0  # سيتم حسابه لاحقاً من قائمة الموظفين
    on_leave_count = 0  # من نظام الإجازات
    
    # جلب قوائم الفلاتر
    departments = Department.objects.filter(is_active=True).order_by('name_ar')
    employees = Employee.objects.filter(status='active').order_by('name')
    
    # إعداد headers للجدول الموحد
    headers = [
        {'key': 'date', 'label': 'التاريخ', 'sortable': True, 'width': '9%', 'template': 'hr/attendance/cells/date.html'},
        {'key': 'employee', 'label': 'الموظف', 'sortable': True, 'width': '13%', 'template': 'hr/attendance/cells/employee.html'},
        {'key': 'department', 'label': 'القسم', 'sortable': True, 'width': '10%', 'template': 'hr/attendance/cells/department.html'},
        {'key': 'check_in', 'label': 'الحضور', 'sortable': True, 'width': '9%', 'class': 'text-center', 'template': 'hr/attendance/cells/check_in.html'},
        {'key': 'check_out', 'label': 'الانصراف', 'sortable': True, 'width': '9%', 'class': 'text-center', 'template': 'hr/attendance/cells/check_out.html'},
        {'key': 'work_hours', 'label': 'ساعات العمل', 'sortable': True, 'width': '9%', 'class': 'text-center', 'template': 'hr/attendance/cells/work_hours.html'},
        {'key': 'late_minutes', 'label': 'التأخير', 'sortable': True, 'width': '7%', 'class': 'text-center', 'template': 'hr/attendance/cells/late_minutes.html'},
        {'key': 'early_leave_minutes', 'label': 'انصراف مبكر', 'sortable': True, 'width': '8%', 'class': 'text-center', 'template': 'hr/attendance/cells/early_leave.html'},
        {'key': 'total_movements', 'label': 'الحركات', 'sortable': True, 'width': '7%', 'class': 'text-center', 'template': 'hr/attendance/cells/movements.html'},
        {'key': 'status', 'label': 'الحالة', 'sortable': True, 'width': '8%', 'class': 'text-center', 'template': 'hr/attendance/cells/status.html'},
        {'key': 'actions', 'label': 'التفاصيل', 'sortable': False, 'width': '8%', 'class': 'text-center', 'template': 'hr/attendance/cells/actions.html'},
    ]
    
    context = {
        'attendance_data': attendance_data,
        'headers': headers,
        'date_from': date_from,
        'date_to': date_to,
        'date_from_display': date_from_obj,
        'date_to_display': date_to_obj,
        'today': date.today(),
        'present_count': present_count,
        'late_count': late_count,
        'absent_count': absent_count,
        'on_leave_count': on_leave_count,
        'departments': departments,
        'employees': employees,
        'paginator': paginator,
        'page_obj': attendances_page,
        
        # بيانات الهيدر الموحد
        'page_title': 'سجل الحضور',
        'page_subtitle': f'متابعة حضور وانصراف الموظفين من نظام البصمة ({date_from_obj.strftime("%d/%m/%Y")} - {date_to_obj.strftime("%d/%m/%Y")})',
        'page_icon': 'fas fa-clock',
        'header_buttons': [
            {
                'onclick': 'processBiometricLogs()',
                'icon': 'fa-cogs',
                'text': 'معالجة البصمات',
                'class': 'btn-success',
                'id': 'btn-process-biometric',
            },
            {
                'url': reverse('hr:biometric_log_list'),
                'icon': 'fa-fingerprint',
                'text': 'سجلات البصمة الخام',
                'class': 'btn-info',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'سجل الحضور', 'active': True},
        ],
    }
    return render(request, 'hr/attendance/list.html', context)


@login_required
def attendance_check_in(request):
    """تسجيل الحضور"""
    if request.method == 'POST':
        employee_id = request.POST.get('employee_id')
        shift_id = request.POST.get('shift_id')
        
        if employee_id:
            try:
                employee = Employee.objects.get(pk=employee_id)
                shift = Shift.objects.get(pk=shift_id) if shift_id else None
                
                # Debug logging
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Attempting check-in for employee {employee.id}, shift {shift.id if shift else None}")
                
                attendance = AttendanceService.record_check_in(employee, shift=shift)
                
                logger.info(f"Check-in successful, attendance ID: {attendance.id}")
                messages.success(request, f'تم تسجيل حضور {employee.get_full_name_ar()} بنجاح')
                return redirect('hr:attendance_list')
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Check-in failed: {str(e)}", exc_info=True)
                messages.error(request, f'خطأ: {str(e)}')
        else:
            messages.error(request, 'يرجى اختيار الموظف')
    
    context = {
        'employees': Employee.objects.filter(status='active'),
        'shifts': Shift.objects.filter(is_active=True)
    }
    return render(request, 'hr/attendance/check_in.html', context)


@login_required
def attendance_summary_list(request):
    """قائمة ملخصات الحضور الشهرية"""
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    from django.db.models import Q
    
    # الفلاتر
    month_str = request.GET.get('month')
    department_id = request.GET.get('department')
    employee_id = request.GET.get('employee')
    status = request.GET.get('status')  # approved, pending
    
    # تحديد الشهر الافتراضي (الشهر الحالي)
    if month_str:
        try:
            month_date = datetime.strptime(month_str, '%Y-%m').date()
        except ValueError:
            month_date = date.today().replace(day=1)
    else:
        month_date = date.today().replace(day=1)
    
    # جلب الملخصات
    summaries = AttendanceSummary.objects.filter(
        month=month_date
    ).select_related('employee', 'employee__department', 'employee__job_title')
    
    # تطبيق الفلاتر
    if department_id:
        summaries = summaries.filter(employee__department_id=department_id)
    
    if employee_id:
        summaries = summaries.filter(employee_id=employee_id)
    
    if status == 'approved':
        summaries = summaries.filter(is_approved=True)
    elif status == 'pending':
        summaries = summaries.filter(is_approved=False)
    
    summaries = summaries.order_by('-is_approved', 'employee__name')
    
    # Pagination
    paginator = Paginator(summaries, 50)
    page = request.GET.get('page', 1)
    
    try:
        summaries_page = paginator.page(page)
    except PageNotAnInteger:
        summaries_page = paginator.page(1)
    except EmptyPage:
        summaries_page = paginator.page(paginator.num_pages)
    
    # تحضير البيانات للجدول
    summary_data = []
    for summary in summaries_page:
        # Check if summary needs update (stale data)
        needs_update = False
        if not summary.is_approved:
            # Check if stale (older than 5 minutes)
            if summary.updated_at:
                from django.utils import timezone
                age = timezone.now() - summary.updated_at
                if age > timedelta(minutes=5):
                    needs_update = True
            else:
                needs_update = True
            
            # Check if has new attendance data
            if not needs_update:
                from hr.models import Attendance
                latest_attendance = Attendance.objects.filter(
                    employee=summary.employee,
                    date__year=summary.month.year,
                    date__month=summary.month.month
                ).order_by('-updated_at').first()
                
                if latest_attendance and latest_attendance.updated_at > summary.updated_at:
                    needs_update = True
        
        # حساب أيام الحضور الفعلية (حضور + تأخير)
        total_present = summary.present_days + summary.late_days
        
        summary_data.append({
            'id': summary.id,
            'employee': summary.employee,
            'department': summary.employee.department.name_ar if summary.employee.department else 'غير محدد',
            'total_working_days': summary.total_working_days,
            'present_days': total_present,
            'absent_days': summary.absent_days,
            'late_days': summary.late_days,
            'total_work_hours': float(summary.total_work_hours) if summary.total_work_hours else 0,
            'total_late_minutes': summary.total_late_minutes,
            'is_approved': summary.is_approved,
            'approved_by': summary.approved_by,
            'approved_at': summary.approved_at,
            'needs_update': needs_update,
            'updated_at': summary.updated_at,
        })
    
    # إحصائيات عامة
    total_summaries = summaries.count()
    approved_count = summaries.filter(is_approved=True).count()
    pending_count = summaries.filter(is_approved=False).count()
    
    # قوائم الفلاتر
    departments = Department.objects.filter(is_active=True).order_by('name_ar')
    employees = Employee.objects.filter(status='active').order_by('name')
    
    # إعداد headers للجدول
    headers = [
        {'key': 'employee', 'label': 'الموظف', 'sortable': True, 'width': '15%'},
        {'key': 'department', 'label': 'القسم', 'sortable': True, 'width': '12%'},
        {'key': 'total_working_days', 'label': 'أيام العمل', 'sortable': True, 'width': '8%', 'class': 'text-center'},
        {'key': 'present_days', 'label': 'الحضور', 'sortable': True, 'width': '8%', 'class': 'text-center'},
        {'key': 'absent_days', 'label': 'الغياب', 'sortable': True, 'width': '8%', 'class': 'text-center'},
        {'key': 'late_days', 'label': 'التأخير', 'sortable': True, 'width': '8%', 'class': 'text-center'},
        {'key': 'total_work_hours', 'label': 'ساعات العمل', 'sortable': True, 'width': '10%', 'class': 'text-center'},
        {'key': 'total_late_minutes', 'label': 'دقائق التأخير', 'sortable': True, 'width': '10%', 'class': 'text-center'},
        {'key': 'status', 'label': 'الحالة', 'sortable': True, 'width': '8%', 'class': 'text-center'},
        {'key': 'actions', 'label': 'الإجراءات', 'sortable': False, 'width': '10%', 'class': 'text-center'},
    ]
    
    context = {
        'summary_data': summary_data,
        'headers': headers,
        'month_str': month_date.strftime('%Y-%m'),
        'month_display': month_date.strftime('%B %Y'),
        'total_summaries': total_summaries,
        'approved_count': approved_count,
        'pending_count': pending_count,
        'departments': departments,
        'employees': employees,
        'paginator': paginator,
        'page_obj': summaries_page,
        
        # بيانات الهيدر الموحد
        'page_title': 'ملخصات الحضور الشهرية',
        'page_subtitle': f'عرض وإدارة ملخصات حضور الموظفين لشهر {month_date.strftime("%B %Y")}',
        'page_icon': 'fas fa-calendar-check',
        'header_buttons': [
            {
                'url': reverse('hr:attendance_list'),
                'icon': 'fa-clock',
                'text': 'سجل الحضور اليومي',
                'class': 'btn-info',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'ملخصات الحضور', 'active': True},
        ],
    }
    return render(request, 'hr/attendance/summary_list.html', context)


# ============================================
# attendance_summary_detail with Smart Auto-recalculate
# ============================================

@login_required
def attendance_summary_detail(request, pk):
    """
    عرض تفاصيل ملخص الحضور مع Smart Auto-recalculate
    - يعيد الحساب تلقائياً لو البيانات قديمة (> 5 دقائق)
    - يستخدم locking لمنع concurrent calculations
    """
    from django.core.cache import cache
    from django.utils import timezone
    from hr.models import PermissionRequest
    from utils.helpers import arabic_date_format
    import time

    summary = get_object_or_404(AttendanceSummary, pk=pk)
    
    # Smart Auto-recalculate: Only if not approved and data is stale
    recalculated = False
    if not summary.is_approved:
        should_recalculate = False
        
        # Check if stale (older than 5 minutes)
        if summary.updated_at:
            age = timezone.now() - summary.updated_at
            if age > timedelta(minutes=5):
                should_recalculate = True
        else:
            should_recalculate = True
        
        # Check if has new attendance data
        if not should_recalculate:
            latest_attendance = Attendance.objects.filter(
                employee=summary.employee,
                date__year=summary.month.year,
                date__month=summary.month.month
            ).order_by('-updated_at').first()
            
            if latest_attendance and latest_attendance.updated_at > summary.updated_at:
                should_recalculate = True
        
        # Recalculate with lock to prevent concurrent calculations
        if should_recalculate:
            lock_key = f'summary_calc_{summary.id}'
            
            # Try to acquire lock (timeout 60 seconds)
            if cache.add(lock_key, 'locked', timeout=60):
                try:
                    summary.calculate()
                    recalculated = True
                finally:
                    cache.delete(lock_key)
            else:
                # Another process is calculating, wait and refresh
                time.sleep(0.5)
                summary.refresh_from_db()

    # تحديد بداية ونهاية الشهر
    start_date = summary.month.replace(day=1)
    if summary.month.month == 12:
        end_date = summary.month.replace(year=summary.month.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end_date = summary.month.replace(month=summary.month.month + 1, day=1) - timedelta(days=1)

    # السجلات اليومية
    daily_records = summary.employee.attendances.filter(
        date__gte=start_date,
        date__lte=end_date,
    ).select_related('shift').order_by('date')

    # إحصائيات
    total_present = summary.present_days + summary.late_days
    permissions_count = PermissionRequest.objects.filter(
        employee=summary.employee,
        date__year=summary.month.year,
        date__month=summary.month.month,
        status='approved'
    ).count()
    
    stats = {
        'total_working_days': summary.total_working_days,
        'present_days': total_present,
        'absent_days': summary.absent_days,
        'late_days': summary.late_days,
        'permissions_count': permissions_count,
        'total_work_hours': summary.total_work_hours,
        'total_late_minutes': summary.total_late_minutes,
        'total_early_leave_minutes': summary.total_early_leave_minutes,
        'present_subtitle': f'من أصل {summary.total_working_days} يوم عمل',
        'absent_subtitle': f'من أصل {summary.total_working_days} يوم عمل',
    }

    # عنوان فرعي
    month_ar = arabic_date_format(summary.month)
    try:
        month_suffix = month_ar.split(' ', 1)[1]
    except Exception:
        month_suffix = summary.month.strftime('%Y-%m')
    
    # إضافة timestamp آخر تحديث للعنوان الفرعي
    subtitle = f'تقرير حضور: {month_suffix}'
    if summary.updated_at:
        subtitle += f' - آخر تحديث: {summary.updated_at.strftime("%Y-%m-%d %H:%M")}'
    
    # إعداد أزرار الهيدر
    header_buttons = [
        {
            'url': reverse('hr:integrated_payroll_dashboard'),
            'icon': 'fa-calculator',
            'text': 'معالجة الرواتب',
            'class': 'btn-outline-primary',
        },
        {
            'url': reverse('hr:payroll_list'),
            'icon': 'fa-money-bill-wave',
            'text': 'قائمة الرواتب',
            'class': 'btn-outline-secondary',
        },
    ]
    
    # إضافة زر الاعتماد إذا لم يكن معتمداً
    if not summary.is_approved and request.user.has_perm('hr.change_attendancesummary'):
        header_buttons.insert(0, {
            'form_id': 'approve-summary-form',
            'icon': 'fa-check-circle',
            'text': 'اعتماد الملخص',
            'class': 'btn-success',
        })

    context = {
        'summary': summary,
        'employee': summary.employee,
        'daily_records': daily_records,
        'stats': stats,
        'recalculated': recalculated,
        'page_title': f'{summary.employee.get_full_name_ar()}',
        'page_subtitle': subtitle,
        'page_icon': 'fas fa-calendar-check',
        'header_buttons': header_buttons,
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'ملخصات الحضور', 'url': reverse('hr:attendance_summary_list'), 'icon': 'fas fa-calendar-check'},
            {'title': 'ملخص الحضور', 'active': True},
        ],
    }
    return render(request, 'hr/attendance/attendance_summary_detail.html', context)


@login_required
@require_POST
def approve_attendance_summary(request, pk):
    """اعتماد ملخص الحضور."""
    summary = get_object_or_404(AttendanceSummary, pk=pk)
    try:
        AttendanceSummaryService.approve_summary(summary, request.user)
        messages.success(request, 'تم اعتماد ملخص الحضور بنجاح.')
    except Exception as e:
        messages.error(request, f'حدث خطأ أثناء اعتماد الملخص: {e}')
    return redirect('hr:attendance_summary_detail', pk=pk)


@login_required
@require_POST
def recalculate_attendance_summary(request, pk):
    """إعادة حساب ملخص الحضور."""
    summary = get_object_or_404(AttendanceSummary, pk=pk)
    try:
        AttendanceSummaryService.recalculate_summary(summary)
        messages.success(request, 'تمت إعادة حساب ملخص الحضور بنجاح.')
    except Exception as e:
        messages.error(request, f'حدث خطأ أثناء إعادة الحساب: {e}')
    return redirect('hr:attendance_summary_detail', pk=pk)


@login_required
def attendance_check_out(request):
    """تسجيل الانصراف"""
    if request.method == 'POST':
        employee_id = request.POST.get('employee_id')
        
        if employee_id:
            try:
                employee = Employee.objects.get(pk=employee_id)
                attendance = AttendanceService.record_check_out(employee)
                messages.success(request, f'تم تسجيل انصراف {employee.get_full_name_ar()} بنجاح')
                return redirect('hr:attendance_list')
            except Exception as e:
                messages.error(request, f'خطأ: {str(e)}')
        else:
            messages.error(request, 'يرجى اختيار الموظف')
    
    context = {
        'employees': Employee.objects.filter(status='active')
    }
    return render(request, 'hr/attendance/check_out.html', context)


# ============================================
# calculate_attendance_summaries (moved from integrated_payroll_views)
# ============================================

@login_required
@permission_required('hr.can_process_payroll', raise_exception=True)
@require_POST
def calculate_attendance_summaries(request):
    """حساب ملخصات الحضور لجميع الموظفين"""
    import logging
    logger = logging.getLogger(__name__)
    
    month_str = request.POST.get('month')
    if not month_str:
        month_date = date.today().replace(day=1)
    else:
        try:
            month_date = date.fromisoformat(month_str + '-01')
        except (ValueError, TypeError):
            messages.error(request, 'تاريخ غير صحيح')
            return redirect('hr:integrated_payroll_dashboard')
    
    # حساب الملخصات
    results = AttendanceSummaryService.calculate_all_summaries_for_month(month_date)
    
    messages.success(
        request,
        f'تم حساب {len(results["success"])} ملخص حضور بنجاح. '
        f'فشل {len(results["failed"])} ملخص.'
    )
    
    if results['failed']:
        for item in results['failed'][:5]:
            messages.warning(
                request,
                f'{item["employee"].get_full_name_ar()}: {item["error"]}'
            )
    
    url = reverse('hr:integrated_payroll_dashboard') + f'?month={month_date.strftime("%Y-%m")}'
    return redirect(url)
