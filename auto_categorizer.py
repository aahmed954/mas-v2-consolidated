#!/usr/bin/env python3
"""
Auto-Categorization Scanner for Work Buddy
Analyzes your files and suggests optimal collection structure
"""

import os
from pathlib import Path
from collections import defaultdict, Counter
import re
import json

class DocumentCategorizer:
    def __init__(self, base_path="/home/starlord/raycastfiles/Life"):
        self.base_path = Path(base_path)
        self.categories = defaultdict(list)
        self.stats = defaultdict(int)
        
        # Smart patterns for categorization
        self.category_rules = {
            'finance': {
                'keywords': ['401k', '401', 'tax', 'irs', 'w2', 'w-2', '1099', 'investment', 
                            'retirement', 'pension', 'income', 'expense', 'budget', 'bank',
                            'financial', 'money', 'salary', 'payroll', 'invoice'],
                'paths': ['401k', 'taxes', 'finance', 'investments'],
                'extensions': ['.xlsx', '.xls', '.csv']  # Financial docs often spreadsheets
            },
            'legal': {
                'keywords': ['lawsuit', 'legal', 'attorney', 'lawyer', 'court', 'case',
                            'contract', 'agreement', 'settlement', 'claim', 'dispute',
                            'litigation', 'plaintiff', 'defendant', 'evidence'],
                'paths': ['lawsuit', 'legal', 'contracts', 'malpractice'],
                'extensions': ['.docx', '.doc']
            },
            'medical': {
                'keywords': ['medical', 'health', 'doctor', 'hospital', 'diagnosis',
                            'treatment', 'prescription', 'lab', 'test', 'insurance',
                            'medicare', 'medicaid', 'patient', 'clinic', 'surgery',
                            'malpractice', 'tb', 'disease'],
                'paths': ['medical', 'health', 'malpractice'],
                'extensions': ['.pdf']
            },
            'estate': {
                'keywords': ['estate', 'will', 'trust', 'beneficiary', 'inheritance',
                            'power of attorney', 'executor', 'probate', 'asset'],
                'paths': ['estate', 'will', 'trust'],
                'extensions': ['.pdf', '.docx']
            },
            'business': {
                'keywords': ['business', 'company', 'client', 'project', 'proposal',
                            'meeting', 'presentation', 'strategy', 'plan', 'report',
                            'export', 'import', 'shipment', 'order'],
                'paths': ['business', 'work', 'projects', 'clients', 'export'],
                'extensions': ['.pptx', '.xlsx']
            },
            'personal': {
                'keywords': ['personal', 'family', 'photo', 'note', 'diary', 'journal',
                            'password', 'credential', 'license', 'passport'],
                'paths': ['personal', 'family', 'documents'],
                'extensions': ['.txt', '.md', '.jpg', '.png']
            },
            'correspondence': {
                'keywords': ['email', 'letter', 'memo', 'message', 'communication'],
                'paths': ['email', 'letters', 'correspondence'],
                'extensions': ['.eml', '.msg', '.txt']
            }
        }
    
    def analyze_file(self, filepath: Path) -> dict:
        """Analyze a single file and determine its category"""
        # Convert to lowercase for matching
        path_str = str(filepath).lower()
        filename = filepath.name.lower()
        extension = filepath.suffix.lower()
        
        # Score each category
        scores = defaultdict(int)
        
        for category, rules in self.category_rules.items():
            # Check keywords in path and filename
            for keyword in rules['keywords']:
                if keyword in path_str:
                    scores[category] += 3  # Path match is strong signal
                if keyword in filename:
                    scores[category] += 2  # Filename match
            
            # Check path patterns
            for pattern in rules['paths']:
                if pattern in path_str:
                    scores[category] += 5  # Direct path match is very strong
            
            # Check extensions
            if extension in rules['extensions']:
                scores[category] += 1
        
        # Determine best category
        if scores:
            best_category = max(scores, key=scores.get)
            confidence = scores[best_category]
        else:
            best_category = 'uncategorized'
            confidence = 0
        
        return {
            'path': str(filepath),
            'name': filepath.name,
            'category': best_category,
            'confidence': confidence,
            'all_scores': dict(scores)
        }
    
    def scan_directory(self):
        """Scan entire directory structure"""
        print(f"🔍 Scanning {self.base_path}...")
        
        all_files = []
        for ext in ['*.*']:  # Get everything
            all_files.extend(self.base_path.rglob(ext))
        
        print(f"Found {len(all_files)} files to analyze")
        
        # Analyze each file
        results = []
        for filepath in all_files:
            if filepath.is_file():
                analysis = self.analyze_file(filepath)
                results.append(analysis)
                self.categories[analysis['category']].append(filepath)
                self.stats[analysis['category']] += 1
        
        return results
    
    def generate_report(self, results):
        """Generate categorization report"""
        print("\n" + "="*60)
        print("📊 AUTO-CATEGORIZATION REPORT")
        print("="*60)
        
        # Category distribution
        print("\n📁 Suggested Collections:")
        for category, count in sorted(self.stats.items(), key=lambda x: x[1], reverse=True):
            print(f"  work-buddy-{category}: {count} files")
        
        # Sample files per category
        print("\n📄 Sample Files by Category:")
        for category in sorted(self.categories.keys()):
            if category == 'uncategorized':
                continue
            print(f"\n{category.upper()}:")
            samples = self.categories[category][:3]
            for sample in samples:
                print(f"  • {sample.name}")
        
        # Confidence analysis
        confidence_levels = {'high': 0, 'medium': 0, 'low': 0, 'none': 0}
        for r in results:
            conf = r['confidence']
            if conf >= 10:
                confidence_levels['high'] += 1
            elif conf >= 5:
                confidence_levels['medium'] += 1
            elif conf > 0:
                confidence_levels['low'] += 1
            else:
                confidence_levels['none'] += 1
        
        print("\n🎯 Categorization Confidence:")
        print(f"  High confidence: {confidence_levels['high']} files")
        print(f"  Medium confidence: {confidence_levels['medium']} files")
        print(f"  Low confidence: {confidence_levels['low']} files")
        print(f"  Uncategorized: {confidence_levels['none']} files")
        
        # Directory patterns
        print("\n📂 Directory Pattern Analysis:")
        dir_patterns = Counter()
        for filepath in self.base_path.rglob("*"):
            if filepath.is_dir():
                dir_name = filepath.name.lower()
                for category, rules in self.category_rules.items():
                    for keyword in rules['keywords']:
                        if keyword in dir_name:
                            dir_patterns[category] += 1
                            break
        
        for category, count in dir_patterns.most_common(5):
            print(f"  {category}: {count} matching directories")
        
        return {
            'total_files': len(results),
            'categories': dict(self.stats),
            'confidence_distribution': confidence_levels,
            'suggested_collections': [f"work-buddy-{cat}" for cat in self.stats.keys() if cat != 'uncategorized']
        }
    
    def export_mapping(self, results, output_file="categorization_map.json"):
        """Export the categorization mapping for review"""
        mapping = defaultdict(list)
        
        for r in results:
            mapping[r['category']].append({
                'file': r['name'],
                'path': r['path'],
                'confidence': r['confidence']
            })
        
        with open(output_file, 'w') as f:
            json.dump(mapping, f, indent=2)
        
        print(f"\n💾 Exported mapping to {output_file}")
        print("   Review and adjust before ingestion")

if __name__ == "__main__":
    categorizer = DocumentCategorizer()
    results = categorizer.scan_directory()
    report = categorizer.generate_report(results)
    categorizer.export_mapping(results)
    
    print("\n" + "="*60)
    print("🚀 RECOMMENDED SETUP")
    print("="*60)
    print("\nBased on your documents, create these collections:")
    for collection in report['suggested_collections']:
        print(f"  • {collection}")
    
    print("\n✨ Next Steps:")
    print("1. Review categorization_map.json")
    print("2. Adjust any miscategorized files")
    print("3. Run ingestion with these collections")
    print("4. Enjoy lightning-fast targeted search!")
