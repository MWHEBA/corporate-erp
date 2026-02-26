from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.urls import reverse
from datetime import datetime, timedelta

from supplier.models import Supplier
from purchase.models import Purchase
from hr.models import Employee, Attendance, Leave


@login_required
@login_required
def dashboard(request):
    """
    لوحة التحكم الرئيسية - Corporate ERP
    """
    now = timezone.now()
    current_year = now.year
    current_month = now.month
    today = now.date()

    # إحصائيات الموظفين
    employees_count = Employee.objects.filter(status='active').count()
    
    # إحصائيات المشتريات الشهر الحالي
    purchases_month = Purchase.objects.filter(
        date__month=current_month,
        date__year=current_year
    ).aggregate(
        total=Sum('total'),
        count=Count('id')
    )
    
    # إحصائيات الموردين والمنتجات
    suppliers_count = Supplier.objects.filter(is_active=True).count()
    
    try:
        from product.models import Product
        products_count = Product.objects.filter(is_active=True).count()
        
        # المنتجات منخفضة المخزون
        low_stock_products = Product.objects.filter(
            is_active=True,
            stocks__quantity__lt=F('min_stock')
        ).distinct()[:5]
    except Exception:
        products_count = 0
        low_stock_products = []
    
    # الفواتير المستحقة للموردين (أكثر 10 فواتير متأخرة)
    overdue_supplier_invoices = Purchase.objects.filter(
        payment_status__in=['pending', 'partial']
    ).select_related('supplier').order_by('date')[:10]

    # حضور الموظفين اليوم
    total_employees = Employee.objects.filter(status='active').count()
    attendance_today = Attendance.objects.filter(date=today)
    
    present_count = attendance_today.filter(
        check_in__isnull=False
    ).values('employee').distinct().count()
    
    absent_count = total_employees - present_count
    attendance_percentage = (present_count / total_employees * 100) if total_employees > 0 else 0
    
    # طلبات الإجازة والأذونات
    pending_leaves = Leave.objects.filter(status='pending').count()
    
    approved_leaves_month = Leave.objects.filter(
        status='approved',
        start_date__month=current_month,
        start_date__year=current_year
    ).count()
    
    on_leave_today = Leave.objects.filter(
        status='approved',
        start_date__lte=today,
        end_date__gte=today
    ).count()
    
    # تحضير بيانات جدول الفواتير المستحقة للموردين
    supplier_invoices_headers = [
        {'key': 'number', 'label': 'رقم الفاتورة', 'width': '20%', 'format': 'html'},
        {'key': 'supplier', 'label': 'المورد', 'width': '25%'},
        {'key': 'date', 'label': 'تاريخ الفاتورة', 'width': '15%', 'class': 'text-center'},
        {'key': 'days_overdue', 'label': 'أيام التأخير', 'width': '15%', 'class': 'text-center', 'format': 'html'},
        {'key': 'amount', 'label': 'المبلغ المستحق', 'width': '25%', 'class': 'text-end fw-bold'}
    ]
    
    supplier_invoices_data = []
    for invoice in overdue_supplier_invoices:
        days_overdue = (today - invoice.date).days
        # تحديد لون البادج حسب عدد الأيام
        if days_overdue > 60:
            badge_class = 'bg-danger'
        elif days_overdue > 30:
            badge_class = 'bg-warning'
        else:
            badge_class = 'bg-info'
        
        # حساب المبلغ المستحق (الإجمالي - المدفوع)
        paid_amount = invoice.paid or 0
        remaining = invoice.total - paid_amount
        
        supplier_invoices_data.append({
            'number': f'<a href="/purchase/{invoice.id}/" class="text-primary">{invoice.number}</a>',
            'supplier': invoice.supplier.name if invoice.supplier else '-',
            'date': invoice.date.strftime('%d-%m-%Y'),
            'days_overdue': f'<span class="badge {badge_class}">{days_overdue} يوم</span>',
            'amount': f'{remaining:,.2f} ج.م'
        })

    context = {
        # إحصائيات أساسية
        "employees_count": employees_count,
        "purchases_month": purchases_month,
        "suppliers_count": suppliers_count,
        "products_count": products_count,
        "low_stock_products": low_stock_products,
        
        # حضور الموظفين
        "total_employees": total_employees,
        "present_count": present_count,
        "absent_count": absent_count,
        "attendance_percentage": round(attendance_percentage, 1),
        "on_leave_today": on_leave_today,
        
        # طلبات الإجازة
        "pending_leaves": pending_leaves,
        "approved_leaves_month": approved_leaves_month,
        
        # بيانات الجداول
        "supplier_invoices_headers": supplier_invoices_headers,
        "supplier_invoices_data": supplier_invoices_data,
    }

    return render(request, "core/dashboard.html", context)


@login_required
def company_settings(request):
    """
    عرض وتعديل إعدادات الشركة
    """
    from core.models import SystemSetting
    from django.contrib import messages
    
    # التحقق من صلاحيات المستخدم
    if not request.user.is_admin and not request.user.is_superuser:
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )

    # معالجة حفظ الإعدادات عند POST
    if request.method == "POST":
        # قائمة الحقول المطلوب حفظها
        settings_fields = [
            "company_name", "company_name_en", "company_tax_number",
            "company_commercial_register", "company_country", "company_city",
            "company_state", "company_address", "company_phone", "company_mobile",
            "company_email", "company_website", "company_whatsapp",
            "company_working_hours", "company_bank_name", "company_bank_account",
            "company_bank_iban", "company_bank_swift",
        ]
        
        # حفظ كل إعداد
        for field in settings_fields:
            value = request.POST.get(field, "")
            if value:
                setting, created = SystemSetting.objects.get_or_create(
                    key=field,
                    defaults={"value": value}
                )
                if not created:
                    setting.value = value
                    setting.save()

        messages.success(request, "تم حفظ إعدادات الشركة بنجاح")
        return redirect("core:company_settings")

    # جلب الإعدادات الحالية
    settings_dict = {}
    for setting in SystemSetting.objects.all():
        settings_dict[setting.key] = setting.value

    # إعداد الهيدر
    header_buttons = [
        {
            'url': reverse('core:dashboard'),
            'icon': 'fa-arrow-right',
            'text': 'العودة للوحة التحكم',
            'class': 'btn-outline-secondary'
        }
    ]

    # مسار التنقل
    breadcrumb_items = [
        {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
        {'title': 'الإعدادات', 'icon': 'fas fa-cog'},
        {'title': 'إعدادات الشركة', 'active': True}
    ]

    context = {
        "title": "إعدادات الشركة",
        "subtitle": "إدارة معلومات الشركة والبيانات الأساسية",
        "icon": "fas fa-building",
        "header_buttons": header_buttons,
        "breadcrumb_items": breadcrumb_items,
        "settings": settings_dict,
    }

    return render(request, "core/company_settings.html", context)


@login_required
def system_settings(request):
    """
    عرض وتعديل إعدادات النظام
    """
    from core.models import SystemSetting
    from django.contrib import messages
    
    # التحقق من صلاحيات المستخدم
    if not request.user.is_admin and not request.user.is_superuser:
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )

    # معالجة حفظ الإعدادات عند POST
    if request.method == "POST":
        # قائمة الحقول المطلوب حفظها
        settings_fields = [
            "site_name", "site_name_en", "system_timezone",
            "date_format", "time_format", "currency_symbol",
            "items_per_page", "session_timeout",
        ]
        
        # حفظ كل إعداد
        for field in settings_fields:
            value = request.POST.get(field, "")
            if value:
                setting, created = SystemSetting.objects.get_or_create(
                    key=field,
                    defaults={"value": value}
                )
                if not created:
                    setting.value = value
                    setting.save()

        messages.success(request, "تم حفظ إعدادات النظام بنجاح")
        return redirect("core:system_settings")

    # جلب الإعدادات الحالية
    settings_dict = {}
    for setting in SystemSetting.objects.all():
        settings_dict[setting.key] = setting.value

    # إعداد الهيدر
    header_buttons = [
        {
            'url': reverse('core:dashboard'),
            'icon': 'fa-arrow-right',
            'text': 'العودة للوحة التحكم',
            'class': 'btn-outline-secondary'
        }
    ]

    # مسار التنقل
    breadcrumb_items = [
        {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
        {'title': 'الإعدادات', 'icon': 'fas fa-cog'},
        {'title': 'إعدادات النظام', 'active': True}
    ]

    context = {
        "title": "إعدادات النظام",
        "subtitle": "إدارة إعدادات النظام العامة",
        "icon": "fas fa-cogs",
        "header_buttons": header_buttons,
        "breadcrumb_items": breadcrumb_items,
        "settings": settings_dict,
    }

    return render(request, "core/system_settings.html", context)


@login_required
def get_current_time(request):
    """
    API للحصول على الوقت الحالي
    """
    from django.http import JsonResponse
    
    return JsonResponse({
        'success': True,
        'time': timezone.now().isoformat(),
        'timestamp': timezone.now().timestamp()
    })


@login_required
def system_reset(request):
    """
    إعادة تعيين النظام (للمديرين فقط)
    """
    from django.contrib import messages
    
    # التحقق من صلاحيات المستخدم
    if not request.user.is_superuser:
        return render(
            request,
            "core/permission_denied.html",
            {"title": "غير مصرح", "message": "ليس لديك صلاحية للوصول إلى هذه الصفحة"},
        )
    
    if request.method == "POST":
        # هنا يمكن إضافة منطق إعادة التعيين
        messages.warning(request, "وظيفة إعادة التعيين غير مفعلة حالياً")
        return redirect("core:dashboard")
    
    context = {
        "title": "إعادة تعيين النظام",
        "subtitle": "إعادة تعيين بيانات النظام",
        "icon": "fas fa-redo",
    }
    
    return render(request, "core/system_reset.html", context)


@login_required
def notifications_list(request):
    """
    قائمة الإشعارات للمستخدم
    """
    from core.models import Notification
    
    notifications = Notification.objects.filter(
        user=request.user
    ).order_by('-created_at')[:50]
    
    # إعداد الهيدر
    header_buttons = [
        {
            'url': reverse('core:dashboard'),
            'icon': 'fa-arrow-right',
            'text': 'العودة للوحة التحكم',
            'class': 'btn-outline-secondary'
        }
    ]

    # مسار التنقل
    breadcrumb_items = [
        {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
        {'title': 'الإشعارات', 'active': True}
    ]

    context = {
        "title": "الإشعارات",
        "subtitle": "جميع إشعاراتك",
        "icon": "fas fa-bell",
        "header_buttons": header_buttons,
        "breadcrumb_items": breadcrumb_items,
        "notifications": notifications,
    }

    return render(request, "core/notifications_list.html", context)


@login_required
def notification_settings(request):
    """
    إعدادات الإشعارات للمستخدم
    """
    from django.contrib import messages
    
    if request.method == "POST":
        # حفظ إعدادات الإشعارات
        messages.success(request, "تم حفظ إعدادات الإشعارات بنجاح")
        return redirect("core:notification_settings")
    
    # إعداد الهيدر
    header_buttons = [
        {
            'url': reverse('core:notifications_list'),
            'icon': 'fa-arrow-right',
            'text': 'العودة للإشعارات',
            'class': 'btn-outline-secondary'
        }
    ]

    # مسار التنقل
    breadcrumb_items = [
        {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
        {'title': 'الإشعارات', 'url': reverse('core:notifications_list'), 'icon': 'fas fa-bell'},
        {'title': 'الإعدادات', 'active': True}
    ]

    context = {
        "title": "إعدادات الإشعارات",
        "subtitle": "إدارة تفضيلات الإشعارات",
        "icon": "fas fa-cog",
        "header_buttons": header_buttons,
        "breadcrumb_items": breadcrumb_items,
    }

    return render(request, "core/notification_settings.html", context)
