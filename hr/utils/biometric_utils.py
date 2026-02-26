from django.db import transaction
from django.utils import timezone

from ..models import BiometricLog, BiometricUserMapping, Employee


def _get_mapping_for_log(log):
    mappings = BiometricUserMapping.objects.filter(
        biometric_user_id=str(log.user_id),
        is_active=True,
    )
    if not mappings.exists():
        return None
    if log.device_id:
        device_mapping = mappings.filter(device_id=log.device_id).first()
        if device_mapping is not None:
            return device_mapping
    return mappings.filter(device__isnull=True).first() or mappings.first()


def link_single_log(log, employee_id=None):
    employee = None
    if employee_id:
        try:
            employee = Employee.objects.get(pk=employee_id)
        except Employee.DoesNotExist:
            return False, "لا يوجد موظف بهذا المعرف"
    else:
        mapping = _get_mapping_for_log(log)
        if mapping is None:
            return False, "لم يتم العثور على ربط مناسب لهذا السجل"
        employee = mapping.employee
        if employee is None:
            return False, "الربط لا يحتوي على موظف فعّال"

    if log.employee_id == employee.id:
        return True, "السجل مربوط بالفعل بنفس الموظف"

    log.employee = employee
    log.save(update_fields=["employee"])
    name = employee.get_full_name_ar() if hasattr(employee, "get_full_name_ar") else str(employee)
    return True, f"تم ربط السجل بالموظف: {name}"


def process_single_log(log):
    if log.employee is None:
        success, _ = link_single_log(log)
        if not success:
            return False, "لا يمكن معالجة السجل بدون ربط موظف"

    if log.is_processed:
        return True, "تمت معالجة السجل مسبقاً"

    log.is_processed = True
    log.processed_at = timezone.now()
    log.save(update_fields=["is_processed", "processed_at"])
    return True, "تم تعليم السجل كمُعالج"


def get_mapping_suggestions():
    suggestions = []
    user_ids = (
        BiometricLog.objects.filter(employee__isnull=True)
        .values_list("user_id", flat=True)
        .distinct()
    )
    for user_id in user_ids[:200]:
        try:
            employee = Employee.objects.get(employee_number=str(user_id))
        except Employee.DoesNotExist:
            continue
        suggestions.append(
            {
                "user_id": str(user_id),
                "employee_id": employee.id,
                "employee_number": employee.employee_number,
                "employee_name": employee.get_full_name_ar()
                if hasattr(employee, "get_full_name_ar")
                else str(employee),
            }
        )
    return suggestions


@transaction.atomic
def bulk_link_logs(device_id=None, unlinked_only=True, dry_run=False, limit=None):
    qs = BiometricLog.objects.all()
    if device_id:
        qs = qs.filter(device_id=device_id)
    if unlinked_only:
        qs = qs.filter(employee__isnull=True)

    qs = qs.order_by("timestamp")
    if limit:
        qs = qs[: int(limit)]

    logs = list(qs)
    mappings = BiometricUserMapping.objects.filter(is_active=True)

    device_map = {}
    global_map = {}
    for m in mappings:
        key = (m.device_id, str(m.biometric_user_id))
        device_map[key] = m
        if m.device_id is None:
            global_map[str(m.biometric_user_id)] = m

    stats = {
        "total_logs": len(logs),
        "linked": 0,
        "skipped_no_mapping": 0,
    }

    for log in logs:
        key = (log.device_id, str(log.user_id))
        mapping = device_map.get(key)
        if mapping is None:
            mapping = global_map.get(str(log.user_id))
        if mapping is None or mapping.employee is None:
            stats["skipped_no_mapping"] += 1
            continue

        if not dry_run:
            if log.employee_id == mapping.employee_id:
                continue
            log.employee = mapping.employee
            log.save(update_fields=["employee"])
        stats["linked"] += 1

    return stats


@transaction.atomic
def bulk_process_logs(date=None, employee_id=None, unprocessed_only=True, dry_run=False):
    """
    معالجة سجلات البصمة وتحويلها لسجلات حضور
    
    هذه الدالة تقوم بـ:
    1. تجميع السجلات حسب الموظف والتاريخ
    2. إنشاء سجلات حضور من سجلات البصمة
    3. ربط السجلات بسجلات الحضور
    """
    from ..models import Attendance, BiometricUserMapping
    from datetime import datetime
    
    qs = BiometricLog.objects.all()
    if date is not None:
        qs = qs.filter(timestamp__date=date)
    if employee_id is not None:
        qs = qs.filter(employee_id=employee_id)
    if unprocessed_only:
        qs = qs.filter(is_processed=False)

    logs = list(qs.select_related('employee', 'device').order_by('timestamp'))
    
    stats = {
        "total_logs": len(logs),
        "processed": 0,
        "created": 0,
        "updated": 0,
        "errors": 0,
    }

    if len(logs) == 0:
        return stats

    # Group logs by employee and date
    grouped_logs = {}
    for log in logs:
        # Try to link employee if not linked
        if not log.employee:
            mapping = BiometricUserMapping.objects.filter(
                biometric_user_id=log.user_id,
                is_active=True
            ).filter(
                device=log.device
            ).first() or BiometricUserMapping.objects.filter(
                biometric_user_id=log.user_id,
                is_active=True,
                device__isnull=True
            ).first()
            
            if mapping and mapping.employee:
                log.employee = mapping.employee
                log.save(update_fields=['employee'])
        
        if not log.employee:
            continue
        
        key = (log.employee.id, log.timestamp.date())
        if key not in grouped_logs:
            grouped_logs[key] = []
        grouped_logs[key].append(log)
    
    # Process each group
    for (employee_id, date), day_logs in grouped_logs.items():
        if dry_run:
            stats["processed"] += len(day_logs)
            continue
        
        try:
            employee = day_logs[0].employee
            
            # Check if attendance already exists
            attendance = Attendance.objects.filter(
                employee=employee,
                date=date
            ).first()
            
            if attendance:
                # Update existing attendance
                stats["updated"] += 1
            else:
                # Create new attendance
                # Sort logs by timestamp
                day_logs_sorted = sorted(day_logs, key=lambda x: x.timestamp)
                
                # Find check-in and check-out
                check_in_log = None
                check_out_log = None
                
                for log in day_logs_sorted:
                    if log.log_type == 'check_in' and not check_in_log:
                        check_in_log = log
                    elif log.log_type == 'check_out' and check_in_log:
                        check_out_log = log
                        break
                
                if not check_in_log:
                    # Mark logs as processed but skip attendance creation
                    for log in day_logs:
                        log.is_processed = True
                        log.processed_at = timezone.now()
                        log.save(update_fields=['is_processed', 'processed_at'])
                    stats["processed"] += len(day_logs)
                    continue
                
                # Get employee shift
                shift = employee.shift
                if not shift:
                    # Mark logs as processed but skip attendance creation
                    for log in day_logs:
                        log.is_processed = True
                        log.processed_at = timezone.now()
                        log.save(update_fields=['is_processed', 'processed_at'])
                    stats["processed"] += len(day_logs)
                    continue
                
                # Calculate late minutes
                shift_start = datetime.combine(date, shift.start_time)
                shift_start = timezone.make_aware(shift_start)
                
                late_minutes = 0
                if check_in_log.timestamp > shift_start:
                    delta = check_in_log.timestamp - shift_start
                    late_minutes = int(delta.total_seconds() / 60)
                
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
                if check_out_log and hasattr(attendance, 'calculate_work_hours'):
                    attendance.calculate_work_hours()
                
                stats["created"] += 1
            
            # Link logs to attendance and mark as processed
            for log in day_logs:
                log.attendance = attendance
                log.is_processed = True
                log.processed_at = timezone.now()
                log.save(update_fields=['attendance', 'is_processed', 'processed_at'])
            
            stats["processed"] += len(day_logs)
            
        except Exception as e:
            stats["errors"] += 1
            # Mark logs as processed to avoid reprocessing
            for log in day_logs:
                if not log.is_processed:
                    log.is_processed = True
                    log.processed_at = timezone.now()
                    log.save(update_fields=['is_processed', 'processed_at'])

    return stats
