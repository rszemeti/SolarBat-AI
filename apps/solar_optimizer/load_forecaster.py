"""
Load Forecaster - AI-Powered Consumption Prediction

Uses Home Assistant historical data to predict future electricity consumption.
Learns from patterns in:
- Time of day
- Day of week
- Recent trends
- Seasonal variations
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import statistics


class LoadForecaster:
    """
    Predicts future electricity consumption based on historical patterns.
    
    Uses multiple prediction methods with confidence weighting:
    1. Same time yesterday (high confidence for stable patterns)
    2. Same time/day last week (accounts for weekday/weekend)
    3. Average for this hour over last 30 days
    4. Recent trend analysis
    """
    
    def __init__(self, hass):
        """
        Initialize load forecaster.
        
        Args:
            hass: Home Assistant API object
        """
        self.hass = hass
        self.load_sensor = None
        self.history_cache = {}
        self.log_func = print  # Default to print, can be overridden
    
    def log(self, message: str, level: str = "INFO"):
        """Log a message"""
        if hasattr(self.hass, 'log'):
            self.hass.log(message, level=level)
        else:
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{timestamp}] {message}")
    
    def setup(self, config: Dict) -> bool:
        """
        Setup load forecaster.
        
        Args:
            config: Configuration dict with 'load_power' sensor
            
        Returns:
            True if setup successful
        """
        try:
            self.load_sensor = config.get('load_power')
            
            if not self.load_sensor:
                self.log("No load_power sensor configured", level="ERROR")
                return False
            
            # Test that sensor exists
            current_load = self.hass.get_state(self.load_sensor)
            if current_load is None:
                self.log(f"Cannot read load sensor: {self.load_sensor}", level="ERROR")
                return False
            
            self.log(f"Load forecaster setup successful (sensor: {self.load_sensor})")
            return True
            
        except Exception as e:
            self.log(f"Failed to setup load forecaster: {e}", level="ERROR")
            return False
    
    def get_historical_load(self, start_time: datetime, end_time: datetime) -> List[Dict]:
        """
        Get historical load data from Home Assistant.
        
        Args:
            start_time: Start of period
            end_time: End of period
            
        Returns:
            List of {'time': datetime, 'load': float} dicts
        """
        try:
            # Check cache first
            cache_key = f"{start_time.isoformat()}_{end_time.isoformat()}"
            if cache_key in self.history_cache:
                return self.history_cache[cache_key]
            
            # Get history from HA
            # Note: In test harness, we'll need to implement get_history
            # In AppDaemon, use: self.hass.get_history()
            
            if hasattr(self.hass, 'get_history'):
                # AppDaemon method
                history = self.hass.get_history(
                    entity_id=self.load_sensor,
                    start_time=start_time,
                    end_time=end_time
                )
            else:
                # Test harness - use REST API
                history = self._get_history_via_api(start_time, end_time)
            
            # Cache result
            self.history_cache[cache_key] = history
            
            # Limit cache size
            if len(self.history_cache) > 100:
                # Remove oldest entry
                oldest_key = min(self.history_cache.keys())
                del self.history_cache[oldest_key]
            
            return history
            
        except Exception as e:
            self.log(f"Error getting historical load: {e}", level="WARNING")
            return []
    
    def _get_history_via_api(self, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Get history via REST API (for test harness)"""
        try:
            import requests
            
            # HA history API endpoint
            url = f"{self.hass.url}/api/history/period/{start_time.isoformat()}"
            params = {
                'filter_entity_id': self.load_sensor,
                'end_time': end_time.isoformat(),
                'minimal_response': 'true',
                'no_attributes': 'true'
            }
            
            response = requests.get(url, headers=self.hass.headers, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Parse response
            history = []
            if data and len(data) > 0:
                for state in data[0]:
                    try:
                        load = float(state.get('state'))
                        timestamp = datetime.fromisoformat(state.get('last_changed').replace('Z', '+00:00')).replace(tzinfo=None)
                        history.append({'time': timestamp, 'load': load})
                    except (ValueError, TypeError):
                        continue
            
            return history
            
        except Exception as e:
            self.log(f"Error getting history via API: {e}", level="WARNING")
            return []
    
    def predict_load(self, target_time: datetime) -> Tuple[float, str]:
        """
        Predict load for a specific time using AI/ML techniques.
        
        Args:
            target_time: Time to predict load for
            
        Returns:
            Tuple of (predicted_load_kw, confidence_level)
        """
        now = datetime.now()
        predictions = []
        
        # Method 1: Same time yesterday
        yesterday = target_time - timedelta(days=1)
        if yesterday < now:  # Only use past data
            yesterday_data = self._get_average_load_for_period(yesterday - timedelta(minutes=15), yesterday + timedelta(minutes=15))
            if yesterday_data:
                predictions.append({
                    'value': yesterday_data,
                    'weight': 3.0,  # High weight - yesterday is usually similar
                    'method': 'yesterday'
                })
        
        # Method 2: Same time/day last week
        last_week = target_time - timedelta(days=7)
        if last_week < now:
            last_week_data = self._get_average_load_for_period(last_week - timedelta(minutes=15), last_week + timedelta(minutes=15))
            if last_week_data:
                predictions.append({
                    'value': last_week_data,
                    'weight': 2.0,  # Medium weight - same weekday matters
                    'method': 'last_week'
                })
        
        # Method 3: Average for this hour over last 30 days
        hour_average = self._get_hour_average(target_time.hour, days_back=30)
        if hour_average:
            predictions.append({
                'value': hour_average,
                'weight': 1.0,  # Lower weight - general pattern
                'method': 'hour_average'
            })
        
        # Method 4: Recent trend (last 7 days at this time)
        trend = self._get_trend_prediction(target_time)
        if trend:
            predictions.append({
                'value': trend,
                'weight': 1.5,
                'method': 'trend'
            })
        
        # Calculate weighted average
        if predictions:
            total_weight = sum(p['weight'] for p in predictions)
            weighted_sum = sum(p['value'] * p['weight'] for p in predictions)
            predicted_load = weighted_sum / total_weight
            
            # Determine confidence based on agreement between methods
            if len(predictions) >= 3:
                # Check standard deviation
                values = [p['value'] for p in predictions]
                std_dev = statistics.stdev(values) if len(values) > 1 else 0
                avg = statistics.mean(values)
                
                if std_dev < avg * 0.2:  # Low variation
                    confidence = 'high'
                elif std_dev < avg * 0.4:
                    confidence = 'medium'
                else:
                    confidence = 'low'
            else:
                confidence = 'low'
            
            return predicted_load, confidence
        else:
            # Fallback: use current load or default
            current_watts = float(self.hass.get_state(self.load_sensor) or 1000.0)
            current_kw = current_watts / 1000.0  # Convert to kW
            return current_kw, 'very_low'
    
    def _get_average_load_for_period(self, start: datetime, end: datetime) -> Optional[float]:
        """Get average load for a specific period (in kW)"""
        history = self.get_historical_load(start, end)
        
        if not history:
            return None
        
        # Filter valid loads and convert watts to kW
        loads = []
        for h in history:
            if isinstance(h['load'], (int, float)) and h['load'] >= 0:
                load_kw = h['load'] / 1000.0  # Convert watts to kW
                loads.append(load_kw)
        
        if not loads:
            return None
        
        return statistics.mean(loads)
    
    def _get_hour_average(self, hour: int, days_back: int = 30) -> Optional[float]:
        """Get average load for a specific hour across multiple days"""
        now = datetime.now()
        samples = []
        
        for days_ago in range(1, min(days_back + 1, 60)):  # Cap at 60 days
            target = now - timedelta(days=days_ago)
            target = target.replace(hour=hour, minute=0, second=0, microsecond=0)
            
            if target >= now:
                continue
            
            avg = self._get_average_load_for_period(target, target + timedelta(hours=1))
            if avg:
                samples.append(avg)
        
        if samples:
            return statistics.median(samples)  # Use median to reduce outlier impact
        return None
    
    def _get_trend_prediction(self, target_time: datetime) -> Optional[float]:
        """Predict based on recent trend at this time"""
        now = datetime.now()
        samples = []
        
        # Get last 7 occurrences of this time
        for days_ago in range(1, 8):
            check_time = target_time - timedelta(days=days_ago)
            if check_time >= now:
                continue
            
            avg = self._get_average_load_for_period(
                check_time - timedelta(minutes=15),
                check_time + timedelta(minutes=15)
            )
            if avg:
                samples.append((days_ago, avg))
        
        if len(samples) < 3:
            return None
        
        # Simple linear regression would go here
        # For now, use weighted average favoring recent data
        total_weight = sum(1.0 / days_ago for days_ago, _ in samples)
        weighted_sum = sum(load / days_ago for days_ago, load in samples)
        
        return weighted_sum / total_weight
    
    def predict_loads_24h(self) -> List[Dict]:
        """
        Predict loads for next 24 hours in 30-minute intervals.
        
        Returns:
            List of {'time': datetime, 'load_kw': float, 'confidence': str} dicts
        """
        predictions = []
        now = datetime.now()
        
        # Round to nearest 30 minutes
        if now.minute < 30:
            start = now.replace(minute=0, second=0, microsecond=0)
        else:
            start = now.replace(minute=30, second=0, microsecond=0)
        
        self.log(f"Predicting loads for next 24 hours starting {start.strftime('%H:%M')}")
        
        for i in range(48):  # 24 hours = 48 half-hour slots
            target_time = start + timedelta(minutes=30 * i)
            load, confidence = self.predict_load(target_time)
            
            predictions.append({
                'time': target_time,
                'load_kw': load,
                'confidence': confidence
            })
        
        # Show sample
        self.log(f"Load prediction sample (first 6 slots):")
        for pred in predictions[:6]:
            self.log(f"  {pred['time'].strftime('%H:%M %d/%m')}: {pred['load_kw']:.2f}kW ({pred['confidence']})")
        
        return predictions
