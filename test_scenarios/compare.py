"""
Test Results Comparator

Compare results from different test runs or versions.

Usage:
    python compare.py results/results_20260111_100000.json results/results_20260111_110000.json
    python compare.py --latest  # Compare two most recent runs
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List
from datetime import datetime


class ResultsComparator:
    """Compare test results from different runs"""
    
    def __init__(self, results_dir: str = "./results"):
        self.results_dir = results_dir
    
    def load_results(self, filename: str) -> Dict:
        """Load results from JSON file"""
        filepath = os.path.join(self.results_dir, filename) if not os.path.isabs(filename) else filename
        
        with open(filepath, 'r') as f:
            return json.load(f)
    
    def get_latest_results(self, n: int = 2) -> List[str]:
        """Get n most recent result files"""
        files = []
        
        for filename in os.listdir(self.results_dir):
            if filename.startswith('results_') and filename.endswith('.json'):
                filepath = os.path.join(self.results_dir, filename)
                mtime = os.path.getmtime(filepath)
                files.append((mtime, filename))
        
        files.sort(reverse=True)
        return [f[1] for f in files[:n]]
    
    def compare(self, file1: str, file2: str):
        """Compare two result sets"""
        print("\n" + "="*70)
        print("  Test Results Comparison")
        print("="*70)
        
        results1 = self.load_results(file1)
        results2 = self.load_results(file2)
        
        print(f"\nRun 1: {results1.get('version', 'unknown')} - {results1['timestamp']}")
        print(f"  File: {file1}")
        print(f"  Scenarios: {results1['total_scenarios']}")
        print(f"  Pass rate: {results1['passed']/results1['total_scenarios']*100:.1f}%")
        
        print(f"\nRun 2: {results2.get('version', 'unknown')} - {results2['timestamp']}")
        print(f"  File: {file2}")
        print(f"  Scenarios: {results2['total_scenarios']}")
        print(f"  Pass rate: {results2['passed']/results2['total_scenarios']*100:.1f}%")
        
        # Compare metrics
        print("\n" + "="*70)
        print("  METRIC COMPARISON")
        print("="*70)
        
        metrics = [
            ('Total Adjusted Cost', 'total_adjusted_cost', '£', lambda x: f"{x:.2f}"),
            ('Average Adjusted Cost', 'average_adjusted_cost', '£', lambda x: f"{x:.2f}"),
            ('Pass Rate', None, '%', lambda x: f"{x:.1f}"),
            ('Total Runtime', 'total_runtime', 's', lambda x: f"{x:.2f}")
        ]
        
        for label, key, unit, fmt in metrics:
            if key:
                val1 = results1.get(key, 0)
                val2 = results2.get(key, 0)
            else:
                # Pass rate
                val1 = results1['passed'] / results1['total_scenarios'] * 100
                val2 = results2['passed'] / results2['total_scenarios'] * 100
            
            diff = val2 - val1
            pct_change = (diff / val1 * 100) if val1 != 0 else 0
            
            symbol = "📈" if diff > 0 else "📉" if diff < 0 else "➡️"
            
            # For cost, lower is better
            if 'cost' in label.lower():
                symbol = "📉" if diff < 0 else "📈" if diff > 0 else "➡️"
                better = "✅" if diff < 0 else "❌" if diff > 0 else "➡️"
            else:
                better = "✅" if diff > 0 else "❌" if diff < 0 else "➡️"
            
            print(f"\n{label}:")
            print(f"  Run 1: {unit}{fmt(val1)}")
            print(f"  Run 2: {unit}{fmt(val2)}")
            print(f"  Change: {symbol} {diff:+.2f} ({pct_change:+.1f}%) {better}")
        
        # Scenario-by-scenario comparison
        print("\n" + "="*70)
        print("  SCENARIO COMPARISON")
        print("="*70)
        
        # Build lookup by scenario name
        scenarios1 = {r['scenario_name']: r for r in results1['results']}
        scenarios2 = {r['scenario_name']: r for r in results2['results']}
        
        all_scenarios = set(scenarios1.keys()) | set(scenarios2.keys())
        
        regressions = []
        improvements = []
        new_failures = []
        new_passes = []
        
        for name in sorted(all_scenarios):
            r1 = scenarios1.get(name)
            r2 = scenarios2.get(name)
            
            if not r1 or not r2:
                continue
            
            cost1 = r1.get('adjusted_total_cost_pounds', r1.get('total_cost_pounds', 0))
            cost2 = r2.get('adjusted_total_cost_pounds', r2.get('total_cost_pounds', 0))
            cost_diff = cost2 - cost1
            
            pass1 = r1['validation']['passed']
            pass2 = r2['validation']['passed']
            
            # Detect changes
            if cost_diff > 0.50:  # Cost increased by >50p
                regressions.append((name, cost1, cost2, cost_diff))
            elif cost_diff < -0.50:  # Cost decreased by >50p
                improvements.append((name, cost1, cost2, cost_diff))
            
            if pass1 and not pass2:
                new_failures.append(name)
            elif not pass1 and pass2:
                new_passes.append(name)
        
        if improvements:
            print(f"\n✅ IMPROVEMENTS ({len(improvements)}):")
            for name, cost1, cost2, diff in improvements[:5]:
                print(f"   {name}: £{cost1:.2f} → £{cost2:.2f} (saved £{abs(diff):.2f})")
            if len(improvements) > 5:
                print(f"   ... and {len(improvements)-5} more")
        
        if regressions:
            print(f"\n❌ REGRESSIONS ({len(regressions)}):")
            for name, cost1, cost2, diff in regressions[:5]:
                print(f"   {name}: £{cost1:.2f} → £{cost2:.2f} (cost +£{diff:.2f})")
            if len(regressions) > 5:
                print(f"   ... and {len(regressions)-5} more")
        
        if new_failures:
            print(f"\n⚠️  NEW FAILURES ({len(new_failures)}):")
            for name in new_failures[:5]:
                print(f"   {name}")
            if len(new_failures) > 5:
                print(f"   ... and {len(new_failures)-5} more")
        
        if new_passes:
            print(f"\n🎉 NEW PASSES ({len(new_passes)}):")
            for name in new_passes[:5]:
                print(f"   {name}")
            if len(new_passes) > 5:
                print(f"   ... and {len(new_passes)-5} more")
        
        # Overall verdict
        print("\n" + "="*70)
        print("  VERDICT")
        print("="*70)
        
        cost_improved = results2.get('total_adjusted_cost', results2.get('total_cost', 0)) < results1.get('total_adjusted_cost', results1.get('total_cost', 0))
        pass_rate_improved = results2['passed'] > results1['passed']
        
        if cost_improved and pass_rate_improved:
            print("\n🏆 CLEAR WIN - Run 2 is better on all metrics!")
        elif cost_improved and not regressions:
            print("\n✅ IMPROVEMENT - Run 2 has better cost with no regressions")
        elif regressions:
            print(f"\n⚠️  WARNING - Run 2 has {len(regressions)} regressions")
        elif not cost_improved:
            print("\n❌ WORSE - Run 2 has higher costs")
        else:
            print("\n➡️  NEUTRAL - Mixed results")
        
        print("="*70 + "\n")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Compare test results')
    parser.add_argument('files', nargs='*', help='Result files to compare')
    parser.add_argument('--results-dir', default='./results',
                       help='Results directory')
    parser.add_argument('--latest', action='store_true',
                       help='Compare two most recent runs')
    
    args = parser.parse_args()
    
    comparator = ResultsComparator(args.results_dir)
    
    if args.latest:
        files = comparator.get_latest_results(2)
        if len(files) < 2:
            print("❌ Need at least 2 result files to compare")
            sys.exit(1)
        print(f"Comparing latest runs:")
        print(f"  Run 1: {files[1]}")
        print(f"  Run 2: {files[0]}")
        comparator.compare(files[1], files[0])
    
    elif len(args.files) == 2:
        comparator.compare(args.files[0], args.files[1])
    
    else:
        print("Usage:")
        print("  python compare.py file1.json file2.json")
        print("  python compare.py --latest")
        sys.exit(1)


if __name__ == '__main__':
    main()
