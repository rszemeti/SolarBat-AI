"""
ML Planner Training Script

Trains the ML planner on test scenarios using the current rule-based planner
as the "teacher". The ML model learns to predict optimal decisions.

Workflow:
1. Load test scenarios
2. Run current planner on each scenario
3. Extract features and labels
4. Train ML models
5. Validate on held-out test set
6. Save trained models

Usage:
    python train_ml_planner.py                              # Train on all scenarios
    python train_ml_planner.py --category typical           # Train on specific category
    python train_ml_planner.py --results results/xxx.json   # Train from existing results
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from apps.solar_optimizer.planners import RuleBasedPlanner, MLPlanner
from generator import ScenarioGenerator
from runner import ScenarioRunner


class MLTrainer:
    """Trains ML planner on test scenarios"""
    
    def __init__(self, scenarios_dir: str = "./scenarios"):
        self.scenarios_dir = scenarios_dir
        self.ml_planner = MLPlanner()
        self.rule_based_planner = RuleBasedPlanner()
        self.runner = ScenarioRunner(scenarios_dir)
    
    def log(self, message: str):
        """Log message"""
        print(f"[TRAIN] {message}")
    
    def generate_training_data(self, category: str = None) -> List[Tuple[Dict, Dict]]:
        """
        Generate training data by running rule-based planner on scenarios.
        
        Returns:
            List of (scenario, plan_result) tuples
        """
        self.log("Generating training data from scenarios...")
        
        # Load scenarios
        scenarios = self.runner.load_scenarios(category)
        
        if not scenarios:
            self.log(f"ERROR: No scenarios found in {self.scenarios_dir}")
            return []
        
        self.log(f"Loaded {len(scenarios)} scenarios")
        
        training_data = []
        
        for i, scenario in enumerate(scenarios, 1):
            self.log(f"[{i}/{len(scenarios)}] Processing {scenario['name']}...")
            
            try:
                # Run planner
                result = self.runner.run_scenario(scenario)
                
                # Extract plan
                plan = {
                    'slots': result.get('plan_metadata', {}).get('slots', []),
                    'metadata': result.get('plan_metadata', {})
                }
                
                # Reconstruct full plan from result
                # (runner stores partial data, we need full plan for training)
                import_prices = self._get_prices_from_scenario(scenario, 'import')
                export_prices = self._get_prices_from_scenario(scenario, 'export')
                solar_forecast = self._expand_solar_profile(scenario)
                load_forecast = self._expand_load_profile(scenario)
                
                system_state = {
                    'current_state': {
                        'battery_soc': scenario['battery']['soc_start']
                    },
                    'capabilities': {
                        'battery_capacity': scenario['battery']['capacity_kwh'],
                        'max_charge_rate': scenario['battery']['max_charge_kw'],
                        'max_discharge_rate': scenario['battery']['max_discharge_kw']
                    }
                }
                
                # Run planner to get full plan
                plan = self.rule_based_planner.create_plan(
                    import_prices=import_prices,
                    export_prices=export_prices,
                    solar_forecast=solar_forecast,
                    load_forecast=load_forecast,
                    system_state=system_state
                )
                
                training_data.append((scenario, plan))
                
                # Show summary
                feed_in_count = sum(1 for s in plan['slots'] if s['mode'] == 'Feed-in Priority')
                self.log(f"  Feed-in Priority: {feed_in_count * 0.5:.1f}h, "
                        f"Cost: £{plan['metadata']['total_cost']:.2f}")
                
            except Exception as e:
                self.log(f"  ERROR: {e}")
                import traceback
                traceback.print_exc()
        
        return training_data
    
    def _get_prices_from_scenario(self, scenario: Dict, price_type: str) -> List[Dict]:
        """Generate price list from scenario"""
        from datetime import datetime, timedelta
        
        start_time = datetime.strptime(scenario['date'], '%Y-%m-%d')
        prices = []
        
        for t in range(48):
            time = start_time + timedelta(minutes=30*t)
            price = 15.0  # Default
            
            if price_type == 'export':
                price = scenario['pricing'].get('export_fixed_p', 15.0)
            else:  # import
                hour = time.hour
                pricing = scenario['pricing']
                
                if 0 <= hour < 7:
                    price = pricing.get('overnight_avg_p', 12.0)
                elif 16 <= hour < 19:
                    price = pricing.get('peak_avg_p', 28.0)
                else:
                    price = pricing.get('day_avg_p', 18.0)
            
            prices.append({'time': time, 'price': price})
        
        return prices
    
    def _expand_solar_profile(self, scenario: Dict) -> List[Dict]:
        """Expand solar profile"""
        start_time = datetime.strptime(scenario['date'], '%Y-%m-%d')
        return self.runner.expand_solar_profile(
            scenario['solar_profile'],
            start_time
        )
    
    def _expand_load_profile(self, scenario: Dict) -> List[Dict]:
        """Expand load profile"""
        start_time = datetime.strptime(scenario['date'], '%Y-%m-%d')
        return self.runner.expand_load_profile(
            scenario['load_profile'],
            start_time
        )
    
    def train_from_data(self, training_data: List[Tuple[Dict, Dict]],
                       test_split: float = 0.2):
        """
        Train ML models on training data with train/test split.
        
        Args:
            training_data: List of (scenario, plan) tuples
            test_split: Fraction to hold out for testing
        """
        if not training_data:
            self.log("ERROR: No training data provided")
            return
        
        self.log(f"\nTraining ML models on {len(training_data)} scenarios...")
        
        # Split into train/test
        n_test = int(len(training_data) * test_split)
        n_train = len(training_data) - n_test
        
        # Shuffle
        import random
        random.seed(42)
        shuffled = training_data.copy()
        random.shuffle(shuffled)
        
        train_data = shuffled[:n_train]
        test_data = shuffled[n_train:]
        
        self.log(f"Train set: {n_train} scenarios")
        self.log(f"Test set: {n_test} scenarios")
        
        # Train models
        self.ml_planner.train_from_scenarios(train_data)
        
        # Evaluate on test set
        if test_data:
            self.log("\n" + "="*70)
            self.log("Evaluating on test set...")
            self.log("="*70)
            
            self._evaluate_on_test_set(test_data)
    
    def _evaluate_on_test_set(self, test_data: List[Tuple[Dict, Dict]]):
        """Evaluate ML predictions on test set"""
        correct_feed_in = 0
        total = len(test_data)
        
        feed_in_hours_errors = []
        
        for scenario, actual_plan in test_data:
            # Get actual labels
            actual_labels = self.ml_planner.extract_labels(actual_plan)
            
            # Get ML prediction
            prediction = self.ml_planner.predict(scenario)
            
            # Check Feed-in Priority classification
            if prediction['use_feed_in_priority'] == actual_labels['used_feed_in_priority']:
                correct_feed_in += 1
            
            # Track hours prediction error
            if actual_labels['used_feed_in_priority']:
                error = abs(prediction['feed_in_hours'] - actual_labels['feed_in_hours'])
                feed_in_hours_errors.append(error)
        
        # Print metrics
        accuracy = correct_feed_in / total * 100
        self.log(f"\nFeed-in Priority Classification:")
        self.log(f"  Accuracy: {accuracy:.1f}% ({correct_feed_in}/{total})")
        
        if feed_in_hours_errors:
            mae = np.mean(feed_in_hours_errors)
            self.log(f"\nFeed-in Priority Timing:")
            self.log(f"  Mean Absolute Error: {mae:.2f} hours")
        
        # Show some example predictions
        self.log("\nExample Predictions:")
        for i, (scenario, actual_plan) in enumerate(test_data[:3]):
            actual_labels = self.ml_planner.extract_labels(actual_plan)
            prediction = self.ml_planner.predict(scenario)
            
            self.log(f"\n{i+1}. {scenario['name']}:")
            self.log(f"   Actual: Feed-in={actual_labels['used_feed_in_priority']}, "
                    f"Hours={actual_labels['feed_in_hours']:.1f}h")
            self.log(f"   Predicted: Feed-in={prediction['use_feed_in_priority']}, "
                    f"Hours={prediction['feed_in_hours']:.1f}h, "
                    f"Confidence={prediction['confidence']:.2f}")
    
    def load_from_results_file(self, results_file: str) -> List[Tuple[Dict, Dict]]:
        """
        Load training data from existing test results file.
        
        Args:
            results_file: Path to results JSON file
            
        Returns:
            List of (scenario, plan) tuples
        """
        self.log(f"Loading training data from {results_file}...")
        
        with open(results_file, 'r') as f:
            results = json.load(f)
        
        training_data = []
        
        # Load scenarios from disk
        scenarios = self.runner.load_scenarios(results.get('category'))
        scenario_map = {s['name']: s for s in scenarios}
        
        for result in results['results']:
            scenario_name = result['scenario_name']
            
            if scenario_name not in scenario_map:
                self.log(f"  WARNING: Scenario {scenario_name} not found, skipping")
                continue
            
            scenario = scenario_map[scenario_name]
            
            # Reconstruct plan from result
            # (We need to re-run to get full plan details)
            try:
                import_prices = self._get_prices_from_scenario(scenario, 'import')
                export_prices = self._get_prices_from_scenario(scenario, 'export')
                solar_forecast = self._expand_solar_profile(scenario)
                load_forecast = self._expand_load_profile(scenario)
                
                system_state = {
                    'current_state': {'battery_soc': scenario['battery']['soc_start']},
                    'capabilities': {
                        'battery_capacity': scenario['battery']['capacity_kwh'],
                        'max_charge_rate': scenario['battery']['max_charge_kw'],
                        'max_discharge_rate': scenario['battery']['max_discharge_kw']
                    }
                }
                
                plan = self.rule_based_planner.create_plan(
                    import_prices, export_prices, solar_forecast, load_forecast, system_state
                )
                
                training_data.append((scenario, plan))
                
            except Exception as e:
                self.log(f"  ERROR processing {scenario_name}: {e}")
        
        self.log(f"Loaded {len(training_data)} training examples")
        return training_data


def main():
    parser = argparse.ArgumentParser(description='Train ML planner')
    parser.add_argument('--scenarios-dir', default='./scenarios',
                       help='Directory containing scenarios')
    parser.add_argument('--category', choices=['typical', 'edge_cases', 'stress_tests'],
                       help='Train on specific category only')
    parser.add_argument('--results', help='Load training data from existing results file')
    parser.add_argument('--test-split', type=float, default=0.2,
                       help='Fraction of data to use for testing (default: 0.2)')
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("  ML Planner Training")
    print("="*70)
    
    trainer = MLTrainer(args.scenarios_dir)
    
    try:
        # Load or generate training data
        if args.results:
            training_data = trainer.load_from_results_file(args.results)
        else:
            # First check if scenarios exist, if not generate them
            scenarios = trainer.runner.load_scenarios(args.category)
            if not scenarios:
                print("\n[TRAIN] No scenarios found. Generating...")
                generator = ScenarioGenerator(args.scenarios_dir)
                generator.generate_all()
            
            training_data = trainer.generate_training_data(args.category)
        
        if not training_data:
            print("\n[ERROR] No training data available")
            sys.exit(1)
        
        # Train models
        trainer.train_from_data(training_data, test_split=args.test_split)
        
        print("\n" + "="*70)
        print("✅ Training complete!")
        print("="*70)
        print("\nNext steps:")
        print("  1. Test ML planner: python test_ml_planner.py")
        print("  2. Compare vs rule-based: python runner.py --planner ml")
        print("  3. Use in production: Edit solar_optimizer.py to use MLPlanner")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Training interrupted")
    except Exception as e:
        print(f"\n\n❌ Training failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
