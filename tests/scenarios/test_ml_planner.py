"""
ML Planner Test Script

Tests trained ML planner and compares predictions vs actual optimal decisions.

Usage:
    python test_ml_planner.py                    # Test on all scenarios
    python test_ml_planner.py --scenario sunny   # Test specific scenario
    python test_ml_planner.py --compare          # Compare ML vs rule-based
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from apps.solar_optimizer.planners import MLPlanner, RuleBasedPlanner
from runner import ScenarioRunner


def test_single_scenario(ml_planner: MLPlanner, scenario: dict, verbose: bool = True):
    """Test ML planner on single scenario"""
    
    if verbose:
        print(f"\n{'='*70}")
        print(f"Testing: {scenario['name']}")
        print(f"{'='*70}")
        print(f"Description: {scenario['description']}")
    
    # Get ML prediction
    prediction = ml_planner.predict(scenario)
    
    if verbose:
        print(f"\n🤖 ML Prediction:")
        print(f"   Use Feed-in Priority: {prediction['use_feed_in_priority']}")
        print(f"   Feed-in Hours: {prediction['feed_in_hours']:.1f}h")
        print(f"   Confidence: {prediction['confidence']*100:.1f}%")
    
    # Show feature values
    features = ml_planner.extract_features(scenario)
    feature_names = [
        'soc_start', 'capacity', 'headroom',
        'total_solar', 'peak_kw', 'efficiency', 'net_surplus',
        'total_load', 'evening_peak',
        'overnight_price', 'peak_price', 'price_spread', 'arbitrage',
        'surplus_ratio', 'surplus_per_kwh'
    ]
    
    if verbose:
        print(f"\n📊 Key Features:")
        important_features = [
            ('total_solar', 3),
            ('net_surplus', 6),
            ('headroom', 2),
            ('surplus_ratio', 13),
            ('peak_kw', 4)
        ]
        
        for name, idx in important_features:
            print(f"   {name}: {features[idx]:.2f}")
    
    return prediction


def compare_planners(scenario: dict, ml_planner: MLPlanner, rule_based: RuleBasedPlanner):
    """Compare ML vs rule-based planner on scenario"""
    
    print(f"\n{'='*70}")
    print(f"Comparison: {scenario['name']}")
    print(f"{'='*70}")
    
    runner = ScenarioRunner()
    
    # Run rule-based
    print("\n📐 Running rule-based planner...")
    try:
        result_rb = runner.run_scenario(scenario)
        cost_rb = result_rb['adjusted_total_cost_pounds']
        feed_in_hours_rb = result_rb['feed_in_priority_hours']
        
        print(f"   Cost: £{cost_rb:.2f}")
        print(f"   Feed-in Priority: {feed_in_hours_rb:.1f}h")
    except Exception as e:
        print(f"   ERROR: {e}")
        cost_rb = None
        feed_in_hours_rb = None
    
    # Get ML prediction
    print("\n🤖 ML Planner prediction...")
    prediction = ml_planner.predict(scenario)
    
    print(f"   Use Feed-in Priority: {prediction['use_feed_in_priority']}")
    print(f"   Feed-in Hours: {prediction['feed_in_hours']:.1f}h")
    print(f"   Confidence: {prediction['confidence']*100:.1f}%")
    
    # Compare
    if feed_in_hours_rb is not None:
        print(f"\n📊 Comparison:")
        
        hours_diff = abs(prediction['feed_in_hours'] - feed_in_hours_rb)
        
        if prediction['use_feed_in_priority'] == (feed_in_hours_rb > 0):
            print(f"   ✅ Feed-in Priority decision: MATCH")
        else:
            print(f"   ❌ Feed-in Priority decision: MISMATCH")
        
        print(f"   Hours difference: {hours_diff:.1f}h")
        
        if hours_diff < 1.0:
            print(f"   ✅ Timing prediction: EXCELLENT")
        elif hours_diff < 2.0:
            print(f"   ⚠️  Timing prediction: GOOD")
        else:
            print(f"   ❌ Timing prediction: NEEDS IMPROVEMENT")


def test_all_scenarios(ml_planner: MLPlanner, category: str = None):
    """Test ML planner on all scenarios"""
    
    print("\n" + "="*70)
    print("  ML Planner Test Suite")
    print("="*70)
    
    runner = ScenarioRunner()
    scenarios = runner.load_scenarios(category)
    
    if not scenarios:
        print(f"\n❌ No scenarios found")
        return
    
    print(f"\nTesting on {len(scenarios)} scenarios...")
    
    results = []
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n[{i}/{len(scenarios)}] {scenario['name']}")
        
        try:
            prediction = test_single_scenario(ml_planner, scenario, verbose=False)
            
            # Quick summary
            print(f"   Feed-in: {prediction['use_feed_in_priority']}, "
                  f"Hours: {prediction['feed_in_hours']:.1f}h, "
                  f"Confidence: {prediction['confidence']*100:.0f}%")
            
            results.append({
                'scenario': scenario['name'],
                'prediction': prediction
            })
            
        except Exception as e:
            print(f"   ERROR: {e}")
    
    # Summary
    print("\n" + "="*70)
    print("  Summary")
    print("="*70)
    
    feed_in_predicted = sum(1 for r in results if r['prediction']['use_feed_in_priority'])
    avg_confidence = sum(r['prediction']['confidence'] for r in results) / len(results) if results else 0
    
    print(f"\nScenarios tested: {len(results)}")
    print(f"Feed-in Priority predicted: {feed_in_predicted}/{len(results)}")
    print(f"Average confidence: {avg_confidence*100:.1f}%")
    
    # High confidence predictions
    high_conf = [r for r in results if r['prediction']['confidence'] > 0.8]
    print(f"\nHigh confidence predictions (>80%): {len(high_conf)}")


def main():
    parser = argparse.ArgumentParser(description='Test ML planner')
    parser.add_argument('--scenario', help='Test specific scenario name (partial match)')
    parser.add_argument('--category', choices=['typical', 'edge_cases', 'stress_tests'],
                       help='Test specific category')
    parser.add_argument('--compare', action='store_true',
                       help='Compare ML vs rule-based planner')
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("  ML Planner Testing")
    print("="*70)
    
    # Load ML planner
    print("\nLoading ML planner...")
    ml_planner = MLPlanner()
    
    if ml_planner.feed_in_classifier is None:
        print("\n❌ No trained model found!")
        print("\nPlease train first:")
        print("  python train_ml_planner.py")
        sys.exit(1)
    
    print("✅ ML model loaded")
    
    # Load scenarios
    runner = ScenarioRunner()
    scenarios = runner.load_scenarios(args.category)
    
    if not scenarios:
        print("\n❌ No scenarios found")
        print("\nGenerate scenarios first:")
        print("  cd test_scenarios")
        print("  python generator.py --generate-all")
        sys.exit(1)
    
    # Filter by scenario name if provided
    if args.scenario:
        scenarios = [s for s in scenarios if args.scenario.lower() in s['name'].lower()]
        
        if not scenarios:
            print(f"\n❌ No scenarios matching '{args.scenario}' found")
            sys.exit(1)
    
    # Run tests
    try:
        if args.compare:
            # Compare mode
            rule_based = RuleBasedPlanner()
            
            for scenario in scenarios:
                compare_planners(scenario, ml_planner, rule_based)
        
        elif len(scenarios) == 1:
            # Single scenario detailed test
            test_single_scenario(ml_planner, scenarios[0], verbose=True)
        
        else:
            # Test all scenarios
            test_all_scenarios(ml_planner, args.category)
        
        print("\n" + "="*70)
        print("✅ Testing complete!")
        print("="*70)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Testing interrupted")
    except Exception as e:
        print(f"\n\n❌ Testing failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
