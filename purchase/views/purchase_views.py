"""
Purchase Invoice Views
عرض وإدارة فواتير المشتريات
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.urls import reverse
from django.core.paginator import Paginator
from django.db.models import Sum
from decimal import Decimal
import logging

from purchase.models import Purchase, PurchasePayment, PurchaseItem
from purchase.forms import PurchaseForm
from product.models import Product, Warehouse
from supplier.models import Supplier

logger = logging.getLogger(__name__)


@login_required
def purchase_list(request):
    """
    عرض قائمة فواتير المشتريات
    """
    # الاستعلام الأساسي مع ترتيب تنازلي حسب التاريخ ثم الرقم
    purchases_query = Purchase.objects.select_related(
        'supplier', 'warehouse', 'financial_category'
    ).all().order_by("-date", "-id")

    # تصفية حسب المورد
    supplier = request.GET.get("supplier")
    if supplier:
        purchases_query = purchases_query.filter(supplier_id=supplier)

    # تصفية حسب حالة الدفع
    payment_status = request.GET.get("payment_status")
    if payment_status:
        purchases_query = purchases_query.filter(payment_status=payment_status)
    
    # تصفية حسب نوع الفاتورة (خدمة/منتج)
    is_service = request.GET.get("is_service")
    if is_service == "true":
        purchases_query = purchases_query.filter(is_service=True)
    elif is_service == "false":
        purchases_query = purchases_query.filter(is_service=False)
    
    # تصفية حسب نوع الخدمة
    service_type = request.GET.get("service_type")
    if service_type:
        purchases_query = purchases_query.filter(service_type=service_type)

    # تصفية حسب التاريخ
    date_from = request.GET.get("date_from")
    if date_from:
        purchases_query = purchases_query.filter(date__gte=date_from)

    date_to = request.GET.get("date_to")
    if date_to:
        purchases_query = purchases_query.filter(date__lte=date_to)

    # التصفح والترقيم
    paginator = Paginator(purchases_query, 25)
    page = request.GET.get("page")
    purchases = paginator.get_page(page)

    # إحصائيات للعرض في الصفحة
    paid_purchases_count = Purchase.objects.filter(payment_status="paid").count()
    partially_paid_purchases_count = Purchase.objects.filter(
        payment_status="partially_paid"
    ).count()
    unpaid_purchases_count = Purchase.objects.filter(payment_status="unpaid").count()

    # عدد الفواتير المرتجعة
    returned_purchases_count = (
        Purchase.objects.filter(returns__status="confirmed").distinct().count()
    )

    # إجمالي المشتريات
    total_amount = Purchase.objects.aggregate(Sum("total"))["total__sum"] or 0
    
    # إحصائيات الخدمات
    services_count = Purchase.objects.filter(is_service=True).count()
    products_count = Purchase.objects.filter(is_service=False).count()
    courses_count = Purchase.objects.filter(service_type='course').count()
    transportation_count = Purchase.objects.filter(service_type='transportation').count()

    # الحصول على قائمة الموردين للفلترة
    suppliers = Supplier.objects.filter(is_active=True).order_by("name")

    # تعريف عناوين أعمدة الجدول
    purchase_headers = [
        {
            "key": "number",
            "label": _("رقم الفاتورة"),
            "sortable": True,
            "class": "text-center",
            "format": "reference",
            "variant": "highlight-code",
            "app": "purchase",
        },
        {
            "key": "created_at",
            "label": _("التاريخ والوقت"),
            "sortable": True,
            "class": "text-center",
            "format": "datetime_12h",
        },
        {"key": "supplier.name", "label": _("المورد"), "sortable": True},
        {
            "key": "service_type_display",
            "label": _("النوع"),
            "sortable": True,
            "class": "text-center",
            "format": "badge",
            "badge_class": "bg-success",
            "default": "منتج",
        },
        {"key": "warehouse.name", "label": _("المخزن"), "sortable": True},
        {
            "key": "financial_category.name",
            "label": _("التصنيف المالي"),
            "sortable": True,
            "class": "text-center",
            "format": "badge",
            "badge_class": "bg-info",
            "default": "غير محدد",
        },
        {
            "key": "total",
            "label": _("الإجمالي"),
            "sortable": True,
            "class": "text-center",
            "format": "currency",
            "decimals": 2,
        },
        {
            "key": "payment_method",
            "label": _("طريقة الدفع"),
            "sortable": True,
            "class": "text-center",
            "template": "components/cells/purchase_payment_method.html",
        },
        {
            "key": "payment_status",
            "label": _("حالة الدفع"),
            "sortable": True,
            "class": "text-center",
            "format": "status",
        },
        {
            "key": "return_status",
            "label": _("حالة الإرجاع"),
            "sortable": True,
            "class": "text-center",
            "format": "status",
        },
    ]

    # تعريف أزرار الإجراءات للجدول
    purchase_actions = [
        {
            "url": "purchase:purchase_detail",
            "icon": "fa-eye",
            "label": _("عرض"),
            "class": "action-view",
        },
        {
            "url": "purchase:purchase_edit",
            "icon": "fa-edit",
            "label": _("تعديل"),
            "class": "action-edit",
            "condition": "not_fully_paid",
        },
        {
            "url": "purchase:purchase_delete",
            "icon": "fa-trash",
            "label": _("حذف"),
            "class": "action-delete",
            "condition": "no_posted_payments",
        },
        {
            "url": "purchase:purchase_add_payment",
            "icon": "fa-money-bill",
            "label": _("إضافة دفعة"),
            "class": "action-paid",
            "condition": "not_fully_paid",
        },
    ]

    # تحضير بيانات الجدول
    table_data = []
    for purchase in purchases:
        # تحضير أزرار الإجراءات لكل فاتورة
        actions = []
        
        # زر العرض (دائماً متاح)
        actions.append({
            'url': reverse('purchase:purchase_detail', args=[purchase.pk]),
            'icon': 'fas fa-eye',
            'label': 'عرض',
            'class': 'btn-outline-info btn-sm'
        })
        
        # زر التعديل (إذا لم تكن مدفوعة بالكامل)
        if purchase.payment_status != 'paid':
            actions.append({
                'url': reverse('purchase:purchase_edit', args=[purchase.pk]),
                'icon': 'fas fa-edit',
                'label': 'تعديل',
                'class': 'btn-outline-primary btn-sm'
            })
        
        # زر إضافة دفعة (إذا لم تكن مدفوعة بالكامل)
        if purchase.payment_status != 'paid':
            actions.append({
                'url': reverse('purchase:purchase_add_payment', args=[purchase.pk]),
                'icon': 'fas fa-money-bill',
                'label': 'دفعة',
                'class': 'btn-outline-success btn-sm'
            })
        
        # زر الحذف (إذا لم يكن لها دفعات مرحّلة)
        has_posted_payments = purchase.payments.filter(status='posted').exists()
        if not has_posted_payments:
            actions.append({
                'onclick': f'confirmDelete({purchase.pk})',
                'icon': 'fas fa-trash',
                'label': 'حذف',
                'class': 'btn-outline-danger btn-sm'
            })
        
        # تحضير بيانات الصف
        row_data = {
            'id': purchase.id,
            'number': purchase.number,
            'created_at': purchase.created_at,
            'supplier.name': purchase.supplier.name,
            'service_type_display': purchase.get_service_type_display() if purchase.is_service else 'منتج',
            'warehouse.name': purchase.warehouse.name if purchase.warehouse else 'غير محدد',
            'financial_category.name': purchase.financial_category.name if purchase.financial_category else 'غير محدد',
            'total': purchase.total,
            'payment_method': purchase.get_payment_method_display(),
            'payment_status': purchase.payment_status,
            'return_status': purchase.return_status if purchase.is_returned else 'none',
            'actions': actions
        }
        table_data.append(row_data)

    context = {
        "purchases": purchases,
        "table_headers": purchase_headers,
        "table_data": table_data,
        "paid_purchases_count": paid_purchases_count,
        "partially_paid_purchases_count": partially_paid_purchases_count,
        "unpaid_purchases_count": unpaid_purchases_count,
        "returned_purchases_count": returned_purchases_count,
        "total_amount": total_amount,
        "suppliers": suppliers,
        "purchase_headers": purchase_headers,
        "purchase_actions": purchase_actions,
        "services_count": services_count,
        "products_count": products_count,
        "courses_count": courses_count,
        "transportation_count": transportation_count,
        "service_types": Purchase.SERVICE_TYPES,
        "page_title": "فواتير المشتريات",
        "page_subtitle": "قائمة بجميع فواتير المشتريات في النظام",
        "page_icon": "fas fa-shopping-cart",
        "header_buttons": [
            {
                "url": reverse("purchase:purchase_create"),
                "icon": "fa-plus",
                "text": "إضافة فاتورة",
                "class": "btn-primary",
            }
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {"title": "المشتريات", "url": "#", "icon": "fas fa-truck"},
            {"title": "فواتير المشتريات", "active": True},
        ],
    }

    return render(request, "purchase/purchase_list.html", context)


@login_required
def purchase_create(request, supplier_id=None):
    """
    إنشاء فاتورة مشتريات جديدة
    يمكن تمرير معرف المورد لاختياره تلقائياً
    """
    # التحقق من وجود المورد إذا تم تمرير معرفه
    selected_supplier = None
    is_service_invoice = False
    
    if supplier_id:
        try:
            selected_supplier = Supplier.objects.get(id=supplier_id, is_active=True)
            # تحديد نوع الفاتورة من إعدادات نوع المورد (ديناميكي)
            if selected_supplier.primary_type and hasattr(selected_supplier.primary_type, 'settings') and selected_supplier.primary_type.settings:
                is_service_invoice = selected_supplier.primary_type.settings.is_service_provider
            else:
                # Fallback للطريقة القديمة
                is_service_invoice = selected_supplier.is_service_provider() or selected_supplier.is_driver()
        except Supplier.DoesNotExist:
            messages.error(request, "المورد المحدد غير موجود أو غير نشط")
            return redirect("purchase:purchase_list")
    
    # فلترة المنتجات حسب نوع المورد
    # استثناء المنتجات المجمعة - لا يمكن شراؤها من الموردين
    if is_service_invoice:
        # موردين خدميين → عرض الخدمات فقط
        products = Product.objects.filter(is_active=True, is_service=True).order_by("name")
    else:
        # موردين عامين → عرض المنتجات فقط (ليس خدمات وليس مجمعة)
        products = Product.objects.filter(is_active=True, is_service=False, is_bundle=False).order_by("name")

    if request.method == "POST":
        form = PurchaseForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    # إنشاء فاتورة المشتريات
                    purchase = form.save(commit=False)
                    purchase.subtotal = Decimal(request.POST.get("subtotal", 0))
                    purchase.total = Decimal(request.POST.get("total", 0))
                    purchase.created_by = request.user
                    
                    # معالجة نوع الفاتورة (نقدي/آجل)
                    invoice_type = request.POST.get("invoice_type", "")
                    if invoice_type == "credit":
                        # فاتورة آجلة: تعيين payment_method كـ credit
                        purchase.payment_method = "credit"
                    elif invoice_type == "cash":
                        # فاتورة نقدية: استخدام payment_method من الفورم (account code)
                        # القيمة موجودة بالفعل في form.cleaned_data
                        pass
                    
                    # تعيين حقول الخدمة تلقائياً من نوع المورد
                    purchase.auto_set_service_fields()
                    
                    # التأكد من عدم وجود مخزن للفواتير الخدمية
                    if purchase.is_service:
                        purchase.warehouse = None
                    
                    purchase.save()

                    # إضافة بنود الفاتورة
                    product_ids = request.POST.getlist("product[]")
                    quantities = request.POST.getlist("quantity[]")
                    unit_prices = request.POST.getlist("unit_price[]")
                    discounts = request.POST.getlist("discount[]")

                    for i in range(len(product_ids)):
                        if product_ids[i]:  # تخطي الصفوف الفارغة
                            product = get_object_or_404(Product, id=product_ids[i])
                            quantity = int(float(quantities[i]))
                            unit_price = Decimal(unit_prices[i])
                            discount = (
                                Decimal(discounts[i]) if discounts[i] else Decimal("0")
                            )

                            # إنشاء بند فاتورة
                            # Signal سيتولى إنشاء حركة المخزون تلقائياً
                            item = PurchaseItem(
                                purchase=purchase,
                                product=product,
                                quantity=quantity,
                                unit_price=unit_price,
                                discount=discount,
                                total=(Decimal(quantity) * unit_price) - discount,
                            )
                            item.save()

                    # إنشاء دفعة تلقائية للفواتير النقدية فقط
                    if invoice_type == "cash" and purchase.payment_method not in ["credit", ""]:
                        # payment_method هو account code (مثل 10100)
                        payment_account_code = purchase.payment_method
                        if payment_account_code:
                            try:
                                from financial.models.chart_of_accounts import (
                                    ChartOfAccounts,
                                )

                                financial_account = ChartOfAccounts.objects.get(
                                    code=payment_account_code
                                )

                                # إنشاء دفعة تلقائية بالمبلغ الكامل
                                payment = PurchasePayment.objects.create(
                                    purchase=purchase,
                                    amount=purchase.total,
                                    payment_date=purchase.date,
                                    payment_method=payment_account_code,
                                    financial_account=financial_account,
                                    created_by=request.user,
                                    notes="دفعة تلقائية - فاتورة نقدية",
                                    status="posted",
                                )

                                # إنشاء قيد محاسبي للدفعة
                                from financial.services.accounting_integration_service import (
                                    AccountingIntegrationService,
                                )

                                journal_entry = AccountingIntegrationService.create_payment_journal_entry(
                                    payment=payment,
                                    payment_type="purchase_payment",
                                    user=request.user,
                                )

                                if journal_entry:
                                    payment.financial_transaction = journal_entry
                                    payment.financial_status = "synced"
                                    payment.save(
                                        update_fields=[
                                            "financial_transaction",
                                            "financial_status",
                                        ]
                                    )
                                    logger.info(
                                        f"✅ تم إنشاء دفعة تلقائية وقيد محاسبي للفاتورة النقدية: {purchase.number}"
                                    )

                            except Exception as e:
                                logger.error(
                                    f"❌ خطأ في إنشاء الدفعة التلقائية: {str(e)}"
                                )
                                messages.warning(
                                    request,
                                    f"تم إنشاء الفاتورة لكن فشل إنشاء الدفعة التلقائية: {str(e)}",
                                )
                        else:
                            messages.warning(
                                request, "تحذير: لم يتم اختيار خزينة للفاتورة النقدية"
                            )

                    messages.success(request, "تم إنشاء فاتورة المشتريات بنجاح")
                    return redirect("purchase:purchase_list")

            except Exception as e:
                messages.error(request, f"حدث خطأ أثناء إنشاء الفاتورة: {str(e)}")
        else:
            messages.error(request, "يرجى تصحيح الأخطاء الموجودة في النموذج")
    else:
        # إنشاء رقم فاتورة مشتريات جديد
        last_purchase = Purchase.objects.order_by("-id").first()
        next_number = f"PUR{(last_purchase.id + 1 if last_purchase else 1):04d}"

        initial_data = {
            "date": timezone.now().date(),
            "number": next_number,
        }
        # إضافة المورد المحدد إلى البيانات الافتراضية
        if selected_supplier:
            initial_data["supplier"] = selected_supplier
            
        form = PurchaseForm(initial=initial_data)

    # جلب البيانات المطلوبة للقوائم المنسدلة (مطلوب في كل الحالات)
    suppliers = Supplier.objects.filter(is_active=True).order_by("name")
    warehouses = Warehouse.objects.filter(is_active=True).order_by("name")
    
    # إضافة أول مخزن متاح كافتراضي للنموذج الجديد
    if request.method == "GET" and warehouses.exists():
        form.initial["warehouse"] = warehouses.first()

    # إنشاء رقم فاتورة مشتريات جديد
    last_purchase = Purchase.objects.order_by("-id").first()
    next_purchase_number = f"PUR{(last_purchase.id + 1 if last_purchase else 1):04d}"

    # إضافة متغيرات عنوان الصفحة
    context = {
        "form": form,
        "products": products,
        "suppliers": suppliers,
        "warehouses": warehouses,
        "next_purchase_number": next_purchase_number,
        "selected_supplier": selected_supplier,
        "is_service_invoice": is_service_invoice,
        "supplier_type_code": selected_supplier.get_primary_type_code() if selected_supplier else None,
        "default_warehouse": warehouses.first() if warehouses.exists() else None,
        "page_title": "إضافة فاتورة مشتريات" + (f" - {selected_supplier.name}" if selected_supplier else ""),
        "page_subtitle": "إضافة فاتورة مشتريات جديدة إلى النظام",
        "page_icon": "fas fa-plus-circle",
        "header_buttons": [
            {
                "url": reverse("supplier:supplier_detail", kwargs={"pk": selected_supplier.pk}) if selected_supplier else reverse("purchase:purchase_list"),
                "icon": "fa-arrow-right",
                "text": "العودة لتفاصيل المورد" if selected_supplier else "العودة للقائمة",
                "class": "btn-secondary",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "المشتريات",
                "url": reverse("purchase:purchase_list"),
                "icon": "fas fa-shopping-bag",
            },
        ] + ([{
            "title": selected_supplier.name,
            "url": reverse("supplier:supplier_detail", kwargs={"pk": selected_supplier.pk}),
            "icon": "fas fa-truck",
        }] if selected_supplier else []) + [
            {"title": "إضافة فاتورة", "active": True},
        ],
    }

    return render(request, "purchase/purchase_form.html", context)


@login_required
def purchase_detail(request, pk):
    """
    عرض تفاصيل فاتورة المشتريات
    """
    purchase = get_object_or_404(Purchase, pk=pk)
    # الحصول على المدفوعات مرتبة حسب تاريخ الإنشاء من الأحدث إلى الأقدم
    payments = purchase.payments.all().order_by("-created_at")

    # فحص إذا كان يجب عرض SweetAlert للترحيل
    show_post_alert = request.session.pop("show_post_alert", None)
    
    # تحديد نوع الفاتورة للعنوان
    invoice_type_name = "فاتورة خدمات" if purchase.is_service_invoice else "فاتورة مشتريات"

    context = {
        "purchase": purchase,
        "payments": payments,
        "title": f"تفاصيل {invoice_type_name}",
        "page_title": f"{invoice_type_name} - {purchase.number}",
        "page_subtitle": f"عرض تفاصيل {invoice_type_name} وإدارتها",
        "page_icon": purchase.invoice_type_icon,
        "show_post_alert": show_post_alert,
        "header_buttons": [
            {
                "url": reverse("purchase:purchase_print", kwargs={"pk": purchase.pk}),
                "icon": "fa-print",
                "text": "طباعة",
                "class": "btn-info",
            },
        ] + ([{
            "url": reverse("purchase:purchase_add_payment", kwargs={"pk": purchase.pk}),
            "icon": "fa-money-bill",
            "text": "إضافة دفعة",
            "class": "btn-success",
        }] if purchase.payment_status != 'paid' else []) + [
            {
                "url": "#",
                "icon": "fa-ellipsis-v",
                "text": "",
                "class": "btn-outline-secondary",
                "toggle": "modal",
                "target": "#actionsModal",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "لوحة التحكم",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-tachometer-alt",
            },
            {
                "title": "المشتريات",
                "url": reverse("purchase:purchase_list"),
                "icon": "fas fa-shopping-basket",
            },
            {
                "title": purchase.supplier.name,
                "url": reverse("supplier:supplier_detail", args=[purchase.supplier.pk]),
                "icon": "fas fa-truck",
            },
            {"title": f"فاتورة {purchase.number}", "active": True},
        ],
    }
    return render(request, "purchase/purchase_detail.html", context)


@login_required
def purchase_update(request, pk):
    """
    تعديل فاتورة مشتريات مع دعم القيود التصحيحية للفواتير المرحّلة
    """
    purchase = get_object_or_404(Purchase, pk=pk)

    # التحقق من الصلاحيات
    if not request.user.has_perm("purchase.change_purchase"):
        messages.error(request, "ليس لديك صلاحية لتعديل فواتير المشتريات")
        return redirect("purchase:purchase_list")

    # منع تعديل الفواتير المدفوعة بالكامل
    if purchase.payment_status == "paid":
        messages.error(request, "لا يمكن تعديل فاتورة مدفوعة بالكامل")
        return redirect("purchase:purchase_detail", pk=purchase.pk)

    # التحقق من حالة القيد المحاسبي
    has_posted_entry = (
        purchase.journal_entry and 
        purchase.journal_entry.status == 'posted'
    )

    # حفظ القيم الأصلية للمقارنة (قبل التعديل)
    original_total = purchase.total

    # الحصول على البنود الأصلية قبل التعديل
    original_items = {}
    for item in purchase.items.all():
        original_items[item.product.id] = item.quantity

    if request.method == "POST":
        from purchase.forms import PurchaseUpdateForm
        form = PurchaseForm(request.POST, instance=purchase)
        if form.is_valid():
            try:
                # استيراد StockMovement محلياً لتجنب مشاكل الاستيراد الدائري
                from product.models import StockMovement
                
                with transaction.atomic():
                    updated_purchase = form.save(commit=False)

                    # الحصول على قيمة الضريبة من النموذج (إذا كانت مقدمة) وتحويلها إلى Decimal
                    tax_value = Decimal(form.cleaned_data.get("tax", 0) or 0)

                    # معالجة بنود الفاتورة
                    product_ids = request.POST.getlist("product[]")
                    quantities = request.POST.getlist("quantity[]")
                    unit_prices = request.POST.getlist("unit_price[]")
                    discounts = request.POST.getlist("discount[]")

                    # تتبع البنود المحفوظة لحذف أي بنود محذوفة
                    saved_item_ids = []

                    # حساب المجموع الفرعي
                    subtotal = Decimal("0")

                    # إنشاء قاموس للكميات الجديدة
                    new_items = {}

                    # حفظ البنود
                    for i in range(len(product_ids)):
                        if not product_ids[i]:  # تخطي البنود الفارغة
                            continue

                        product = get_object_or_404(Product, id=product_ids[i])
                        quantity = int(quantities[i])
                        unit_price = Decimal(unit_prices[i])
                        discount = Decimal(discounts[i] if discounts[i] else "0")

                        # حساب إجمالي البند
                        item_total = (quantity * unit_price) - discount
                        subtotal += item_total

                        # البحث عن البند الموجود أو إنشاء بند جديد
                        item, created = PurchaseItem.objects.update_or_create(
                            purchase=purchase,
                            product=product,
                            defaults={
                                "quantity": quantity,
                                "unit_price": unit_price,
                                "discount": discount,
                                "total": item_total,
                            },
                        )

                        saved_item_ids.append(item.id)
                        # حفظ الكمية الجديدة في القاموس
                        new_items[product.id] = quantity

                    # حذف البنود الغير موجودة في النموذج
                    PurchaseItem.objects.filter(purchase=purchase).exclude(
                        id__in=saved_item_ids
                    ).delete()

                    # تحديث المجموع الفرعي والإجمالي
                    updated_purchase.subtotal = subtotal
                    updated_purchase.tax = tax_value
                    updated_purchase.total = (
                        subtotal - Decimal(updated_purchase.discount) + tax_value
                    )

                    # حفظ التعديلات
                    updated_purchase.save()

                    # تعريف رقم المرجع الرئيسي
                    main_reference = f"PURCHASE-{updated_purchase.number}"

                    # معالجة المنتجات المضافة أو التي تغيرت كميتها - استخدام MovementService
                    from governance.services import MovementService
                    
                    movement_service = MovementService()
                    
                    for product_id, new_quantity in new_items.items():
                        original_quantity = original_items.get(product_id, 0)
                        quantity_diff = new_quantity - original_quantity

                        if quantity_diff != 0:  # فقط إذا كان هناك تغيير في الكمية
                            product = Product.objects.get(id=product_id)
                            
                            # تخطي الخدمات
                            if product.is_service:
                                continue

                            # استخدام MovementService بدلاً من التحديث المباشر
                            try:
                                if quantity_diff > 0:  # زيادة الكمية
                                    movement = movement_service.process_movement(
                                        product_id=product_id,
                                        quantity_change=Decimal(str(quantity_diff)),
                                        movement_type='in',
                                        source_reference=f"PUR-EDIT-{updated_purchase.number}",
                                        idempotency_key=f"purchase_edit_{updated_purchase.id}_{product_id}_increase_{timezone.now().timestamp()}",
                                        user=request.user,
                                        unit_cost=Decimal(str(unit_prices[list(new_items.keys()).index(product_id)])),
                                        document_number=updated_purchase.number,
                                        notes=f"زيادة كمية منتج في تعديل فاتورة مشتريات رقم {updated_purchase.number}"
                                    )
                                else:  # نقص الكمية
                                    movement = movement_service.process_movement(
                                        product_id=product_id,
                                        quantity_change=-Decimal(str(abs(quantity_diff))),
                                        movement_type='out',
                                        source_reference=f"PUR-EDIT-{updated_purchase.number}",
                                        idempotency_key=f"purchase_edit_{updated_purchase.id}_{product_id}_decrease_{timezone.now().timestamp()}",
                                        user=request.user,
                                        document_number=updated_purchase.number,
                                        notes=f"نقص كمية منتج في تعديل فاتورة مشتريات رقم {updated_purchase.number}"
                                    )
                                
                                logger.info(
                                    f"✅ تم تحديث المخزون عبر MovementService: {movement.id} - "
                                    f"المنتج {product.name} - الفرق: {quantity_diff}"
                                )
                            except Exception as e:
                                logger.error(f"❌ خطأ في تحديث المخزون عبر MovementService: {str(e)}")
                                raise

                    # معالجة المنتجات المحذوفة - استخدام MovementService
                    for product_id, original_quantity in original_items.items():
                        if product_id not in new_items:  # إذا كان المنتج موجود سابقًا وتم حذفه
                            product = Product.objects.get(id=product_id)
                            
                            # تخطي الخدمات
                            if product.is_service:
                                continue

                            # استخدام MovementService لخصم الكمية المحذوفة
                            try:
                                movement = movement_service.process_movement(
                                    product_id=product_id,
                                    quantity_change=-Decimal(str(original_quantity)),
                                    movement_type='out',
                                    source_reference=f"PUR-EDIT-DELETE-{updated_purchase.number}",
                                    idempotency_key=f"purchase_edit_{updated_purchase.id}_{product_id}_delete_{timezone.now().timestamp()}",
                                    user=request.user,
                                    document_number=updated_purchase.number,
                                    notes=f"حذف منتج من فاتورة مشتريات رقم {updated_purchase.number}"
                                )
                                
                                logger.info(
                                    f"✅ تم خصم المخزون عبر MovementService: {movement.id} - "
                                    f"المنتج {product.name} - الكمية: {original_quantity}"
                                )
                            except Exception as e:
                                logger.error(f"❌ خطأ في خصم المخزون عبر MovementService: {str(e)}")
                                raise

                    # تحديث مديونية المورد (يتم تنفيذه من خلال الإشارة في signals.py)

                    # إنشاء قيد تصحيحي إذا كانت الفاتورة مرحّلة
                    if has_posted_entry:
                        try:
                            from financial.services.accounting_integration_service import (
                                AccountingIntegrationService,
                            )
                            
                            adjustment_entry = AccountingIntegrationService.create_purchase_adjustment_entry(
                                purchase=updated_purchase,
                                old_total=original_total,
                                user=request.user
                            )
                            
                            if adjustment_entry:
                                messages.success(
                                    request,
                                    f"تم تعديل فاتورة المشتريات بنجاح وإنشاء قيد تصحيحي: {adjustment_entry.number}"
                                )
                                logger.info(
                                    f"✅ تم إنشاء قيد تصحيحي {adjustment_entry.number} "
                                    f"لتعديل فاتورة {updated_purchase.number}"
                                )
                            else:
                                messages.success(
                                    request,
                                    "تم تعديل فاتورة المشتريات بنجاح (لا توجد فروقات تتطلب قيد تصحيحي)"
                                )
                        except Exception as e:
                            logger.error(f"❌ خطأ في إنشاء القيد التصحيحي: {str(e)}")
                            messages.warning(
                                request,
                                f"تم تعديل الفاتورة لكن فشل إنشاء القيد التصحيحي: {str(e)}"
                            )
                    else:
                        messages.success(request, _("تم تعديل فاتورة المشتريات بنجاح"))
                    
                return redirect("purchase:purchase_detail", pk=pk)
            except Exception as e:
                messages.error(request, f"حدث خطأ أثناء تعديل الفاتورة: {str(e)}")
                logger.error(f"Error updating purchase: {str(e)}")
        else:
            # طباعة أخطاء النموذج بشكل مفصل
            logger.error(f"Form errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"خطأ في الحقل {field}: {error}")
    else:
        from purchase.forms import PurchaseUpdateForm
        form = PurchaseUpdateForm(instance=purchase)

    # جلب البيانات المطلوبة للقوائم المنسدلة
    suppliers = Supplier.objects.filter(is_active=True).order_by("name")
    warehouses = Warehouse.objects.filter(is_active=True).order_by("name")
    products = Product.objects.filter(is_active=True).order_by("name")

    context = {
        "form": form,
        "purchase": purchase,
        "products": products,
        "suppliers": suppliers,
        "warehouses": warehouses,
        "title": "تعديل فاتورة مشتريات",
        "page_title": f"تعديل فاتورة مشتريات - {purchase.number}",
        "page_icon": "fas fa-edit",
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "فواتير المشتريات",
                "url": reverse("purchase:purchase_list"),
                "icon": "fas fa-shopping-cart",
            },
            {"title": f"تعديل {purchase.number}", "active": True},
        ],
    }

    return render(request, "purchase/purchase_form.html", context)


@login_required
def purchase_delete(request, pk):
    """
    حذف فاتورة المشتريات
    """
    purchase = get_object_or_404(Purchase, pk=pk)

    # التحقق مما إذا كانت الفاتورة لها مرتجعات مؤكدة
    has_confirmed_returns = purchase.returns.filter(status="confirmed").exists()

    if has_confirmed_returns:
        messages.error(request, "لا يمكن حذف الفاتورة لأنها تحتوي على مرتجعات مؤكدة")
        return redirect("purchase:purchase_detail", pk=purchase.pk)

    # التحقق من وجود دفعات مرحلة
    has_posted_payments = purchase.payments.filter(status="posted").exists()

    if has_posted_payments:
        messages.error(
            request,
            "لا يمكن حذف الفاتورة لأنها تحتوي على دفعات مرحلة. يجب إلغاء ترحيل الدفعات أولاً."
        )
        return redirect("purchase:purchase_detail", pk=purchase.pk)

    if request.method == "POST":
        try:
            # استيراد Stock محلياً لتجنب مشاكل الاستيراد الدائري
            from product.models import Stock
            
            # التحقق من المخزون المتاح قبل الحذف
            insufficient_stock_items = []
            for item in purchase.items.all():
                stock = Stock.objects.filter(
                    product=item.product,
                    warehouse=purchase.warehouse
                ).first()
                
                current_quantity = stock.quantity if stock else 0
                
                if current_quantity < item.quantity:
                    insufficient_stock_items.append({
                        'product': item.product.name,
                        'required': item.quantity,
                        'available': current_quantity,
                        'sold': item.quantity - current_quantity
                    })
            
            # إذا كان هناك منتجات تم بيعها، منع الحذف
            if insufficient_stock_items:
                error_message = "لا يمكن حذف الفاتورة - تم بيع جزء من المنتجات:\n\n"
                for item_info in insufficient_stock_items:
                    error_message += (
                        f"• {item_info['product']}: "
                        f"الكمية المطلوب إرجاعها {item_info['required']}، "
                        f"المتاح في المخزون {item_info['available']}، "
                        f"تم بيع {item_info['sold']}\n"
                    )
                error_message += "\nيجب إنشاء مرتجع مشتريات بدلاً من حذف الفاتورة."
                messages.error(request, error_message)
                return redirect("purchase:purchase_detail", pk=purchase.pk)
            
            with transaction.atomic():
                # signal handle_deleted_purchase_item سيتولى إنشاء الحركات المعاكسة

                # إلغاء ترحيل وحذف القيد المحاسبي المرتبط بالفاتورة إذا وُجد
                journal_entry_info = ""
                if purchase.journal_entry:
                    journal_entry = purchase.journal_entry
                    journal_entry_number = journal_entry.number
                    journal_entry_status = journal_entry.status
                    
                    # إلغاء ترحيل القيد أولاً إذا كان مرحلاً
                    if journal_entry_status == "posted":
                        try:
                            journal_entry.status = "draft"
                            journal_entry.save(update_fields=['status'])
                            logger.info(f"✅ تم إلغاء ترحيل القيد المحاسبي {journal_entry_number}")
                            journal_entry_info = f" وتم إلغاء ترحيل وحذف القيد المحاسبي {journal_entry_number}"
                        except Exception as e:
                            logger.error(f"❌ فشل في إلغاء ترحيل القيد {journal_entry_number}: {e}")
                            journal_entry_info = f" وتم حذف القيد المحاسبي {journal_entry_number} (فشل إلغاء الترحيل)"
                    else:
                        journal_entry_info = f" وتم حذف القيد المحاسبي {journal_entry_number}"
                    
                    # حذف القيد المحاسبي وخطوطه
                    journal_entry.delete()
                    logger.info(f"✅ تم حذف القيد المحاسبي {journal_entry_number} المرتبط بفاتورة المشتريات {purchase.number}")

                # حذف الفاتورة (CASCADE سيحذف البنود و signals ستعالج المخزون)
                purchase_number = purchase.number
                purchase.delete()

                messages.success(
                    request,
                    f"تم حذف فاتورة المشتريات {purchase_number} بنجاح{journal_entry_info}. تم إرجاع المخزون بشكل صحيح.",
                )
                return redirect("purchase:purchase_list")

        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء حذف الفاتورة: {str(e)}")
            return redirect("purchase:purchase_detail", pk=purchase.pk)

    context = {
        "purchase": purchase,
        "page_title": f"حذف فاتورة {purchase.number}",
        "page_subtitle": f"{purchase.supplier.name} | {purchase.date.strftime('%d-%m-%Y')}",
        "page_icon": "fas fa-trash",
        "breadcrumb_items": [
            {
                "title": "لوحة التحكم",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-tachometer-alt",
            },
            {
                "title": "المشتريات",
                "url": reverse("purchase:purchase_list"),
                "icon": "fas fa-shopping-basket",
            },
            {
                "title": f"فاتورة {purchase.number}",
                "url": reverse("purchase:purchase_detail", kwargs={"pk": purchase.pk}),
                "icon": "fas fa-file-invoice",
            },
            {"title": "حذف", "active": True},
        ],
    }

    return render(request, "purchase/purchase_confirm_delete.html", context)


@login_required
def purchase_print(request, pk):
    """
    طباعة فاتورة المشتريات
    """
    purchase = get_object_or_404(Purchase, pk=pk)
    today = timezone.now().date()
    year = timezone.now().year

    context = {
        "purchase": purchase,
        "title": f"طباعة فاتورة المشتريات - {purchase.number}",
        "today": today,
        "year": year,
    }

    return render(request, "purchase/purchase_print.html", context)
