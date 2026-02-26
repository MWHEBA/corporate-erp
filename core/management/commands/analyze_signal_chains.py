"""
Phase -1.1: Signal Chain Analysis Command
يبني Graph: sender → handler → side effects
يحسب عمق السلاسل (depth)
يطلع "Top chains by depth" + "Top chains by risk"
"""

import os
import ast
import json
import importlib
from collections import defaultdict, deque
from django.core.management.base import BaseCommand
from django.apps import apps
from django.db.models.signals import (
    pre_save, post_save, pre_delete, post_delete,
    m2m_changed, pre_migrate, post_migrate
)
from django.dispatch import Signal


class SignalChainAnalyzer:
    def __init__(self):
        self.signal_graph = defaultdict(list)
        self.signal_handlers = defaultdict(list)
        self.risk_indicators = {
            'journal_entry_creation': ['JournalEntry', 'create_journal', 'journal_entry'],
            'stock_modification': ['stock', 'quantity', 'inventory', 'movement'],
            'fee_generation': ['StudentFee', 'generate_fee', 'fee_creation'],
            'payment_processing': ['Payment', 'process_payment', 'payment_sync'],
            'status_changes': ['status', 'state', 'is_active', 'is_paid'],
            'cascade_operations': ['bulk_create', 'bulk_update', 'delete', 'cascade']
        }
        
    def scan_signal_handlers(self):
        """مسح جميع signal handlers في المشروع"""
        print("🔍 Scanning signal handlers...")
        
        # البحث في جميع ملفات signals.py
        for app_config in apps.get_app_configs():
            app_path = app_config.path
            signals_files = []
            
            # البحث عن ملفات signals
            for root, dirs, files in os.walk(app_path):
                for file in files:
                    if file.startswith('signals') and file.endswith('.py'):
                        signals_files.append(os.path.join(root, file))
            
            for signals_file in signals_files:
                self._analyze_signals_file(signals_file, app_config.name)
    
    def _analyze_signals_file(self, file_path, app_name):
        """تحليل ملف signals واستخراج handlers"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # البحث عن decorators للـ signals
                    for decorator in node.decorator_list:
                        if self._is_signal_decorator(decorator):
                            handler_info = {
                                'app': app_name,
                                'file': file_path,
                                'function': node.name,
                                'line': node.lineno,
                                'signal_type': self._extract_signal_type(decorator),
                                'sender': self._extract_sender(decorator),
                                'risk_score': self._calculate_risk_score(content, node),
                                'side_effects': self._extract_side_effects(node, content)
                            }
                            
                            signal_key = f"{handler_info['signal_type']}:{handler_info['sender']}"
                            self.signal_handlers[signal_key].append(handler_info)
                            
        except Exception as e:
            print(f"⚠️  Error analyzing {file_path}: {e}")
    
    def _is_signal_decorator(self, decorator):
        """تحديد ما إذا كان decorator خاص بـ signal"""
        if isinstance(decorator, ast.Name):
            return decorator.id in ['receiver']
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                return decorator.func.id in ['receiver']
        return False
    
    def _extract_signal_type(self, decorator):
        """استخراج نوع الـ signal"""
        if isinstance(decorator, ast.Call):
            for arg in decorator.args:
                if isinstance(arg, ast.Attribute):
                    return f"{arg.attr}"
                elif isinstance(arg, ast.Name):
                    return arg.id
        return "unknown"
    
    def _extract_sender(self, decorator):
        """استخراج الـ sender model"""
        if isinstance(decorator, ast.Call):
            for keyword in decorator.keywords:
                if keyword.arg == 'sender':
                    if isinstance(keyword.value, ast.Attribute):
                        return keyword.value.attr
                    elif isinstance(keyword.value, ast.Name):
                        return keyword.value.id
        return "unknown"
    
    def _calculate_risk_score(self, content, node):
        """حساب مستوى الخطر للـ handler"""
        risk_score = 0
        
        # استخراج محتوى الدالة
        function_content = ast.get_source_segment(content, node) or ""
        
        # فحص مؤشرات الخطر
        for risk_type, indicators in self.risk_indicators.items():
            for indicator in indicators:
                if indicator.lower() in function_content.lower():
                    risk_score += 1
        
        # مؤشرات خطر إضافية
        high_risk_patterns = [
            'objects.create', 'objects.bulk_create', 'objects.update',
            'save()', 'delete()', 'transaction.atomic',
            'signals.post_save.send', 'signals.pre_save.send'
        ]
        
        for pattern in high_risk_patterns:
            if pattern in function_content:
                risk_score += 2
        
        return min(risk_score, 10)  # Cap at 10
    
    def _extract_side_effects(self, node, content):
        """استخراج الآثار الجانبية للـ handler"""
        side_effects = []
        function_content = ast.get_source_segment(content, node) or ""
        
        # البحث عن عمليات إنشاء/تعديل
        if 'objects.create' in function_content:
            side_effects.append('creates_records')
        if 'objects.update' in function_content:
            side_effects.append('updates_records')
        if 'delete()' in function_content:
            side_effects.append('deletes_records')
        if 'JournalEntry' in function_content:
            side_effects.append('creates_journal_entries')
        if 'send(' in function_content:
            side_effects.append('triggers_other_signals')
        if 'quantity' in function_content.lower():
            side_effects.append('modifies_stock')
        if 'status' in function_content.lower():
            side_effects.append('changes_status')
        
        return side_effects
    
    def build_signal_graph(self):
        """بناء graph للـ signal chains"""
        print("🔗 Building signal dependency graph...")
        
        for signal_key, handlers in self.signal_handlers.items():
            for handler in handlers:
                # إذا كان handler يرسل signals أخرى
                if 'triggers_other_signals' in handler['side_effects']:
                    # محاولة تحديد الـ signals المرسلة
                    triggered_signals = self._find_triggered_signals(handler)
                    for triggered in triggered_signals:
                        self.signal_graph[signal_key].append(triggered)
    
    def _find_triggered_signals(self, handler):
        """البحث عن الـ signals التي يرسلها handler"""
        # هذا تحليل مبسط - يمكن تحسينه
        triggered = []
        try:
            with open(handler['file'], 'r', encoding='utf-8') as f:
                content = f.read()
            
            # البحث عن patterns مثل signals.post_save.send
            import re
            signal_patterns = [
                r'signals\.(\w+)\.send',
                r'(\w+)\.send\(',
                r'post_save\.send',
                r'pre_save\.send'
            ]
            
            for pattern in signal_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0] if match[0] else match[1]
                    triggered.append(f"{match}:unknown")
                    
        except Exception:
            pass
            
        return triggered
    
    def calculate_chain_depths(self):
        """حساب عمق السلاسل"""
        print("📏 Calculating chain depths...")
        
        depths = {}
        
        def dfs_depth(signal_key, visited=None):
            if visited is None:
                visited = set()
            
            if signal_key in visited:
                return 0  # تجنب الدورات اللانهائية
            
            visited.add(signal_key)
            max_depth = 0
            
            for connected_signal in self.signal_graph.get(signal_key, []):
                depth = 1 + dfs_depth(connected_signal, visited.copy())
                max_depth = max(max_depth, depth)
            
            return max_depth
        
        for signal_key in self.signal_handlers.keys():
            depths[signal_key] = dfs_depth(signal_key)
        
        return depths
    
    def generate_report(self):
        """توليد التقرير النهائي"""
        print("📊 Generating signal chain analysis report...")
        
        # حساب الإحصائيات
        total_handlers = sum(len(handlers) for handlers in self.signal_handlers.values())
        depths = self.calculate_chain_depths()
        
        # ترتيب حسب العمق
        top_chains_by_depth = sorted(depths.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # ترتيب حسب الخطر
        risk_scores = {}
        for signal_key, handlers in self.signal_handlers.items():
            avg_risk = sum(h['risk_score'] for h in handlers) / len(handlers)
            risk_scores[signal_key] = avg_risk
        
        top_chains_by_risk = sorted(risk_scores.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # إنشاء التقرير
        report = {
            'analysis_summary': {
                'total_signal_handlers': total_handlers,
                'unique_signal_chains': len(self.signal_handlers),
                'max_chain_depth': max(depths.values()) if depths else 0,
                'avg_chain_depth': sum(depths.values()) / len(depths) if depths else 0,
                'high_risk_chains': len([r for r in risk_scores.values() if r >= 5])
            },
            'top_chains_by_depth': [
                {
                    'signal_chain': chain[0],
                    'depth': chain[1],
                    'handlers': len(self.signal_handlers.get(chain[0], [])),
                    'avg_risk_score': risk_scores.get(chain[0], 0)
                }
                for chain in top_chains_by_depth
            ],
            'top_chains_by_risk': [
                {
                    'signal_chain': chain[0],
                    'risk_score': chain[1],
                    'depth': depths.get(chain[0], 0),
                    'handlers': len(self.signal_handlers.get(chain[0], []))
                }
                for chain in top_chains_by_risk
            ],
            'detailed_handlers': {}
        }
        
        # إضافة تفاصيل الـ handlers
        for signal_key, handlers in self.signal_handlers.items():
            report['detailed_handlers'][signal_key] = [
                {
                    'app': h['app'],
                    'file': h['file'].replace(os.getcwd(), ''),
                    'function': h['function'],
                    'line': h['line'],
                    'risk_score': h['risk_score'],
                    'side_effects': h['side_effects']
                }
                for h in handlers
            ]
        
        return report


class Command(BaseCommand):
    help = 'Phase -1.1: Analyze signal chains and calculate depth/risk metrics'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--output-format',
            choices=['markdown', 'json', 'both'],
            default='both',
            help='Output format for the report'
        )
        parser.add_argument(
            '--output-dir',
            default='reports',
            help='Directory to save reports'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting Signal Chain Analysis (Phase -1.1)')
        )
        
        # إنشاء مجلد التقارير
        output_dir = options['output_dir']
        os.makedirs(output_dir, exist_ok=True)
        
        # تشغيل التحليل
        analyzer = SignalChainAnalyzer()
        analyzer.scan_signal_handlers()
        analyzer.build_signal_graph()
        report = analyzer.generate_report()
        
        # حفظ التقارير
        if options['output_format'] in ['json', 'both']:
            json_path = os.path.join(output_dir, 'signal_chains_analysis.json')
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            self.stdout.write(f"📄 JSON report saved: {json_path}")
        
        if options['output_format'] in ['markdown', 'both']:
            md_path = os.path.join(output_dir, 'signal_chains_analysis.md')
            self._generate_markdown_report(report, md_path)
            self.stdout.write(f"📄 Markdown report saved: {md_path}")
        
        # عرض ملخص في الكونسول
        self._display_summary(report)
        
        self.stdout.write(
            self.style.SUCCESS('✅ Signal Chain Analysis completed successfully')
        )
    
    def _generate_markdown_report(self, report, file_path):
        """توليد تقرير Markdown"""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("# Signal Chain Analysis Report\n\n")
            f.write(f"**Generated:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # ملخص التحليل
            summary = report['analysis_summary']
            f.write("## Analysis Summary\n\n")
            f.write(f"- **Total Signal Handlers:** {summary['total_signal_handlers']}\n")
            f.write(f"- **Unique Signal Chains:** {summary['unique_signal_chains']}\n")
            f.write(f"- **Maximum Chain Depth:** {summary['max_chain_depth']}\n")
            f.write(f"- **Average Chain Depth:** {summary['avg_chain_depth']:.2f}\n")
            f.write(f"- **High Risk Chains (≥5):** {summary['high_risk_chains']}\n\n")
            
            # أعمق السلاسل
            f.write("## Top Chains by Depth\n\n")
            f.write("| Signal Chain | Depth | Handlers | Avg Risk |\n")
            f.write("|--------------|-------|----------|----------|\n")
            for chain in report['top_chains_by_depth']:
                f.write(f"| {chain['signal_chain']} | {chain['depth']} | {chain['handlers']} | {chain['avg_risk_score']:.1f} |\n")
            
            # أخطر السلاسل
            f.write("\n## Top Chains by Risk\n\n")
            f.write("| Signal Chain | Risk Score | Depth | Handlers |\n")
            f.write("|--------------|------------|-------|----------|\n")
            for chain in report['top_chains_by_risk']:
                f.write(f"| {chain['signal_chain']} | {chain['risk_score']:.1f} | {chain['depth']} | {chain['handlers']} |\n")
            
            # تفاصيل الـ handlers
            f.write("\n## Detailed Handler Information\n\n")
            for signal_key, handlers in report['detailed_handlers'].items():
                f.write(f"### {signal_key}\n\n")
                for handler in handlers:
                    f.write(f"**{handler['function']}** ({handler['app']})\n")
                    f.write(f"- File: `{handler['file']}:{handler['line']}`\n")
                    f.write(f"- Risk Score: {handler['risk_score']}/10\n")
                    f.write(f"- Side Effects: {', '.join(handler['side_effects']) if handler['side_effects'] else 'None'}\n\n")
    
    def _display_summary(self, report):
        """عرض ملخص في الكونسول"""
        summary = report['analysis_summary']
        
        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.WARNING("📊 SIGNAL CHAIN ANALYSIS SUMMARY"))
        self.stdout.write("="*50)
        
        self.stdout.write(f"Total Signal Handlers: {summary['total_signal_handlers']}")
        self.stdout.write(f"Unique Signal Chains: {summary['unique_signal_chains']}")
        self.stdout.write(f"Maximum Chain Depth: {summary['max_chain_depth']}")
        self.stdout.write(f"High Risk Chains: {summary['high_risk_chains']}")
        
        if report['top_chains_by_depth']:
            self.stdout.write(f"\n🏆 Deepest Chain: {report['top_chains_by_depth'][0]['signal_chain']} (depth: {report['top_chains_by_depth'][0]['depth']})")
        
        if report['top_chains_by_risk']:
            self.stdout.write(f"⚠️  Riskiest Chain: {report['top_chains_by_risk'][0]['signal_chain']} (risk: {report['top_chains_by_risk'][0]['risk_score']:.1f})")
        
        self.stdout.write("="*50 + "\n")