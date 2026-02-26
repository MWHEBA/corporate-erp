"""
Permissions لوحدة الموارد البشرية
Phase 3: Enhanced with Authority Service integration
"""
from rest_framework import permissions
from governance.services.authority_service import AuthorityService
import logging

logger = logging.getLogger(__name__)


class IsHRManager(permissions.BasePermission):
    """
    صلاحية مدير الموارد البشرية
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser or
            hasattr(request.user, 'employee') and 
            request.user.employee.job_title.code in ['HR-MGR', 'HR-DIR']
        )


class IsHRStaff(permissions.BasePermission):
    """
    صلاحية موظف الموارد البشرية
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser or
            hasattr(request.user, 'employee') and 
            request.user.employee.department.code == 'HR'
        )


class IsEmployeeOrHR(permissions.BasePermission):
    """
    صلاحية الموظف نفسه أو موظف HR
    """
    def has_object_permission(self, request, view, obj):
        # السماح للموظف بعرض بياناته
        if hasattr(request.user, 'employee') and obj == request.user.employee:
            return True
        
        # السماح لموظفي HR
        if request.user.is_superuser:
            return True
            
        if hasattr(request.user, 'employee'):
            return request.user.employee.department.code == 'HR'
        
        return False


class CanApproveLeave(permissions.BasePermission):
    """
    صلاحية اعتماد الإجازات
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser or
            hasattr(request.user, 'employee') and (
                request.user.employee.department.code == 'HR' or
                request.user.employee.is_manager
            )
        )


class CanProcessPayroll(permissions.BasePermission):
    """
    صلاحية معالجة الرواتب
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser or
            hasattr(request.user, 'employee') and 
            request.user.employee.job_title.code in ['HR-MGR', 'HR-DIR', 'FIN-MGR']
        )


class CanViewAttendance(permissions.BasePermission):
    """
    صلاحية عرض الحضور
    """
    def has_permission(self, request, view):
        # الجميع يمكنهم عرض حضورهم
        return request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # الموظف يمكنه عرض حضوره فقط
        if hasattr(request.user, 'employee') and obj.employee == request.user.employee:
            return True
        
        # HR يمكنهم عرض الجميع
        if request.user.is_superuser:
            return True
            
        if hasattr(request.user, 'employee'):
            return request.user.employee.department.code == 'HR'
        
        return False


class CanManageDepartment(permissions.BasePermission):
    """
    صلاحية إدارة الأقسام
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser or
            hasattr(request.user, 'employee') and 
            request.user.employee.job_title.code in ['HR-MGR', 'HR-DIR', 'CEO']
        )


class IsDirectManager(permissions.BasePermission):
    """
    صلاحية المدير المباشر
    """
    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        
        if hasattr(request.user, 'employee'):
            # المدير المباشر
            if hasattr(obj, 'direct_manager') and obj.direct_manager == request.user.employee:
                return True
            
            # مدير القسم
            if hasattr(obj, 'department') and obj.department.manager == request.user.employee:
                return True
        
        return False


class CanRequestAdvance(permissions.BasePermission):
    """
    صلاحية طلب سلفة
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # يجب أن يكون موظفاً
        if not hasattr(request.user, 'employee'):
            return False
        
        # يجب أن يكون نشطاً
        return request.user.employee.status == 'active'


class CanTerminateEmployee(permissions.BasePermission):
    """
    صلاحية إنهاء خدمة الموظفين - مع التحقق من Authority Service
    Issue #1: Missing API permissions
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # Validate through governance Authority Service
        try:
            is_authorized = AuthorityService.validate_authority(
                service_name='EmployeeAPI',
                model_name='Employee',
                operation='TERMINATE'
            )
            
            if not is_authorized:
                logger.warning(
                    f"User {request.user.username} attempted to terminate employee without authority"
                )
                return False
            
            # Additional HR-specific check
            if request.user.is_superuser:
                return True
            
            if hasattr(request.user, 'employee'):
                return request.user.employee.job_title.code in ['HR-MGR', 'HR-DIR', 'CEO']
            
            return False
            
        except Exception as e:
            logger.error(f"Authority validation error: {e}")
            return False


class CanViewSensitiveData(permissions.BasePermission):
    """
    صلاحية عرض البيانات الحساسة (الرقم القومي، الهاتف، البريد الشخصي)
    Issue #4: Exposed sensitive data
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # Only HR managers and directors can view full sensitive data
        if request.user.is_superuser:
            return True
        
        if hasattr(request.user, 'employee'):
            return request.user.employee.job_title.code in ['HR-MGR', 'HR-DIR']
        
        return False
    
    def has_object_permission(self, request, view, obj):
        # Employee can view their own data
        if hasattr(request.user, 'employee') and obj == request.user.employee:
            return True
        
        # HR managers can view all
        return self.has_permission(request, view)
