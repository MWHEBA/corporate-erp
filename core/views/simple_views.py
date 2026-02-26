from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F
from django.db.models.functions import TruncMonth
from django.utils import timezone
from datetime import datetime, timedelta
from calendar import monthrange

from purchase.models import Purchase
from supplier.models import Supplier
from product.models import Product


@login_required
def dashboard(request):
    """
    لوحة التحكم الرئيسية - Corporate ERP
    """
    now = timezone.now()
    current_year = now.year
    current_month = now.month

    # إحصائيات المشتريات الشهر الحالي
    purchases_today = Purchase.objects.filter(date__month=current_month, date__year=current_year)
    purchases_today_count = purchases_today.count()
    purchases_today_total = purchases_today.aggregate(total=Sum("total"))["total"] or 0

    # إحصائيات الموردين والمنتجات
    suppliers_count = Supplier.objects.filter(is_active=True).count()
    products_count = Product.objects.filter(is_active=True).count()

    # أحدث المشتريات
    recent_purchases = Purchase.objects.select_related('supplier').order_by("-date", "-id")[:5]

    # المنتجات منخفضة المخزون
    stock_condition = Q(stocks__quantity__lt=F("min_stock"))
    low_stock_products = (
        Product.objects.filter(is_active=True).filter(stock_condition).distinct()[:5]
    )

    # إحصائيات الشهر الحالي
    purchases_month = Purchase.objects.filter(
        date__month=current_month,
        date__year=current_year
    ).aggregate(
        total=Sum('total'),
        count=Count('id')
    )

    # ديون الموردين = الرصيد الموجب فقط
    supplier_debts = Supplier.objects.filter(balance__gt=0).aggregate(
        total=Sum('balance')
    )['total'] or 0

    # بيانات المشتريات الشهرية للرسم البياني
    purchases_by_month = Purchase.objects.filter(
        date__year=current_year
    ).annotate(
        month=TruncMonth('date')
    ).values('month').annotate(
        total=Sum('total')
    ).order_by('month')

    # تحضير بيانات الرسم البياني
    months_ar = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
                 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']
    
    purchases_data = [0] * 12
    for item in purchases_by_month:
        month_index = item['month'].month - 1
        purchases_data[month_index] = float(item['total'] or 0)

    # بيانات اليوم (كل ساعتين)
    today_start = now.replace(hour=8, minute=0, second=0, microsecond=0)
    purchases_by_hour = []
    for i in range(7):
        hour_start = today_start + timedelta(hours=i*2)
        hour_end = hour_start + timedelta(hours=2)
        purchases_hour = Purchase.objects.filter(date=now.date(), created_at__gte=hour_start, created_at__lt=hour_end).aggregate(total=Sum('total'))['total'] or 0
        purchases_by_hour.append(float(purchases_hour))

    # بيانات الأسبوع (آخر 7 أيام)
    week_start = now.date() - timedelta(days=6)
    purchases_by_day = []
    days_ar = []
    for i in range(7):
        day = week_start + timedelta(days=i)
        purchases_day = Purchase.objects.filter(date=day).aggregate(total=Sum('total'))['total'] or 0
        purchases_by_day.append(float(purchases_day))
        days_ar.append(['السبت', 'الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة'][day.weekday()])

    # بيانات الشهر (أسبوعياً)
    days_in_month = monthrange(current_year, current_month)[1]
    
    purchases_by_week = []
    week_labels = []
    
    # تقسيم الشهر إلى أسابيع
    for week in range(4):
        start_day = week * 7 + 1
        end_day = min((week + 1) * 7, days_in_month)
        
        if start_day > days_in_month:
            break
            
        week_start_date = now.date().replace(day=start_day)
        week_end_date = now.date().replace(day=end_day)
        
        purchases_week = Purchase.objects.filter(date__gte=week_start_date, date__lte=week_end_date).aggregate(total=Sum('total'))['total'] or 0
        
        purchases_by_week.append(float(purchases_week))
        week_labels.append(f"{start_day}-{end_day} {months_ar[current_month-1]}")

    context = {
        "purchases_today": {
            "count": purchases_today_count,
            "total": purchases_today_total,
        },
        "suppliers_count": suppliers_count,
        "products_count": products_count,
        "recent_purchases": recent_purchases,
        "low_stock_products": low_stock_products,
        
        # إحصائيات الشهر
        "purchases_month": purchases_month,
        "supplier_debts": supplier_debts,
        
        # بيانات الرسوم البيانية
        "months_ar": months_ar,
        "purchases_data": purchases_data,
        "purchases_by_hour": purchases_by_hour,
        "purchases_by_day": purchases_by_day,
        "days_ar": days_ar,
        "purchases_by_week": purchases_by_week,
        "week_labels": week_labels,
    }

    return render(request, "core/dashboard.html", context)
