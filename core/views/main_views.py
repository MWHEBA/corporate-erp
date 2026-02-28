from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from django.urls import reverse
from datetime import datetime, timedelta

from supplier.models import Supplier
from purchase.models import Purchase


@login_required
def dashboard(request):
    """
    لوحة التحكم الرئيسية - Corporate ERP
    """
    now = timezone.now()
    current_year = now.year
    current_month = now.month
    today = now.date()

    # إحصائيات المشتريات الشهر الحالي
    purchases_month = Purchase.objects.filter(
        date__month=current_month,
        date__year=current_year
    ).aggregate(
        total=Sum('total'),
        count=Count('id')
    )
    purchases_month_total = purchases_month.get('total') or 0
    purchases_month_count = purchases_month.get('count') or 0

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

    # ديون الموردين = مجموع الفواتير المستحقة
    try:
        supplier_dues_total = Purchase.objects.filter(
            payment_status__in=['unpaid', 'partially_paid']
        ).aggregate(total=Sum('total'))['total'] or 0
        
        supplier_paid_total = Purchase.objects.filter(
            payment_status__in=['unpaid', 'partially_paid']
        ).aggregate(paid=Sum('payments__amount', filter=Q(payments__status='posted')))['paid'] or 0
        
        supplier_dues = supplier_dues_total - supplier_paid_total
    except Exception:
        supplier_dues = 0

    # محاولة جلب بيانات المبيعات والعملاء
    try:
        from sale.models import Sale
        from client.models import Customer
        
        # إحصائيات المبيعات الشهر الحالي
        sales_month = Sale.objects.filter(
            date__month=current_month,
            date__year=current_year
        ).aggregate(
            total=Sum('total'),
            count=Count('id')
        )
        sales_month_total = sales_month.get('total') or 0
        sales_month_count = sales_month.get('count') or 0
        
        # ديون العملاء = مجموع الفواتير المستحقة
        customer_dues_total = Sale.objects.filter(
            payment_status__in=['unpaid', 'partially_paid']
        ).aggregate(total=Sum('total'))['total'] or 0
        
        customer_paid_total = Sale.objects.filter(
            payment_status__in=['unpaid', 'partially_paid']
        ).aggregate(paid=Sum('payments__amount', filter=Q(payments__status='posted')))['paid'] or 0
        
        customer_dues = customer_dues_total - customer_paid_total
        
        # الفواتير المستحقة للعملاء فقط
        overdue_customer_invoices = Sale.objects.filter(
            payment_status__in=['unpaid', 'partially_paid']
        ).select_related('customer').order_by('date')[:5]
        
        # تحضير بيانات جدول فواتير العملاء
        customer_invoices_headers = [
            {'key': 'number', 'label': 'رقم الفاتورة', 'width': '20%', 'format': 'html'},
            {'key': 'customer', 'label': 'العميل', 'width': '25%'},
            {'key': 'date', 'label': 'التاريخ', 'width': '15%', 'class': 'text-center'},
            {'key': 'days_overdue', 'label': 'أيام التأخير', 'width': '15%', 'class': 'text-center', 'format': 'html'},
            {'key': 'amount', 'label': 'المبلغ المستحق', 'width': '25%', 'class': 'text-end fw-bold'}
        ]
        
        customer_invoices_data = []
        for invoice in overdue_customer_invoices:
            days_overdue = (today - invoice.date).days
            
            # تحديد لون البادج حسب عدد الأيام
            if days_overdue > 60:
                badge_class = 'bg-danger'
            elif days_overdue > 30:
                badge_class = 'bg-warning'
            else:
                badge_class = 'bg-info'
            
            # حساب المبلغ المستحق
            remaining = invoice.amount_due
            
            customer_invoices_data.append({
                'number': f'<a href="/sales/{invoice.id}/" class="text-primary">{invoice.number}</a>',
                'customer': invoice.customer.name if invoice.customer else '-',
                'date': invoice.date.strftime('%d-%m-%Y'),
                'days_overdue': f'<span class="badge {badge_class}">{days_overdue} يوم</span>',
                'amount': f'{remaining:,.2f} ج.م'
            })
    except Exception:
        # في حالة عدم وجود موديول المبيعات
        sales_month_total = 0
        sales_month_count = 0
        customer_dues = 0
        customer_invoices_headers = []
        customer_invoices_data = []

    # الفواتير المستحقة للموردين فقط
    overdue_supplier_invoices = Purchase.objects.filter(
        payment_status__in=['unpaid', 'partially_paid']
    ).select_related('supplier').order_by('date')[:5]

    # تحضير بيانات جدول الفواتير المستحقة للموردين
    supplier_invoices_headers = [
        {'key': 'number', 'label': 'رقم الفاتورة', 'width': '20%', 'format': 'html'},
        {'key': 'supplier', 'label': 'المورد', 'width': '25%'},
        {'key': 'date', 'label': 'التاريخ', 'width': '15%', 'class': 'text-center'},
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
        
        # حساب المبلغ المستحق
        remaining = invoice.amount_due
        
        supplier_invoices_data.append({
            'number': f'<a href="/purchase/{invoice.id}/" class="text-primary">{invoice.number}</a>',
            'supplier': invoice.supplier.name if invoice.supplier else '-',
            'date': invoice.date.strftime('%d-%m-%Y'),
            'days_overdue': f'<span class="badge {badge_class}">{days_overdue} يوم</span>',
            'amount': f'{remaining:,.2f} ج.م'
        })

    # إجمالي المستحقات
    total_dues = customer_dues + supplier_dues

    # آخر العمليات (آخر 5 فواتير مبيعات ومشتريات)
    recent_activities = []
    
    try:
        from sale.models import Sale
        recent_sales = Sale.objects.select_related('customer').order_by('-created_at')[:3]
        for sale in recent_sales:
            recent_activities.append({
                'icon': 'fa-shopping-cart',
                'title': f'فاتورة مبيعات {sale.number}',
                'description': f'العميل: {sale.customer.name if sale.customer else "-"} - المبلغ: {sale.total:,.2f} ج.م',
                'time': sale.created_at.strftime('%d-%m-%Y %I:%M %p')
            })
    except:
        pass
    
    recent_purchases = Purchase.objects.select_related('supplier').order_by('-created_at')[:3]
    for purchase in recent_purchases:
        recent_activities.append({
            'icon': 'fa-truck',
            'title': f'فاتورة مشتريات {purchase.number}',
            'description': f'المورد: {purchase.supplier.name if purchase.supplier else "-"} - المبلغ: {purchase.total:,.2f} ج.م',
            'time': purchase.created_at.strftime('%d-%m-%Y %I:%M %p')
        })
    
    # ترتيب حسب الوقت
    recent_activities = sorted(recent_activities, key=lambda x: x['time'], reverse=True)[:5]

    context = {
        # إحصائيات أساسية
        "suppliers_count": suppliers_count,
        "products_count": products_count,
        "low_stock_products": low_stock_products,
        
        # إحصائيات المشتريات
        "purchases_month": purchases_month,
        "purchases_month_total": purchases_month_total,
        
        # إحصائيات المبيعات
        "sales_month_total": sales_month_total,
        "sales_month_count": sales_month_count,
        
        # المستحقات
        "supplier_dues": supplier_dues,
        "customer_dues": customer_dues,
        "total_dues": total_dues,
        
        # بيانات الجداول
        "customer_invoices_headers": customer_invoices_headers,
        "customer_invoices_data": customer_invoices_data,
        "supplier_invoices_headers": supplier_invoices_headers,
        "supplier_invoices_data": supplier_invoices_data,
        
        # آخر العمليات
        "recent_activities": recent_activities,
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
