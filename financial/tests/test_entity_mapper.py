"""
اختبارات خدمة EntityAccountMapper
"""

import pytest
from django.test import TestCase
from financial.services.entity_mapper import EntityAccountMapper


class TestEntityAccountMapper(TestCase):
    """اختبارات خدمة ربط الكيانات بالحسابات المحاسبية"""
    
    def test_entity_account_fields_defined(self):
        """اختبار أن قاموس ENTITY_ACCOUNT_FIELDS محدد بشكل صحيح"""
        # التحقق من وجود القاموس
        self.assertIsNotNone(EntityAccountMapper.ENTITY_ACCOUNT_FIELDS)
        
        # التحقق من وجود الأنواع الأساسية
        expected_types = ['student', 'supplier', 'employee', 'activity', 'transportation_route', 'bus', 'parent', 'fee_type']
        for entity_type in expected_types:
            self.assertIn(entity_type, EntityAccountMapper.ENTITY_ACCOUNT_FIELDS)
    
    def test_model_to_entity_type_mapping(self):
        """اختبار أن خريطة MODEL_TO_ENTITY_TYPE محددة بشكل صحيح"""
        # التحقق من وجود الخريطة
        self.assertIsNotNone(EntityAccountMapper.MODEL_TO_ENTITY_TYPE)
        
        # التحقق من وجود النماذج الأساسية
        expected_models = ['Student', 'Supplier', 'Employee', 'Activity', 'Bus', 'Parent', 'FeeType']
        for model_name in expected_models:
            self.assertIn(model_name, EntityAccountMapper.MODEL_TO_ENTITY_TYPE)
    
    def test_get_supported_entity_types(self):
        """اختبار الحصول على قائمة أنواع الكيانات المدعومة"""
        supported_types = EntityAccountMapper.get_supported_entity_types()
        
        # التحقق من أن القائمة ليست فارغة
        self.assertGreater(len(supported_types), 0)
        
        # التحقق من وجود الأنواع الأساسية
        self.assertIn('student', supported_types)
        self.assertIn('supplier', supported_types)
        self.assertIn('parent', supported_types)
    
    def test_is_entity_type_supported(self):
        """اختبار التحقق من دعم نوع كيان معين"""
        # أنواع مدعومة
        self.assertTrue(EntityAccountMapper.is_entity_type_supported('student'))
        self.assertTrue(EntityAccountMapper.is_entity_type_supported('supplier'))
        self.assertTrue(EntityAccountMapper.is_entity_type_supported('parent'))
        self.assertTrue(EntityAccountMapper.is_entity_type_supported('fee_type'))
        
        # أنواع غير مدعومة
        self.assertFalse(EntityAccountMapper.is_entity_type_supported('unknown'))
        self.assertFalse(EntityAccountMapper.is_entity_type_supported('invalid_type'))
    
    def test_detect_entity_type_with_none(self):
        """اختبار استنتاج نوع الكيان مع None"""
        entity_type = EntityAccountMapper.detect_entity_type(None)
        self.assertIsNone(entity_type)
    
    def test_get_account_with_none_entity(self):
        """اختبار الحصول على الحساب المحاسبي مع كيان None"""
        account = EntityAccountMapper.get_account(None)
        self.assertIsNone(account)
    
    def test_validate_entity_account_with_none(self):
        """اختبار التحقق من الحساب المحاسبي مع كيان None"""
        is_valid, message = EntityAccountMapper.validate_entity_account(None)
        self.assertFalse(is_valid)
        self.assertEqual(message, "الكيان غير موجود")
    
    def test_get_entity_info_structure(self):
        """اختبار بنية معلومات الكيان"""
        # اختبار مع None
        info = EntityAccountMapper.get_entity_info(None)
        
        # التحقق من وجود المفاتيح المطلوبة
        expected_keys = ['entity', 'entity_type', 'entity_name', 'model_name', 'account', 'account_field_path', 'has_account']
        for key in expected_keys:
            self.assertIn(key, info)
        
        # التحقق من القيم مع None
        self.assertIsNone(info['entity'])
        self.assertIsNone(info['entity_type'])
        self.assertIsNone(info['account'])
        self.assertFalse(info['has_account'])


class TestEntityAccountMapperIntegration(TestCase):
    """اختبارات التكامل لخدمة EntityAccountMapper"""
    
    def setUp(self):
        """إعداد بيانات الاختبار"""
        from financial.models import ChartOfAccounts, AccountType
        from client.models import Customer  # Changed from students.models.Parent
        from supplier.models import Supplier
        
        # إنشاء نوع حساب
        self.account_type = AccountType.objects.create(
            code='1000',
            name='أصول',
            category='asset'
        )
        
        # إنشاء حساب محاسبي
        self.chart_account = ChartOfAccounts.objects.create(
            code='1001',
            name='حساب اختبار',
            account_type=self.account_type,
            is_active=True,
            is_leaf=True
        )
        
        # إنشاء ولي أمر مع حساب محاسبي
        self.parent_with_account = Parent.objects.create(
            name='أحمد محمد',
            national_id='12345678901234',
            phone_primary='01234567890',
            financial_account=self.chart_account
        )
        
        # إنشاء ولي أمر بدون حساب محاسبي
        self.parent_without_account = Parent.objects.create(
            name='محمد علي',
            national_id='12345678901235',
            phone_primary='01234567891'
        )
        
        # إنشاء مورد مع حساب محاسبي
        self.supplier_with_account = Supplier.objects.create(
            name='مورد اختبار',
            code='SUP001',
            phone='01234567892',
            financial_account=self.chart_account
        )
    
    def test_detect_entity_type_parent(self):
        """اختبار استنتاج نوع الكيان لالعميل"""
        entity_type = EntityAccountMapper.detect_entity_type(self.parent_with_account)
        self.assertEqual(entity_type, 'parent')
    
    def test_detect_entity_type_supplier(self):
        """اختبار استنتاج نوع الكيان للمورد"""
        entity_type = EntityAccountMapper.detect_entity_type(self.supplier_with_account)
        self.assertEqual(entity_type, 'supplier')
    
    def test_get_account_parent_with_account(self):
        """اختبار الحصول على الحساب المحاسبي لولي أمر لديه حساب"""
        account = EntityAccountMapper.get_account(self.parent_with_account, 'parent')
        self.assertIsNotNone(account)
        self.assertEqual(account, self.chart_account)
    
    def test_get_account_parent_without_account(self):
        """اختبار الحصول على الحساب المحاسبي لولي أمر ليس لديه حساب"""
        account = EntityAccountMapper.get_account(self.parent_without_account, 'parent')
        self.assertIsNone(account)
    
    def test_get_account_supplier_with_account(self):
        """اختبار الحصول على الحساب المحاسبي لمورد لديه حساب"""
        account = EntityAccountMapper.get_account(self.supplier_with_account, 'supplier')
        self.assertIsNotNone(account)
        self.assertEqual(account, self.chart_account)
    
    def test_get_account_with_auto_detection(self):
        """اختبار الحصول على الحساب المحاسبي مع الاستنتاج التلقائي"""
        # بدون تحديد نوع الكيان
        account = EntityAccountMapper.get_account(self.parent_with_account)
        self.assertIsNotNone(account)
        self.assertEqual(account, self.chart_account)
    
    def test_validate_entity_account_parent_with_account(self):
        """اختبار التحقق من الحساب المحاسبي لولي أمر لديه حساب"""
        is_valid, message = EntityAccountMapper.validate_entity_account(self.parent_with_account)
        self.assertTrue(is_valid)
        self.assertIn("موجود وصحيح", message)
    
    def test_validate_entity_account_parent_without_account(self):
        """اختبار التحقق من الحساب المحاسبي لولي أمر ليس لديه حساب"""
        is_valid, message = EntityAccountMapper.validate_entity_account(self.parent_without_account)
        self.assertFalse(is_valid)
        self.assertIn("لا يوجد حساب محاسبي", message)
    
    def test_get_entity_info_parent(self):
        """اختبار الحصول على معلومات الكيان لالعميل"""
        info = EntityAccountMapper.get_entity_info(self.parent_with_account)
        
        # التحقق من البيانات
        self.assertEqual(info['entity'], self.parent_with_account)
        self.assertEqual(info['entity_type'], 'parent')
        self.assertEqual(info['model_name'], 'Parent')
        self.assertEqual(info['account'], self.chart_account)
        self.assertEqual(info['account_field_path'], 'financial_account')
        self.assertTrue(info['has_account'])

    # DEPRECATED: FeeType tests are no longer supported
    # These tests were part of the school management system
    
    # def test_detect_entity_type_fee_type(self):
    #     """DEPRECATED: FeeType is no longer used"""
    #     pass
    
    # def test_get_account_fee_type_revenue(self):
    #     """DEPRECATED: FeeType is no longer used"""
    #     pass
    
    # def test_get_fee_type_accounts(self):
    #     """DEPRECATED: FeeType is no longer used"""
    #     pass
    
    # def test_validate_entity_account_fee_type(self):
    #     """DEPRECATED: FeeType is no longer used"""
    #     pass
