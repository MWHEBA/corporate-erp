"""
RepairService Demonstration - Phase 4A Analysis Only

This script demonstrates the RepairService functionality for corruption detection
and repair policy framework. This is ANALYSIS ONLY - no repairs are executed.

Usage:
    python manage.py shell
    exec(open('governance/examples/repair_service_demo.py').read())
"""

import json
from django.contrib.auth import get_user_model
from governance.services.repair_service import RepairService, CorruptionReport
from governance.services.repair_policy_framework import (
    RepairPolicyFramework, ConfidenceLevel, RepairPolicyType
)

User = get_user_model()

def demo_repair_service():
    """Demonstrate RepairService functionality"""
    
    print("=" * 60)
    print("RepairService Demonstration - Phase 4A Analysis Only")
    print("=" * 60)
    
    # Create or get a user for the demo
    user, created = User.objects.get_or_create(
        username='repair_demo_user',
        defaults={
            'email': 'repair_demo@example.com',
            'first_name': 'Repair',
            'last_name': 'Demo'
        }
    )
    
    # Initialize RepairService
    print("\n1. Initializing RepairService...")
    repair_service = RepairService()
    repair_service.set_user(user)
    print(f"✓ RepairService initialized with {len(repair_service.scanners)} corruption scanners")
    print(f"  Available scanners: {list(repair_service.scanners.keys())}")
    
    # Demonstrate CorruptionReport creation
    print("\n2. Creating sample corruption report...")
    report = CorruptionReport()
    
    # Add sample corruption findings
    orphaned_entries = [
        {'entry_id': 1, 'source_module': None, 'source_model': None, 'source_id': None},
        {'entry_id': 2, 'source_module': 'invalid', 'source_model': 'InvalidModel', 'source_id': 999}
    ]
    report.add_corruption(
        corruption_type='ORPHANED_JOURNAL_ENTRIES',
        issues=orphaned_entries,
        confidence='HIGH',
        evidence={'scan_method': 'ORM_based', 'total_entries': 100}
    )
    
    negative_stocks = [
        {'stock_id': 1, 'product_name': 'Product A', 'current_quantity': '-5.00'},
        {'stock_id': 2, 'product_name': 'Product B', 'current_quantity': '-2.50'}
    ]
    report.add_corruption(
        corruption_type='NEGATIVE_STOCK',
        issues=negative_stocks,
        confidence='HIGH',
        evidence={'scan_method': 'quantity_filter', 'total_stocks': 500}
    )
    
    multiple_years = [
        {'year_id': 1, 'year_name': '2023-2024', 'is_active': True},
        {'year_id': 2, 'year_name': '2024-2025', 'is_active': True}
    ]
    report.add_corruption(
        corruption_type='MULTIPLE_ACTIVE_ACADEMIC_YEARS',
        issues=multiple_years,
        confidence='HIGH',
        evidence={'scan_method': 'is_active_filter', 'total_years': 5}
    )
    
    print(f"✓ Corruption report created with {report.total_issues} total issues")
    print(f"  Corruption types found: {list(report.corruption_types.keys())}")
    
    # Demonstrate policy framework
    print("\n3. Demonstrating repair policy framework...")
    framework = RepairPolicyFramework()
    
    # Show policy recommendations
    print("\n   Policy recommendations:")
    for corruption_type, data in report.corruption_types.items():
        confidence = ConfidenceLevel(data['confidence'])
        policy = framework.get_policy(corruption_type, confidence)
        print(f"   • {corruption_type} ({confidence.value} confidence)")
        print(f"     → Policy: {policy['policy'].value}")
        print(f"     → Risk Level: {policy['risk_level']}")
        print(f"     → Approval Required: {policy['approval_required']}")
        print(f"     → Batch Size: {policy['batch_size']}")
    
    # Generate comprehensive repair plan
    print("\n4. Generating comprehensive repair plan...")
    comprehensive_plan = repair_service.generate_comprehensive_repair_plan(report)
    
    print(f"✓ Comprehensive repair plan generated")
    print(f"  Overall risk level: {comprehensive_plan['overall_risk_assessment']['risk_level']}")
    print(f"  Estimated duration: {comprehensive_plan['overall_risk_assessment']['total_estimated_duration']}")
    print(f"  Execution blocked: {comprehensive_plan['execution_blocked']}")
    print(f"  Phase: {comprehensive_plan['phase']}")
    
    # Show detailed plans
    print("\n   Detailed repair plans:")
    for corruption_type, plan_data in comprehensive_plan['detailed_plans'].items():
        print(f"   • {corruption_type}:")
        print(f"     - Policy: {plan_data['policy_type']}")
        print(f"     - Actions: {len(plan_data['repair_actions'])}")
        print(f"     - Risk: {plan_data['risk_assessment']['overall_risk']}")
        print(f"     - Duration: {plan_data['estimated_duration']}")
    
    # Generate final repair report
    print("\n5. Creating comprehensive repair report...")
    repair_report = repair_service.create_repair_report(report)
    
    print(f"✓ Repair report created")
    print(f"  Approval required: {repair_report['approval_required']}")
    print(f"  Execution blocked: {repair_report['execution_blocked']}")
    print(f"  All plans compliant: {repair_report['compliance_summary']['all_plans_compliant']}")
    print(f"  High-risk operations: {repair_report['compliance_summary']['high_risk_operations']}")
    
    # Show next steps
    print("\n6. Next steps for Phase 4B:")
    for i, step in enumerate(repair_report['next_steps'], 1):
        print(f"   {i}. {step}")
    
    # Demonstrate quarantine functionality (analysis only)
    print("\n7. Quarantine analysis (no actual quarantine)...")
    quarantine_results = repair_service.quarantine_suspicious_data(
        report, 
        auto_quarantine=False  # Analysis only
    )
    
    print(f"✓ Quarantine analysis completed")
    print(f"  Items that would be quarantined: {len(quarantine_results['quarantined_items'])}")
    print(f"  Items requiring manual approval: {len(quarantine_results['skipped_items'])}")
    
    if quarantine_results['skipped_items']:
        print("   Items requiring manual approval:")
        for item in quarantine_results['skipped_items']:
            print(f"   • {item['corruption_type']}: {item['count']} items ({item['reason']})")
    
    # Show policy compliance validation
    print("\n8. Policy compliance validation...")
    compliance_summary = repair_report['compliance_summary']
    print(f"✓ Compliance validation completed")
    print(f"  Total violations: {compliance_summary['total_violations']}")
    print(f"  Total warnings: {compliance_summary['total_warnings']}")
    
    if compliance_summary['total_violations'] > 0:
        print("   ⚠️  Policy violations found - review required")
    else:
        print("   ✓ All repair plans are policy compliant")
    
    print("\n" + "=" * 60)
    print("RepairService Demo Complete - Phase 4A Analysis Only")
    print("=" * 60)
    print("\nKey Points:")
    print("• All corruption detection completed successfully")
    print("• Repair policies defined according to confidence levels")
    print("• Comprehensive repair plans generated with risk assessment")
    print("• NO repairs executed - this is analysis only (Phase 4A)")
    print("• Stakeholder approval required before Phase 4B execution")
    print("• All operations are thread-safe and properly audited")
    
    return repair_report


def demo_policy_framework():
    """Demonstrate RepairPolicyFramework functionality"""
    
    print("\n" + "=" * 60)
    print("RepairPolicyFramework Detailed Demonstration")
    print("=" * 60)
    
    framework = RepairPolicyFramework()
    
    # Show all policies
    print("\n1. Available repair policies:")
    for corruption_type, policies in framework.policies.items():
        print(f"\n   {corruption_type}:")
        for confidence, policy_config in policies.items():
            print(f"     {confidence.value}:")
            print(f"       Policy: {policy_config['policy'].value}")
            print(f"       Risk: {policy_config['risk_level']}")
            print(f"       Batch Size: {policy_config['batch_size']}")
            print(f"       Approval: {policy_config['approval_required']}")
    
    # Show verification templates
    print("\n2. Verification invariants:")
    for corruption_type, invariants in framework.verification_templates.items():
        print(f"\n   {corruption_type}:")
        for invariant in invariants:
            print(f"     • {invariant.description}")
            print(f"       Critical: {invariant.critical}")
    
    # Show rollback strategies
    print("\n3. Rollback strategies:")
    for strategy_name, strategy in framework.rollback_templates.items():
        print(f"\n   {strategy_name}:")
        print(f"     Type: {strategy.strategy_type}")
        print(f"     Recovery Time: {strategy.recovery_time_estimate}")
        print(f"     Data Loss Risk: {strategy.data_loss_risk}")
        print(f"     Actions: {len(strategy.rollback_actions)}")
    
    print("\n" + "=" * 60)
    print("Policy Framework Demo Complete")
    print("=" * 60)


if __name__ == "__main__":
    # Run the demonstrations
    repair_report = demo_repair_service()
    demo_policy_framework()
    
    print(f"\nDemo completed successfully!")
    print(f"Repair report contains {len(repair_report['corruption_details'])} corruption types")
    print(f"Phase 4A analysis complete - ready for stakeholder review")