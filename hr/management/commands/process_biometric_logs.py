"""
Django management command to process biometric logs into attendance records
معالجة سجلات البصمة وتحويلها لسجلات حضور
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from datetime import datetime, timedelta

from hr.models import BiometricLog, Attendance, BiometricUserMapping
from hr.services.attendance_service import AttendanceService


class Command(BaseCommand):
    help = 'Process biometric logs and create attendance records'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Process logs for specific date (YYYY-MM-DD)'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Process all unprocessed logs'
        )
    
    def handle(self, *args, **options):
        date_str = options.get('date')
        process_all = options.get('all', False)
        
        self.stdout.write(self.style.SUCCESS(
            '\n🔄 بدء معالجة سجلات البصمة\n'
        ))
        
        # Get unprocessed logs
        logs_query = BiometricLog.objects.filter(is_processed=False)
        
        if date_str and not process_all:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            logs_query = logs_query.filter(timestamp__date=target_date)
            self.stdout.write(f'📅 معالجة سجلات تاريخ: {target_date}')
        elif not process_all:
            # Default: process last 7 days
            week_ago = timezone.now() - timedelta(days=7)
            logs_query = logs_query.filter(timestamp__gte=week_ago)
            self.stdout.write('📅 معالجة سجلات آخر 7 أيام')
        else:
            self.stdout.write('📅 معالجة جميع السجلات غير المعالجة')
        
        logs = logs_query.select_related('employee', 'device').order_by('timestamp')
        total_logs = logs.count()
        
        if total_logs == 0:
            self.stdout.write(self.style.WARNING('⚠️  لا توجد سجلات للمعالجة'))
            return
        
        self.stdout.write(f'📊 عدد السجلات: {total_logs}\n')
        
        # Group logs by employee and date
        grouped_logs = self.group_logs_by_employee_date(logs)
        
        # Process each group
        processed = 0
        failed = 0
        skipped = 0
        
        for (employee, date), day_logs in grouped_logs.items():
            try:
                result = self.process_employee_day(employee, date, day_logs)
                if result == 'processed':
                    processed += 1
                elif result == 'skipped':
                    skipped += 1
            except Exception as e:
                failed += 1
                self.stdout.write(self.style.ERROR(
                    f'❌ خطأ في معالجة {employee.name} - {date}: {e}'
                ))
        
        # Summary
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('✅ اكتملت المعالجة'))
        self.stdout.write('=' * 60)
        self.stdout.write(f'✅ تمت المعالجة: {processed}')
        self.stdout.write(f'⏭️  تم التخطي: {skipped}')
        self.stdout.write(f'❌ فشلت: {failed}')
        self.stdout.write('=' * 60 + '\n')

    
    def group_logs_by_employee_date(self, logs):
        """Group logs by employee and date"""
        grouped = {}
        
        for log in logs:
            if not log.employee:
                # Try to find employee from mapping
                mapping = BiometricUserMapping.objects.filter(
                    biometric_user_id=log.user_id,
                    device=log.device
                ).first()
                
                if mapping:
                    log.employee = mapping.employee
                    log.save(update_fields=['employee'])
                else:
                    continue
            
            key = (log.employee, log.timestamp.date())
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(log)
        
        return grouped
    
    def process_employee_day(self, employee, date, logs):
        """Process logs for one employee on one day"""
        # Check if attendance already exists
        if Attendance.objects.filter(employee=employee, date=date).exists():
            self.stdout.write(
                f'⏭️  {employee.name[:30]:30} - {date} (موجود مسبقاً)'
            )
            # Mark logs as processed anyway
            for log in logs:
                log.is_processed = True
                log.processed_at = timezone.now()
                log.save(update_fields=['is_processed', 'processed_at'])
            return 'skipped'
        
        # Sort logs by timestamp
        logs = sorted(logs, key=lambda x: x.timestamp)
        
        # Find check-in and check-out
        check_in_log = None
        check_out_log = None
        
        for log in logs:
            if log.log_type == 'check_in' and not check_in_log:
                check_in_log = log
            elif log.log_type == 'check_out' and check_in_log:
                check_out_log = log
                break
        
        if not check_in_log:
            self.stdout.write(self.style.WARNING(
                f'⚠️  {employee.name[:30]:30} - {date} (لا يوجد دخول)'
            ))
            return 'skipped'
        
        # Get employee shift
        shift = employee.shift
        if not shift:
            self.stdout.write(self.style.WARNING(
                f'⚠️  {employee.name[:30]:30} - {date} (لا توجد وردية)'
            ))
            return 'skipped'
        
        # Create attendance record
        with transaction.atomic():
            # Calculate late minutes
            late_minutes = self.calculate_late_minutes(
                check_in_log.timestamp, shift
            )
            
            # Determine status
            if late_minutes > shift.grace_period_in:
                status = 'late'
            else:
                status = 'present'
            
            # Create attendance
            attendance = Attendance.objects.create(
                employee=employee,
                date=date,
                shift=shift,
                check_in=check_in_log.timestamp,
                check_out=check_out_log.timestamp if check_out_log else None,
                late_minutes=late_minutes,
                status=status
            )
            
            # Calculate work hours if check-out exists
            if check_out_log:
                attendance.calculate_work_hours()
            
            # Link logs to attendance
            check_in_log.attendance = attendance
            check_in_log.is_processed = True
            check_in_log.processed_at = timezone.now()
            check_in_log.save()
            
            if check_out_log:
                check_out_log.attendance = attendance
                check_out_log.is_processed = True
                check_out_log.processed_at = timezone.now()
                check_out_log.save()
            
            # Mark remaining logs as processed
            for log in logs:
                if not log.is_processed:
                    log.is_processed = True
                    log.processed_at = timezone.now()
                    log.save(update_fields=['is_processed', 'processed_at'])
        
        # Print status
        check_in_time = check_in_log.timestamp.strftime('%H:%M')
        check_out_time = check_out_log.timestamp.strftime('%H:%M') if check_out_log else '--:--'
        late_info = f'(متأخر {late_minutes} دقيقة)' if late_minutes > shift.grace_period_in else ''
        
        self.stdout.write(
            f'✅ {employee.name[:30]:30} - {date} | '
            f'{check_in_time} → {check_out_time} {late_info}'
        )
        
        return 'processed'
    
    def calculate_late_minutes(self, check_in, shift):
        """Calculate late minutes"""
        shift_start = datetime.combine(check_in.date(), shift.start_time)
        shift_start = timezone.make_aware(shift_start)
        
        if check_in > shift_start:
            delta = check_in - shift_start
            return int(delta.total_seconds() / 60)
        return 0
