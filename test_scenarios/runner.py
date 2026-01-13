"""
Test Scenario Runner

Runs all test scenarios and validates results against expected outcomes.

Usage:
    python runner.py                           # Run all scenarios (rule-based)
    python runner.py --planner ml              # Use ML planner
    python runner.py --planner lp              # Use LP planner
    python runner.py --planner rule-based      # Use rule-based (default)
    python runner.py --category typical        # Run only typical scenarios
    python runner.py --compare v2.2 v2.3       # Compare two versions
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.solar_optimizer.plan_creator import PlanCreator


class ScenarioRunner:
    """Runs test scenarios and validates results"""
    
    def __init__(self, scenarios_dir: str = "./scenarios", results_dir: str = "./results", 
                 planner_type: str = "rule-based"):
        self.scenarios_dir = scenarios_dir
        self.results_dir = results_dir
        self.planner_type = planner_type
        os.makedirs(results_dir, exist_ok=True)
        
        # Initialize planner based on type
        self._init_planner()
    
    def _init_planner(self):
        """Initialize the specified planner"""
        print(f"\n[RUNNER] Initializing {self.planner_type} planner...")
        
        if self.planner_type == "rule-based":
            self.plan_creator = PlanCreator()
            print("[RUNNER] ✅ Rule-based planner loaded")
            
        elif self.planner_type == "ml":
            try:
                from apps.solar_optimizer.ml_planner import MLPlanner
                self.plan_creator = MLPlanner()
                
                if self.plan_creator.feed_in_classifier is None:
                    print("[RUNNER] ⚠️  WARNING: ML planner not trained!")
                    print("[RUNNER]    Using heuristics. Train first: python train_ml_planner.py")
                else:
                    print("[RUNNER] ✅ ML planner loaded (trained model found)")
                    
            except ImportError:
                print("[RUNNER] ❌ ERROR: ML planner requires scikit-learn")
                print("[RUNNER]    Install: pip install scikit-learn numpy")
                sys.exit(1)
                
        elif self.planner_type == "lp":
            try:
                from apps.solar_optimizer.lp_planner import LinearProgrammingPlanner
                self.plan_creator = LinearProgrammingPlanner()
                print("[RUNNER] ✅ LP planner loaded (PuLP solver)")
                
            except ImportError:
                print("[RUNNER] ❌ ERROR: LP planner requires PuLP")
                print("[RUNNER]    Install: pip install pulp")
                sys.exit(1)
                
        else:
            print(f"[RUNNER] ❌ ERROR: Unknown planner type: {self.planner_type}")
            print("[RUNNER]    Valid options: rule-based, ml, lp")
            sys.exit(1)
    
    def load_scenarios(self, category: str = None) -> List[Dict]:
        """Load all scenarios from a category or all categories"""
        scenarios = []
        
        if category:
            categories = [category]
        else:
            categories = ['typical', 'edge_cases', 'stress_tests']
        
        for cat in categories:
            cat_dir = os.path.join(self.scenarios_dir, cat)
            if not os.path.exists(cat_dir):
                continue
            
            for filename in sorted(os.listdir(cat_dir)):
                if filename.endswith('.json'):
                    filepath = os.path.join(cat_dir, filename)
                    with open(filepath, 'r') as f:
                        scenario = json.load(f)
                        scenario['category'] = cat
                        scenario['filename'] = filename
                        scenarios.append(scenario)
        
        return scenarios
    
    def expand_solar_profile(self, profile: Dict, start_time: datetime) -> List[Dict]:
        """Expand parametric solar profile to 48 half-hour slots"""
        slots = []
        
        if profile['type'] == 'zero':
            # No solar
            for slot in range(48):
                time = start_time + timedelta(minutes=30 * slot)
                slots.append({'time': time, 'kw': 0.0})
            return slots
        
        # Parametric bell curve
        peak_kw = profile['peak_kw']
        sunrise = profile['sunrise_hour']
        sunset = profile['sunset_hour']
        efficiency = profile['efficiency']
        variability = profile.get('variability', 0.02)
        
        import math
        import random
        
        for slot in range(48):
            time = start_time + timedelta(minutes=30 * slot)
            hour = time.hour + (time.minute / 60.0)
            
            if sunrise <= hour <= sunset:
                day_length = sunset - sunrise
                position = (hour - sunrise) / day_length
                solar_kw = peak_kw * efficiency * math.sin(position * math.pi)
                
                # Add variability
                variation = 1.0 + (random.random() - 0.5) * 2 * variability
                solar_kw *= variation
                solar_kw = max(0, min(solar_kw, peak_kw))
            else:
                solar_kw = 0.0
            
            slots.append({'time': time, 'kw': round(solar_kw, 3)})
        
        return slots
    
    def expand_load_profile(self, profile: Dict, start_time: datetime) -> List[Dict]:
        """Expand parametric load profile to 48 half-hour slots"""
        slots = []
        
        base_kw = profile['base_kw']
        morning_peak = profile['morning_peak_kw']
        evening_peak = profile['evening_peak_kw']
        
        import math
        import random
        
        for slot in range(48):
            time = start_time + timedelta(minutes=30 * slot)
            hour = time.hour + (time.minute / 60.0)
            
            # Time-of-day pattern
            if 0 <= hour < 6:
                load_kw = base_kw + 0.1 * math.sin(hour * math.pi / 6)
            elif 6 <= hour < 9:
                progress = (hour - 6) / 3.0
                load_kw = base_kw + progress * morning_peak
            elif 9 <= hour < 16:
                load_kw = 0.5 + 0.3 * math.sin((hour - 9) * math.pi / 7)
            elif 16 <= hour < 22:
                progress = (hour - 16) / 6.0
                peak_now = evening_peak * math.sin(progress * math.pi)
                load_kw = base_kw + peak_now
            else:
                progress = (hour - 22) / 2.0
                load_kw = evening_peak * (1 - progress) + base_kw * progress
            
            # Add variation
            load_kw *= (0.9 + random.random() * 0.2)
            
            slots.append({
                'time': time,
                'load_kw': round(load_kw, 3),
                'confidence': 'high'
            })
        
        return slots
    
    def expand_pricing_profile(self, profile: Dict, start_time: datetime) -> Tuple[List[Dict], List[Dict]]:
        """Expand pricing profile to import and export prices"""
        import_prices = []
        export_prices = []
        
        import random
        
        for slot in range(48):
            time = start_time + timedelta(minutes=30 * slot)
            hour = time.hour
            
            # Handle different profile types
            if profile['type'] == 'agile_negative':
                # Negative overnight pricing
                if 0 <= hour < 7:
                    base = profile['overnight_avg_p']
                elif 7 <= hour < 9:
                    base = profile.get('day_avg_p', 20.0)
                elif 16 <= hour < 19:
                    base = profile.get('peak_avg_p', 30.0)
                else:
                    base = profile.get('day_avg_p', 18.0)
            
            elif profile['type'] == 'agile_volatile':
                # Extreme volatility
                min_p, max_p = profile['range_p']
                base = random.uniform(min_p, max_p)
            
            elif profile['type'] in ['agile_typical', 'agile_extreme']:
                # Typical Agile pattern
                if 0 <= hour < 7:
                    base = profile['overnight_avg_p']
                    variation = 3.0
                elif 7 <= hour < 9:
                    base = profile.get('peak_avg_p', 28.0) * 0.8
                    variation = 3.0
                elif 9 <= hour < 16:
                    base = profile['day_avg_p']
                    variation = 2.0
                elif 16 <= hour < 19:
                    base = profile['peak_avg_p']
                    variation = 5.0
                else:
                    base = profile['day_avg_p']
                    variation = 2.0
                
                # Add random variation (unless volatile)
                if profile['type'] != 'agile_volatile':
                    price = base + (random.random() - 0.5) * variation
                else:
                    price = base
            else:
                base = 18.0
                price = base
            
            import_prices.append({
                'time': time,
                'price': round(price, 2) if 'price' in locals() else round(base, 2),
                'is_predicted': False
            })
            
            export_prices.append({
                'time': time,
                'price': profile.get('export_fixed_p', 15.0)
            })
        
        return import_prices, export_prices
    
    def run_scenario(self, scenario: Dict) -> Dict:
        """Run a single scenario and return results"""
        # Parse date
        start_time = datetime.strptime(scenario['date'], '%Y-%m-%d')
        start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Expand profiles
        solar_forecast = self.expand_solar_profile(scenario['solar_profile'], start_time)
        load_forecast = self.expand_load_profile(scenario['load_profile'], start_time)
        import_prices, export_prices = self.expand_pricing_profile(scenario['pricing'], start_time)
        
        # Build system state
        battery = scenario['battery']
        system_state = {
            'current_state': {
                'battery_soc': battery['soc_start'],
                'battery_power': 0.0,
                'pv_power': 0.0,
                'current_mode': 'Self-Use'
            },
            'capabilities': {
                'battery_capacity': battery['capacity_kwh'],
                'max_charge_rate': battery['max_charge_kw'],
                'max_discharge_rate': battery['max_discharge_kw']
            },
            'active_slots': {'charge': [], 'discharge': []},
            'mode_switch': {
                'entity': 'select.solis_inverter_energy_storage_control_switch',
                'current_mode': 'Self-Use - No Timed Charge/Discharge'
            }
        }
        
        # Run optimizer
        start = time.time()
        plan = self.plan_creator.create_plan(
            import_prices=import_prices,
            export_prices=export_prices,
            solar_forecast=solar_forecast,
            load_forecast=load_forecast,
            system_state=system_state
        )
        runtime = time.time() - start
        
        # Analyze results
        slots = plan['slots']
        
        mode_counts = {}
        feed_in_slots = []
        charge_slots = []
        discharge_slots = []
        
        for slot in slots:
            mode = slot['mode']
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
            
            if mode == 'Feed-in Priority':
                feed_in_slots.append(slot)
            elif mode == 'Force Charge':
                charge_slots.append(slot)
            elif mode == 'Force Discharge':
                discharge_slots.append(slot)
        
        total_cost = plan['metadata'].get('total_cost', 0)
        
        # Calculate battery value change
        battery_capacity = battery['capacity_kwh']
        export_rate = export_prices[0]['price'] / 100  # Convert pence to pounds
        
        start_kwh = battery['soc_start'] / 100 * battery_capacity
        end_kwh = slots[-1]['soc_end'] / 100 * battery_capacity if slots else start_kwh
        
        battery_value_start = start_kwh * export_rate
        battery_value_end = end_kwh * export_rate
        battery_value_change = battery_value_end - battery_value_start
        
        # Adjusted cost accounts for battery value change
        # If battery increases, subtract value (you've stored wealth)
        # If battery decreases, add value (you've consumed wealth)
        adjusted_total_cost = total_cost - battery_value_change
        
        # Calculate clipping (rough estimate)
        clipping_kwh = 0.0
        # TODO: More accurate clipping calculation
        
        results = {
            'scenario_name': scenario['name'],
            'category': scenario['category'],
            'timestamp': datetime.now().isoformat(),
            'runtime_seconds': round(runtime, 3),
            'plan_metadata': plan['metadata'],
            'mode_counts': mode_counts,
            'feed_in_priority_hours': len(feed_in_slots) * 0.5,
            'charge_slot_count': len(charge_slots),
            'discharge_slot_count': len(discharge_slots),
            'total_cost_pounds': round(total_cost, 2),
            'battery_value_start_pounds': round(battery_value_start, 2),
            'battery_value_end_pounds': round(battery_value_end, 2),
            'battery_value_change_pounds': round(battery_value_change, 2),
            'adjusted_total_cost_pounds': round(adjusted_total_cost, 2),
            'clipping_kwh': round(clipping_kwh, 2),
            'battery_start_soc': battery['soc_start'],
            'battery_end_soc': slots[-1]['soc_end'] if slots else battery['soc_start'],
            'validation': self.validate_results(scenario, plan, mode_counts, adjusted_total_cost)
        }
        
        return results
    
    def validate_results(self, scenario: Dict, plan: Dict, mode_counts: Dict, 
                        total_cost: float) -> Dict:
        """Validate results against expected outcomes"""
        expected = scenario.get('expected_outcomes', {})
        validation = {'passed': True, 'failures': []}
        
        # Check Feed-in Priority hours
        if 'feed_in_priority_hours' in expected:
            exp_hours = expected['feed_in_priority_hours']
            actual_hours = mode_counts.get('Feed-in Priority', 0) * 0.5
            
            if exp_hours == 0 and actual_hours > 0:
                validation['passed'] = False
                validation['failures'].append(
                    f"Expected no Feed-in Priority, got {actual_hours}h"
                )
            elif exp_hours != 0 and '>' in str(exp_hours):
                threshold = float(exp_hours.replace('>', ''))
                if actual_hours <= threshold:
                    validation['passed'] = False
                    validation['failures'].append(
                        f"Expected >{threshold}h Feed-in Priority, got {actual_hours}h"
                    )
        
        # Check total cost
        if 'total_cost_max' in expected:
            if total_cost > expected['total_cost_max']:
                validation['passed'] = False
                validation['failures'].append(
                    f"Cost £{total_cost:.2f} exceeds max £{expected['total_cost_max']:.2f}"
                )
        
        # Check clipping
        if 'clipping_kwh' in expected:
            # TODO: Calculate actual clipping
            pass
        
        # Check arbitrage profit (negative cost)
        if expected.get('total_cost_max', 0) < 0:
            if total_cost >= 0:
                validation['passed'] = False
                validation['failures'].append(
                    f"Expected profit, got cost of £{total_cost:.2f}"
                )
        
        return validation
    
    def run_all(self, category: str = None) -> Dict:
        """Run all scenarios and return summary"""
        print("\n" + "="*70)
        print("  SolarBat-AI Test Scenario Runner")
        print("="*70)
        
        scenarios = self.load_scenarios(category)
        
        if not scenarios:
            print(f"\n❌ No scenarios found in {self.scenarios_dir}")
            return None
        
        print(f"\nLoaded {len(scenarios)} scenarios")
        if category:
            print(f"Category: {category}")
        
        results = []
        passed = 0
        failed = 0
        
        for i, scenario in enumerate(scenarios, 1):
            print(f"\n[{i}/{len(scenarios)}] {scenario['category']}/{scenario['name']}")
            print(f"  {scenario['description']}")
            
            try:
                result = self.run_scenario(scenario)
                results.append(result)
                
                # Print key metrics
                print(f"  ⚡ Feed-in Priority: {result['feed_in_priority_hours']:.1f}h")
                print(f"  💰 Raw Cost: £{result['total_cost_pounds']:.2f}")
                print(f"  🔋 Battery Value: £{result['battery_value_start_pounds']:.2f} → £{result['battery_value_end_pounds']:.2f} ({result['battery_value_change_pounds']:+.2f})")
                print(f"  💷 Adjusted Cost: £{result['adjusted_total_cost_pounds']:.2f}")
                print(f"  🔋 SOC: {result['battery_start_soc']:.0f}% → {result['battery_end_soc']:.0f}%")
                
                # Validation
                if result['validation']['passed']:
                    print(f"  ✅ PASS")
                    passed += 1
                else:
                    print(f"  ❌ FAIL")
                    for failure in result['validation']['failures']:
                        print(f"     - {failure}")
                    failed += 1
                
            except Exception as e:
                print(f"  ❌ ERROR: {e}")
                import traceback
                traceback.print_exc()
                failed += 1
        
        # Summary
        print("\n" + "="*70)
        print("  TEST SUMMARY")
        print("="*70)
        print(f"Planner: {self.planner_type.upper()}")
        print(f"Total Scenarios: {len(scenarios)}")
        print(f"Passed: {passed} ({passed/len(scenarios)*100:.1f}%)")
        print(f"Failed: {failed} ({failed/len(scenarios)*100:.1f}%)")
        
        total_raw_cost = sum(r['total_cost_pounds'] for r in results)
        total_adjusted_cost = sum(r['adjusted_total_cost_pounds'] for r in results)
        avg_adjusted_cost = total_adjusted_cost / len(results) if results else 0
        
        print(f"\nTotal Raw Cost: £{total_raw_cost:.2f}")
        print(f"Total Adjusted Cost: £{total_adjusted_cost:.2f} (accounting for battery value)")
        print(f"Average Adjusted Cost: £{avg_adjusted_cost:.2f}/scenario")
        
        total_runtime = sum(r['runtime_seconds'] for r in results)
        print(f"\nTotal Runtime: {total_runtime:.2f}s")
        print(f"Average Runtime: {total_runtime/len(results):.3f}s/scenario")
        
        # Save results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_file = os.path.join(self.results_dir, f'results_{timestamp}.json')
        
        summary = {
            'timestamp': datetime.now().isoformat(),
            'version': 'v2.3',
            'planner_type': self.planner_type,
            'category': category,
            'total_scenarios': len(scenarios),
            'passed': passed,
            'failed': failed,
            'total_raw_cost': round(total_raw_cost, 2),
            'total_adjusted_cost': round(total_adjusted_cost, 2),
            'average_adjusted_cost': round(avg_adjusted_cost, 2),
            'total_runtime': round(total_runtime, 2),
            'results': results
        }
        
        with open(results_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"\n📄 Results saved: {results_file}")
        print("="*70 + "\n")
        
        return summary


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Run test scenarios')
    parser.add_argument('--scenarios-dir', default='./scenarios',
                       help='Directory containing scenarios')
    parser.add_argument('--results-dir', default='./results',
                       help='Directory for results')
    parser.add_argument('--category', choices=['typical', 'edge_cases', 'stress_tests'],
                       help='Run only specific category')
    parser.add_argument('--planner', choices=['rule-based', 'ml', 'lp'],
                       default='rule-based',
                       help='Planner type: rule-based (default), ml (machine learning), lp (linear programming)')
    
    args = parser.parse_args()
    
    runner = ScenarioRunner(args.scenarios_dir, args.results_dir, args.planner)
    
    try:
        runner.run_all(args.category)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test run interrupted")
    except Exception as e:
        print(f"\n\n❌ Test run failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
