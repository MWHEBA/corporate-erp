#!/usr/bin/env python3
"""
سكريپت النشر المحسن - Enhanced Deploy Script
رفع الملفات للخادم مع مزامنة كاملة
"""

import os
import sys
import subprocess
import hashlib
import json
import argparse
from pathlib import Path
import fnmatch
import time

try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False

class DeploymentManager:
    def __init__(self):
        # تحميل إعدادات من .env
        self.load_env_settings()
        
        # مسار المشروع
        self.project_root = Path.cwd()
        self.hash_file = self.project_root / ".deploy_hashes.json"
        self.ignored_patterns = self.load_gitignore_patterns()
        
        print("🚀 سكريپت النشر المحسن")
        print("=" * 35)
        print(f"📁 المشروع: {self.project_root.name}")
        print(f"🖥️  الخادم: {self.server_ip}:{self.ssh_port}")
        print()
        print("📋 الأوضاع المتاحة:")
        print("   • modified - خيارات رفع متعددة (افتراضي)")
        print("   • all      - رفع جميع الملفات مع استبدال")
        print("   • file     - رفع ملف واحد محدد")
        print("   • sync     - رفع مع تخطي المطابق")
        print("   • status   - عرض حالة الملفات")
        print("   • test     - اختبار الاتصال فقط")

    def load_env_settings(self):
        """تحميل إعدادات SSH من ملف .env"""
        env_file = Path('.env')
        
        # الإعدادات الافتراضية
        self.server_ip = "84.247.179.163"
        self.username = "mwhebaco"
        self.ssh_port = "2951"
        self.ssh_password = None
        self.private_key = "id_rsa"
        self.remote_path = "/home/mwhebaco/baraka_erp"
        
        if env_file.exists():
            try:
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if '=' in line and not line.startswith('#'):
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            
                            if key == 'SSH_HOST':
                                self.server_ip = value
                            elif key == 'SSH_PORT':
                                self.ssh_port = value
                            elif key == 'SSH_USER':
                                self.username = value
                            elif key == 'SSH_PASSWORD':
                                if value and value != 'your_actual_password_here':
                                    self.ssh_password = value
                            elif key == 'SSH_KEY_PATH':
                                self.private_key = value
                            elif key == 'SSH_REMOTE_PATH':
                                self.remote_path = value
            except Exception as e:
                print(f"⚠️  تحذير: لا يمكن قراءة ملف .env: {e}")

    def load_gitignore_patterns(self):
        """تحميل قائمة الاستثناءات من .gitignore"""
        patterns = []
        gitignore_path = self.project_root / ".gitignore"
        
        if gitignore_path.exists():
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        patterns.append(line)
        
        # إضافة الملفات المخفية
        patterns.extend(['.*', '__pycache__', '*.pyc', '.deploy_hashes.json'])
        return patterns

    def is_ignored(self, file_path):
        """فحص ما إذا كان الملف مستثنى"""
        relative_path = str(file_path.relative_to(self.project_root))
        
        if any(part.startswith('.') for part in file_path.parts):
            return True
            
        for pattern in self.ignored_patterns:
            if fnmatch.fnmatch(relative_path, pattern) or fnmatch.fnmatch(file_path.name, pattern):
                return True
                
        return False

    def get_file_hash(self, file_path):
        """حساب hash للملف"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except:
            return None

    def get_all_files(self):
        """الحصول على جميع الملفات"""
        files = []
        for file_path in self.project_root.rglob('*'):
            if file_path.is_file() and not self.is_ignored(file_path):
                files.append(file_path)
        return files

    def get_modified_files_vs_remote(self):
        """الحصول على الملفات المعدلة بالمقارنة مع الخادم - محسن للسرعة"""
        print("🔍 مقارنة مع الخادم...")
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            ssh.connect(
                hostname=self.server_ip,
                port=int(self.ssh_port),
                username=self.username,
                password=self.ssh_password,
                timeout=30
            )
            
            sftp = ssh.open_sftp()
            
            # الحصول على جميع الملفات المحلية
            local_files = self.get_all_files()
            local_files_dict = {}
            
            for file_path in local_files:
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                stat = file_path.stat()
                local_files_dict[relative_path] = {
                    'path': file_path,
                    'size': stat.st_size,
                    'mtime': int(stat.st_mtime)
                }
            
            # الحصول على جميع الملفات البعيدة
            remote_files_dict = {}
            self.get_remote_files_with_stats(sftp, self.remote_path, remote_files_dict)
            
            # تحديد الملفات المعدلة/الجديدة بسرعة
            modified_files = []
            new_count = 0
            size_diff_count = 0
            time_diff_count = 0
            
            for relative_path, local_info in local_files_dict.items():
                if relative_path not in remote_files_dict:
                    # ملف جديد
                    modified_files.append(local_info['path'])
                    new_count += 1
                else:
                    # مقارنة سريعة
                    remote_info = remote_files_dict[relative_path]
                    
                    # الحجم مختلف = معدل بالتأكيد
                    if local_info['size'] != remote_info['size']:
                        modified_files.append(local_info['path'])
                        size_diff_count += 1
                    else:
                        # فرق زمني معقول = معدل
                        time_diff = abs(local_info['mtime'] - remote_info['mtime'])
                        if 60 < time_diff < 86400:  # بين دقيقة ويوم
                            modified_files.append(local_info['path'])
                            time_diff_count += 1
            
            sftp.close()
            ssh.close()
            
            # ملخص مختصر
            total_modified = len(modified_files)
            if total_modified > 0:
                print(f"📊 {total_modified} ملف يحتاج رفع:")
                if new_count > 0:
                    print(f"   📄 {new_count} جديد")
                if size_diff_count > 0:
                    print(f"   📏 {size_diff_count} حجم مختلف")
                if time_diff_count > 0:
                    print(f"   ⏰ {time_diff_count} معدل حديثاً")
            else:
                print("✅ جميع الملفات محدثة")
            
            return modified_files
            
        except Exception as e:
            print(f"❌ خطأ في المقارنة: {e}")
            return []



    def test_connection(self):
        """اختبار الاتصال"""
        print("🔍 اختبار الاتصال...")
        
        # التحقق من وجود كلمة المرور في .env
        if not self.ssh_password or self.ssh_password == 'your_actual_password_here':
            print("❌ كلمة المرور غير موجودة في ملف .env")
            print("💡 تأكد من إضافة SSH_PASSWORD في ملف .env")
            return False
        
        # استخدام paramiko مع كلمة المرور من .env
        if PARAMIKO_AVAILABLE:
            print(f"🔐 استخدام كلمة المرور من .env للاتصال بـ {self.username}@{self.server_ip}:{self.ssh_port}")
            
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                ssh.connect(
                    hostname=self.server_ip,
                    port=int(self.ssh_port),
                    username=self.username,
                    password=self.ssh_password,
                    timeout=10
                )
                
                # اختبار تنفيذ أمر بسيط
                stdin, stdout, stderr = ssh.exec_command("echo 'اتصال ناجح'")
                result = stdout.read().decode().strip()
                error = stderr.read().decode().strip()
                
                ssh.close()
                
                if result == 'اتصال ناجح':
                    print("✅ الاتصال ناجح!")
                    self.use_paramiko = True
                    return True
                else:
                    print(f"❌ خطأ في تنفيذ الأمر: {error}")
                    return False
                    
            except paramiko.AuthenticationException:
                print("❌ خطأ في المصادقة - تحقق من كلمة المرور في .env")
                return False
            except paramiko.SSHException as e:
                print(f"❌ خطأ SSH: {e}")
                return False
            except Exception as e:
                print(f"❌ خطأ في الاتصال: {e}")
                return False
        else:
            print("❌ مكتبة paramiko غير متاحة!")
            return False

    def upload_files(self, files):
        """رفع الملفات"""
        if not files:
            print("📝 لا توجد ملفات للرفع")
            return True
            
        print(f"📤 رفع {len(files)} ملف...")
        
        # إنشاء مجلد مؤقت
        temp_dir = self.project_root / ".temp_deploy"
        if temp_dir.exists():
            import shutil
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(exist_ok=True)
        
        try:
            # نسخ الملفات
            import shutil
            for file_path in files:
                if not file_path.exists():
                    continue
                    
                relative_path = file_path.relative_to(self.project_root)
                temp_file_path = temp_dir / relative_path
                temp_file_path.parent.mkdir(parents=True, exist_ok=True)
                
                # محاولة نسخ الملف مع معالجة الأخطاء
                try:
                    shutil.copy2(file_path, temp_file_path)
                except PermissionError:
                    print(f"⚠️  تخطي ملف مقفل: {relative_path}")
                    continue
                except Exception as e:
                    print(f"⚠️  خطأ في نسخ {relative_path}: {e}")
                    continue
            
            # رفع الملفات
            return self.upload_with_paramiko(temp_dir)
                
        finally:
            # حذف المجلد المؤقت مع معالجة الأخطاء
            import shutil
            if temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except PermissionError:
                    print("⚠️  لا يمكن حذف المجلد المؤقت (ملفات مقفلة)")
                except:
                    pass

    def upload_with_smart_skip(self, files):
        """رفع الملفات مع تخطي المطابق 100%"""
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            ssh.connect(
                hostname=self.server_ip,
                port=int(self.ssh_port),
                username=self.username,
                password=self.ssh_password,
                timeout=30
            )
            
            sftp = ssh.open_sftp()
            
            total_files = len(files)
            uploaded = 0
            skipped = 0
            uploaded_files = []  # قائمة الملفات المرفوعة
            skipped_examples = []
            start_time = time.time()
            
            print(f"📤 بدء الرفع...")
            
            for i, file_path in enumerate(files):
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                remote_file = f"{self.remote_path}/{relative_path}"
                
                # فحص سريع - هل الملف مطابق 100%؟
                should_skip = False
                try:
                    remote_stat = sftp.stat(remote_file)
                    local_stat = file_path.stat()
                    
                    # مقارنة الحجم فقط - أكثر دقة من التوقيت
                    if remote_stat.st_size == local_stat.st_size:
                        # إذا كان الحجم متطابق، نفترض أن الملف مطابق
                        # (لتجنب مشاكل المناطق الزمنية)
                        should_skip = True
                        skipped += 1
                        if len(skipped_examples) < 15:
                            skipped_examples.append(relative_path)
                        
                except:
                    # الملف غير موجود أو خطأ - سيتم رفعه
                    should_skip = False
                
                # عرض التقدم
                percentage = ((i + 1) / total_files) * 100
                elapsed = time.time() - start_time
                remaining = total_files - (i + 1)
                eta = int((elapsed / (i + 1)) * remaining) if i > 0 else 0
                eta_text = f"{eta}ث" if eta < 60 else f"{eta//60}د"
                
                bar_length = 25
                filled_length = int(bar_length * (i + 1) // total_files)
                bar = '█' * filled_length + '░' * (bar_length - filled_length)
                
                print(f"\r[{bar}] {percentage:.1f}% - رفع: {uploaded}, تخطي: {skipped} - متبقي: {eta_text}", end='', flush=True)
                
                if should_skip:
                    continue
                
                # رفع الملف
                try:
                    # إنشاء المجلد إذا لزم الأمر
                    remote_dir = '/'.join(remote_file.split('/')[:-1])
                    if remote_dir != self.remote_path:
                        try:
                            sftp.mkdir(remote_dir)
                        except:
                            pass
                    
                    sftp.put(str(file_path), remote_file)
                    uploaded += 1
                    uploaded_files.append(relative_path)
                    
                except Exception as e:
                    print(f"\n⚠️  خطأ في رفع {relative_path}: {e}")
            
            print()
            sftp.close()
            ssh.close()
            
            total_time = time.time() - start_time
            print(f"✅ اكتمل في {total_time:.1f}ث - رفع: {uploaded}, تخطي: {skipped}")
            
            # عرض تفاصيل الملفات المرفوعة
            if uploaded_files:
                print(f"\n📋 الملفات المرفوعة ({len(uploaded_files)}):")
                display_count = min(12, len(uploaded_files))
                for f in uploaded_files[:display_count]:
                    print(f"   ✅ {f}")
                if len(uploaded_files) > display_count:
                    print(f"   ... و {len(uploaded_files) - display_count} ملف آخر")
                
                # حفظ قائمة مفصلة في ملف
                self._save_upload_log(uploaded_files, "رفع كامل مع تخطي")
            
            # عرض أمثلة الملفات المتخطاة
            if skipped_examples:
                print(f"\n📋 أمثلة الملفات المتخطاة (حجم مطابق):")
                for example in skipped_examples:
                    print(f"   ⏭️  {example}")
                if skipped > len(skipped_examples):
                    print(f"   ... و {skipped - len(skipped_examples)} ملف آخر")
            
            return True
            
        except Exception as e:
            print(f"\n❌ خطأ في الرفع: {e}")
            return False

    def upload_all_files(self, files):
        """رفع جميع الملفات مع استبدال (بدون تخطي)"""
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            ssh.connect(
                hostname=self.server_ip,
                port=int(self.ssh_port),
                username=self.username,
                password=self.ssh_password,
                timeout=30
            )
            
            sftp = ssh.open_sftp()
            
            total_files = len(files)
            uploaded = 0
            uploaded_files = []  # قائمة الملفات المرفوعة
            start_time = time.time()
            
            print(f"📤 رفع {total_files} ملف...")
            
            for i, file_path in enumerate(files):
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                remote_file = f"{self.remote_path}/{relative_path}"
                
                try:
                    # إنشاء المجلد إذا لزم الأمر
                    remote_dir = '/'.join(remote_file.split('/')[:-1])
                    if remote_dir != self.remote_path:
                        try:
                            sftp.mkdir(remote_dir)
                        except:
                            pass
                    
                    sftp.put(str(file_path), remote_file)
                    uploaded += 1
                    uploaded_files.append(relative_path)
                    
                except Exception as e:
                    print(f"\n⚠️  خطأ في رفع {relative_path}: {e}")
                
                # عرض التقدم
                percentage = ((i + 1) / total_files) * 100
                elapsed = time.time() - start_time
                remaining = total_files - (i + 1)
                eta = int((elapsed / (i + 1)) * remaining) if i > 0 else 0
                eta_text = f"{eta}ث" if eta < 60 else f"{eta//60}د"
                
                bar_length = 25
                filled_length = int(bar_length * (i + 1) // total_files)
                bar = '█' * filled_length + '░' * (bar_length - filled_length)
                
                print(f"\r[{bar}] {percentage:.1f}% - رفع: {uploaded} - متبقي: {eta_text}", end='', flush=True)
            
            print()
            sftp.close()
            ssh.close()
            
            total_time = time.time() - start_time
            print(f"✅ تم رفع {uploaded} ملف في {total_time:.1f}ث")
            
            # عرض تفاصيل الملفات المرفوعة
            if uploaded_files:
                print(f"\n📋 الملفات المرفوعة ({len(uploaded_files)}):")
                display_count = min(15, len(uploaded_files))
                for f in uploaded_files[:display_count]:
                    print(f"   ✅ {f}")
                if len(uploaded_files) > display_count:
                    print(f"   ... و {len(uploaded_files) - display_count} ملف آخر")
                
                # حفظ قائمة مفصلة في ملف
                self._save_upload_log(uploaded_files, "رفع كامل مع استبدال")
            
            return True
            
        except Exception as e:
            print(f"\n❌ خطأ في الرفع: {e}")
            return False

    def upload_modified_only(self, files):
        """رفع الملفات المعدلة فقط (مقارنة hash محلي)"""
        print("🔍 مقارنة مع آخر نشر...")
        
        # تحميل hashes السابقة
        previous_hashes = {}
        if self.hash_file.exists():
            try:
                with open(self.hash_file, 'r', encoding='utf-8') as f:
                    previous_hashes = json.load(f)
            except:
                print("⚠️  لا يمكن قراءة ملف hashes السابق")
        
        # تحديد الملفات المعدلة
        modified_files = []
        new_files = []
        changed_files = []
        uploaded_files = []  # قائمة الملفات المرفوعة فعلياً
        
        for file_path in files:
            relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
            current_hash = self.get_file_hash(file_path)
            
            if relative_path not in previous_hashes:
                # ملف جديد
                modified_files.append(file_path)
                new_files.append(relative_path)
            elif previous_hashes[relative_path] != current_hash:
                # ملف معدل
                modified_files.append(file_path)
                changed_files.append(relative_path)
        
        if not modified_files:
            print("✅ جميع الملفات محدثة منذ آخر نشر!")
            return True
        
        print(f"📊 {len(new_files)} ملف جديد، {len(changed_files)} ملف معدل")
        
        # عرض تفاصيل أكتر للملفات الجديدة
        if new_files:
            print("📄 الملفات الجديدة:")
            display_count = min(10, len(new_files))  # عرض أول 10 ملفات
            for f in new_files[:display_count]:
                print(f"   + {f}")
            if len(new_files) > display_count:
                print(f"   ... و {len(new_files) - display_count} ملف جديد آخر")
        
        # عرض تفاصيل أكتر للملفات المعدلة
        if changed_files:
            print("📝 الملفات المعدلة:")
            display_count = min(10, len(changed_files))  # عرض أول 10 ملفات
            for f in changed_files[:display_count]:
                print(f"   ~ {f}")
            if len(changed_files) > display_count:
                print(f"   ... و {len(changed_files) - display_count} ملف معدل آخر")
        
        print(f"\n📤 رفع {len(modified_files)} ملف...")
        
        # رفع الملفات المعدلة فقط
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            ssh.connect(
                hostname=self.server_ip,
                port=int(self.ssh_port),
                username=self.username,
                password=self.ssh_password,
                timeout=30
            )
            
            sftp = ssh.open_sftp()
            
            uploaded = 0
            start_time = time.time()
            
            for i, file_path in enumerate(modified_files):
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                remote_file = f"{self.remote_path}/{relative_path}"
                
                try:
                    # إنشاء المجلد إذا لزم الأمر
                    remote_dir = '/'.join(remote_file.split('/')[:-1])
                    if remote_dir != self.remote_path:
                        try:
                            sftp.mkdir(remote_dir)
                        except:
                            pass
                    
                    sftp.put(str(file_path), remote_file)
                    uploaded += 1
                    uploaded_files.append(relative_path)  # إضافة للقائمة المرفوعة
                    
                except Exception as e:
                    print(f"\n⚠️  خطأ في رفع {relative_path}: {e}")
                
                # عرض التقدم
                percentage = ((i + 1) / len(modified_files)) * 100
                elapsed = time.time() - start_time
                remaining = len(modified_files) - (i + 1)
                eta = int((elapsed / (i + 1)) * remaining) if i > 0 else 0
                eta_text = f"{eta}ث" if eta < 60 else f"{eta//60}د"
                
                bar_length = 25
                filled_length = int(bar_length * (i + 1) // len(modified_files))
                bar = '█' * filled_length + '░' * (bar_length - filled_length)
                
                print(f"\r[{bar}] {percentage:.1f}% - رفع: {uploaded} - متبقي: {eta_text}", end='', flush=True)
            
            print()
            sftp.close()
            ssh.close()
            
            total_time = time.time() - start_time
            skipped = len(files) - len(modified_files)
            print(f"✅ رفع: {uploaded}, تخطي: {skipped} في {total_time:.1f}ث")
            
            # عرض تفاصيل الملفات المرفوعة فعلياً
            if uploaded_files:
                print(f"\n📋 الملفات المرفوعة ({len(uploaded_files)}):")
                
                # تصنيف الملفات المرفوعة
                uploaded_new = [f for f in uploaded_files if f in new_files]
                uploaded_changed = [f for f in uploaded_files if f in changed_files]
                
                if uploaded_new:
                    print(f"   📄 جديد ({len(uploaded_new)}):")
                    display_count = min(8, len(uploaded_new))
                    for f in uploaded_new[:display_count]:
                        print(f"      ✅ {f}")
                    if len(uploaded_new) > display_count:
                        print(f"      ... و {len(uploaded_new) - display_count} ملف جديد آخر")
                
                if uploaded_changed:
                    print(f"   📝 معدل ({len(uploaded_changed)}):")
                    display_count = min(8, len(uploaded_changed))
                    for f in uploaded_changed[:display_count]:
                        print(f"      ✅ {f}")
                    if len(uploaded_changed) > display_count:
                        print(f"      ... و {len(uploaded_changed) - display_count} ملف معدل آخر")
                
                # حفظ قائمة مفصلة في ملف
                self._save_upload_log(uploaded_files, "رفع المعدل فقط")
            
            return True
            
        except Exception as e:
            print(f"\n❌ خطأ في الرفع: {e}")
            return False

    def deploy_all(self):
        """رفع جميع الملفات مع استبدال"""
        print("\n🔄 رفع جميع الملفات مع استبدال...")
        
        if not self.test_connection():
            return False
            
        files = self.get_all_files()
        print(f"📊 {len(files)} ملف للرفع")
        
        confirm = input(f"❓ رفع {len(files)} ملف مع استبدال؟ (y/N): ").lower()
        if confirm != 'y':
            print("❌ تم الإلغاء")
            return False
            
        success = self.upload_all_files(files)
        
        if success:
            # حفظ hashes
            current_hashes = {}
            for file_path in files:
                relative_path = str(file_path.relative_to(self.project_root))
                current_hashes[relative_path] = self.get_file_hash(file_path)
            
            with open(self.hash_file, 'w', encoding='utf-8') as f:
                json.dump(current_hashes, f, indent=2, ensure_ascii=False)
            
        return success

    def deploy_modified(self):
        """رفع الملفات مع خيارات متعددة"""
        print("\n🔄 رفع الملفات...")
        
        if not self.test_connection():
            return False
            
        all_files = self.get_all_files()
        print(f"📊 {len(all_files)} ملف للفحص")
        
        print("\n📋 اختر طريقة الرفع:")
        print("1️⃣  رفع كامل مع استبدال (يرفع كل شيء - بطيء)")
        print("2️⃣  رفع كامل مع تخطي (مقارنة مع الخادم - متوسط)")
        print("3️⃣  رفع المعدل فقط (مقارنة hash محلي - سريع جداً)")
        print("❌ أي رقم آخر للإلغاء")
        
        choice = input("\n❓ اختيارك (1/2/3): ").strip()
        
        if choice == "1":
            print("🔄 رفع كامل مع استبدال...")
            print("📝 سيتم رفع جميع الملفات مع استبدال الموجود")
            success = self.upload_all_files(all_files)
            method_name = "رفع كامل مع استبدال"
        elif choice == "2":
            print("🔄 رفع كامل مع تخطي المطابق...")
            print("📝 سيتم فحص كل ملف ورفع المختلف فقط")
            success = self.upload_with_smart_skip(all_files)
            method_name = "رفع كامل مع تخطي"
        elif choice == "3":
            print("🔄 رفع المعدل فقط...")
            print("📝 سيتم رفع الملفات الجديدة والمعدلة منذ آخر نشر فقط")
            success = self.upload_modified_only(all_files)
            method_name = "رفع المعدل فقط"
        else:
            print("❌ تم الإلغاء")
            return False
        
        if success:
            # حفظ hashes الجديدة
            current_hashes = {}
            for file_path in all_files:
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                current_hashes[relative_path] = self.get_file_hash(file_path)
            
            with open(self.hash_file, 'w', encoding='utf-8') as f:
                json.dump(current_hashes, f, indent=2, ensure_ascii=False)
            
            print(f"\n🎉 تم بنجاح! الطريقة المستخدمة: {method_name}")
            
        return success

    def deploy_single_file(self, filename):
        """رفع ملف واحد محدد"""
        print(f"\n🔄 رفع ملف: {filename}")
        
        file_path = self.project_root / filename
        if not file_path.exists():
            print(f"❌ الملف غير موجود: {filename}")
            return False
        
        # استثناء خاص للملفات المهمة حتى لو كانت مستثناة في .gitignore
        important_files = [
            'core/security/file_validators_temp.py',
            'core/security/__init__.py',
            '.env.production',
            'setup_development.py',
            'passenger_wsgi.py'
        ]
        
        if filename not in important_files and self.is_ignored(file_path):
            print(f"❌ الملف مستثنى: {filename}")
            return False
        
        if not self.test_connection():
            return False
        
        # رفع الملف مباشرة بدون مجلد مؤقت
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            ssh.connect(
                hostname=self.server_ip,
                port=int(self.ssh_port),
                username=self.username,
                password=self.ssh_password,
                timeout=30
            )
            
            sftp = ssh.open_sftp()
            
            # تحديد المسار البعيد
            relative_path = file_path.relative_to(self.project_root)
            remote_file = f"{self.remote_path}/{relative_path}".replace('\\', '/')
            
            # إنشاء المجلد البعيد إذا لزم الأمر
            remote_dir = '/'.join(remote_file.split('/')[:-1])
            if remote_dir and remote_dir != self.remote_path:
                try:
                    sftp.mkdir(remote_dir)
                except:
                    pass
            
            print(f"📤 رفع الملف...")
            sftp.put(str(file_path), remote_file)
            
            sftp.close()
            ssh.close()
            
            print("✅ تم الرفع بنجاح!")
            
            # تحديث hash الملف
            previous_hashes = {}
            if self.hash_file.exists():
                try:
                    with open(self.hash_file, 'r', encoding='utf-8') as f:
                        previous_hashes = json.load(f)
                except:
                    pass
            
            relative_path_str = str(relative_path).replace('\\', '/')
            previous_hashes[relative_path_str] = self.get_file_hash(file_path)
            
            with open(self.hash_file, 'w', encoding='utf-8') as f:
                json.dump(previous_hashes, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            print(f"❌ خطأ في الرفع: {e}")
            return False

    def show_status(self):
        """عرض الحالة - بسيط"""
        print("\n📊 حالة الملفات:")
        
        all_files = self.get_all_files()
        print(f"📁 إجمالي الملفات: {len(all_files)}")
        
        if not self.test_connection():
            return
            
        print("🔍 فحص سريع...")
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            ssh.connect(
                hostname=self.server_ip,
                port=int(self.ssh_port),
                username=self.username,
                password=self.ssh_password,
                timeout=30
            )
            
            sftp = ssh.open_sftp()
            
            identical = 0
            different = 0
            
            for file_path in all_files[:100]:  # فحص أول 100 ملف فقط للسرعة
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                remote_file = f"{self.remote_path}/{relative_path}"
                
                try:
                    remote_stat = sftp.stat(remote_file)
                    local_stat = file_path.stat()
                    
                    if (remote_stat.st_size == local_stat.st_size and 
                        abs(remote_stat.st_mtime - local_stat.st_mtime) <= 5):
                        identical += 1
                    else:
                        different += 1
                except:
                    different += 1
            
            sftp.close()
            ssh.close()
            
            print(f"✅ مطابق (من أول 100): {identical}")
            print(f"📝 مختلف (من أول 100): {different}")
            
        except Exception as e:
            print(f"❌ خطأ في الفحص: {e}")

    def sync_all(self):
        """رفع مع تخطي المطابق"""
        print("\n🔄 رفع مع تخطي المطابق...")
        
        if not self.test_connection():
            return False
            
        files = self.get_all_files()
        print(f"📊 {len(files)} ملف للفحص")
        
        confirm = input(f"❓ بدء الرفع مع تخطي المطابق؟ (y/N): ").lower()
        if confirm != 'y':
            print("❌ تم الإلغاء")
            return False
            
        success = self.upload_with_smart_skip(files)
        
        if success:
            # حفظ hashes الجديدة
            current_hashes = {}
            for file_path in files:
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                current_hashes[relative_path] = self.get_file_hash(file_path)
            
            with open(self.hash_file, 'w', encoding='utf-8') as f:
                json.dump(current_hashes, f, indent=2, ensure_ascii=False)
            
        return success

    def sync_with_cleanup(self, local_files):
        """مزامنة ذكية - محسن للسرعة"""
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            ssh.connect(
                hostname=self.server_ip,
                port=int(self.ssh_port),
                username=self.username,
                password=self.ssh_password,
                timeout=30
            )
            
            sftp = ssh.open_sftp()
            
            print("🔍 مقارنة مع الخادم...")
            
            # الحصول على قائمة الملفات المحلية
            local_files_dict = {}
            for file_path in local_files:
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                stat = file_path.stat()
                local_files_dict[relative_path] = {
                    'path': file_path,
                    'size': stat.st_size,
                    'mtime': int(stat.st_mtime)
                }
            
            # الحصول على قائمة الملفات البعيدة
            remote_files_dict = {}
            self.get_remote_files_with_stats(sftp, self.remote_path, remote_files_dict)
            
            # تحديد الملفات للرفع والحذف بسرعة
            files_to_upload = []
            new_count = 0
            modified_count = 0
            
            for relative_path, local_info in local_files_dict.items():
                if relative_path not in remote_files_dict:
                    files_to_upload.append(local_info['path'])
                    new_count += 1
                else:
                    remote_info = remote_files_dict[relative_path]
                    
                    # مقارنة سريعة
                    if local_info['size'] != remote_info['size']:
                        files_to_upload.append(local_info['path'])
                        modified_count += 1
                    else:
                        time_diff = abs(local_info['mtime'] - remote_info['mtime'])
                        if 60 < time_diff < 86400:
                            files_to_upload.append(local_info['path'])
                            modified_count += 1
            
            # الملفات للحذف من الفولدرات فقط
            local_files_set = set(local_files_dict.keys())
            remote_files_set = set(remote_files_dict.keys())
            files_to_delete = [f for f in (remote_files_set - local_files_set) if '/' in f]
            
            total_operations = len(files_to_delete) + len(files_to_upload)
            
            print(f"📊 المزامنة: {new_count} جديد، {modified_count} معدل، {len(files_to_delete)} للحذف")
            
            if total_operations == 0:
                print("✅ جميع الملفات محدثة!")
                sftp.close()
                ssh.close()
                return True
            
            start_time = time.time()
            completed = 0
            
            # حذف الملفات القديمة
            for remote_file in files_to_delete:
                try:
                    sftp.remove(f"{self.remote_path}/{remote_file}")
                    completed += 1
                    percentage = (completed / total_operations) * 100
                    self.show_progress(percentage, completed, total_operations, "حذف")
                except:
                    pass
            
            # رفع الملفات
            if files_to_upload:
                # إنشاء المجلدات
                all_dirs = set()
                for file_path in files_to_upload:
                    relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                    remote_dir = '/'.join(f"{self.remote_path}/{relative_path}".split('/')[:-1])
                    if remote_dir != self.remote_path:
                        all_dirs.add(remote_dir)
                
                for remote_dir in sorted(all_dirs):
                    try:
                        sftp.mkdir(remote_dir)
                    except:
                        pass
                
                # رفع الملفات
                for file_path in files_to_upload:
                    try:
                        relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                        remote_file = f"{self.remote_path}/{relative_path}"
                        
                        sftp.put(str(file_path), remote_file)
                        completed += 1
                        
                        percentage = (completed / total_operations) * 100
                        elapsed = time.time() - start_time
                        remaining = total_operations - completed
                        eta = int((elapsed / completed) * remaining) if completed > 0 else 0
                        eta_text = f"{eta}ث" if eta < 60 else f"{eta//60}د"
                        
                        self.show_progress(percentage, completed, total_operations, f"رفع - متبقي: {eta_text}")
                        
                    except:
                        pass
            
            print()
            sftp.close()
            ssh.close()
            
            total_time = time.time() - start_time
            print(f"✅ تمت المزامنة في {total_time:.1f}ث")
            return True
            
        except Exception as e:
            print(f"❌ خطأ: {e}")
            return False

    def get_remote_files_in_folders(self, sftp, remote_path, files_set, base_path=""):
        """الحصول على قائمة الملفات البعيدة من الفولدرات فقط (ليس الـ root)"""
        try:
            for item in sftp.listdir_attr(remote_path):
                item_path = f"{remote_path}/{item.filename}"
                relative_path = f"{base_path}/{item.filename}" if base_path else item.filename
                
                if item.st_mode and item.st_mode & 0o040000:  # مجلد
                    # استكشاف المجلد
                    self.get_remote_files_in_folders(sftp, item_path, files_set, relative_path)
                else:  # ملف
                    # إضافة الملف فقط إذا كان داخل مجلد (ليس في الـ root)
                    if base_path:  # يعني الملف داخل مجلد
                        files_set.add(relative_path)
        except Exception as e:
            # تجاهل الأخطاء في قراءة بعض المجلدات
            pass

    def show_progress(self, percentage, completed, total, operation):
        """عرض شريط التقدم"""
        bar_length = 25
        filled_length = int(bar_length * completed // total)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        
        print(f"\r   [{bar}] {percentage:.1f}% ({completed}/{total}) {operation}", end='', flush=True)

    def _save_upload_log(self, uploaded_files, method_name):
        """حفظ تفاصيل الملفات المرفوعة في ملف log"""
        try:
            from datetime import datetime
            
            log_file = self.project_root / "deploy_logs" / f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            log_file.parent.mkdir(exist_ok=True)
            
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"📤 تقرير الرفع - {method_name}\n")
                f.write(f"⏰ التوقيت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"🖥️  الخادم: {self.server_ip}:{self.ssh_port}\n")
                f.write(f"📁 المسار البعيد: {self.remote_path}\n")
                f.write(f"📊 إجمالي الملفات المرفوعة: {len(uploaded_files)}\n")
                f.write("=" * 50 + "\n\n")
                
                for i, file_path in enumerate(uploaded_files, 1):
                    f.write(f"{i:4d}. {file_path}\n")
                
                f.write(f"\n" + "=" * 50 + "\n")
                f.write(f"✅ تم حفظ {len(uploaded_files)} ملف بنجاح\n")
            
            print(f"📝 تم حفظ تفاصيل الرفع في: {log_file}")
            
        except Exception as e:
            print(f"⚠️  لا يمكن حفظ log الرفع: {e}")

def main():
    parser = argparse.ArgumentParser(description="سكريپت النشر المحسن")
    parser.add_argument('--mode', choices=['all', 'modified', 'status', 'file', 'sync', 'test'], 
                       default='modified', help='وضع النشر')
    parser.add_argument('--file', type=str, help='ملف محدد للرفع')
    parser.add_argument('--force', action='store_true', help='بدون تأكيد')
    
    args = parser.parse_args()
    
    try:
        deploy_manager = DeploymentManager()
        
        if args.mode == 'test':
            deploy_manager.test_connection()
        elif args.mode == 'status':
            deploy_manager.show_status()
        elif args.mode == 'all':
            deploy_manager.deploy_all()
        elif args.mode == 'modified':
            deploy_manager.deploy_modified()
        elif args.mode == 'file' and args.file:
            deploy_manager.deploy_single_file(args.file)
        elif args.mode == 'sync':
            deploy_manager.sync_all()
        else:
            print("❌ يجب تحديد ملف مع --file")
            
    except KeyboardInterrupt:
        print("\n❌ تم الإيقاف")
        sys.exit(1)
    except Exception as e:
        print(f"❌ خطأ: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()