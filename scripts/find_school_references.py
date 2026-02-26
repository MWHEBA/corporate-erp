#!/usr/bin/env python
"""
Script to find all school-related references in the codebase.
Searches for Arabic and English patterns, model fields, and URLs.
Categorizes results by file type and risk level.
"""

import os
import re
import json
from pathlib import Path
from typing import List, Dict, Tuple
from collections import defaultdict


# Search patterns
ARABIC_PATTERNS = [
    r'طالب',
    r'طلاب',
    r'مدرسة',
    r'معلم',
    r'ولي أمر',
    r'أولياء الأمور',
    r'أكاديمي',
]

ENGLISH_PATTERNS = [
    r'\bstudent\b',
    r'\bstudents\b',
    r'\bschool\b',
    r'\bteacher\b',
    r'\bparent\b',
    r'\bguardian\b',
    r'\bacademic\b',
]

MODEL_FIELD_PATTERNS = [
    r'is_sold_to_parents',
    r'parent_selling_price',
]

URL_PATTERNS = [
    r'/students/',
    r'students/',
]

# File type patterns
FILE_TYPES = {
    'Python': ['.py'],
    'Templates': ['.html'],
    'JavaScript': ['.js'],
    'CSS': ['.css'],
    'Documentation': ['.md', '.txt', '.rst'],
    'Config': ['.ini', '.cfg', '.conf', '.json', '.yaml', '.yml'],
}

# Directories to exclude
EXCLUDE_DIRS = {
    '__pycache__', '.git', '.pytest_cache', '.hypothesis',
    'node_modules', 'staticfiles', 'media', '.venv', 'venv',
    '.kiro', 'logs', '.db_snapshots'
}

# Risk level determination
def determine_risk_level(file_path: str, pattern: str, line_content: str) -> str:
    """
    Determine risk level based on file type and pattern context.
    HIGH: Database models, forms, critical business logic
    MEDIUM: Templates, JavaScript, settings
    LOW: Comments, documentation, examples
    """
    file_path_lower = file_path.lower()
    line_lower = line_content.lower().strip()
    
    # HIGH RISK: Model fields and database-related
    if any(p in pattern for p in ['is_sold_to_parents', 'parent_selling_price']):
        return 'HIGH'
    
    # HIGH RISK: Model definitions
    if 'models.py' in file_path or 'models/' in file_path:
        if 'class ' in line_content or 'Field' in line_content:
            return 'HIGH'
    
    # HIGH RISK: Forms
    if 'forms.py' in file_path:
        if 'fields' in line_lower or 'class ' in line_content:
            return 'HIGH'
    
    # HIGH RISK: Migrations
    if 'migrations/' in file_path:
        return 'HIGH'
    
    # MEDIUM RISK: Templates with variables
    if file_path.endswith('.html'):
        if '{{' in line_content or '{%' in line_content:
            return 'MEDIUM'
        # LOW if just example text
        if 'مثال' in line_content or 'example' in line_lower:
            return 'LOW'
        return 'MEDIUM'
    
    # MEDIUM RISK: JavaScript URLs and functions
    if file_path.endswith('.js'):
        if 'url' in line_lower or 'fetch' in line_lower or 'ajax' in line_lower:
            return 'MEDIUM'
        return 'LOW'
    
    # MEDIUM RISK: Settings and configuration
    if 'settings' in file_path_lower or 'config' in file_path_lower:
        if line_content.strip().startswith('#'):
            return 'LOW'
        return 'MEDIUM'
    
    # LOW RISK: Comments
    if line_content.strip().startswith('#') or line_content.strip().startswith('//'):
        return 'LOW'
    
    # LOW RISK: Documentation
    if any(file_path.endswith(ext) for ext in ['.md', '.txt', '.rst']):
        return 'LOW'
    
    # Default to MEDIUM
    return 'MEDIUM'


def get_file_type(file_path: str) -> str:
    """Determine file type based on extension."""
    ext = Path(file_path).suffix
    for file_type, extensions in FILE_TYPES.items():
        if ext in extensions:
            return file_type
    return 'Other'


def search_file(file_path: str, patterns: List[str]) -> List[Dict]:
    """
    Search a single file for all patterns.
    Returns list of matches with context.
    """
    matches = []
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            
        for line_num, line in enumerate(lines, 1):
            for pattern in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    risk_level = determine_risk_level(file_path, pattern, line)
                    matches.append({
                        'file': file_path,
                        'line': line_num,
                        'pattern': pattern,
                        'content': line.strip(),
                        'file_type': get_file_type(file_path),
                        'risk_level': risk_level,
                    })
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    
    return matches


def find_all_files(root_dir: str) -> List[str]:
    """Find all relevant files in the project."""
    files = []
    root_path = Path(root_dir)
    
    for file_path in root_path.rglob('*'):
        # Skip directories
        if file_path.is_dir():
            continue
        
        # Skip excluded directories
        if any(excluded in file_path.parts for excluded in EXCLUDE_DIRS):
            continue
        
        # Only include relevant file types
        if file_path.suffix in [ext for exts in FILE_TYPES.values() for ext in exts]:
            files.append(str(file_path))
    
    return files


def search_codebase(root_dir: str = '.') -> Dict:
    """
    Search entire codebase for school references.
    Returns categorized results.
    """
    print("🔍 Starting search for school references...")
    print(f"Root directory: {os.path.abspath(root_dir)}")
    
    # Combine all patterns
    all_patterns = (
        ARABIC_PATTERNS +
        ENGLISH_PATTERNS +
        MODEL_FIELD_PATTERNS +
        URL_PATTERNS
    )
    
    print(f"Patterns to search: {len(all_patterns)}")
    
    # Find all files
    files = find_all_files(root_dir)
    print(f"Files to scan: {len(files)}")
    
    # Search all files
    all_matches = []
    for i, file_path in enumerate(files, 1):
        if i % 100 == 0:
            print(f"Progress: {i}/{len(files)} files scanned...")
        
        matches = search_file(file_path, all_patterns)
        all_matches.extend(matches)
    
    print(f"\n✅ Search complete! Found {len(all_matches)} matches.")
    
    # Categorize results
    results = {
        'summary': {
            'total_matches': len(all_matches),
            'total_files_scanned': len(files),
            'patterns_searched': len(all_patterns),
        },
        'by_file_type': defaultdict(list),
        'by_risk_level': defaultdict(list),
        'by_pattern': defaultdict(list),
        'all_matches': all_matches,
    }
    
    # Categorize matches
    for match in all_matches:
        results['by_file_type'][match['file_type']].append(match)
        results['by_risk_level'][match['risk_level']].append(match)
        results['by_pattern'][match['pattern']].append(match)
    
    # Convert defaultdicts to regular dicts for JSON serialization
    results['by_file_type'] = dict(results['by_file_type'])
    results['by_risk_level'] = dict(results['by_risk_level'])
    results['by_pattern'] = dict(results['by_pattern'])
    
    # Add counts to summary
    results['summary']['by_file_type'] = {
        ft: len(matches) for ft, matches in results['by_file_type'].items()
    }
    results['summary']['by_risk_level'] = {
        rl: len(matches) for rl, matches in results['by_risk_level'].items()
    }
    
    return results


def print_summary(results: Dict):
    """Print a human-readable summary of results."""
    print("\n" + "="*80)
    print("📊 SEARCH RESULTS SUMMARY")
    print("="*80)
    
    summary = results['summary']
    print(f"\nTotal matches found: {summary['total_matches']}")
    print(f"Files scanned: {summary['total_files_scanned']}")
    print(f"Patterns searched: {summary['patterns_searched']}")
    
    print("\n📁 By File Type:")
    for file_type, count in sorted(summary['by_file_type'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {file_type:20s}: {count:4d} matches")
    
    print("\n⚠️  By Risk Level:")
    risk_order = ['HIGH', 'MEDIUM', 'LOW']
    for risk_level in risk_order:
        count = summary['by_risk_level'].get(risk_level, 0)
        emoji = '🔴' if risk_level == 'HIGH' else '🟡' if risk_level == 'MEDIUM' else '🟢'
        print(f"  {emoji} {risk_level:10s}: {count:4d} matches")
    
    print("\n🔍 Top Patterns Found:")
    pattern_counts = [(p, len(m)) for p, m in results['by_pattern'].items()]
    for pattern, count in sorted(pattern_counts, key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {pattern:30s}: {count:4d} matches")
    
    print("\n" + "="*80)


def save_results(results: Dict, output_file: str = 'school_references_report.json'):
    """Save results to JSON file."""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 Results saved to: {output_file}")


def main():
    """Main execution function."""
    print("="*80)
    print("🏫 School References Finder")
    print("="*80)
    
    # Search codebase
    results = search_codebase()
    
    # Print summary
    print_summary(results)
    
    # Save results
    save_results(results)
    
    print("\n✨ Done!")


if __name__ == '__main__':
    main()
