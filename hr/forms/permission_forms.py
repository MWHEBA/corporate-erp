"""
نماذج الأذونات
"""
from django import forms
from ..models import PermissionRequest, PermissionType, Employee


class PermissionRequestForm(forms.ModelForm):
    """نموذج طلب إذن - نفس نمط LeaveRequestForm"""
    
    # إضافة حقل اختيار الموظف (للـ HR فقط)
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.filter(status='active'),
        label='الموظف',
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True
    )
    
    class Meta:
        model = PermissionRequest
        fields = ['employee', 'permission_type', 'date', 'start_time', 'end_time', 'reason', 'is_emergency']
        widgets = {
            'permission_type': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'اذكر سبب الإذن...'}),
            'is_emergency': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'employee': 'الموظف',
            'permission_type': 'نوع الإذن',
            'date': 'التاريخ',
            'start_time': 'وقت البداية',
            'end_time': 'وقت النهاية',
            'reason': 'السبب',
            'is_emergency': 'ظرف طارئ',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # فقط الأنواع النشطة
        self.fields['permission_type'].queryset = PermissionType.objects.filter(is_active=True)
    
    def clean(self):
        """التحقق - نفس نمط LeaveRequestForm.clean()"""
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        
        if start_time and end_time:
            if end_time <= start_time:
                raise forms.ValidationError('وقت النهاية يجب أن يكون بعد وقت البداية')
        
        return cleaned_data
