"""
Self-Improving ML Planner

Machine learning-based planner that learns from test scenarios
and self-improves by adjusting its own parameters.

Architecture:
1. Feature Extractor - Extracts features from scenarios
2. ML Models - Predict optimal decisions
3. LP Optimizer - Finds optimal path given predictions
4. Self-Trainer - Learns from results, adjusts weights

Inherits from BasePlanner to ensure consistent interface.

Requires:
    pip install scikit-learn xgboost
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
import pickle

# Import base planner
from .base_planner import BasePlanner

try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler
    import numpy as np
except ImportError:
    print("ERROR: scikit-learn not installed. Run: pip install scikit-learn")
    sys.exit(1)


class MLPlanner(BasePlanner):
    """
    Self-improving ML-based battery planner.
    
    Learns from test scenarios to predict:
    - Should we use Feed-in Priority mode?
    - When to start/end Feed-in Priority?
    - Optimal charge/discharge timing
    - Target SOC levels
    """
    
    def __init__(self, model_dir: str = "./models", charge_efficiency=None, discharge_efficiency=None, min_profit_margin=None):
        super().__init__(charge_efficiency, discharge_efficiency, min_profit_margin)
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
        arbitrage_margin = (peak_price * self.round_trip_efficiency) - overnight_price
        
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
        peak_solar = solar.get('peak_kw', 0.0)
        net_surplus = total_solar - total_load
        
        # Simple heuristic: use feed-in if surplus > headroom + 2kWh
        use_feed_in = net_surplus > headroom + 2.0 or peak_solar > 5.0
        
        # Calculate Feed-in hours based on surplus ratio
        # More surplus = longer Feed-in Priority window
        if use_feed_in:
            surplus_ratio = net_surplus / max(headroom, 1.0)
            if surplus_ratio > 10.0:
                feed_in_hours = 14.0  # Massive solar
            elif surplus_ratio > 5.0:
                feed_in_hours = 12.0  # Very high solar
            elif surplus_ratio > 2.0:
                feed_in_hours = 10.0  # High solar
            else:
                feed_in_hours = 8.0   # Moderate solar
        else:
            feed_in_hours = 0.0
        
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
    
    def create_plan(self,
                   import_prices: List[Dict],
                   export_prices: List[Dict],
                   solar_forecast: List[Dict],
                   load_forecast: List[Dict],
                   system_state: Dict) -> Dict:
        """
        Create optimization plan using ML predictions + backwards simulation.
        
        Unlike the rule-based planner which uses fixed heuristics, this:
        1. Uses ML to predict optimal strategy parameters
        2. Applies backwards simulation with ML-guided parameters
        3. Falls back to heuristics if ML is untrained
        """
        self.log("Creating optimal plan using ML predictions...")
        
        # Extract system state
        current_state = system_state.get('current_state', {})
        capabilities = system_state.get('capabilities', {})
        
        battery_soc = current_state.get('battery_soc', 50.0)
        battery_capacity = capabilities.get('battery_capacity', 10.0)
        max_charge_rate = capabilities.get('max_charge_rate', 3.0)
        max_discharge_rate = capabilities.get('max_discharge_rate', 3.0)
        
        export_price_value = export_prices[0]['price'] if export_prices else 15.0
        
        self.log(f"Starting SOC: {battery_soc:.1f}%")
        self.log(f"Battery: {battery_capacity}kWh, Charge: {max_charge_rate}kW, Discharge: {max_discharge_rate}kW")
        
        # Build scenario for ML prediction
        total_solar = sum(s['kw'] * 0.5 for s in solar_forecast)
        total_load = sum(l['load_kw'] * 0.5 for l in load_forecast)
        peak_solar = max(s['kw'] for s in solar_forecast) if solar_forecast else 0
        
        scenario = {
            'battery': {
                'soc_start': battery_soc,
                'capacity_kwh': battery_capacity,
                'max_charge_kw': max_charge_rate,
                'max_discharge_kw': max_discharge_rate
            },
            'solar_profile': {
                'total_kwh': total_solar,
                'peak_kw': peak_solar,
                'efficiency': 0.8
            },
            'load_profile': {
                'total_kwh': total_load,
                'evening_peak_kw': 2.5
            },
            'pricing': {
                'overnight_avg_p': 12.0,
                'peak_avg_p': 28.0,
                'export_fixed_p': export_price_value
            }
        }
        
        # Get ML predictions
        prediction = self.predict(scenario)
        self.log(f"ML Prediction: Feed-in={prediction['use_feed_in_priority']}, Hours={prediction['feed_in_hours']:.1f}h")
        
        # Convert to internal format
        prices_internal = [{'start': p['time'], 'price': p['price'], 'is_predicted': p.get('is_predicted', False)} 
                          for p in import_prices]
        solar_internal = [{'period_end': s['time'], 'pv_estimate': s['kw']} 
                         for s in solar_forecast]
        load_internal = load_forecast
        
        # Run ML-guided optimization
        plan_slots = self._optimize_with_ml_guidance(
            prices=prices_internal,
            solar_forecast=solar_internal,
            load_forecast=load_internal,
            battery_soc=battery_soc,
            battery_capacity=battery_capacity,
            max_charge_rate=max_charge_rate,
            max_discharge_rate=max_discharge_rate,
            export_price=export_price_value,
            ml_prediction=prediction,
            min_soc=10.0,
            max_soc=95.0
        )
        
        # Build plan object
        total_cost = plan_slots[-1].get('cumulative_cost', 0) / 100 if plan_slots else 0.0
        
        plan = {
            'timestamp': datetime.now(),
            'slots': plan_slots,
            'metadata': {
                'total_cost': total_cost,
                'confidence': 'high',
                'data_sources': {
                    'import_prices': len(import_prices),
                    'export_prices': len(export_prices),
                    'solar_forecast': len(solar_forecast),
                    'load_forecast': len(load_forecast)
                },
                'charge_slots': sum(1 for s in plan_slots if s['mode'] == 'Force Charge'),
                'discharge_slots': sum(1 for s in plan_slots if s['mode'] == 'Force Discharge'),
                'ml_prediction': prediction,
                'planner_type': 'ml_independent'
            }
        }
        
        self.log(f"Plan complete: {plan['metadata']['charge_slots']} charge, {plan['metadata']['discharge_slots']} discharge, cost: £{total_cost:.2f}")
        
        return plan
    
    def _optimize_with_ml_guidance(self,
                                   prices: List[Dict],
                                   solar_forecast: List[Dict],
                                   load_forecast: List[Dict],
                                   battery_soc: float,
                                   battery_capacity: float,
                                   max_charge_rate: float,
                                   max_discharge_rate: float,
                                   export_price: float,
                                   ml_prediction: Dict,
                                   min_soc: float = 10.0,
                                   max_soc: float = 95.0) -> List[Dict]:
        """
        Optimize using ML predictions to guide strategy.
        
        This is the ML planner's independent implementation with:
        - ML-predicted Feed-in Priority windows
        - ML-predicted pre-sunrise discharge targets
        - Backwards simulation (like rule-based but ML-guided)
        """
        self.log("Generating ML-guided plan...")
        
        plan = []
        current_soc = battery_soc
        
        # Align forecasts to 30-min slots
        slots = self._align_forecasts(prices, solar_forecast, load_forecast)
        
        self.log(f"Planning for {len(slots)} slots")
        
        # Get ML-guided strategy decisions
        feed_in_strategy = self._ml_guided_feed_in_strategy(
            slots, current_soc, battery_capacity, ml_prediction, max_charge_rate
        )
        
        presunrise_strategy = self._ml_guided_presunrise_discharge(
            slots, current_soc, battery_capacity, max_discharge_rate, 
            feed_in_strategy, ml_prediction
        )
        
        # Re-run feed-in with post-discharge SOC if pre-sunrise will happen
        if presunrise_strategy['use_strategy']:
            post_discharge_soc = presunrise_strategy['target_soc']
            if post_discharge_soc != current_soc:
                feed_in_strategy = self._ml_guided_feed_in_strategy(
                    slots, post_discharge_soc, battery_capacity, ml_prediction, max_charge_rate
                )
        
        if feed_in_strategy['use_strategy']:
            self.log(f"📊 ML-GUIDED Feed-in Priority: {feed_in_strategy['start_time'].strftime('%H:%M')}-{feed_in_strategy['end_time'].strftime('%H:%M')}")
            self.log(f"   {feed_in_strategy['reason']}")
        
        if presunrise_strategy['use_strategy']:
            self.log(f"🌅 ML-GUIDED Pre-sunrise Discharge: {presunrise_strategy['start_time'].strftime('%H:%M')}-{presunrise_strategy['end_time'].strftime('%H:%M')}")
            self.log(f"   Target: {presunrise_strategy['target_soc']:.0f}% SOC")
        
        # Create physics model for simulation
        from .inverter_physics import InverterPhysics
        physics = InverterPhysics(
            battery_capacity=battery_capacity,
            max_charge_rate=max_charge_rate,
            max_discharge_rate=max_discharge_rate,
            charge_efficiency=self.charge_efficiency,
            discharge_efficiency=self.discharge_efficiency,
            export_limit=5.0,
            min_soc=min_soc,
            max_soc=max_soc
        )
        
        # Optimize each slot
        cumulative_cost = 0.0
        
        for i, slot in enumerate(slots):
            solar_kw = slot['solar_kw']
            load_kw = slot['load_kw']
            solar_kwh = solar_kw * 0.5
            load_kwh = load_kw * 0.5
            import_price = slot['import_price']
            
            # Future lookahead
            future_deficit = self._calculate_future_deficit(
                slots[i:], current_soc, battery_capacity, min_soc
            )
            future_solar_surplus = self._calculate_future_solar_surplus(slots[i:])
            future_min_price = min((s['import_price'] for s in slots[i:]), default=import_price)
            
            # Decide mode with ML guidance (mode decision only)
            mode, _action, _soc_change = self._decide_mode_ml_guided(
                slot=slot,
                feed_in_strategy=feed_in_strategy,
                presunrise_strategy=presunrise_strategy,
                current_soc=current_soc,
                solar_kwh=solar_kwh,
                load_kwh=load_kwh,
                import_price=import_price,
                export_price=export_price,
                future_deficit=future_deficit,
                future_solar_surplus=future_solar_surplus,
                future_min_price=future_min_price,
                battery_capacity=battery_capacity,
                max_charge_rate=max_charge_rate,
                max_discharge_rate=max_discharge_rate,
                min_soc=min_soc,
                max_soc=max_soc
            )
            
            # Use physics model for actual simulation
            target_soc = presunrise_strategy.get('target_soc') if mode == 'Force Discharge' and presunrise_strategy.get('use_strategy') else None
            
            if mode == 'Feed-in Priority':
                result = physics.simulate_feed_in_priority(solar_kw, load_kw, current_soc, import_price, export_price)
            elif mode == 'Force Charge':
                result = physics.simulate_force_charge(solar_kw, load_kw, current_soc, max_charge_rate, import_price, export_price)
            elif mode == 'Force Discharge':
                result = physics.simulate_force_discharge(solar_kw, load_kw, current_soc, max_discharge_rate, import_price, export_price, target_soc=target_soc)
            else:  # Self Use
                result = physics.simulate_self_use(solar_kw, load_kw, current_soc, import_price, export_price)
            
            # Apply result
            action = result.action
            soc_change = result.soc_change
            new_soc = max(min_soc, min(max_soc, current_soc + soc_change))
            cost_impact = result.cost_pence
            
            cumulative_cost += cost_impact
            
            plan.append({
                'time': slot['time'],
                'mode': mode,
                'action': action,
                'soc_end': new_soc,
                'solar_kw': slot['solar_kw'],
                'load_kw': slot['load_kw'],
                'import_price': import_price,
                'export_price': export_price,
                'soc_change': soc_change,
                'cumulative_cost': cumulative_cost
            })
            
            current_soc = new_soc
        
        self.log(f"[OPT] Plan complete: {sum(1 for s in plan if s['mode']=='Force Charge')} charge slots, "
                f"{sum(1 for s in plan if s['mode']=='Force Discharge')} discharge slots")
        self.log(f"[OPT] Total estimated cost: £{cumulative_cost/100:.2f} over 24 hours")
        
        return plan


    def _align_forecasts(self, prices, solar_forecast, load_forecast) -> List[Dict]:
        """Align all forecasts to common 30-min time slots"""
        slots = []
        
        for price in prices[:48]:
            slot_time = price['start']
            
            # Find matching solar
            solar_kw = 0.0
            for sf in solar_forecast:
                time_diff = abs((sf['period_end'] - slot_time).total_seconds())
                if time_diff < 300:
                    solar_kw = sf['pv_estimate']
                    break
            
            # Find matching load
            load_kw = 1.0
            for lf in load_forecast:
                time_diff = abs((lf['time'] - slot_time).total_seconds())
                if time_diff < 300:
                    load_kw = lf['load_kw']
                    break
            
            slots.append({
                'time': slot_time,
                'solar_kw': solar_kw,
                'load_kw': load_kw,
                'import_price': price['price']
            })
        
        return slots
    
    def _ml_guided_feed_in_strategy(self, slots, current_soc, battery_capacity, ml_prediction, max_charge_rate=None):
        """Use ML to decide IF to use Feed-in Priority, but physics-based backwards
        simulation to determine WHEN to transition to Self-Use.
        
        The ML model predicts whether feed-in is beneficial, but the actual
        transition timing must come from physics to ensure battery fills by end of solar.
        """
        
        if not ml_prediction['use_feed_in_priority']:
            return {'use_strategy': False, 'reason': 'ML predicts no Feed-in Priority needed'}
        
        # Find solar window
        fi_start_idx = None
        fi_solar_end_idx = None
        
        for i, slot in enumerate(slots):
            if slot.get('solar_kw', 0) > 0.5:
                if fi_start_idx is None:
                    fi_start_idx = i
                fi_solar_end_idx = i
        
        if fi_start_idx is None or fi_solar_end_idx is None:
            return {'use_strategy': False, 'reason': 'No solar detected'}
        
        max_soc = 95.0
        max_charge_rate_kw = max_charge_rate if max_charge_rate else battery_capacity / 4
        export_limit = 5.0
        
        # ── Forward sim in Self-Use to check if clipping occurs ──
        su_soc = current_soc
        su_clipped = 0
        su_full_at_idx = None
        
        for i in range(fi_start_idx, fi_solar_end_idx + 1):
            slot = slots[i]
            solar_kw = slot.get('solar_kw', 0)
            load_kw = slot.get('load_kw', 0)
            net_solar = max(0, solar_kw - load_kw)
            
            headroom = max(0, (max_soc - su_soc) / 100 * battery_capacity)
            charge_kwh = min(net_solar * 0.5, max_charge_rate_kw * 0.5, headroom)
            remaining = net_solar - charge_kwh * 2
            grid_kw = min(remaining, export_limit)
            clip = max(0, remaining - export_limit) * 0.5
            
            su_soc = min(max_soc, su_soc + (charge_kwh / battery_capacity) * 100)
            su_clipped += clip
            
            if solar_kw < load_kw:
                drain = min((load_kw - solar_kw) * 0.5, (su_soc - 10) / 100 * battery_capacity)
                su_soc = max(10, su_soc - (drain / battery_capacity) * 100)
            
            if su_soc >= max_soc and su_full_at_idx is None and net_solar > 0.5:
                su_full_at_idx = i
        
        if su_clipped < 2.0:
            return {'use_strategy': False, 'reason': f'ML suggested feed-in but only {su_clipped:.1f}kWh clipping'}
        
        # ── Backwards simulation to find transition point ──
        backward_soc = max_soc
        transition_idx = fi_start_idx
        
        for i in range(fi_solar_end_idx, fi_start_idx - 1, -1):
            slot = slots[i]
            solar_kw = slot.get('solar_kw', 0)
            load_kw = slot.get('load_kw', 0)
            net_solar = solar_kw - load_kw
            
            if net_solar > 0:
                charge_kwh = min(net_solar * 0.5, max_charge_rate_kw * 0.5)
                soc_change = (charge_kwh / battery_capacity) * 100
                potential_soc = backward_soc - soc_change
                
                if potential_soc < current_soc:
                    transition_idx = i
                    break
                backward_soc = potential_soc
            else:
                drain_kwh = abs(net_solar) * 0.5
                soc_change = (drain_kwh / battery_capacity) * 100
                backward_soc = min(max_soc, backward_soc + soc_change)
            
            transition_idx = i
        
        # ── Validate with forward sim ──
        fi_soc = current_soc
        fi_clipped = 0
        fi_full_at_idx = None
        
        for i in range(fi_start_idx, fi_solar_end_idx + 1):
            slot = slots[i]
            solar_kw = slot.get('solar_kw', 0)
            load_kw = slot.get('load_kw', 0)
            
            if i < transition_idx:
                grid_kw = min(solar_kw, export_limit)
                after_grid = solar_kw - grid_kw
                load_from_solar = min(after_grid, load_kw)
                after_load = after_grid - load_from_solar
                headroom = max(0, (max_soc - fi_soc) / 100 * battery_capacity)
                charge_kwh = min(after_load * 0.5, max_charge_rate_kw * 0.5, headroom)
                fi_soc = min(max_soc, fi_soc + (charge_kwh / battery_capacity) * 100)
                fi_clipped += max(0, after_load * 0.5 - charge_kwh)
                if load_from_solar < load_kw:
                    drain = min((load_kw - load_from_solar) * 0.5, (fi_soc - 10) / 100 * battery_capacity)
                    fi_soc = max(10, fi_soc - (drain / battery_capacity) * 100)
            else:
                net_solar = max(0, solar_kw - load_kw)
                headroom = max(0, (max_soc - fi_soc) / 100 * battery_capacity)
                charge_kwh = min(net_solar * 0.5, max_charge_rate_kw * 0.5, headroom)
                remaining = net_solar - charge_kwh * 2
                fi_clipped += max(0, remaining - export_limit) * 0.5
                fi_soc = min(max_soc, fi_soc + (charge_kwh / battery_capacity) * 100)
                if solar_kw < load_kw:
                    drain = min((load_kw - solar_kw) * 0.5, (fi_soc - 10) / 100 * battery_capacity)
                    fi_soc = max(10, fi_soc - (drain / battery_capacity) * 100)
            
            if fi_soc >= max_soc and fi_full_at_idx is None:
                fi_full_at_idx = i
        
        clip_saved = su_clipped - fi_clipped
        if clip_saved < 2.0:
            return {'use_strategy': False, 'reason': f'Feed-in only saves {clip_saved:.1f}kWh'}
        
        start_time = slots[fi_start_idx]['time']
        transition_time = slots[transition_idx]['time']
        su_full_time = slots[su_full_at_idx]['time'].strftime('%H:%M') if su_full_at_idx else 'never'
        fi_full_time = slots[fi_full_at_idx]['time'].strftime('%H:%M') if fi_full_at_idx else 'never'
        
        return {
            'use_strategy': True,
            'start_time': start_time,
            'end_time': transition_time,
            'reason': (f"ML+physics: saves {clip_saved:.1f}kWh, "
                      f"full at {su_full_time} (Self-Use) vs {fi_full_time} (Feed-in)")
        }
    
    def _ml_guided_presunrise_discharge(self, slots, current_soc, battery_capacity, 
                                       max_discharge_rate, feed_in_strategy, ml_prediction):
        """Use ML to guide pre-sunrise discharge decisions.
        
        Accounts for natural Self-Use drain before sunrise and starts
        forced discharge as LATE as possible.
        """
        import math
        
        now = slots[0]['time'] if slots else datetime.now()
        
        # Find sunrise
        sunrise_time = None
        sunrise_slot_idx = None
        for i, slot in enumerate(slots):
            if slot['solar_kw'] > 0.5:
                sunrise_time = slot['time']
                sunrise_slot_idx = i
                break
        
        if not sunrise_time:
            return {'use_strategy': False, 'reason': 'No sunrise detected'}
        
        # Step 1: Calculate battery absorption during solar hours
        export_limit = 5.0
        battery_absorption_kwh = 0
        
        for slot in slots:
            solar_kw = slot.get('solar_kw', 0)
            load_kw = slot.get('load_kw', 0)
            if solar_kw < 0.5:
                continue
            
            if feed_in_strategy['use_strategy']:
                slot_time = slot['time']
                if feed_in_strategy['start_time'] <= slot_time <= feed_in_strategy['end_time']:
                    after_grid = max(0, solar_kw - export_limit)
                    after_load = max(0, after_grid - load_kw)
                    battery_absorption_kwh += after_load * 0.5
                else:
                    net = max(0, solar_kw - load_kw)
                    battery_absorption_kwh += net * 0.5
            else:
                net = max(0, solar_kw - load_kw)
                battery_absorption_kwh += net * 0.5
        
        # Step 2: Forward-simulate natural drain to sunrise
        soc_at_sunrise = current_soc
        for i in range(sunrise_slot_idx):
            load_kw = slots[i].get('load_kw', 0)
            solar_kw = slots[i].get('solar_kw', 0)
            net_drain = max(0, load_kw - solar_kw)
            drain_kwh = net_drain * 0.5
            soc_drop = (drain_kwh / battery_capacity) * 100
            soc_at_sunrise = max(15.0, soc_at_sunrise - soc_drop)
        
        # Step 3: Check if we need forced discharge
        space_at_sunrise_kwh = ((95 - soc_at_sunrise) / 100) * battery_capacity
        space_shortfall = battery_absorption_kwh - space_at_sunrise_kwh
        
        if space_shortfall <= 1.0:
            return {'use_strategy': False, 'reason': f'Sufficient space at sunrise ({space_at_sunrise_kwh:.1f}kWh)'}
        
        # Step 4: Calculate target and forced discharge amount
        needed_discharge_kwh = space_shortfall + 2.0
        max_discharge_kwh = ((soc_at_sunrise - 15.0) / 100) * battery_capacity
        actual_discharge_kwh = min(needed_discharge_kwh, max_discharge_kwh)
        target_soc = max(15.0, soc_at_sunrise - (actual_discharge_kwh / battery_capacity * 100))
        
        forced_discharge_kwh = ((soc_at_sunrise - target_soc) / 100) * battery_capacity
        if forced_discharge_kwh < 0.5:
            return {'use_strategy': False, 'reason': f'Minimal forced discharge needed'}
        
        # Step 5: Start as LATE as possible before sunrise
        discharge_hours = forced_discharge_kwh / max_discharge_rate
        discharge_slots_needed = math.ceil(discharge_hours * 2) + 1
        
        if sunrise_slot_idx < discharge_slots_needed:
            return {'use_strategy': False, 'reason': 'Not enough time before sunrise'}
        
        discharge_start_idx = sunrise_slot_idx - discharge_slots_needed
        discharge_start_time = slots[discharge_start_idx]['time']
        
        if discharge_start_time <= now:
            discharge_start_time = now
        
        return {
            'use_strategy': True,
            'start_time': discharge_start_time,
            'end_time': sunrise_time,
            'target_soc': target_soc,
            'discharge_rate': max_discharge_rate,
            'reason': f"ML-guided pre-sunrise: SOC at sunrise ~{soc_at_sunrise:.0f}%, force to {target_soc:.0f}% ({forced_discharge_kwh:.1f}kWh)"
        }
    
    def _calculate_future_deficit(self, future_slots, current_soc, battery_capacity, min_soc):
        """Calculate if we'll run out of battery"""
        available_kwh = (current_soc - min_soc) / 100 * battery_capacity
        deficit_kwh = 0.0
        
        for slot in future_slots:
            net_need = slot['load_kw'] - slot['solar_kw']
            if net_need > 0:
                if available_kwh >= net_need * 0.5:
                    available_kwh -= net_need * 0.5
                else:
                    deficit_kwh += (net_need * 0.5 - available_kwh)
                    available_kwh = 0
            else:
                available_kwh += min((-net_need * 0.5), (100 - current_soc) / 100 * battery_capacity)
        
        return deficit_kwh
    
    def _calculate_future_solar_surplus(self, future_slots):
        """Calculate excess solar coming"""
        surplus = 0.0
        for slot in future_slots[:12]:
            net = slot['solar_kw'] - slot['load_kw']
            if net > 0:
                surplus += net * 0.5
        return surplus
    
    def _decide_mode_ml_guided(self, slot, feed_in_strategy, presunrise_strategy,
                              current_soc, solar_kwh, load_kwh, import_price, export_price,
                              future_deficit, future_solar_surplus, future_min_price,
                              battery_capacity, max_charge_rate, max_discharge_rate,
                              min_soc, max_soc):
        """Decide mode using ML-guided strategies"""
        
        # Round-trip efficiency from base class settings
        round_trip_efficiency = self.round_trip_efficiency
        min_profit_margin = self.min_profit_margin
        
        # Pre-sunrise discharge - stop if already at target
        if presunrise_strategy['use_strategy']:
            slot_time = slot['time']
            target_soc = presunrise_strategy['target_soc']
            if (presunrise_strategy['start_time'] <= slot_time < presunrise_strategy['end_time']
                and current_soc > target_soc + 1.0):
                soc_deficit = current_soc - target_soc
                max_discharge_kwh = (soc_deficit / 100) * battery_capacity
                discharge_kwh = min(max_discharge_rate * 0.5, max_discharge_kwh)
                soc_change = -(discharge_kwh / battery_capacity) * 100
                return 'Force Discharge', f"ML-guided pre-sunrise discharge", soc_change
        
        # Feed-in Priority: grid gets first 5kW, battery charges from overflow
        if feed_in_strategy['use_strategy']:
            slot_time = slot['time']
            if (feed_in_strategy['start_time'] <= slot_time <= feed_in_strategy['end_time']):
                solar_kw = solar_kwh * 2  # Convert back to kW (solar_kwh is per 30min)
                # Only use Feed-in Priority when there's actual solar to route
                if solar_kw > 0.5:
                    load_kw = load_kwh * 2
                    grid_kw = min(solar_kw, 5.0)
                    after_grid = max(0, solar_kw - grid_kw)
                    load_from_solar = min(after_grid, load_kw)
                    battery_charge_kw = max(0, after_grid - load_from_solar)
                    
                    charge_kwh = min(battery_charge_kw * 0.5,
                                   (max_soc - current_soc) / 100 * battery_capacity)
                    soc_change = (charge_kwh / battery_capacity) * 100
                    
                    # Load not covered drains battery
                    if load_from_solar < load_kw:
                        drain_kw = load_kw - load_from_solar
                        drain_kwh = min(drain_kw * 0.5, (current_soc - min_soc) / 100 * battery_capacity)
                        soc_change -= (drain_kwh / battery_capacity) * 100
                    
                    return 'Feed-in Priority', f"ML-guided grid-first routing", soc_change
        
        # Arbitrage: only if profitable after round-trip losses
        break_even_export = import_price / round_trip_efficiency
        if export_price > break_even_export + min_profit_margin and current_soc < 92:
            charge_kwh = min(max_charge_rate * 0.5, ((92 - current_soc) / 100) * battery_capacity)
            soc_change = (charge_kwh / battery_capacity) * 100
            net_profit = (export_price * round_trip_efficiency) - import_price
            return 'Force Charge', f"Arbitrage: {net_profit:.1f}p/kWh profit after losses", soc_change
        
        # Deficit prevention
        if future_deficit > 0.5 and import_price <= future_min_price + 1.0:
            charge_kwh = min(max_charge_rate * 0.5, ((max_soc - current_soc) / 100) * battery_capacity)
            soc_change = (charge_kwh / battery_capacity) * 100
            return 'Force Charge', f"Deficit prevention", soc_change
        
        # Wastage prevention
        if current_soc > 85 and future_solar_surplus > 2.0:
            discharge_kwh = min(max_discharge_rate * 0.5, ((current_soc - min_soc) / 100) * battery_capacity)
            soc_change = -(discharge_kwh / battery_capacity) * 100
            return 'Force Discharge', f"Wastage prevention", soc_change
        
        # Profitable export: only if export revenue covers recharge cost + losses
        discharge_profit = export_price * round_trip_efficiency - import_price
        if discharge_profit > min_profit_margin and current_soc > min_soc + 10:
            discharge_kwh = min(max_discharge_rate * 0.5, ((current_soc - min_soc) / 100) * battery_capacity)
            soc_change = -(discharge_kwh / battery_capacity) * 100
            return 'Force Discharge', f"Profitable export: {discharge_profit:.1f}p/kWh after losses", soc_change
        
        # Default: Self-Use - battery serves household load
        # SOC drains from net load (load minus any solar)
        net_load = max(0, load_kwh - solar_kwh)  # kwh per 30-min slot
        drain_kwh = min(net_load, (current_soc - min_soc) / 100 * battery_capacity)
        soc_change = -(drain_kwh / battery_capacity) * 100
        return 'Self Use', f"Load {load_kwh:.2f}kWh > Solar {solar_kwh:.2f}kWh, using battery" if net_load > 0 else "Self-use mode", soc_change


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
