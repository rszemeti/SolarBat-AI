"""
Time Series Predictor - Unified prediction for Load and Pricing

Uses historical patterns with intelligent weighting to predict future values.
Works for both electricity load (kW) and Agile pricing (p/kWh).

Prediction strategy (priority order):
1. Yesterday's value at this exact time (primary - days are similar)
2. Same day-of-week last week (captures weekday/weekend patterns)
3. Weighted 7-day rolling average (accounts for trends)
4. Hour-based statistical patterns (general fallback)
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import statistics


class TimeSeriesPredictor:
    """
    Unified predictor for time-series data (load, pricing, etc).
    
    Features:
    - Yesterday-first strategy (best predictor)
    - Day-of-week awareness (weekday vs weekend)
    - Trend detection and weighting
    - Confidence scoring
    - Handles sparse historical data gracefully
    """
    
    def __init__(self, name: str = "predictor"):
        """
        Initialize time series predictor.
        
        Args:
            name: Name for logging (e.g., "load", "pricing")
        """
        self.name = name
        self.history = []  # List of {'timestamp': datetime, 'value': float}
    
    def add_historical_data(self, data: List[Dict]):
        """
        Add historical data for training.
        
        Args:
            data: List of {'timestamp': datetime, 'value': float} dicts
        """
        self.history.extend(data)
        
        # Sort by timestamp
        self.history.sort(key=lambda x: x['timestamp'])
        
        # Keep only last 30 days to manage memory
        cutoff = datetime.now() - timedelta(days=30)
        self.history = [h for h in self.history if h['timestamp'] > cutoff]
    
    def predict(self, target_time: datetime, fallback_value: float = None) -> Tuple[float, str]:
        """
        Predict value for target time using historical patterns.
        
        Args:
            target_time: Time to predict for
            fallback_value: Value to use if no history available
            
        Returns:
            Tuple of (predicted_value, confidence_level)
            confidence_level: 'very_high', 'high', 'medium', 'low', 'very_low'
        """
        if not self.history:
            # No history - return fallback
            return fallback_value if fallback_value is not None else 0.0, 'very_low'
        
        predictions = []
        
        # Strategy 1: Yesterday's value at this exact time (PRIMARY)
        # This is the BEST predictor - days tend to be very similar
        yesterday_value = self._get_yesterday_value(target_time)
        if yesterday_value is not None:
            predictions.append({
                'value': yesterday_value,
                'weight': 5.0,  # Highest weight - yesterday is king!
                'method': 'yesterday'
            })
        
        # Strategy 2: Same day-of-week last week
        # Captures weekday vs weekend patterns
        last_week_value = self._get_last_week_value(target_time)
        if last_week_value is not None:
            predictions.append({
                'value': last_week_value,
                'weight': 3.0,  # High weight - day-of-week matters
                'method': 'last_week'
            })
        
        # Strategy 3: Weighted rolling average (last 7 days at this time)
        # With day-of-week similarity weighting
        rolling_avg = self._get_weighted_rolling_average(target_time, days=7)
        if rolling_avg is not None:
            predictions.append({
                'value': rolling_avg,
                'weight': 2.0,  # Medium weight - general pattern
                'method': 'rolling_avg'
            })
        
        # Strategy 4: Hour-based statistical average
        # Fallback for when specific days aren't available
        hour_avg = self._get_hour_average(target_time.hour, days_back=14)
        if hour_avg is not None:
            predictions.append({
                'value': hour_avg,
                'weight': 1.0,  # Lower weight - very general
                'method': 'hour_avg'
            })
        
        # Calculate weighted prediction
        if predictions:
            total_weight = sum(p['weight'] for p in predictions)
            weighted_sum = sum(p['value'] * p['weight'] for p in predictions)
            predicted_value = weighted_sum / total_weight
            
            # Determine confidence based on:
            # 1. Number of methods available
            # 2. Agreement between methods (low std deviation)
            # 3. Which methods are available (yesterday = high confidence)
            confidence = self._calculate_confidence(predictions)
            
            return predicted_value, confidence
        else:
            # No predictions possible - use fallback
            return fallback_value if fallback_value is not None else 0.0, 'very_low'
    
    def _get_yesterday_value(self, target_time: datetime) -> Optional[float]:
        """Get value from yesterday at the same time (±15 min window)"""
        yesterday = target_time - timedelta(days=1)
        
        # Find closest value within 15-minute window
        candidates = [
            h for h in self.history
            if abs((h['timestamp'] - yesterday).total_seconds()) < 900  # 15 min
        ]
        
        if candidates:
            # Return closest match
            closest = min(candidates, key=lambda h: abs((h['timestamp'] - yesterday).total_seconds()))
            return closest['value']
        
        return None
    
    def _get_last_week_value(self, target_time: datetime) -> Optional[float]:
        """Get value from last week at the same day/time"""
        last_week = target_time - timedelta(days=7)
        
        # Find closest value within 15-minute window
        candidates = [
            h for h in self.history
            if abs((h['timestamp'] - last_week).total_seconds()) < 900
        ]
        
        if candidates:
            closest = min(candidates, key=lambda h: abs((h['timestamp'] - last_week).total_seconds()))
            return closest['value']
        
        return None
    
    def _get_weighted_rolling_average(self, target_time: datetime, days: int = 7) -> Optional[float]:
        """
        Get weighted average over last N days with day-of-week similarity weighting.
        
        Higher weight for same day-of-week and more recent data.
        """
        target_hour = target_time.hour
        target_minute = target_time.minute
        target_dow = target_time.weekday()  # 0=Monday, 6=Sunday
        
        weighted_values = []
        
        for h in self.history:
            h_time = h['timestamp']
            
            # Same hour (±30 min window)
            if (h_time.hour == target_hour and 
                abs(h_time.minute - target_minute) <= 30):
                
                # How many days ago?
                days_ago = (target_time - h_time).days
                
                if 0 < days_ago <= days:
                    # Calculate weight based on day-of-week similarity
                    h_dow = h_time.weekday()
                    
                    if h_dow == target_dow:
                        dow_weight = 3.0  # Same day-of-week
                    elif (h_dow >= 5 and target_dow >= 5) or (h_dow < 5 and target_dow < 5):
                        dow_weight = 2.0  # Same category (weekend/weekday)
                    else:
                        dow_weight = 1.0  # Different category
                    
                    # Recency weight (more recent = more relevant)
                    recency_weight = 1.0 - (days_ago / days * 0.4)  # Up to 40% decay
                    
                    total_weight = dow_weight * recency_weight
                    
                    weighted_values.append({
                        'value': h['value'],
                        'weight': total_weight
                    })
        
        if weighted_values:
            total_weight = sum(v['weight'] for v in weighted_values)
            weighted_sum = sum(v['value'] * v['weight'] for v in weighted_values)
            return weighted_sum / total_weight
        
        return None
    
    def _get_hour_average(self, hour: int, days_back: int = 14) -> Optional[float]:
        """Get average value for this hour over last N days"""
        cutoff = datetime.now() - timedelta(days=days_back)
        
        hour_values = [
            h['value'] for h in self.history
            if h['timestamp'] > cutoff and h['timestamp'].hour == hour
        ]
        
        if hour_values:
            return statistics.mean(hour_values)
        
        return None
    
    def _calculate_confidence(self, predictions: List[Dict]) -> str:
        """
        Calculate confidence level based on available predictions.
        
        Returns: 'very_high', 'high', 'medium', 'low', 'very_low'
        """
        if not predictions:
            return 'very_low'
        
        # Extract methods and values
        methods = [p['method'] for p in predictions]
        values = [p['value'] for p in predictions]
        
        # High confidence if we have yesterday's data
        if 'yesterday' in methods:
            # Calculate agreement
            if len(values) > 1:
                std_dev = statistics.stdev(values)
                avg = statistics.mean(values)
                variation = std_dev / avg if avg > 0 else 1.0
                
                if variation < 0.15:  # Low variation
                    return 'very_high'
                elif variation < 0.25:
                    return 'high'
                else:
                    return 'medium'
            else:
                return 'high'  # Only yesterday, still good
        
        # Medium confidence with last week or multiple methods
        if 'last_week' in methods or len(methods) >= 3:
            if len(values) > 1:
                std_dev = statistics.stdev(values)
                avg = statistics.mean(values)
                variation = std_dev / avg if avg > 0 else 1.0
                
                if variation < 0.3:
                    return 'medium'
                else:
                    return 'low'
            else:
                return 'medium'
        
        # Low confidence otherwise
        return 'low'
    
    def get_prediction_details(self, target_time: datetime) -> Dict:
        """
        Get detailed prediction breakdown for debugging/transparency.
        
        Returns dict with:
        - predicted_value
        - confidence
        - methods_used: List of prediction methods
        - method_values: Individual predictions from each method
        """
        predictions = []
        
        # Run all prediction methods
        yesterday_value = self._get_yesterday_value(target_time)
        if yesterday_value is not None:
            predictions.append({'method': 'yesterday', 'value': yesterday_value, 'weight': 5.0})
        
        last_week_value = self._get_last_week_value(target_time)
        if last_week_value is not None:
            predictions.append({'method': 'last_week', 'value': last_week_value, 'weight': 3.0})
        
        rolling_avg = self._get_weighted_rolling_average(target_time, days=7)
        if rolling_avg is not None:
            predictions.append({'method': 'rolling_avg', 'value': rolling_avg, 'weight': 2.0})
        
        hour_avg = self._get_hour_average(target_time.hour, days_back=14)
        if hour_avg is not None:
            predictions.append({'method': 'hour_avg', 'value': hour_avg, 'weight': 1.0})
        
        if predictions:
            total_weight = sum(p['weight'] for p in predictions)
            weighted_sum = sum(p['value'] * p['weight'] for p in predictions)
            predicted_value = weighted_sum / total_weight
            confidence = self._calculate_confidence(predictions)
        else:
            predicted_value = 0.0
            confidence = 'very_low'
        
        return {
            'predicted_value': predicted_value,
            'confidence': confidence,
            'methods_used': [p['method'] for p in predictions],
            'method_values': {p['method']: p['value'] for p in predictions},
            'method_weights': {p['method']: p['weight'] for p in predictions}
        }
