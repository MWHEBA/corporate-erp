#!/bin/bash

# ✅ Daily Cleanup Script - تنظيف يومي للنظام
# يجب تشغيله يومياً عبر cron job

# إعداد المتغيرات
PROJECT_DIR="/path/to/your/project"  # ⚠️ يجب تغيير هذا المسار
PYTHON_PATH="$PROJECT_DIR/venv/bin/python"  # مسار Python في البيئة الافتراضية
MANAGE_PY="$PROJECT_DIR/manage.py"
LOG_FILE="$PROJECT_DIR/logs/daily_cleanup.log"

# إنشاء مجلد logs إذا لم يكن موجوداً
mkdir -p "$PROJECT_DIR/logs"

# بدء التسجيل
echo "========================================" >> "$LOG_FILE"
echo "Daily Cleanup Started: $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# 1. تنظيف JWT Tokens المنتهية الصلاحية
echo "🧹 تنظيف JWT Tokens..." >> "$LOG_FILE"
$PYTHON_PATH $MANAGE_PY cleanup_jwt_tokens --days=7 >> "$LOG_FILE" 2>&1

# 2. تنظيف Django Sessions المنتهية الصلاحية
echo "🧹 تنظيف Django Sessions..." >> "$LOG_FILE"
$PYTHON_PATH $MANAGE_PY clearsessions >> "$LOG_FILE" 2>&1

# 3. تنظيف ملفات الـ cache المؤقتة
echo "🧹 تنظيف Cache Files..." >> "$LOG_FILE"
find "$PROJECT_DIR/media/temp" -type f -mtime +7 -delete >> "$LOG_FILE" 2>&1

# 4. تنظيف ملفات الـ logs القديمة (أكثر من 30 يوم)
echo "🧹 تنظيف Log Files القديمة..." >> "$LOG_FILE"
find "$PROJECT_DIR/logs" -name "*.log" -mtime +30 -delete >> "$LOG_FILE" 2>&1

# 5. إنشاء نسخة احتياطية من قاعدة البيانات (اختياري)
if [ "$1" = "--backup" ]; then
    echo "💾 إنشاء نسخة احتياطية..." >> "$LOG_FILE"
    BACKUP_DIR="$PROJECT_DIR/backups"
    mkdir -p "$BACKUP_DIR"
    BACKUP_FILE="$BACKUP_DIR/db_backup_$(date +%Y%m%d_%H%M%S).sqlite3"
    cp "$PROJECT_DIR/db.sqlite3" "$BACKUP_FILE" >> "$LOG_FILE" 2>&1
    
    # حذف النسخ الاحتياطية القديمة (أكثر من 7 أيام)
    find "$BACKUP_DIR" -name "db_backup_*.sqlite3" -mtime +7 -delete >> "$LOG_FILE" 2>&1
fi

# انتهاء التسجيل
echo "========================================" >> "$LOG_FILE"
echo "Daily Cleanup Completed: $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# إرسال تقرير بالبريد الإلكتروني (اختياري)
if [ "$2" = "--email" ]; then
    tail -50 "$LOG_FILE" | mail -s "Daily Cleanup Report - $(date +%Y-%m-%d)" admin@yourschool.com
fi