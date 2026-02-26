"""
مصانع بيانات الاختبار - Test Data Factories
"""

# استيراد المصانع البسيطة فقط لتجنب مشاكل النماذج غير الموجودة
try:
    from .simple_factories import (
        SimpleUserFactory,
        SimpleAcademicYearFactory,
        SimpleAgeGroupFactory,
        SimpleParentFactory,
        SimpleStudentFactory,
        create_simple_academic_year,
        create_simple_student,
        create_simple_parent,
        create_simple_batch,
        ARABIC_FIRST_NAMES_MALE,
        ARABIC_FIRST_NAMES_FEMALE,
        ARABIC_LAST_NAMES,
        ARABIC_CITIES
    )
    
    # إعادة تسمية للتوافق مع الكود الموجود
    UserFactory = SimpleUserFactory
    AcademicYearFactory = SimpleAcademicYearFactory
    AgeGroupFactory = SimpleAgeGroupFactory
    ParentFactory = SimpleParentFactory
    StudentFactory = SimpleStudentFactory
    
    create_test_academic_year = create_simple_academic_year
    create_test_student = create_simple_student
    create_test_parent = create_simple_parent
    create_test_batch = create_simple_batch
    
except ImportError as e:
    print(f"تحذير: فشل في استيراد المصانع البسيطة: {e}")
    
    # مصانع وهمية لتجنب أخطاء الاستيراد
    class DummyFactory:
        @classmethod
        def create(cls, **kwargs):
            raise NotImplementedError("المصنع غير متاح")
    
    UserFactory = DummyFactory
    AcademicYearFactory = DummyFactory
    AgeGroupFactory = DummyFactory
    ParentFactory = DummyFactory
    StudentFactory = DummyFactory

# قائمة المصانع المتاحة
__all__ = [
    'UserFactory',
    'AcademicYearFactory',
    'AgeGroupFactory',
    'ParentFactory',
    'StudentFactory',
    'create_test_academic_year',
    'create_test_student',
    'create_test_parent',
    'create_test_batch',
    'ARABIC_FIRST_NAMES_MALE',
    'ARABIC_FIRST_NAMES_FEMALE',
    'ARABIC_LAST_NAMES',
    'ARABIC_CITIES'
]

# دوال مساعدة سريعة
def quick_setup(scenario='basic_school'):
    """إعداد سريع لبيئة الاختبار"""
    if scenario == 'basic_school':
        return create_test_batch(5)
    else:
        raise NotImplementedError(f"السيناريو {scenario} غير متاح")

def quick_cleanup():
    """تنظيف سريع لبيانات الاختبار"""
    try:
        from .data_cleanup import cleanup_test_data
        return cleanup_test_data()
    except ImportError:
        print("تحذير: نظام التنظيف غير متاح")
        return {}

def quick_stats():
    """إحصائيات سريعة لبيانات الاختبار"""
    try:
        from .data_cleanup import get_test_data_stats
        return get_test_data_stats()
    except ImportError:
        print("تحذير: نظام الإحصائيات غير متاح")
        return {}