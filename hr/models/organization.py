"""
نماذج الهيكل التنظيمي
"""
from django.db import models


class Department(models.Model):
    """نموذج الأقسام والإدارات"""
    
    code = models.CharField(max_length=20, unique=True, verbose_name='كود القسم')
    name_ar = models.CharField(max_length=200, verbose_name='اسم القسم (عربي)')
    name_en = models.CharField(max_length=200, verbose_name='اسم القسم (إنجليزي)', blank=True)
    description = models.TextField(blank=True, verbose_name='الوصف')
    
    # التسلسل الهرمي
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='sub_departments',
        verbose_name='القسم الأب'
    )
    
    # المدير
    manager = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_departments',
        verbose_name='مدير القسم'
    )
    
    # الحالة
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    
    class Meta:
        verbose_name = 'قسم'
        verbose_name_plural = 'الأقسام'
        ordering = ['code']
    
    def __str__(self):
        return f"{self.code} - {self.name_ar}"
    
    @property
    def employees_count(self):
        """عدد الموظفين النشطين في القسم"""
        return self.employees.filter(status='active').count()
    
    @property
    def full_path(self):
        """المسار الكامل للقسم في الهيكل التنظيمي"""
        if self.parent:
            return f"{self.parent.full_path} > {self.name_ar}"
        return self.name_ar
    
    @classmethod
    def create_default_departments(cls):
        """إنشاء الأقسام الافتراضية"""
        from django.db import transaction
        
        # الأقسام الافتراضية
        default_departments = [
            {'code': 'ADM', 'name_ar': 'الإدارة العامة', 'name_en': 'Administration', 'parent_code': None},
            {'code': 'FIN', 'name_ar': 'الشؤون المالية', 'name_en': 'Financial Affairs', 'parent_code': None},
            {'code': 'HR', 'name_ar': 'الموارد البشرية', 'name_en': 'Human Resources', 'parent_code': None},
            {'code': 'SAL', 'name_ar': 'المبيعات', 'name_en': 'Sales', 'parent_code': None},
            {'code': 'PUR', 'name_ar': 'المشتريات', 'name_en': 'Purchasing', 'parent_code': None},
            {'code': 'PRD', 'name_ar': 'الإنتاج', 'name_en': 'Production', 'parent_code': None},
            {'code': 'IT', 'name_ar': 'تقنية المعلومات', 'name_en': 'IT', 'parent_code': None},
            {'code': 'MKT', 'name_ar': 'التسويق', 'name_en': 'Marketing', 'parent_code': None},
            {'code': 'SRV', 'name_ar': 'الخدمات المساندة', 'name_en': 'Support Services', 'parent_code': None},
            
            # أقسام فرعية للإدارة
            {'code': 'ADM-SEC', 'name_ar': 'السكرتارية', 'name_en': 'Secretariat', 'parent_code': 'ADM'},
            {'code': 'ADM-LEG', 'name_ar': 'الشؤون القانونية', 'name_en': 'Legal Affairs', 'parent_code': 'ADM'},
            
            # أقسام فرعية للمبيعات
            {'code': 'SAL-RET', 'name_ar': 'مبيعات التجزئة', 'name_en': 'Retail Sales', 'parent_code': 'SAL'},
            {'code': 'SAL-WHO', 'name_ar': 'مبيعات الجملة', 'name_en': 'Wholesale Sales', 'parent_code': 'SAL'},
            
            # أقسام فرعية للخدمات
            {'code': 'SRV-MNT', 'name_ar': 'الصيانة', 'name_en': 'Maintenance', 'parent_code': 'SRV'},
            {'code': 'SRV-SEC', 'name_ar': 'الأمن', 'name_en': 'Security', 'parent_code': 'SRV'},
            {'code': 'SRV-CLN', 'name_ar': 'النظافة', 'name_en': 'Cleaning', 'parent_code': 'SRV'},
        ]
        
        try:
            with transaction.atomic():
                # إنشاء الأقسام الرئيسية أولاً
                for dept_data in default_departments:
                    if dept_data['parent_code'] is None:
                        cls.objects.get_or_create(
                            code=dept_data['code'],
                            defaults={
                                'name_ar': dept_data['name_ar'],
                                'name_en': dept_data['name_en'],
                                'is_active': True
                            }
                        )
                
                # ثم إنشاء الأقسام الفرعية
                for dept_data in default_departments:
                    if dept_data['parent_code'] is not None:
                        parent_dept = cls.objects.get(code=dept_data['parent_code'])
                        cls.objects.get_or_create(
                            code=dept_data['code'],
                            defaults={
                                'name_ar': dept_data['name_ar'],
                                'name_en': dept_data['name_en'],
                                'parent': parent_dept,
                                'is_active': True
                            }
                        )
                
                return True
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"فشل في إنشاء الأقسام الافتراضية: {e}")
            return False


class JobTitle(models.Model):
    """نموذج المسميات الوظيفية"""
    
    code = models.CharField(max_length=20, unique=True, verbose_name='كود الوظيفة')
    title_ar = models.CharField(max_length=200, verbose_name='المسمى (عربي)')
    title_en = models.CharField(max_length=200, verbose_name='المسمى (إنجليزي)', blank=True)
    description = models.TextField(blank=True, verbose_name='الوصف')
    
    # القسم
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='job_titles',
        verbose_name='القسم'
    )
    
    # المسؤوليات والمتطلبات
    responsibilities = models.TextField(verbose_name='المسؤوليات', blank=True)
    requirements = models.TextField(verbose_name='المتطلبات', blank=True)
    
    # الحالة
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    
    # التواريخ
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    
    class Meta:
        verbose_name = 'مسمى وظيفي'
        verbose_name_plural = 'المسميات الوظيفية'
        ordering = ['code']
    
    def __str__(self):
        return f"{self.code} - {self.title_ar}"
    
    @staticmethod
    def generate_code():
        """توليد كود تلقائي مسلسل للوظيفة"""
        # جلب جميع الوظائف وترتيبها حسب الكود
        job_titles = JobTitle.objects.filter(code__startswith='JOB-').order_by('-code')
        
        if job_titles.exists():
            last_job_title = job_titles.first()
            try:
                last_number = int(last_job_title.code.split('-')[1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = 1
        else:
            new_number = 1
        
        return f"JOB-{new_number:04d}"
    
    def save(self, *args, **kwargs):
        """حفظ الوظيفة مع توليد الكود تلقائياً إذا لم يكن موجوداً"""
        if not self.code:
            self.code = self.generate_code()
        super().save(*args, **kwargs)
    
    @classmethod
    def create_default_job_titles(cls):
        """إنشاء المسميات الوظيفية الافتراضية"""
        from django.db import transaction
        
        # إنشاء الأقسام أولاً
        Department.create_default_departments()
        
        # المسميات الوظيفية الافتراضية
        default_job_titles = [
            # الإدارة العليا
            {'code': 'JOB-001', 'title_ar': 'المدير العام', 'title_en': 'General Manager', 'department_code': 'ADM'},
            {'code': 'JOB-002', 'title_ar': 'نائب المدير', 'title_en': 'Deputy Manager', 'department_code': 'ADM'},
            {'code': 'JOB-003', 'title_ar': 'مدير إداري', 'title_en': 'Administrative Manager', 'department_code': 'ADM'},
            
            # الشؤون المالية
            {'code': 'JOB-101', 'title_ar': 'مدير مالي', 'title_en': 'Financial Manager', 'department_code': 'FIN'},
            {'code': 'JOB-102', 'title_ar': 'محاسب رئيسي', 'title_en': 'Chief Accountant', 'department_code': 'FIN'},
            {'code': 'JOB-103', 'title_ar': 'محاسب', 'title_en': 'Accountant', 'department_code': 'FIN'},
            {'code': 'JOB-104', 'title_ar': 'أمين صندوق', 'title_en': 'Cashier', 'department_code': 'FIN'},
            
            # الموارد البشرية
            {'code': 'JOB-201', 'title_ar': 'مدير موارد بشرية', 'title_en': 'HR Manager', 'department_code': 'HR'},
            {'code': 'JOB-202', 'title_ar': 'أخصائي موارد بشرية', 'title_en': 'HR Specialist', 'department_code': 'HR'},
            {'code': 'JOB-203', 'title_ar': 'منسق توظيف', 'title_en': 'Recruitment Coordinator', 'department_code': 'HR'},
            
            # المبيعات
            {'code': 'JOB-301', 'title_ar': 'مدير مبيعات', 'title_en': 'Sales Manager', 'department_code': 'SAL'},
            {'code': 'JOB-302', 'title_ar': 'مشرف مبيعات', 'title_en': 'Sales Supervisor', 'department_code': 'SAL'},
            {'code': 'JOB-303', 'title_ar': 'مندوب مبيعات', 'title_en': 'Sales Representative', 'department_code': 'SAL'},
            {'code': 'JOB-304', 'title_ar': 'موظف مبيعات', 'title_en': 'Sales Associate', 'department_code': 'SAL'},
            
            # المشتريات
            {'code': 'JOB-401', 'title_ar': 'مدير مشتريات', 'title_en': 'Purchasing Manager', 'department_code': 'PUR'},
            {'code': 'JOB-402', 'title_ar': 'موظف مشتريات', 'title_en': 'Purchasing Officer', 'department_code': 'PUR'},
            {'code': 'JOB-403', 'title_ar': 'أمين مخزن', 'title_en': 'Storekeeper', 'department_code': 'PUR'},
            
            # الإنتاج
            {'code': 'JOB-501', 'title_ar': 'مدير إنتاج', 'title_en': 'Production Manager', 'department_code': 'PRD'},
            {'code': 'JOB-502', 'title_ar': 'مشرف إنتاج', 'title_en': 'Production Supervisor', 'department_code': 'PRD'},
            {'code': 'JOB-503', 'title_ar': 'عامل إنتاج', 'title_en': 'Production Worker', 'department_code': 'PRD'},
            
            # تقنية المعلومات
            {'code': 'JOB-601', 'title_ar': 'مدير تقنية معلومات', 'title_en': 'IT Manager', 'department_code': 'IT'},
            {'code': 'JOB-602', 'title_ar': 'مطور برمجيات', 'title_en': 'Software Developer', 'department_code': 'IT'},
            {'code': 'JOB-603', 'title_ar': 'فني دعم فني', 'title_en': 'IT Support Technician', 'department_code': 'IT'},
            
            # التسويق
            {'code': 'JOB-701', 'title_ar': 'مدير تسويق', 'title_en': 'Marketing Manager', 'department_code': 'MKT'},
            {'code': 'JOB-702', 'title_ar': 'أخصائي تسويق', 'title_en': 'Marketing Specialist', 'department_code': 'MKT'},
            
            # الإدارة والخدمات
            {'code': 'JOB-801', 'title_ar': 'سكرتير', 'title_en': 'Secretary', 'department_code': 'ADM'},
            {'code': 'JOB-802', 'title_ar': 'موظف استقبال', 'title_en': 'Receptionist', 'department_code': 'ADM'},
            
            # الخدمات المساندة
            {'code': 'JOB-901', 'title_ar': 'عامل نظافة', 'title_en': 'Cleaner', 'department_code': 'SRV'},
            {'code': 'JOB-902', 'title_ar': 'حارس أمن', 'title_en': 'Security Guard', 'department_code': 'SRV'},
            {'code': 'JOB-903', 'title_ar': 'فني صيانة', 'title_en': 'Maintenance Technician', 'department_code': 'SRV'},
            {'code': 'JOB-904', 'title_ar': 'سائق', 'title_en': 'Driver', 'department_code': 'SRV'},
        ]
        
        try:
            with transaction.atomic():
                for job_data in default_job_titles:
                    department = Department.objects.get(code=job_data['department_code'])
                    
                    cls.objects.get_or_create(
                        code=job_data['code'],
                        defaults={
                            'title_ar': job_data['title_ar'],
                            'title_en': job_data['title_en'],
                            'department': department,
                            'is_active': True
                        }
                    )
                
                return True
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"فشل في إنشاء المسميات الوظيفية الافتراضية: {e}")
            return False
