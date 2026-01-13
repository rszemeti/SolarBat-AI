"""
Planner Comparison Script

Run all three planners on test scenarios and compare results.

Usage:
    python compare_planners.py                 # Compare all three planners
    python compare_planners.py --category typical  # Compare on specific category
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from runner import ScenarioRunner
from compare import ResultsComparator


def run_all_planners(scenarios_dir: str = "./scenarios", 
                     results_dir: str = "./results",
                     category: str = None):
    """Run all three planners and save results"""
    
    print("\n" + "="*70)
    print("  Planner Comparison - Running All Three Planners")
    print("="*70)
    
    planners = ['rule-based', 'ml', 'lp']
    result_files = {}
    
    for planner in planners:
        print(f"\n{'='*70}")
        print(f"  Running {planner.upper()} Planner")
        print(f"{'='*70}")
        
        try:
            runner = ScenarioRunner(scenarios_dir, results_dir, planner)
            summary = runner.run_all(category)
            
            if summary:
                # Find the most recent result file
                files = [f for f in os.listdir(results_dir) if f.startswith('results_') and f.endswith('.json')]
                if files:
                    latest = sorted(files)[-1]
                    result_files[planner] = os.path.join(results_dir, latest)
                    print(f"\n✅ {planner} complete: {result_files[planner]}")
                
        except Exception as e:
            print(f"\n❌ {planner} failed: {e}")
            import traceback
            traceback.print_exc()
    
    return result_files


def compare_all_results(result_files: dict):
    """Compare results from all planners"""
    
    if len(result_files) < 2:
        print("\n❌ Need at least 2 planners to compare")
        return
    
    print("\n" + "="*70)
    print("  PLANNER COMPARISON SUMMARY")
    print("="*70)
    
    # Load all results
    results = {}
    for planner, filepath in result_files.items():
        with open(filepath, 'r') as f:
            results[planner] = json.load(f)
    
    # Compare metrics
    print(f"\n{'Planner':<15} {'Cost':<12} {'Pass Rate':<12} {'Runtime':<12}")
    print("-" * 70)
    
    metrics = []
    for planner in ['rule-based', 'ml', 'lp']:
        if planner not in results:
            continue
        
        r = results[planner]
        cost = r.get('total_adjusted_cost', r.get('total_cost', 0))
        pass_rate = r['passed'] / r['total_scenarios'] * 100
        runtime = r.get('total_runtime', 0)
        
        metrics.append({
            'planner': planner,
            'cost': cost,
            'pass_rate': pass_rate,
            'runtime': runtime
        })
        
        print(f"{planner.upper():<15} £{cost:<11.2f} {pass_rate:<11.1f}% {runtime:<11.2f}s")
    
    # Find best
    if metrics:
        best_cost = min(metrics, key=lambda x: x['cost'])
        best_pass = max(metrics, key=lambda x: x['pass_rate'])
        fastest = min(metrics, key=lambda x: x['runtime'])
        
        print("\n" + "="*70)
        print("  WINNERS")
        print("="*70)
        print(f"💰 Lowest Cost:     {best_cost['planner'].upper():<15} £{best_cost['cost']:.2f}")
        print(f"✅ Best Pass Rate:  {best_pass['planner'].upper():<15} {best_pass['pass_rate']:.1f}%")
        print(f"⚡ Fastest:         {fastest['planner'].upper():<15} {fastest['runtime']:.3f}s")
        
        # Overall recommendation
        print("\n" + "="*70)
        print("  RECOMMENDATION")
        print("="*70)
        
        # Calculate scores (normalize to 0-100)
        for m in metrics:
            cost_score = (1 - (m['cost'] / max(x['cost'] for x in metrics))) * 100
            pass_score = m['pass_rate']
            speed_score = (1 - (m['runtime'] / max(x['runtime'] for x in metrics))) * 100
            
            # Weighted average: 50% cost, 30% pass rate, 20% speed
            m['overall_score'] = cost_score * 0.5 + pass_score * 0.3 + speed_score * 0.2
        
        best_overall = max(metrics, key=lambda x: x['overall_score'])
        
        print(f"\n🏆 Overall Winner: {best_overall['planner'].upper()}")
        print(f"   Score: {best_overall['overall_score']:.1f}/100")
        print(f"   Cost: £{best_overall['cost']:.2f}")
        print(f"   Pass Rate: {best_overall['pass_rate']:.1f}%")
        print(f"   Runtime: {best_overall['runtime']:.2f}s")
        
        # Detailed analysis
        print("\n📊 Detailed Comparison:")
        
        if 'rule-based' in results and 'ml' in results:
            rb_cost = next(m['cost'] for m in metrics if m['planner'] == 'rule-based')
            ml_cost = next(m['cost'] for m in metrics if m['planner'] == 'ml')
            
            if ml_cost < rb_cost:
                savings = rb_cost - ml_cost
                pct = (savings / rb_cost) * 100
                print(f"   ML vs Rule-Based: Saves £{savings:.2f} ({pct:.1f}%)")
            else:
                extra = ml_cost - rb_cost
                pct = (extra / rb_cost) * 100
                print(f"   ML vs Rule-Based: Costs £{extra:.2f} more ({pct:.1f}%)")
        
        if 'rule-based' in results and 'lp' in results:
            rb_cost = next(m['cost'] for m in metrics if m['planner'] == 'rule-based')
            lp_cost = next(m['cost'] for m in metrics if m['planner'] == 'lp')
            
            if lp_cost < rb_cost:
                savings = rb_cost - lp_cost
                pct = (savings / rb_cost) * 100
                print(f"   LP vs Rule-Based: Saves £{savings:.2f} ({pct:.1f}%) - Optimal!")
            else:
                extra = lp_cost - rb_cost
                pct = (extra / rb_cost) * 100
                print(f"   LP vs Rule-Based: Costs £{extra:.2f} more ({pct:.1f}%)")
        
        if 'ml' in results and 'lp' in results:
            ml_cost = next(m['cost'] for m in metrics if m['planner'] == 'ml')
            lp_cost = next(m['cost'] for m in metrics if m['planner'] == 'lp')
            
            gap = abs(ml_cost - lp_cost)
            gap_pct = (gap / lp_cost) * 100
            
            if gap_pct < 5:
                print(f"   ML vs LP: Within {gap_pct:.1f}% of optimal! ML is learning well!")
            else:
                print(f"   ML vs LP: {gap_pct:.1f}% gap - ML can improve further")


def main():
    parser = argparse.ArgumentParser(description='Compare all planners')
    parser.add_argument('--scenarios-dir', default='./scenarios',
                       help='Directory containing scenarios')
    parser.add_argument('--results-dir', default='./results',
                       help='Directory for results')
    parser.add_argument('--category', choices=['typical', 'edge_cases', 'stress_tests'],
                       help='Run only specific category')
    
    args = parser.parse_args()
    
    try:
        # Run all planners
        result_files = run_all_planners(args.scenarios_dir, args.results_dir, args.category)
        
        # Compare results
        if result_files:
            compare_all_results(result_files)
        
        print("\n" + "="*70)
        print("✅ Comparison complete!")
        print("="*70 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Comparison interrupted")
    except Exception as e:
        print(f"\n\n❌ Comparison failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
