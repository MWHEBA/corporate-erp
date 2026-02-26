"""
Management command to migrate from heavy business logic signals to thin adapter signals.

This command provides a safe migration path with feature flags and rollback capability.
It follows the governance principles of gradual activation with monitoring.

Usage:
    python manage.py migrate_signals_to_thin_adapters --phase=prepare
    python manage.py migrate_signals_to_thin_adapters --phase=enable
    python manage.py migrate_signals_to_thin_adapters --phase=validate
    python manage.py migrate_signals_to_thin_adapters --phase=rollback
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from governance.services import governance_switchboard, signal_router, AuditService
from governance.models import GovernanceContext

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Migrate from heavy business logic signals to thin adapter signals with feature flag protection'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--phase',
            type=str,
            choices=['prepare', 'enable', 'validate', 'rollback', 'status'],
            required=True,
            help='Migration phase to execute'
        )
        
        parser.add_argument(
            '--workflow',
            type=str,
            choices=[
                'student_fee_to_journal_entry',
                'fee_payment_to_journal_entry', 
                'stock_movement_to_journal_entry',
                'transportation_fee_to_journal_entry',
                'all'
            ],
            default='all',
            help='Specific workflow to migrate (default: all)'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force operation even if validation fails'
        )
    
    def handle(self, *args, **options):
        phase = options['phase']
        workflow = options['workflow']
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write(
            self.style.SUCCESS(f'🚀 Starting signal migration - Phase: {phase}, Workflow: {workflow}')
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made'))
        
        try:
            with transaction.atomic():
                # Set governance context
                GovernanceContext.set_context(
                    user=None,  # System operation
                    service='SignalMigrationCommand',
                    operation=f'migrate_signals_{phase}'
                )
                
                if phase == 'prepare':
                    self._prepare_migration(workflow, dry_run)
                elif phase == 'enable':
                    self._enable_thin_adapters(workflow, dry_run, force)
                elif phase == 'validate':
                    self._validate_migration(workflow)
                elif phase == 'rollback':
                    self._rollback_migration(workflow, dry_run)
                elif phase == 'status':
                    self._show_migration_status(workflow)
                
                # Create audit trail
                if not dry_run:
                    AuditService.log_operation(
                        model_name='SignalMigration',
                        object_id=0,
                        operation=f'MIGRATION_{phase.upper()}',
                        source_service='SignalMigrationCommand',
                        user=None,
                        workflow=workflow,
                        phase=phase
                    )
                
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Signal migration {phase} completed successfully')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Signal migration {phase} failed: {e}')
            )
            raise CommandError(f'Migration failed: {e}')
            
        finally:
            GovernanceContext.clear_context()
    
    def _prepare_migration(self, workflow: str, dry_run: bool):
        """Prepare for signal migration by setting up infrastructure"""
        self.stdout.write('📋 Preparing signal migration infrastructure...')
        
        # 1. Validate governance infrastructure
        self._validate_governance_infrastructure()
        
        # 2. Register thin adapter signals
        self._register_thin_adapter_signals(dry_run)
        
        # 3. Initialize feature flags (disabled by default)
        self._initialize_feature_flags(workflow, dry_run)
        
        # 4. Validate signal independence
        if not dry_run:
            self._test_signal_independence()
        
        self.stdout.write('✅ Migration preparation completed')
    
    def _enable_thin_adapters(self, workflow: str, dry_run: bool, force: bool):
        """Enable thin adapter signals with gradual activation"""
        self.stdout.write('🔄 Enabling thin adapter signals...')
        
        # 1. Validate readiness
        if not force:
            self._validate_migration_readiness(workflow)
        
        # 2. Enable workflow flags gradually
        workflows_to_enable = self._get_workflows_to_migrate(workflow)
        
        for wf in workflows_to_enable:
            self.stdout.write(f'  🔧 Enabling workflow: {wf}')
            
            if not dry_run:
                governance_switchboard.enable_workflow(wf)
                
                # Wait a moment for monitoring
                import time
                time.sleep(1)
                
                # Check for immediate issues
                stats = signal_router.get_signal_statistics()
                if stats['counters']['signal_errors'] > 0:
                    self.stdout.write(
                        self.style.WARNING(f'⚠️  Signal errors detected for {wf}: {stats["counters"]["signal_errors"]}')
                    )
        
        # 3. Enable component flags
        components_to_enable = self._get_components_to_enable(workflow)
        
        for component in components_to_enable:
            self.stdout.write(f'  🔧 Enabling component: {component}')
            
            if not dry_run:
                governance_switchboard.enable_component(component)
        
        self.stdout.write('✅ Thin adapter signals enabled')
    
    def _validate_migration(self, workflow: str):
        """Validate that migration is working correctly"""
        self.stdout.write('🔍 Validating signal migration...')
        
        validation_results = {
            'signal_router_health': False,
            'workflow_flags_active': False,
            'signal_independence': False,
            'orchestrator_services': False,
            'audit_trails': False
        }
        
        # 1. Check signal router health
        try:
            stats = signal_router.get_signal_statistics()
            validation_results['signal_router_health'] = stats['global_enabled']
            self.stdout.write(f'  📊 Signal router health: {"✅" if stats["global_enabled"] else "❌"}')
            self.stdout.write(f'     Signals processed: {stats["counters"]["signals_processed"]}')
            self.stdout.write(f'     Signals blocked: {stats["counters"]["signals_blocked"]}')
            self.stdout.write(f'     Signal errors: {stats["counters"]["signal_errors"]}')
        except Exception as e:
            self.stdout.write(f'  ❌ Signal router health check failed: {e}')
        
        # 2. Check workflow flags
        workflows = self._get_workflows_to_migrate(workflow)
        active_workflows = 0
        
        for wf in workflows:
            is_active = governance_switchboard.is_workflow_enabled(wf)
            if is_active:
                active_workflows += 1
            self.stdout.write(f'  🚩 Workflow {wf}: {"✅" if is_active else "❌"}')
        
        validation_results['workflow_flags_active'] = active_workflows > 0
        
        # 3. Test signal independence
        try:
            independence_result = self._test_signal_independence()
            validation_results['signal_independence'] = independence_result
            self.stdout.write(f'  🔒 Signal independence: {"✅" if independence_result else "❌"}')
        except Exception as e:
            self.stdout.write(f'  ❌ Signal independence test failed: {e}')
        
        # 4. Check orchestrator services
        try:
            orchestrator_result = self._test_orchestrator_services(workflow)
            validation_results['orchestrator_services'] = orchestrator_result
            self.stdout.write(f'  🎯 Orchestrator services: {"✅" if orchestrator_result else "❌"}')
        except Exception as e:
            self.stdout.write(f'  ❌ Orchestrator services test failed: {e}')
        
        # 5. Check audit trails
        try:
            audit_result = self._test_audit_trails()
            validation_results['audit_trails'] = audit_result
            self.stdout.write(f'  📝 Audit trails: {"✅" if audit_result else "❌"}')
        except Exception as e:
            self.stdout.write(f'  ❌ Audit trails test failed: {e}')
        
        # Overall validation result
        all_passed = all(validation_results.values())
        
        if all_passed:
            self.stdout.write('✅ All validation checks passed')
        else:
            failed_checks = [k for k, v in validation_results.items() if not v]
            self.stdout.write(
                self.style.WARNING(f'⚠️  Some validation checks failed: {", ".join(failed_checks)}')
            )
        
        return all_passed
    
    def _rollback_migration(self, workflow: str, dry_run: bool):
        """Rollback to old signal system"""
        self.stdout.write('🔄 Rolling back signal migration...')
        
        # 1. Disable workflow flags
        workflows_to_disable = self._get_workflows_to_migrate(workflow)
        
        for wf in workflows_to_disable:
            self.stdout.write(f'  🔧 Disabling workflow: {wf}')
            
            if not dry_run:
                governance_switchboard.disable_workflow(wf, 'Migration rollback')
        
        # 2. Disable component flags
        components_to_disable = self._get_components_to_enable(workflow)
        
        for component in components_to_disable:
            self.stdout.write(f'  🔧 Disabling component: {component}')
            
            if not dry_run:
                governance_switchboard.disable_component(component, 'Migration rollback')
        
        # 3. Verify rollback
        if not dry_run:
            import time
            time.sleep(2)  # Wait for changes to take effect
            
            # Check that workflows are disabled
            for wf in workflows_to_disable:
                is_enabled = governance_switchboard.is_workflow_enabled(wf)
                if is_enabled:
                    self.stdout.write(
                        self.style.ERROR(f'❌ Failed to disable workflow: {wf}')
                    )
                else:
                    self.stdout.write(f'  ✅ Workflow disabled: {wf}')
        
        self.stdout.write('✅ Signal migration rollback completed')
    
    def _show_migration_status(self, workflow: str):
        """Show current migration status"""
        self.stdout.write('📊 Signal Migration Status Report')
        self.stdout.write('=' * 50)
        
        # 1. Governance switchboard status
        try:
            stats = governance_switchboard.get_governance_statistics()
            self.stdout.write(f'🎛️  Governance Switchboard:')
            self.stdout.write(f'   Components active: {stats.get("components", {}).get("enabled", 0)}/{stats.get("components", {}).get("total", 0)}')
            self.stdout.write(f'   Workflows active: {stats.get("workflows", {}).get("enabled", 0)}/{stats.get("workflows", {}).get("total", 0)}')
            self.stdout.write(f'   Emergency flags: {stats.get("emergency", {}).get("active", 0)}')
        except Exception as e:
            self.stdout.write(f'❌ Failed to get switchboard status: {e}')
        
        # 2. Signal router status
        try:
            stats = signal_router.get_signal_statistics()
            self.stdout.write(f'\n📡 Signal Router:')
            self.stdout.write(f'   Global enabled: {stats["global_enabled"]}')
            self.stdout.write(f'   Maintenance mode: {stats["maintenance_mode"]}')
            self.stdout.write(f'   Signals processed: {stats["counters"]["signals_processed"]}')
            self.stdout.write(f'   Signals blocked: {stats["counters"]["signals_blocked"]}')
            self.stdout.write(f'   Signal errors: {stats["counters"]["signal_errors"]}')
            self.stdout.write(f'   Disabled signals: {len(stats["disabled_signals"])}')
        except Exception as e:
            self.stdout.write(f'❌ Failed to get signal router status: {e}')
        
        # 3. Workflow-specific status
        workflows = self._get_workflows_to_migrate(workflow)
        self.stdout.write(f'\n🚩 Workflow Status:')
        
        for wf in workflows:
            try:
                is_enabled = governance_switchboard.is_workflow_enabled(wf)
                status = "✅ ENABLED" if is_enabled else "❌ DISABLED"
                self.stdout.write(f'   {wf}: {status}')
            except Exception as e:
                self.stdout.write(f'   {wf}: ❌ ERROR - {e}')
        
        # 4. Component status
        components = self._get_components_to_enable(workflow)
        self.stdout.write(f'\n🔧 Component Status:')
        
        for component in components:
            try:
                is_enabled = governance_switchboard.is_component_enabled(component)
                status = "✅ ENABLED" if is_enabled else "❌ DISABLED"
                self.stdout.write(f'   {component}: {status}')
            except Exception as e:
                self.stdout.write(f'   {component}: ❌ ERROR - {e}')
    
    def _validate_governance_infrastructure(self):
        """Validate that governance infrastructure is ready"""
        self.stdout.write('  🔍 Validating governance infrastructure...')
        
        # Check governance switchboard
        try:
            stats = governance_switchboard.get_governance_statistics()
            if not stats.get('health', {}).get('governance_active', False):
                raise CommandError('Governance switchboard is not active')
        except Exception as e:
            raise CommandError(f'Governance switchboard validation failed: {e}')
        
        # Check signal router
        try:
            stats = signal_router.get_signal_statistics()
            if not stats['global_enabled']:
                raise CommandError('Signal router is not enabled')
        except Exception as e:
            raise CommandError(f'Signal router validation failed: {e}')
        
        # Check audit service
        try:
            from governance.services.audit_service import AuditService
            # Test audit service is working
            AuditService.log_operation(
                model_name='ValidationTest',
                object_id=0,
                operation='INFRASTRUCTURE_CHECK',
                source_service='SignalMigrationCommand',
                user=None
            )
        except Exception as e:
            raise CommandError(f'Audit service validation failed: {e}')
        
        self.stdout.write('  ✅ Governance infrastructure validated')
    
    def _register_thin_adapter_signals(self, dry_run: bool):
        """Register thin adapter signals with the signal router"""
        self.stdout.write('  📝 Registering thin adapter signals...')
        
        if not dry_run:
            try:
                # Student signals removed - no longer part of Corporate ERP
                
                # Register product signals
                from product.signals.thin_adapter_signals import register_thin_adapter_signals as register_product_signals
                register_product_signals()
                
                # Transportation signals removed - no longer part of Corporate ERP
                
                self.stdout.write('  ✅ Thin adapter signals registered')
                
            except Exception as e:
                raise CommandError(f'Failed to register thin adapter signals: {e}')
        else:
            self.stdout.write('  🔍 [DRY RUN] Would register thin adapter signals')
    
    def _initialize_feature_flags(self, workflow: str, dry_run: bool):
        """Initialize feature flags (disabled by default for safety)"""
        self.stdout.write('  🚩 Initializing feature flags...')
        
        workflows = self._get_workflows_to_migrate(workflow)
        components = self._get_components_to_enable(workflow)
        
        if not dry_run:
            # Ensure all flags are disabled initially for safety
            for wf in workflows:
                governance_switchboard.disable_workflow(wf, 'Initial migration setup')
            
            for component in components:
                governance_switchboard.disable_component(component, 'Initial migration setup')
            
            self.stdout.write('  ✅ Feature flags initialized (disabled for safety)')
        else:
            self.stdout.write('  🔍 [DRY RUN] Would initialize feature flags')
    
    def _test_signal_independence(self) -> bool:
        """Test that write operations work with signals disabled"""
        self.stdout.write('  🔒 Testing signal independence...')
        
        try:
            # Test with all signals disabled
            with signal_router.signals_disabled("Migration independence test"):
                # Test basic model operations
                from product.models import Product
                
                # These operations should work without signals
                test_product = Product.objects.first()
                
                # Student model removed - no longer part of Corporate ERP
                
                if test_product:
                    test_student.name = f"{original_name}_test"
                    test_student.save()
                    test_student.name = original_name
                    test_student.save()
                
                if test_product:
                    # Test product update
                    original_name = test_product.name
                    test_product.name = f"{original_name}_test"
                    test_product.save()
                    test_product.name = original_name
                    test_product.save()
            
            self.stdout.write('  ✅ Signal independence test passed')
            return True
            
        except Exception as e:
            self.stdout.write(f'  ❌ Signal independence test failed: {e}')
            return False
    
    def _test_orchestrator_services(self, workflow: str) -> bool:
        """Test that orchestrator services are working"""
        self.stdout.write('  🎯 Testing orchestrator services...')
        
        try:
            # Test service imports
            # Student and transportation services removed - no longer part of Corporate ERP
            
            # ✅ استبدال StockOrchestrator بـ MovementService
            if workflow in ['stock_movement_to_journal_entry', 'all']:
                from governance.services import MovementService
                # Test MovementService is available
                assert hasattr(MovementService, 'process_movement')
            
            # Transportation services removed - no longer part of Corporate ERP
            
            self.stdout.write('  ✅ Orchestrator services test passed')
            return True
            
        except Exception as e:
            self.stdout.write(f'  ❌ Orchestrator services test failed: {e}')
            return False
    
    def _test_audit_trails(self) -> bool:
        """Test that audit trails are working"""
        self.stdout.write('  📝 Testing audit trails...')
        
        try:
            # Test audit service
            AuditService.log_operation(
                model_name='MigrationTest',
                object_id=0,
                operation='AUDIT_TEST',
                source_service='SignalMigrationCommand',
                user=None
            )
            
            self.stdout.write('  ✅ Audit trails test passed')
            return True
            
        except Exception as e:
            self.stdout.write(f'  ❌ Audit trails test failed: {e}')
            return False
    
    def _validate_migration_readiness(self, workflow: str):
        """Validate that system is ready for migration"""
        self.stdout.write('  🔍 Validating migration readiness...')
        
        # Check that governance infrastructure is healthy
        self._validate_governance_infrastructure()
        
        # Check that orchestrator services are available
        if not self._test_orchestrator_services(workflow):
            raise CommandError('Orchestrator services are not ready')
        
        # Check that audit trails are working
        if not self._test_audit_trails():
            raise CommandError('Audit trails are not working')
        
        self.stdout.write('  ✅ Migration readiness validated')
    
    def _get_workflows_to_migrate(self, workflow: str) -> list:
        """Get list of workflows to migrate based on selection"""
        if workflow == 'all':
            return [
                'student_fee_to_journal_entry',
                'fee_payment_to_journal_entry',
                'stock_movement_to_journal_entry',
                'transportation_fee_to_journal_entry'
            ]
        else:
            return [workflow]
    
    def _get_components_to_enable(self, workflow: str) -> list:
        """Get list of components to enable based on workflow selection"""
        components = []
        
        if workflow in ['student_fee_to_journal_entry', 'fee_payment_to_journal_entry', 'all']:
            components.extend(['auto_fee_creation', 'auto_account_creation'])
        
        if workflow in ['stock_movement_to_journal_entry', 'all']:
            components.extend(['auto_sku_generation', 'auto_image_management'])
        
        if workflow in ['transportation_fee_to_journal_entry', 'all']:
            components.extend(['bus_deletion_protection'])
        
        return list(set(components))  # Remove duplicates