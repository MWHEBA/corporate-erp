# -*- coding: utf-8 -*-
"""
نماذج الأدوات النظامية
يحتوي على: SerialNumber
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


class SerialNumber(models.Model):
    """
    نموذج لتتبع الأرقام التسلسلية للمستندات
    """

    DOCUMENT_TYPES = (
        ("sale", _("فاتورة مبيعات")),
        ("purchase", _("فاتورة مشتريات")),
        ("stock_movement", _("حركة مخزون")),
    )

    document_type = models.CharField(
        _("نوع المستند"), max_length=20, choices=DOCUMENT_TYPES
    )
    last_number = models.PositiveIntegerField(_("آخر رقم"), default=0)
    prefix = models.CharField(_("بادئة"), max_length=10, blank=True)
    year = models.PositiveIntegerField(_("السنة"), null=True, blank=True)

    class Meta:
        verbose_name = _("رقم تسلسلي")
        verbose_name_plural = _("الأرقام التسلسلية")
        unique_together = ["document_type", "year"]

    def get_next_number(self):
        """
        الحصول على الرقم التالي في التسلسل (thread-safe using F() expression)
        """
        from django.db.models import F
        
        # استخدام F() expression لعمل atomic increment
        SerialNumber.objects.filter(pk=self.pk).update(last_number=F('last_number') + 1)
        
        # إعادة تحميل القيمة الجديدة
        self.refresh_from_db()
        return self.last_number

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.year} - {self.last_number}"