"""
Self-Improving ML Planner

Machine learning-based planner that learns from test scenarios
and self-improves by adjusting its own parameters.

Architecture:
1. Feature Extractor - Extracts features from scenarios
2. ML Models - Predict optimal decisions
3. LP Optimizer - Finds optimal path given predictions
4. Self-Trainer - Learns from results, adjusts weights

Requires:
    pip install scikit-learn xgboost
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
import pickle

try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler
    import numpy as np
except ImportError:
    print("ERROR: scikit-learn not installed. Run: pip install scikit-learn")
    sys.exit(1)


class MLPlanner:
    """
    Self-improving ML-based battery planner.
    
    Learns from test scenarios to predict:
    - Should we use Feed-in Priority mode?
    - When to start/end Feed-in Priority?
    - Optimal charge/discharge timing
    - Target SOC levels
    """
    
    def __init__(self, model_dir: str = "./models"):
        self.model_dir = model_dir
        os.makedirs(model_dir, exist_ok=True)
        
        # Models
        self.feed_in_classifier = None
        self.timing_regressor = None
        self.scaler = StandardScaler()
        
        # Training data accumulator
        self.training_data = []
        
        # Load existing models if available
        self.load_models()
    
    def log(self, message: str):
        """Log message"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"[{timestamp}] [ML] {message}")
    
    def extract_features(self, scenario: Dict) -> np.ndarray:
        """
        Extract features from scenario for ML models.
        
        Features:
        - Battery state (SOC, capacity, headroom)
        - Solar forecast (total, peak, surplus)
        - Load forecast (total, peaks)
        - Pricing (spread, peaks, arbitrage opportunity)
        """
        battery = scenario.get('battery', {})
        solar = scenario.get('solar_profile', {})
        load = scenario.get('load_profile', {})
        pricing = scenario.get('pricing', {})
        
        # Battery features
        soc_start = battery.get('soc_start', 50.0)
        capacity = battery.get('capacity_kwh', 10.0)
        headroom_kwh = (95.0 - soc_start) / 100 * capacity
        
        # Solar features
        total_solar = solar.get('total_kwh', 0.0)
        peak_kw = solar.get('peak_kw', 0.0)
        efficiency = solar.get('efficiency', 0.8)
        
        # Load features  
        total_load = load.get('total_kwh', 0.0)
        evening_peak = load.get('evening_peak_kw', 2.0)
        
        # Derived features
        net_surplus = total_solar - total_load
        surplus_ratio = net_surplus / headroom_kwh if headroom_kwh > 0 else 0
        
        # Pricing features
        overnight_price = pricing.get('overnight_avg_p', 12.0)
        peak_price = pricing.get('peak_avg_p', 28.0)
        price_spread = peak_price - overnight_price
        export_price = pricing.get('export_fixed_p', 15.0)
        arbitrage_margin = peak_price - overnight_price - 1.0  # After round-trip losses
        
        features = np.array([
            # Battery (3)
            soc_start,
            capacity,
            headroom_kwh,
            
            # Solar (4)
            total_solar,
            peak_kw,
            efficiency,
            net_surplus,
            
            # Load (2)
            total_load,
            evening_peak,
            
            # Pricing (4)
            overnight_price,
            peak_price,
            price_spread,
            arbitrage_margin,
            
            # Derived (2)
            surplus_ratio,
            net_surplus / capacity if capacity > 0 else 0
        ])
        
        return features
    
    def extract_labels(self, plan_result: Dict) -> Dict:
        """
        Extract labels from plan result for training.
        
        Labels:
        - used_feed_in_priority: bool
        - feed_in_hours: float
        - total_cost: float
        - charge_slots: int
        - discharge_slots: int
        """
        slots = plan_result.get('slots', [])
        metadata = plan_result.get('metadata', {})
        
        feed_in_count = sum(1 for s in slots if s['mode'] == 'Feed-in Priority')
        
        return {
            'used_feed_in_priority': feed_in_count > 0,
            'feed_in_hours': feed_in_count * 0.5,
            'total_cost': metadata.get('total_cost', 0),
            'charge_slots': metadata.get('charge_slots', 0),
            'discharge_slots': metadata.get('discharge_slots', 0)
        }
    
    def train_from_scenarios(self, scenario_results: List[Tuple[Dict, Dict]]):
        """
        Train models from scenario-result pairs.
        
        Args:
            scenario_results: List of (scenario, plan_result) tuples
        """
        self.log(f"Training on {len(scenario_results)} scenarios...")
        
        X = []
        y_feed_in = []
        y_feed_in_hours = []
        
        for scenario, result in scenario_results:
            features = self.extract_features(scenario)
            labels = self.extract_labels(result)
            
            X.append(features)
            y_feed_in.append(1 if labels['used_feed_in_priority'] else 0)
            y_feed_in_hours.append(labels['feed_in_hours'])
            
            # Store for later retraining
            self.training_data.append((scenario, result))
        
        X = np.array(X)
        y_feed_in = np.array(y_feed_in)
        y_feed_in_hours = np.array(y_feed_in_hours)
        
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        
        # Train Feed-in Priority classifier
        self.log("Training Feed-in Priority classifier...")
        self.feed_in_classifier = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42
        )
        self.feed_in_classifier.fit(X_scaled, y_feed_in)
        
        accuracy = self.feed_in_classifier.score(X_scaled, y_feed_in)
        self.log(f"  Classifier accuracy: {accuracy*100:.1f}%")
        
        # Train timing regressor (only on samples where feed-in was used)
        feed_in_mask = y_feed_in == 1
        if np.sum(feed_in_mask) > 0:
            self.log("Training Feed-in Priority timing regressor...")
            self.timing_regressor = GradientBoostingRegressor(
                n_estimators=100,
                max_depth=5,
                random_state=42
            )
            self.timing_regressor.fit(X_scaled[feed_in_mask], y_feed_in_hours[feed_in_mask])
            
            score = self.timing_regressor.score(X_scaled[feed_in_mask], y_feed_in_hours[feed_in_mask])
            self.log(f"  Timing regressor R²: {score:.3f}")
        
        # Save models
        self.save_models()
        
        # Feature importance
        if hasattr(self.feed_in_classifier, 'feature_importances_'):
            importances = self.feed_in_classifier.feature_importances_
            feature_names = [
                'soc_start', 'capacity', 'headroom',
                'total_solar', 'peak_kw', 'efficiency', 'net_surplus',
                'total_load', 'evening_peak',
                'overnight_price', 'peak_price', 'price_spread', 'arbitrage',
                'surplus_ratio', 'surplus_per_kwh'
            ]
            
            top_features = sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)[:5]
            self.log("Top 5 features:")
            for name, importance in top_features:
                self.log(f"  {name}: {importance:.3f}")
    
    def predict(self, scenario: Dict) -> Dict:
        """
        Predict optimal strategy for scenario.
        
        Returns:
            Dict with predictions:
                - use_feed_in_priority: bool
                - feed_in_hours: float (if applicable)
                - confidence: float
        """
        if self.feed_in_classifier is None:
            self.log("WARNING: No trained model, using heuristics")
            return self._heuristic_predict(scenario)
        
        # Extract and scale features
        features = self.extract_features(scenario).reshape(1, -1)
        features_scaled = self.scaler.transform(features)
        
        # Predict
        use_feed_in = self.feed_in_classifier.predict(features_scaled)[0]
        confidence = np.max(self.feed_in_classifier.predict_proba(features_scaled))
        
        feed_in_hours = 0.0
        if use_feed_in and self.timing_regressor:
            feed_in_hours = self.timing_regressor.predict(features_scaled)[0]
        
        return {
            'use_feed_in_priority': bool(use_feed_in),
            'feed_in_hours': float(feed_in_hours),
            'confidence': float(confidence)
        }
    
    def _heuristic_predict(self, scenario: Dict) -> Dict:
        """Fallback heuristic when no model is trained"""
        battery = scenario.get('battery', {})
        solar = scenario.get('solar_profile', {})
        load = scenario.get('load_profile', {})
        
        soc_start = battery.get('soc_start', 50.0)
        capacity = battery.get('capacity_kwh', 10.0)
        headroom = (95.0 - soc_start) / 100 * capacity
        
        total_solar = solar.get('total_kwh', 0.0)
        total_load = load.get('total_kwh', 0.0)
        net_surplus = total_solar - total_load
        
        # Simple heuristic: use feed-in if surplus > headroom + 2kWh
        use_feed_in = net_surplus > headroom + 2.0
        feed_in_hours = 8.0 if use_feed_in else 0.0
        
        return {
            'use_feed_in_priority': use_feed_in,
            'feed_in_hours': feed_in_hours,
            'confidence': 0.5
        }
    
    def save_models(self):
        """Save trained models to disk"""
        models = {
            'feed_in_classifier': self.feed_in_classifier,
            'timing_regressor': self.timing_regressor,
            'scaler': self.scaler,
            'training_data_count': len(self.training_data)
        }
        
        filepath = os.path.join(self.model_dir, 'ml_planner_models.pkl')
        with open(filepath, 'wb') as f:
            pickle.dump(models, f)
        
        self.log(f"Models saved to {filepath}")
    
    def load_models(self):
        """Load trained models from disk"""
        filepath = os.path.join(self.model_dir, 'ml_planner_models.pkl')
        
        if not os.path.exists(filepath):
            self.log("No saved models found, starting fresh")
            return
        
        try:
            with open(filepath, 'rb') as f:
                models = pickle.load(f)
            
            self.feed_in_classifier = models.get('feed_in_classifier')
            self.timing_regressor = models.get('timing_regressor')
            self.scaler = models.get('scaler')
            
            self.log(f"Models loaded from {filepath}")
            self.log(f"  Trained on {models.get('training_data_count', 0)} scenarios")
        except Exception as e:
            self.log(f"Error loading models: {e}")
    
    def self_improve(self, test_results: Dict, baseline_results: Dict) -> bool:
        """
        Self-improvement: Compare results and retrain if beneficial.
        
        Returns:
            True if improvement found, False otherwise
        """
        current_cost = test_results.get('total_adjusted_cost', 0)
        baseline_cost = baseline_results.get('total_adjusted_cost', 0)
        
        improvement = baseline_cost - current_cost
        improvement_pct = (improvement / baseline_cost * 100) if baseline_cost > 0 else 0
        
        self.log(f"Self-improvement check:")
        self.log(f"  Current: £{current_cost:.2f}")
        self.log(f"  Baseline: £{baseline_cost:.2f}")
        self.log(f"  Improvement: £{improvement:.2f} ({improvement_pct:+.1f}%)")
        
        if improvement > 0:
            self.log("✅ Improvement found! Keeping current weights")
            return True
        else:
            self.log("❌ No improvement, consider retraining")
            return False


# Example usage
if __name__ == '__main__':
    print("\n" + "="*70)
    print("  Self-Improving ML Planner Test")
    print("="*70)
    
    planner = MLPlanner()
    
    # Mock scenario
    scenario = {
        'battery': {'soc_start': 70.0, 'capacity_kwh': 10.0},
        'solar_profile': {'total_kwh': 68.5, 'peak_kw': 17.0, 'efficiency': 0.8},
        'load_profile': {'total_kwh': 12.4, 'evening_peak_kw': 2.5},
        'pricing': {'overnight_avg_p': 12.0, 'peak_avg_p': 28.0, 'export_fixed_p': 15.0}
    }
    
    # Predict
    prediction = planner.predict(scenario)
    print(f"\n✅ Prediction:")
    print(f"   Use Feed-in Priority: {prediction['use_feed_in_priority']}")
    print(f"   Feed-in Hours: {prediction['feed_in_hours']:.1f}h")
    print(f"   Confidence: {prediction['confidence']:.2f}")
