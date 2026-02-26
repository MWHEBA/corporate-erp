// Classroom Year Management JavaScript
// Version: 2.0

document.addEventListener('DOMContentLoaded', function() {
    
    // استخدام selectors أكثر دقة للمودال
    const modal = document.getElementById('createClassroomYearModal');
    const classroomSelect = modal ? modal.querySelector('select[name="classroom"]') : null;
    const capacityInput = modal ? modal.querySelector('input[name="capacity_for_year"]') : null;
    const academicYearSelect = modal ? modal.querySelector('select[name="academic_year"]') : null;
    const ageGroupSelect = modal ? modal.querySelector('select[name="age_group"]') : null;
    const classroomTypeFilter = modal ? modal.querySelector('select[name="classroom_type_filter"]') : null;
    const nameInput = modal ? modal.querySelector('input[name="name_for_year"]') : null;
    
    // عناصر خارج المودال
    const mainClassroomTypeFilter = document.getElementById('mainClassroomTypeFilter');
    const usedNamesAlert = document.getElementById('usedNamesAlert');
    const usedNamesList = document.getElementById('usedNamesList');
    const duplicateAlert = document.getElementById('duplicateNameAlert');
    const nameValidAlert = document.getElementById('nameValidAlert');
    
    let allClassrooms = [];
    let usedNames = [];
    
    // حفظ جميع الفصول للفلترة
    if (classroomSelect) {
        for (let i = 0; i < classroomSelect.options.length; i++) {
            const option = classroomSelect.options[i];
            if (option.value) {
                const classroom = {
                    value: option.value,
                    text: option.text,
                    capacity: option.getAttribute('data-capacity') || option.dataset.capacity,
                    type: option.getAttribute('data-type') || 'english',
                    typeDisplay: option.getAttribute('data-type-display') || 'إنجليزي'
                };
                allClassrooms.push(classroom);
            }
        }
    }
    
    // فلترة الفصول حسب النوع مع إخفاء الفصول المستخدمة
    function filterClassrooms() {
        const selectedType = classroomTypeFilter?.value || '';
        const selectedAcademicYear = academicYearSelect?.value || '';
        
        if (!classroomSelect) return;
        
        classroomSelect.innerHTML = '<option value="">جاري التحميل...</option>';
        classroomSelect.disabled = true;
        
        const baseUrl = classroomSelect.getAttribute('data-filter-url') || '/academic/classroom-years/filter-classrooms/';
        let url = `${baseUrl}?classroom_type=${selectedType}`;
        if (selectedAcademicYear) {
            url += `&academic_year_id=${selectedAcademicYear}`;
        }
        
        fetch(url)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    classroomSelect.innerHTML = '<option value="">اختر الفصل</option>';
                    
                    data.classrooms.forEach(classroom => {
                        const option = document.createElement('option');
                        option.value = classroom.value;
                        option.text = classroom.text;
                        option.setAttribute('data-capacity', classroom.capacity);
                        option.setAttribute('data-type', classroom.type);
                        option.setAttribute('data-type-display', classroom.type_display);
                        classroomSelect.appendChild(option);
                    });
                    
                    allClassrooms = data.classrooms;
                    
                    if (data.classrooms.length === 0) {
                        classroomSelect.innerHTML = '<option value="">لا توجد فصول متاحة</option>';
                    }
                } else {
                    console.error('Server error:', data.message);
                    classroomSelect.innerHTML = '<option value="">خطأ في التحميل</option>';
                }
            })
            .catch(error => {
                console.error('Network error:', error);
                classroomSelect.innerHTML = '<option value="">خطأ في الاتصال</option>';
            })
            .finally(() => {
                classroomSelect.disabled = false;
                
                if (capacityInput) {
                    capacityInput.value = '';
                    capacityInput.removeAttribute('max');
                    capacityInput.placeholder = 'سيتم تعيينها تلقائياً';
                }
            });
    }
    
    // تحديث السعة تلقائياً عند اختيار الفصل
    if (classroomSelect && capacityInput) {
        classroomSelect.addEventListener('change', function() {
            const selectedOption = this.options[this.selectedIndex];
            if (selectedOption.dataset.capacity) {
                const maxCapacity = parseInt(selectedOption.dataset.capacity);
                capacityInput.value = maxCapacity;
                capacityInput.max = maxCapacity;
                capacityInput.placeholder = `الحد الأقصى: ${maxCapacity}`;
            } else {
                capacityInput.value = '';
                capacityInput.removeAttribute('max');
                capacityInput.placeholder = 'سيتم تعيينها تلقائياً';
            }
        });
    }
    
    // Event listener لفلترة نوع الفصل في المودال
    if (classroomTypeFilter) {
        classroomTypeFilter.addEventListener('change', function() {
            filterClassrooms();
        });
    }
    
    // Event listener لتغيير السنة الدراسية
    if (academicYearSelect) {
        academicYearSelect.addEventListener('change', function() {
            filterClassrooms();
        });
    }
    
    // تحميل الفصول عند فتح المودال
    if (modal) {
        modal.addEventListener('shown.bs.modal', function() {
            if (mainClassroomTypeFilter && classroomTypeFilter) {
                classroomTypeFilter.value = mainClassroomTypeFilter.value;
            }
            filterClassrooms();
        });
        
        modal.addEventListener('hidden.bs.modal', function() {
            const form = document.getElementById('createClassroomYearForm');
            if (form) {
                form.reset();
                
                if (usedNamesAlert) usedNamesAlert.style.display = 'none';
                if (duplicateAlert) duplicateAlert.style.display = 'none';
                if (nameValidAlert) nameValidAlert.style.display = 'none';
                
                const submitBtn = form.querySelector('button[type="submit"]');
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<i class="fas fa-save me-2"></i>إنشاء اسم الفصل';
                }
            }
        });
    }
    
    // Event listener للفلتر الرئيسي في الصفحة
    if (mainClassroomTypeFilter) {
        mainClassroomTypeFilter.addEventListener('change', function() {
            if (classroomTypeFilter) {
                classroomTypeFilter.value = this.value;
            }
            this.form.submit();
        });
    }
    
    // تحديث الأسماء المستخدمة
    function updateUsedNames() {
        const academicYearId = academicYearSelect?.value;
        const ageGroupId = ageGroupSelect?.value;
        
        if (academicYearId && ageGroupId) {
            const usedNamesUrl = ageGroupSelect.getAttribute('data-used-names-url') || '/academic/classroom-years/used-names/';
            fetch(`${usedNamesUrl}?academic_year=${academicYearId}&age_group=${ageGroupId}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        usedNames = data.used_names || [];
                        displayUsedNames();
                        checkNameDuplicate();
                    }
                })
                .catch(error => {
                    console.error('Error fetching used names:', error);
                });
        } else {
            hideUsedNames();
        }
    }
    
    function displayUsedNames() {
        if (usedNames.length > 0 && usedNamesList) {
            const namesBadges = usedNames.map(name => 
                `<span class="badge bg-secondary me-1">${name}</span>`
            ).join('');
            usedNamesList.innerHTML = namesBadges;
            if (usedNamesAlert) usedNamesAlert.style.display = 'block';
        } else {
            hideUsedNames();
        }
    }
    
    function hideUsedNames() {
        if (usedNamesAlert) usedNamesAlert.style.display = 'none';
        if (duplicateAlert) duplicateAlert.style.display = 'none';
    }
    
    function checkNameDuplicate() {
        const currentName = nameInput?.value?.trim();
        
        if (duplicateAlert) duplicateAlert.style.display = 'none';
        if (nameValidAlert) nameValidAlert.style.display = 'none';
        
        if (currentName) {
            if (currentName.length < 2) {
                return;
            }
            
            if (usedNames.length > 0) {
                const isDuplicate = usedNames.some(name => 
                    name.toLowerCase() === currentName.toLowerCase()
                );
                
                if (isDuplicate) {
                    if (duplicateAlert) duplicateAlert.style.display = 'block';
                } else {
                    if (nameValidAlert) nameValidAlert.style.display = 'block';
                }
            } else {
                if (nameValidAlert) nameValidAlert.style.display = 'block';
            }
        }
    }
    
    if (academicYearSelect) {
        academicYearSelect.addEventListener('change', updateUsedNames);
    }
    
    if (ageGroupSelect) {
        ageGroupSelect.addEventListener('change', updateUsedNames);
    }
    
    if (nameInput) {
        nameInput.addEventListener('input', checkNameDuplicate);
    }
    
    // التحقق من صحة النموذج
    function validateForm() {
        const form = document.getElementById('createClassroomYearForm');
        const currentName = nameInput?.value?.trim();
        const formClassroomSelect = form.querySelector('select[name="classroom"]');
        const formAcademicYearSelect = form.querySelector('select[name="academic_year"]');
        const formAgeGroupSelect = form.querySelector('select[name="age_group"]');
        
        if (!formAcademicYearSelect?.value) {
            alert('يجب اختيار السنة الدراسية');
            return false;
        }
        
        if (!formAgeGroupSelect?.value) {
            alert('يجب اختيار الفئة العمرية');
            return false;
        }
        
        if (!formClassroomSelect?.value) {
            alert('يجب اختيار الفصل');
            return false;
        }
        
        if (currentName && usedNames.length > 0) {
            const isDuplicate = usedNames.some(name => 
                name.toLowerCase() === currentName.toLowerCase()
            );
            
            if (isDuplicate) {
                alert('لا يمكن استخدام هذا الاسم لأنه مستخدم بالفعل في فصل آخر لنفس الفئة العمرية');
                return false;
            }
        }
        
        if (currentName && currentName.length < 2) {
            alert('اسم الفصل يجب أن يكون على الأقل حرفين');
            return false;
        }
        
        const formCapacityInput = form.querySelector('input[name="capacity_for_year"]');
        
        if (formCapacityInput?.value && formClassroomSelect?.value) {
            const capacity = parseInt(formCapacityInput.value);
            const selectedOption = formClassroomSelect.options[formClassroomSelect.selectedIndex];
            const maxCapacity = parseInt(selectedOption.dataset.capacity);
            
            if (capacity > maxCapacity) {
                alert(`السعة المدخلة (${capacity}) تتجاوز السعة الأساسية للفصل (${maxCapacity})`);
                return false;
            }
        }
        
        return true;
    }
    
    // إرسال النموذج
    const form = document.getElementById('createClassroomYearForm');
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            
            if (!validateForm()) {
                return;
            }
            
            const formData = new FormData(this);
            const submitBtn = this.querySelector('button[type="submit"]');
            
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>جاري الإنشاء...';
            
            const createUrl = this.getAttribute('action') || '/academic/classroom-years/create/';
            
            fetch(createUrl, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => {
                if (!response.ok) {
                    return response.text().then(text => {
                        console.error('Server error response:', text);
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    });
                }
                
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    alert('تم إنشاء اسم الفصل بنجاح!');
                    
                    const modal = bootstrap.Modal.getInstance(document.getElementById('createClassroomYearModal'));
                    if (modal) {
                        modal.hide();
                    }
                    
                    setTimeout(() => {
                        location.reload();
                    }, 500);
                } else {
                    alert('خطأ: ' + (data.message || 'حدث خطأ غير معروف'));
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<i class="fas fa-save me-2"></i>إنشاء اسم الفصل';
                }
            })
            .catch(error => {
                console.error('💥 خطأ في الشبكة:', error);
                let errorMessage = 'حدث خطأ في العملية';
                if (error.message) {
                    errorMessage += ': ' + error.message;
                }
                alert(errorMessage);
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<i class="fas fa-save me-2"></i>إنشاء اسم الفصل';
            });
        });
    }
    
    // إرسال نموذج التعديل
    const editForm = document.getElementById('editClassroomYearForm');
    if (editForm) {
        editForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const classroomYearId = document.getElementById('editClassroomYearId').value;
            const formData = new FormData(this);
            const submitBtn = this.querySelector('button[type="submit"]');
            
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>جاري الحفظ...';
            
            fetch(`/academic/classroom-years/${classroomYearId}/update/`, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    location.reload();
                } else {
                    alert('خطأ: ' + data.message);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('حدث خطأ في العملية');
            })
            .finally(() => {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<i class="fas fa-save me-2"></i>حفظ التغييرات';
            });
        });
    }
    
    // تأكيد الحذف
    const confirmDeleteBtn = document.getElementById('confirmDeleteClassroomYear');
    if (confirmDeleteBtn) {
        confirmDeleteBtn.addEventListener('click', function() {
            const classroomYearId = this.getAttribute('data-id');
            
            this.disabled = true;
            this.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>جاري الحذف...';
            
            fetch(`/academic/classroom-years/${classroomYearId}/delete/`, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('تم حذف اسم الفصل بنجاح!');
                    location.reload();
                } else {
                    alert('خطأ: ' + data.message);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('حدث خطأ في العملية');
            })
            .finally(() => {
                this.disabled = false;
                this.innerHTML = '<i class="fas fa-trash me-2"></i>حذف نهائياً';
            });
        });
    }
});

// وظائف عامة للتعديل والحذف (خارج DOMContentLoaded)
function editClassroomYear(id, name, capacity, notes) {
    document.getElementById('editClassroomYearId').value = id;
    document.getElementById('editNameForYear').value = name || '';
    document.getElementById('editCapacityForYear').value = capacity || '';
    document.getElementById('editNotes').value = notes || '';
    
    const editModal = new bootstrap.Modal(document.getElementById('editClassroomYearModal'));
    editModal.show();
}

function deleteClassroomYear(id, name) {
    document.getElementById('deleteClassroomYearName').textContent = name;
    document.getElementById('confirmDeleteClassroomYear').setAttribute('data-id', id);
    
    const deleteModal = new bootstrap.Modal(document.getElementById('deleteClassroomYearModal'));
    deleteModal.show();
}
