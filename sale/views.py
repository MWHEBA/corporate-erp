"""
Sale Views - Updated with SaleService
محدث: يستخدم SaleService مع AccountingGateway و MovementService
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.translation import gettext as _
from django.urls import reverse
from django.core.paginator import Paginator
from decimal import Decimal
import logging

from sale.models import Sale, SaleItem, SalePayment, SaleReturn, SaleReturnItem
from sale.forms import SaleForm, SalePaymentForm, SaleReturnForm
from sale.services import SaleService
from product.models import Product, Warehouse, SerialNumber
from client.models import Customer

logger = logging.getLogger(__name__)


@login_required
def sale_create(request, customer_id=None):
    """
    إنشاء فاتورة مبيعات جديدة
    ✅ محدث: يستخدم SaleService مع الحوكمة الكاملة
    """
    products = Product.objects.filter(is_active=True).order_by("name")
    
    # التحقق من وجود العميل إذا تم تمرير معرفه
    selected_customer = None
    if customer_id:
        try:
            selected_customer = Customer.objects.get(id=customer_id, is_active=True)
        except Customer.DoesNotExist:
            messages.error(request, "العميل المحدد غير موجود أو غير نشط")
            return redirect("sale:sale_list")

    if request.method == "POST":
        form = SaleForm(request.POST)

        if form.is_valid():
            try:
                # تجهيز بيانات الفاتورة
                sale_data = {
                    'date': form.cleaned_data['date'],
                    'customer_id': form.cleaned_data['customer'].id,
                    'warehouse_id': form.cleaned_data['warehouse'].id,
                    'payment_method': form.cleaned_data['payment_method'],
                    'discount': Decimal(request.POST.get("discount", "0")),
                    'tax': Decimal(request.POST.get("tax", "0")),
                    'notes': form.cleaned_data.get('notes', ''),
                    'items': []
                }
                
                # تجهيز بيانات البنود
                product_ids = request.POST.getlist("product[]")
                quantities = request.POST.getlist("quantity[]")
                unit_prices = request.POST.getlist("unit_price[]")
                discounts = request.POST.getlist("discount[]")
                
                for i in range(len(product_ids)):
                    if product_ids[i]:
                        sale_data['items'].append({
                            'product_id': int(product_ids[i]),
                            'quantity': Decimal(quantities[i]),
                            'unit_price': Decimal(unit_prices[i]),
                            'discount': Decimal(discounts[i] if discounts[i] else '0'),
                        })
                
                # إنشاء الفاتورة عبر SaleService (مع الحوكمة الكاملة)
                sale = SaleService.create_sale(data=sale_data, user=request.user)
                
                # معالجة الدفعة التلقائية للفواتير النقدية
                if sale.payment_method == "cash":
                    payment_account_code = request.POST.get("payment_method")  # من payment_account_select
                    if payment_account_code:
                        payment_data = {
                            'amount': sale.total,
                            'payment_method': payment_account_code,
                            'payment_date': sale.date,
                            'notes': 'دفعة تلقائية - فاتورة نقدية'
                        }
                        SaleService.process_payment(sale, payment_data, request.user)
                        logger.info(f"✅ تم إنشاء دفعة تلقائية للفاتورة النقدية: {sale.number}")
                
                messages.success(request, "تم إنشاء فاتورة المبيعات بنجاح")
                return redirect("sale:sale_detail", pk=sale.pk)

            except Exception as e:
                logger.error(f"❌ خطأ في إنشاء الفاتورة: {str(e)}")
                messages.error(request, f"حدث خطأ أثناء إنشاء الفاتورة: {str(e)}")
    else:
        # تهيئة بيانات افتراضية
        initial_data = {
            "date": timezone.now().date(),
        }
        if selected_customer:
            initial_data["customer"] = selected_customer
        
        warehouses = Warehouse.objects.filter(is_active=True).order_by("name")
        if warehouses.exists():
            initial_data["warehouse"] = warehouses.first()
            
        form = SaleForm(initial=initial_data)

    # الحصول على الرقم التسلسلي التالي
    next_sale_number = None
    try:
        serial, created = SerialNumber.objects.get_or_create(
            document_type="sale",
            year=timezone.now().year,
            defaults={"prefix": "SALE", "last_number": 0},
        )
        last_sale = Sale.objects.order_by("-id").first()
        last_number = 0
        if last_sale and last_sale.number:
            try:
                last_number = int(last_sale.number.replace("SALE", ""))
            except (ValueError, AttributeError):
                pass
        next_number = max(serial.last_number, last_number) + 1
        next_sale_number = f"{serial.prefix}{next_number:04d}"
    except Exception as e:
        logger.error(f"خطأ في الحصول على الرقم التالي: {str(e)}")

    # جلب البيانات للنموذج
    customers = Customer.objects.filter(is_active=True).order_by("name")
    warehouses = Warehouse.objects.filter(is_active=True).order_by("name")

    context = {
        "products": products,
        "form": form,
        "next_sale_number": next_sale_number,
        "customers": customers,
        "warehouses": warehouses,
        "selected_customer": selected_customer,
        "default_warehouse": warehouses.first() if warehouses.exists() else None,
        "page_title": "إضافة فاتورة مبيعات" + (f" - {selected_customer.name}" if selected_customer else ""),
        "page_subtitle": "إضافة فاتورة مبيعات جديدة إلى النظام",
        "page_icon": "fas fa-file-invoice-dollar",
        "header_buttons": [
            {
                "url": reverse("client:customer_detail", kwargs={"pk": selected_customer.pk}) if selected_customer else reverse("sale:sale_list"),
                "icon": "fa-arrow-right",
                "text": f"العودة لتفاصيل {selected_customer.name}" if selected_customer else "العودة للقائمة",
                "class": "btn-secondary",
            }
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "المبيعات", "url": reverse("sale:sale_list"), "icon": "fas fa-shopping-cart"},
        ] + ([{
            "title": selected_customer.name,
            "url": reverse("client:customer_detail", kwargs={"pk": selected_customer.pk}),
            "icon": "fas fa-user",
        }] if selected_customer else []) + [
            {"title": "إضافة فاتورة", "active": True},
        ],
    }

    return render(request, "sale/sale_form.html", context)


@login_required
def sale_delete(request, pk):
    """
    حذف فاتورة مبيعات
    ✅ محدث: يستخدم SaleService للحذف الآمن
    """
    sale = get_object_or_404(Sale, pk=pk)

    if request.method == "POST":
        try:
            sale_number = sale.number
            
            # حذف الفاتورة عبر SaleService (مع التراجع الكامل)
            SaleService.delete_sale(sale, request.user)
            
            messages.success(request, f"تم حذف فاتورة المبيعات {sale_number} بنجاح")
            return redirect("sale:sale_list")
            
        except Exception as e:
            logger.error(f"❌ خطأ في حذف الفاتورة: {str(e)}")
            messages.error(request, f"حدث خطأ أثناء حذف الفاتورة: {str(e)}")
            return redirect("sale:sale_detail", pk=pk)

    context = {
        "sale": sale,
        "page_title": f"حذف فاتورة {sale.number}",
        "page_subtitle": "تأكيد حذف فاتورة المبيعات",
        "page_icon": "fas fa-trash",
    }
    return render(request, "sale/sale_confirm_delete.html", context)


@login_required
def add_payment(request, pk):
    """
    إضافة دفعة على فاتورة مبيعات
    ✅ محدث: يستخدم SaleService لمعالجة الدفعات
    """
    sale = get_object_or_404(Sale, pk=pk)

    if request.method == "POST":
        form = SalePaymentForm(request.POST)
        if form.is_valid():
            try:
                # تجهيز بيانات الدفعة
                payment_data = {
                    'amount': form.cleaned_data['amount'],
                    'payment_method': request.POST.get('payment_method'),  # من payment_account_select
                    'payment_date': form.cleaned_data.get('payment_date', timezone.now().date()),
                    'notes': form.cleaned_data.get('notes', ''),
                }
                
                # معالجة الدفعة عبر SaleService
                payment = SaleService.process_payment(sale, payment_data, request.user)
                
                messages.success(request, f"تم إضافة الدفعة بنجاح - المبلغ: {payment.amount} ج.م")
                return redirect("sale:sale_detail", pk=sale.pk)
                
            except Exception as e:
                logger.error(f"❌ خطأ في إضافة الدفعة: {str(e)}")
                messages.error(request, f"حدث خطأ أثناء إضافة الدفعة: {str(e)}")
        else:
            messages.error(request, "يرجى تصحيح الأخطاء في النموذج")
    else:
        initial_data = {
            'amount': sale.amount_due,
            'payment_date': timezone.now().date(),
        }
        form = SalePaymentForm(initial=initial_data)

    context = {
        "sale": sale,
        "form": form,
        "page_title": f"إضافة دفعة - فاتورة {sale.number}",
        "page_subtitle": f"المبلغ المتبقي: {sale.amount_due} ج.م",
        "page_icon": "fas fa-money-bill-wave",
        "header_buttons": [
            {
                "url": reverse("sale:sale_detail", kwargs={"pk": sale.pk}),
                "icon": "fa-arrow-right",
                "text": "العودة للفاتورة",
                "class": "btn-secondary",
            }
        ],
    }
    return render(request, "sale/add_payment.html", context)


@login_required
def sale_return(request, pk):
    """
    إنشاء مرتجع لفاتورة مبيعات
    ✅ محدث: يستخدم SaleService لإنشاء المرتجعات
    """
    sale = get_object_or_404(Sale, pk=pk)

    if request.method == "POST":
        form = SaleReturnForm(request.POST)
        if form.is_valid():
            try:
                # تجهيز بيانات المرتجع
                return_data = {
                    'return_date': form.cleaned_data.get('return_date', timezone.now().date()),
                    'reason': form.cleaned_data.get('reason', ''),
                    'notes': form.cleaned_data.get('notes', ''),
                    'items': []
                }
                
                # تجهيز بنود المرتجع
                sale_item_ids = request.POST.getlist("sale_item[]")
                quantities = request.POST.getlist("quantity[]")
                
                for i in range(len(sale_item_ids)):
                    if sale_item_ids[i] and quantities[i]:
                        sale_item = get_object_or_404(SaleItem, id=sale_item_ids[i], sale=sale)
                        return_data['items'].append({
                            'sale_item_id': int(sale_item_ids[i]),
                            'quantity': Decimal(quantities[i]),
                            'unit_price': sale_item.unit_price,
                        })
                
                # إنشاء المرتجع عبر SaleService
                sale_return = SaleService.create_return(sale, return_data, request.user)
                
                messages.success(request, f"تم إنشاء المرتجع بنجاح - رقم المرتجع: {sale_return.number}")
                return redirect("sale:sale_return_detail", pk=sale_return.pk)
                
            except Exception as e:
                logger.error(f"❌ خطأ في إنشاء المرتجع: {str(e)}")
                messages.error(request, f"حدث خطأ أثناء إنشاء المرتجع: {str(e)}")
        else:
            messages.error(request, "يرجى تصحيح الأخطاء في النموذج")
    else:
        initial_data = {
            'return_date': timezone.now().date(),
        }
        form = SaleReturnForm(initial=initial_data)

    context = {
        "sale": sale,
        "form": form,
        "sale_items": sale.items.all(),
        "page_title": f"إنشاء مرتجع - فاتورة {sale.number}",
        "page_subtitle": f"العميل: {sale.customer.name}",
        "page_icon": "fas fa-undo",
        "header_buttons": [
            {
                "url": reverse("sale:sale_detail", kwargs={"pk": sale.pk}),
                "icon": "fa-arrow-right",
                "text": "العودة للفاتورة",
                "class": "btn-secondary",
            }
        ],
    }
    return render(request, "sale/sale_return_form.html", context)


@login_required
def sale_detail(request, pk):
    """
    عرض تفاصيل فاتورة مبيعات
    ✅ محدث: يستخدم SaleService للإحصائيات
    """
    sale = get_object_or_404(Sale, pk=pk)
    
    # الحصول على الإحصائيات من SaleService
    statistics = SaleService.get_sale_statistics(sale)
    
    # الحصول على البنود والدفعات والمرتجعات
    items = sale.items.all()
    payments = sale.payments.all().order_by('-payment_date')
    returns = sale.returns.filter(status='confirmed').order_by('-return_date')

    context = {
        "sale": sale,
        "items": items,
        "payments": payments,
        "returns": returns,
        "statistics": statistics,
        "page_title": f"فاتورة مبيعات {sale.number}",
        "page_subtitle": f"العميل: {sale.customer.name} - التاريخ: {sale.date}",
        "page_icon": "fas fa-file-invoice-dollar",
        "header_buttons": [
            {
                "url": reverse("sale:add_payment", kwargs={"pk": sale.pk}),
                "icon": "fa-money-bill-wave",
                "text": "إضافة دفعة",
                "class": "btn-success",
            },
            {
                "url": reverse("sale:sale_return", kwargs={"pk": sale.pk}),
                "icon": "fa-undo",
                "text": "إنشاء مرتجع",
                "class": "btn-warning",
            },
            {
                "url": reverse("sale:sale_print", kwargs={"pk": sale.pk}),
                "icon": "fa-print",
                "text": "طباعة",
                "class": "btn-info",
            },
            {
                "url": reverse("sale:sale_list"),
                "icon": "fa-arrow-right",
                "text": "العودة للقائمة",
                "class": "btn-secondary",
            }
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "المبيعات", "url": reverse("sale:sale_list"), "icon": "fas fa-shopping-cart"},
            {"title": f"فاتورة {sale.number}", "active": True},
        ],
    }
    return render(request, "sale/sale_detail.html", context)



@login_required
def sale_list(request):
    """
    عرض قائمة فواتير المبيعات
    """
    sales_query = Sale.objects.all().order_by("-date", "-id")

    # تصفية حسب العميل
    customer = request.GET.get("customer")
    if customer:
        sales_query = sales_query.filter(customer_id=customer)

    # تصفية حسب حالة الدفع
    payment_status = request.GET.get("payment_status")
    if payment_status:
        sales_query = sales_query.filter(payment_status=payment_status)

    # تصفية حسب التاريخ
    date_from = request.GET.get("date_from")
    if date_from:
        sales_query = sales_query.filter(date__gte=date_from)

    date_to = request.GET.get("date_to")
    if date_to:
        sales_query = sales_query.filter(date__lte=date_to)

    # الترقيم
    from django.core.paginator import Paginator
    paginator = Paginator(sales_query, 25)
    page = request.GET.get("page")
    sales = paginator.get_page(page)

    # إحصائيات
    paid_sales_count = Sale.objects.filter(payment_status="paid").count()
    partially_paid_sales_count = Sale.objects.filter(payment_status="partially_paid").count()
    unpaid_sales_count = Sale.objects.filter(payment_status="unpaid").count()
    returned_sales_count = Sale.objects.filter(returns__status="confirmed").distinct().count()
    total_amount = Sale.objects.aggregate(Sum("total"))["total__sum"] or 0

    customers = Customer.objects.filter(is_active=True).order_by("name")

    context = {
        "sales": sales,
        "paid_sales_count": paid_sales_count,
        "partially_paid_sales_count": partially_paid_sales_count,
        "unpaid_sales_count": unpaid_sales_count,
        "returned_sales_count": returned_sales_count,
        "total_amount": total_amount,
        "customers": customers,
        "page_title": "فواتير المبيعات",
        "page_subtitle": "قائمة بجميع فواتير المبيعات في النظام",
        "page_icon": "fas fa-shopping-cart",
        "header_buttons": [
            {
                "url": reverse("sale:sale_create"),
                "icon": "fa-plus",
                "text": "إضافة فاتورة",
                "class": "btn-primary",
            }
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "المبيعات", "url": "#", "icon": "fas fa-truck"},
            {"title": "فواتير المبيعات", "active": True},
        ],
    }

    return render(request, "sale/sale_list.html", context)


@login_required
def sale_print(request, pk):
    """
    طباعة فاتورة مبيعات
    """
    sale = get_object_or_404(Sale, pk=pk)
    items = sale.items.all()
    
    context = {
        "sale": sale,
        "items": items,
        "company_name": "اسم الشركة",
        "company_address": "عنوان الشركة",
        "company_phone": "رقم الهاتف",
    }
    
    return render(request, "sale/sale_print.html", context)


@login_required
def sale_edit(request, pk):
    """
    تعديل فاتورة مبيعات
    ملاحظة: التعديل محدود - لا يمكن تعديل فاتورة مدفوعة بالكامل
    """
    sale = get_object_or_404(Sale, pk=pk)
    
    # التحقق من إمكانية التعديل
    if sale.is_fully_paid:
        messages.error(request, "لا يمكن تعديل فاتورة مدفوعة بالكامل")
        return redirect("sale:sale_detail", pk=pk)
    
    if sale.has_posted_payments:
        messages.warning(request, "تحذير: هذه الفاتورة تحتوي على دفعات مرحلة. التعديل محدود.")
    
    messages.info(request, "تعديل الفواتير محدود حالياً. يُنصح بإنشاء فاتورة جديدة.")
    return redirect("sale:sale_detail", pk=pk)


# Import necessary for sale_list
from django.db.models import Sum


# ==================== Payment Views ====================

@login_required
def redirect_to_unified_payments(request):
    """
    إعادة توجيه لصفحة المدفوعات الموحدة
    """
    messages.info(request, "يتم استخدام نظام المدفوعات الموحد")
    return redirect("financial:cash_accounts_list")


@login_required
def payment_detail(request, pk):
    """
    عرض تفاصيل دفعة
    """
    payment = get_object_or_404(SalePayment, pk=pk)
    
    context = {
        "payment": payment,
        "sale": payment.sale,
        "active_menu": "sales",
        "title": f"تفاصيل الدفعة #{payment.id}",
    }
    
    return render(request, "sale/payment_detail.html", context)


@login_required
def post_payment(request, payment_id):
    """
    ترحيل دفعة
    """
    payment = get_object_or_404(SalePayment, pk=payment_id)
    
    if payment.is_posted:
        messages.warning(request, "هذه الدفعة مرحلة بالفعل")
    else:
        try:
            # TODO: Implement posting logic with SaleService
            payment.is_posted = True
            payment.posted_at = timezone.now()
            payment.posted_by = request.user
            payment.save()
            messages.success(request, "تم ترحيل الدفعة بنجاح")
        except Exception as e:
            messages.error(request, f"خطأ في ترحيل الدفعة: {str(e)}")
    
    return redirect("sale:payment_detail", pk=payment_id)


@login_required
def unpost_payment(request, payment_id):
    """
    إلغاء ترحيل دفعة
    """
    payment = get_object_or_404(SalePayment, pk=payment_id)
    
    if not payment.is_posted:
        messages.warning(request, "هذه الدفعة غير مرحلة")
    else:
        try:
            # TODO: Implement unposting logic with SaleService
            payment.is_posted = False
            payment.posted_at = None
            payment.posted_by = None
            payment.save()
            messages.success(request, "تم إلغاء ترحيل الدفعة بنجاح")
        except Exception as e:
            messages.error(request, f"خطأ في إلغاء ترحيل الدفعة: {str(e)}")
    
    return redirect("sale:payment_detail", pk=payment_id)


@login_required
def unpost_payment_only(request, payment_id):
    """
    إلغاء ترحيل دفعة فقط (بدون إعادة توجيه)
    """
    payment = get_object_or_404(SalePayment, pk=payment_id)
    
    if not payment.is_posted:
        messages.warning(request, "هذه الدفعة غير مرحلة")
    else:
        try:
            payment.is_posted = False
            payment.posted_at = None
            payment.posted_by = None
            payment.save()
            messages.success(request, "تم إلغاء ترحيل الدفعة")
        except Exception as e:
            messages.error(request, f"خطأ: {str(e)}")
    
    return redirect("sale:sale_detail", pk=payment.sale.id)


@login_required
def edit_payment(request, payment_id):
    """
    تعديل دفعة
    """
    payment = get_object_or_404(SalePayment, pk=payment_id)
    
    if payment.is_posted:
        messages.error(request, "لا يمكن تعديل دفعة مرحلة. يجب إلغاء الترحيل أولاً")
        return redirect("sale:payment_detail", pk=payment_id)
    
    if request.method == "POST":
        form = SalePaymentForm(request.POST, instance=payment)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تعديل الدفعة بنجاح")
            return redirect("sale:payment_detail", pk=payment_id)
    else:
        form = SalePaymentForm(instance=payment)
    
    context = {
        "form": form,
        "payment": payment,
        "active_menu": "sales",
        "title": "تعديل دفعة",
    }
    
    return render(request, "sale/payment_edit.html", context)


# ==================== Sale Return Views ====================

@login_required
def sale_return_list(request):
    """
    قائمة مرتجعات المبيعات
    """
    returns = SaleReturn.objects.select_related("sale", "sale__customer").order_by("-date")
    
    # Pagination
    paginator = Paginator(returns, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    
    context = {
        "returns": page_obj,
        "active_menu": "sales",
        "title": "مرتجعات المبيعات",
    }
    
    return render(request, "sale/sale_return_list.html", context)


@login_required
def sale_return_detail(request, pk):
    """
    تفاصيل مرتجع مبيعات
    """
    sale_return = get_object_or_404(SaleReturn, pk=pk)
    items = sale_return.items.select_related("product").all()
    
    context = {
        "sale_return": sale_return,
        "items": items,
        "active_menu": "sales",
        "title": f"تفاصيل المرتجع #{sale_return.id}",
    }
    
    return render(request, "sale/sale_return_detail.html", context)


@login_required
def sale_return_confirm(request, pk):
    """
    تأكيد مرتجع مبيعات
    """
    sale_return = get_object_or_404(SaleReturn, pk=pk)
    
    if sale_return.status == "confirmed":
        messages.warning(request, "هذا المرتجع مؤكد بالفعل")
    else:
        try:
            # TODO: Implement confirmation logic with SaleService
            sale_return.status = "confirmed"
            sale_return.confirmed_at = timezone.now()
            sale_return.confirmed_by = request.user
            sale_return.save()
            messages.success(request, "تم تأكيد المرتجع بنجاح")
        except Exception as e:
            messages.error(request, f"خطأ في تأكيد المرتجع: {str(e)}")
    
    return redirect("sale:sale_return_detail", pk=pk)


@login_required
def sale_return_cancel(request, pk):
    """
    إلغاء مرتجع مبيعات
    """
    sale_return = get_object_or_404(SaleReturn, pk=pk)
    
    if sale_return.status == "cancelled":
        messages.warning(request, "هذا المرتجع ملغي بالفعل")
    elif sale_return.status == "confirmed":
        messages.error(request, "لا يمكن إلغاء مرتجع مؤكد")
    else:
        try:
            sale_return.status = "cancelled"
            sale_return.save()
            messages.success(request, "تم إلغاء المرتجع بنجاح")
        except Exception as e:
            messages.error(request, f"خطأ في إلغاء المرتجع: {str(e)}")
    
    return redirect("sale:sale_return_detail", pk=pk)
