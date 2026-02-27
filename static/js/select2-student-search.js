/**
 * تحسينات Select2 للبحث في الطلاب
 */

function initializeStudentSelect2(selector, ajaxUrl) {
    $(selector).select2({
        theme: 'bootstrap-5',
        dir: 'rtl',
        placeholder: 'ابحث عن الطالب...',
        allowClear: true,
        width: '100%',
        ajax: {
            url: ajaxUrl,
            dataType: 'json',
            delay: 250,
            data: function (params) {
                return {
                    q: params.term,
                    page: params.page || 1
                };
            },
            processResults: function (data, params) {
                params.page = params.page || 1;
                return {
                    results: data.results,
                    pagination: {
                        more: data.pagination.more
                    }
                };
            },
            cache: true
        },
        language: {
            noResults: function() {
                return '<div class="text-center p-3"><i class="fas fa-search text-muted mb-2"></i><br>لا توجد نتائج مطابقة</div>';
            },
            searching: function() {
                return "جاري البحث...";
            },
            inputTooShort: function() {
                return "اكتب حرفين على الأقل للبحث";
            },
            loadingMore: function() {
                return "جاري تحميل المزيد...";
            }
        },
        minimumInputLength: 2,
        escapeMarkup: function (markup) {
            return markup;
        },
        templateResult: function(data) {
            if (data.loading) {
                return data.text;
            }
            
            let html = '<div class="select2-result-student">';
            html += '<i class="fas fa-user-graduate me-2 text-primary"></i>';
            html += '<div class="student-details">';
            html += '<div class="student-name">' + (data.name || data.text) + '</div>';
            
            if (data.code) {
                html += '<small class="text-muted">كود: ' + data.code + '</small>';
            }
            
            if (data.parent_name) {
                html += '<small class="text-muted ms-2">العميل: ' + data.parent_name + '</small>';
            }
            
            html += '</div></div>';
            return html;
        },
        templateSelection: function(data) {
            if (data.name) {
                return data.name + (data.code ? ' (' + data.code + ')' : '');
            }
            return data.text;
        }
    });
}

function setupStudentSelectEvents(selector, studentInfoCallback) {
    // Load student info when student is selected
    $(selector).on('select2:select', function(e) {
        const data = e.params.data;
        if (data.id && studentInfoCallback) {
            studentInfoCallback(data);
        }
    });
    
    $(selector).on('select2:clear', function() {
        if (studentInfoCallback) {
            studentInfoCallback(null);
        }
    });
}

function setupKeyboardShortcuts(selector) {
    // إضافة اختصارات لوحة المفاتيح
    $(document).keydown(function(e) {
        // Ctrl + F للتركيز على حقل البحث
        if (e.ctrlKey && e.keyCode === 70) {
            e.preventDefault();
            $(selector).select2('open');
        }
        
        // Escape لإغلاق Select2
        if (e.keyCode === 27) {
            $(selector).select2('close');
        }
    });
}