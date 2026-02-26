"""
أمر لتدقيق المعاملات المالية الموجودة
Audit Existing Financial Transactions Command

يقوم هذا الأمر بـ:
1. فحص جميع المعاملات المالية الموجودة في النظام
2. التحقق من توافقها مع الشروط المحاسبية (الحساب المحاسبي، الفترة المحاسبية)
3. إنشاء تقرير بالمعاملات المشكوك فيها
4. خيار لتصحيح المعاملات تلقائياً (مع تأكيد)
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.db.models import Q
from datetime import datetime, date
import csv
import os

from financial.models.journal_entry import JournalEntry, AccountingPeriod
# FeePayment removed - students module no longer used
from financial.models.transactions import FinancialTransaction
from financial.models.loan_transactions import Loan, LoanPayment
from financial.models.partner_transactions import PartnerTransaction
from financial.services.validation_service import FinancialValidationService
from financial.services.entity_mapper import EntityAccountMapper


class Command(BaseCommand):
    help = 'تدقيق المعاملات المالية الموجودة والتحقق من توافقها مع الشروط المحاسبية'

    def add_arguments(self, parser):
        parser.add_argument(
            '--module',
            type=str,
            choices=['all', 'financial', 'students', 'activities', 'transportation', 'hr', 'supplier'],
            default='all',
            help='الوحدة المراد تدقيقها (افتراضي: all)',
        )
        parser.add_argument(
            '--check-type',
            type=str,
            choices=['all', 'account', 'period'],
            default='all',
            help='نوع التحقق (all: كلاهما، account: الحساب المحاسبي، period: الفترة المحاسبية)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='عدد المعاملات المراد فحصها (افتراضي: جميع المعاملات)',
        )
        parser.add_argument(
            '--export',
            type=str,
            default=None,
            help='تصدير التقرير إلى ملف CSV (مثال: --export=report.csv)',
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='محاولة تصحيح المعاملات تلقائياً (يتطلب تأكيد)',
        )
        parser.add_argument(
            '--yes',
            action='store_true',
            help='تأكيد التصحيح التلقائي بدون سؤال',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='عرض تفاصيل إضافية',
        )

    def handle(self, *args, **options):
        self.module = options['module']
        self.check_type = options['check_type']
        self.limit = options['limit']
        self.export_file = options['export']
        self.fix_mode = options['fix']
        self.auto_confirm = options['yes']
        self.verbose = options['verbose']
        
        self.stdout.write(
            self.style.SUCCESS('🔍 بدء تدقيق المعاملات المالية الموجودة...\n')
        )
        
        # إحصائيات
        self.stats = {
            'total_checked': 0,
            'valid': 0,
            'invalid_account': 0,
            'invalid_period': 0,
            'invalid_both': 0,
            'fixed': 0,
            'fix_failed': 0,
        }
        
        # قائمة المعاملات المشكوك فيها
        self.suspicious_transactions = []
        
        # تدقيق المعاملات حسب الوحدة
        if self.module == 'all' or self.module == 'financial':
            self.audit_journal_entries()
            self.audit_financial_transactions()
            self.audit_loan_transactions()
            self.audit_partner_transactions()
        
        if self.module == 'all' or self.module == 'students':
            self.audit_fee_payments()
        
        # عرض التقرير
        self.display_report()
        
        # تصدير التقرير
        if self.export_file:
            self.export_report()
        
        # تصحيح المعاملات
        if self.fix_mode:
            self.fix_transactions()

    def audit_journal_entries(self):
        """تدقيق القيود اليومية"""
        self.stdout.write('📝 تدقيق القيود اليومية...')
        
        queryset = JournalEntry.objects.all()
        if self.limit:
            queryset = queryset[:self.limit]
        
        for entry in queryset:
            self.stats['total_checked'] += 1
            
            # تخطي القيود الافتتاحية
            if entry.entry_type == 'opening':
                self.stats['valid'] += 1
                continue
            
            issues = []
            
            # التحقق من الفترة المحاسبية
            if self.check_type in ['all', 'period']:
                period_valid, period_error, period = FinancialValidationService.validate_accounting_period(
                    transaction_date=entry.date,
                    raise_exception=False
                )
                
                if not period_valid:
                    issues.append({
                        'type': 'period',
                        'message': period_error
                    })
            
            # تسجيل المعاملة المشكوك فيها
            if issues:
                self.record_suspicious_transaction(
                    transaction_type='JournalEntry',
                    transaction_id=entry.id,
                    transaction_number=entry.number,
                    transaction_date=entry.date,
                    entity_type='journal_entry',
                    entity_name=entry.description,
                    issues=issues
                )
                
                if len(issues) == 1:
                    if issues[0]['type'] == 'account':
                        self.stats['invalid_account'] += 1
                    else:
                        self.stats['invalid_period'] += 1
                else:
                    self.stats['invalid_both'] += 1
            else:
                self.stats['valid'] += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'  ✅ تم فحص {queryset.count()} قيد يومي\n')
        )

    def audit_financial_transactions(self):
        """تدقيق المعاملات المالية العامة"""
        self.stdout.write('💰 تدقيق المعاملات المالية العامة...')
        
        queryset = FinancialTransaction.objects.all()
        if self.limit:
            queryset = queryset[:self.limit]
        
        for trans in queryset:
            self.stats['total_checked'] += 1
            
            issues = []
            entity = None
            entity_type = None
            
            # محاولة الحصول على الكيان المرتبط
            if trans.student:
                entity = trans.student
                entity_type = 'student'
            elif trans.supplier:
                entity = trans.supplier
                entity_type = 'supplier'
            elif trans.employee:
                entity = trans.employee
                entity_type = 'employee'
            
            # التحقق من الحساب المحاسبي
            if entity and self.check_type in ['all', 'account']:
                account_valid, account_error, account = FinancialValidationService.validate_chart_of_accounts(
                    entity=entity,
                    entity_type=entity_type,
                    raise_exception=False
                )
                
                if not account_valid:
                    issues.append({
                        'type': 'account',
                        'message': account_error
                    })
            
            # التحقق من الفترة المحاسبية
            if self.check_type in ['all', 'period']:
                period_valid, period_error, period = FinancialValidationService.validate_accounting_period(
                    transaction_date=trans.date,
                    entity=entity,
                    entity_type=entity_type,
                    raise_exception=False
                )
                
                if not period_valid:
                    issues.append({
                        'type': 'period',
                        'message': period_error
                    })
            
            # تسجيل المعاملة المشكوك فيها
            if issues:
                self.record_suspicious_transaction(
                    transaction_type='FinancialTransaction',
                    transaction_id=trans.id,
                    transaction_number=trans.reference_number or f'TRANS-{trans.id}',
                    transaction_date=trans.date,
                    transaction_amount=trans.amount,
                    entity_type=entity_type or 'unknown',
                    entity_name=str(entity) if entity else 'غير محدد',
                    issues=issues
                )
                
                if len(issues) == 1:
                    if issues[0]['type'] == 'account':
                        self.stats['invalid_account'] += 1
                    else:
                        self.stats['invalid_period'] += 1
                else:
                    self.stats['invalid_both'] += 1
            else:
                self.stats['valid'] += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'  ✅ تم فحص {queryset.count()} معاملة مالية\n')
        )

    def audit_fee_payments(self):
        """تدقيق مدفوعات الرسوم"""
        self.stdout.write('🎓 تدقيق مدفوعات الرسوم...')
        
        queryset = FeePayment.objects.select_related('student_fee__student', 'student_fee__student__parent').all()
        if self.limit:
            queryset = queryset[:self.limit]
        
        for payment in queryset:
            self.stats['total_checked'] += 1
            
            issues = []
            
            # الحصول على الطالب من student_fee
            student = payment.student_fee.student
            
            # التحقق من الحساب المحاسبي (حساب ولي الأمر)
            if self.check_type in ['all', 'account']:
                account_valid, account_error, account = FinancialValidationService.validate_chart_of_accounts(
                    entity=student,
                    entity_type='student',
                    raise_exception=False
                )
                
                if not account_valid:
                    issues.append({
                        'type': 'account',
                        'message': account_error
                    })
            
            # التحقق من الفترة المحاسبية
            if self.check_type in ['all', 'period']:
                period_valid, period_error, period = FinancialValidationService.validate_accounting_period(
                    transaction_date=payment.payment_date,
                    entity=student,
                    entity_type='student',
                    raise_exception=False
                )
                
                if not period_valid:
                    issues.append({
                        'type': 'period',
                        'message': period_error
                    })
            
            # تسجيل المعاملة المشكوك فيها
            if issues:
                self.record_suspicious_transaction(
                    transaction_type='FeePayment',
                    transaction_id=payment.id,
                    transaction_number=f'PAY-{payment.id}',
                    transaction_date=payment.payment_date,
                    transaction_amount=payment.amount,
                    entity_type='student',
                    entity_name=str(student),
                    issues=issues
                )
                
                if len(issues) == 1:
                    if issues[0]['type'] == 'account':
                        self.stats['invalid_account'] += 1
                    else:
                        self.stats['invalid_period'] += 1
                else:
                    self.stats['invalid_both'] += 1
            else:
                self.stats['valid'] += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'  ✅ تم فحص {queryset.count()} دفعة رسوم\n')
        )

    def audit_loan_transactions(self):
        """تدقيق معاملات القروض"""
        self.stdout.write('🏦 تدقيق معاملات القروض...')
        
        # تدقيق القروض
        loans = Loan.objects.all()
        if self.limit:
            loans = loans[:self.limit // 2]
        
        for loan in loans:
            self.stats['total_checked'] += 1
            
            issues = []
            
            # التحقق من الفترة المحاسبية
            if self.check_type in ['all', 'period']:
                period_valid, period_error, period = FinancialValidationService.validate_accounting_period(
                    transaction_date=loan.loan_date,
                    raise_exception=False
                )
                
                if not period_valid:
                    issues.append({
                        'type': 'period',
                        'message': period_error
                    })
            
            if issues:
                self.record_suspicious_transaction(
                    transaction_type='Loan',
                    transaction_id=loan.id,
                    transaction_number=loan.loan_number,
                    transaction_date=loan.loan_date,
                    transaction_amount=loan.principal_amount,
                    entity_type='loan',
                    entity_name=loan.lender_name,
                    issues=issues
                )
                self.stats['invalid_period'] += 1
            else:
                self.stats['valid'] += 1
        
        # تدقيق دفعات القروض
        payments = LoanPayment.objects.select_related('loan').all()
        if self.limit:
            payments = payments[:self.limit // 2]
        
        for payment in payments:
            self.stats['total_checked'] += 1
            
            issues = []
            
            # التحقق من الفترة المحاسبية
            if self.check_type in ['all', 'period']:
                period_valid, period_error, period = FinancialValidationService.validate_accounting_period(
                    transaction_date=payment.payment_date,
                    raise_exception=False
                )
                
                if not period_valid:
                    issues.append({
                        'type': 'period',
                        'message': period_error
                    })
            
            if issues:
                self.record_suspicious_transaction(
                    transaction_type='LoanPayment',
                    transaction_id=payment.id,
                    transaction_number=f'LOAN-PAY-{payment.id}',
                    transaction_date=payment.payment_date,
                    transaction_amount=payment.amount,
                    entity_type='loan',
                    entity_name=payment.loan.lender_name,
                    issues=issues
                )
                self.stats['invalid_period'] += 1
            else:
                self.stats['valid'] += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'  ✅ تم فحص {loans.count()} قرض و {payments.count()} دفعة قرض\n')
        )

    def audit_partner_transactions(self):
        """تدقيق معاملات الشركاء"""
        self.stdout.write('🤝 تدقيق معاملات الشركاء...')
        
        queryset = PartnerTransaction.objects.select_related('partner_account').all()
        if self.limit:
            queryset = queryset[:self.limit]
        
        for trans in queryset:
            self.stats['total_checked'] += 1
            
            issues = []
            
            # التحقق من الفترة المحاسبية
            if self.check_type in ['all', 'period']:
                period_valid, period_error, period = FinancialValidationService.validate_accounting_period(
                    transaction_date=trans.transaction_date,
                    raise_exception=False
                )
                
                if not period_valid:
                    issues.append({
                        'type': 'period',
                        'message': period_error
                    })
            
            if issues:
                # Get partner name from partner_account if available
                partner_name = 'غير محدد'
                if trans.partner_account:
                    partner_name = str(trans.partner_account)
                
                self.record_suspicious_transaction(
                    transaction_type='PartnerTransaction',
                    transaction_id=trans.id,
                    transaction_number=trans.transaction_number,
                    transaction_date=trans.transaction_date,
                    transaction_amount=trans.amount,
                    entity_type='partner',
                    entity_name=partner_name,
                    issues=issues
                )
                self.stats['invalid_period'] += 1
            else:
                self.stats['valid'] += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'  ✅ تم فحص {queryset.count()} معاملة شريك\n')
        )

    def record_suspicious_transaction(self, transaction_type, transaction_id, transaction_number,
                                     transaction_date, entity_type, entity_name, issues,
                                     transaction_amount=None):
        """تسجيل معاملة مشكوك فيها"""
        self.suspicious_transactions.append({
            'transaction_type': transaction_type,
            'transaction_id': transaction_id,
            'transaction_number': transaction_number,
            'transaction_date': transaction_date,
            'transaction_amount': transaction_amount,
            'entity_type': entity_type,
            'entity_name': entity_name,
            'issues': issues,
        })
        
        if self.verbose:
            self.stdout.write(
                self.style.WARNING(
                    f'  ⚠️  {transaction_type} #{transaction_number}: '
                    f'{entity_name} - {len(issues)} مشكلة'
                )
            )

    def display_report(self):
        """عرض تقرير التدقيق"""
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.SUCCESS('📊 تقرير التدقيق'))
        self.stdout.write('=' * 80 + '\n')
        
        # الإحصائيات
        self.stdout.write(f'إجمالي المعاملات المفحوصة: {self.stats["total_checked"]}')
        self.stdout.write(
            self.style.SUCCESS(f'✅ معاملات صحيحة: {self.stats["valid"]}')
        )
        
        total_invalid = (
            self.stats['invalid_account'] +
            self.stats['invalid_period'] +
            self.stats['invalid_both']
        )
        
        if total_invalid > 0:
            self.stdout.write(
                self.style.ERROR(f'\n❌ معاملات مشكوك فيها: {total_invalid}')
            )
            self.stdout.write(
                f'   - مشاكل في الحساب المحاسبي: {self.stats["invalid_account"]}'
            )
            self.stdout.write(
                f'   - مشاكل في الفترة المحاسبية: {self.stats["invalid_period"]}'
            )
            self.stdout.write(
                f'   - مشاكل في كليهما: {self.stats["invalid_both"]}'
            )
        
        # عرض تفاصيل المعاملات المشكوك فيها
        if self.suspicious_transactions and self.verbose:
            self.stdout.write('\n' + '-' * 80)
            self.stdout.write('تفاصيل المعاملات المشكوك فيها:')
            self.stdout.write('-' * 80 + '\n')
            
            for trans in self.suspicious_transactions[:20]:  # عرض أول 20 فقط
                self.stdout.write(
                    f'\n{trans["transaction_type"]} #{trans["transaction_number"]}'
                )
                self.stdout.write(f'  الكيان: {trans["entity_name"]} ({trans["entity_type"]})')
                self.stdout.write(f'  التاريخ: {trans["transaction_date"]}')
                if trans['transaction_amount']:
                    self.stdout.write(f'  المبلغ: {trans["transaction_amount"]}')
                self.stdout.write('  المشاكل:')
                for issue in trans['issues']:
                    self.stdout.write(f'    - {issue["message"]}')
            
            if len(self.suspicious_transactions) > 20:
                self.stdout.write(
                    f'\n... و {len(self.suspicious_transactions) - 20} معاملة أخرى'
                )
        
        self.stdout.write('\n' + '=' * 80 + '\n')

    def export_report(self):
        """تصدير التقرير إلى ملف CSV"""
        self.stdout.write(f'📄 تصدير التقرير إلى {self.export_file}...')
        
        try:
            with open(self.export_file, 'w', newline='', encoding='utf-8-sig') as csvfile:
                fieldnames = [
                    'نوع المعاملة',
                    'رقم المعاملة',
                    'التاريخ',
                    'المبلغ',
                    'نوع الكيان',
                    'اسم الكيان',
                    'نوع المشكلة',
                    'رسالة الخطأ'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for trans in self.suspicious_transactions:
                    for issue in trans['issues']:
                        writer.writerow({
                            'نوع المعاملة': trans['transaction_type'],
                            'رقم المعاملة': trans['transaction_number'],
                            'التاريخ': trans['transaction_date'],
                            'المبلغ': trans['transaction_amount'] or '',
                            'نوع الكيان': trans['entity_type'],
                            'اسم الكيان': trans['entity_name'],
                            'نوع المشكلة': issue['type'],
                            'رسالة الخطأ': issue['message'],
                        })
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ تم تصدير التقرير بنجاح إلى {self.export_file}\n')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ فشل تصدير التقرير: {str(e)}\n')
            )

    def fix_transactions(self):
        """محاولة تصحيح المعاملات تلقائياً"""
        if not self.suspicious_transactions:
            self.stdout.write('لا توجد معاملات تحتاج إلى تصحيح.')
            return
        
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.WARNING('⚠️  وضع التصحيح التلقائي'))
        self.stdout.write('=' * 80 + '\n')
        
        # طلب التأكيد
        if not self.auto_confirm:
            self.stdout.write(
                self.style.WARNING(
                    f'سيتم محاولة تصحيح {len(self.suspicious_transactions)} معاملة.'
                )
            )
            confirm = input('هل تريد المتابعة؟ (yes/no): ')
            if confirm.lower() not in ['yes', 'y', 'نعم']:
                self.stdout.write('تم إلغاء التصحيح.')
                return
        
        self.stdout.write('🔧 بدء التصحيح التلقائي...\n')
        
        # ملاحظة: التصحيح التلقائي محدود حالياً
        # يمكن توسيعه في المستقبل لتصحيح مشاكل محددة
        
        self.stdout.write(
            self.style.WARNING(
                '⚠️  التصحيح التلقائي غير متاح حالياً.\n'
                'يرجى مراجعة التقرير وتصحيح المعاملات يدوياً.\n'
                'يمكن تصحيح المشاكل التالية:\n'
                '  - إضافة حسابات محاسبية للكيانات المفقودة\n'
                '  - إنشاء فترات محاسبية للتواريخ المفقودة\n'
                '  - تحديث تواريخ المعاملات لتتوافق مع الفترات المفتوحة\n'
            )
        )
