"""
Abstract Base Class for Electricity Pricing Providers

Handles both known prices (from integration) and predicted prices (when data unavailable).
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple


class PricingProvider(ABC):
    """
    Abstract base class for electricity pricing.
    
    Provides consistent interface for getting electricity prices,
    whether they're known (from integration) or predicted.
    """
    
    def __init__(self, hass):
        """
        Initialize the pricing provider.
        
        Args:
            hass: Home Assistant API object
        """
        self.hass = hass
        self.price_history = []  # Store historical prices for prediction
    
    # ========== ABSTRACT METHODS ==========
    
    @abstractmethod
    def setup(self, config: Dict) -> bool:
        """
        Setup the pricing provider with configuration.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            bool: True if setup successful
        """
        pass
    
    @abstractmethod
    def get_known_prices(self) -> List[Dict]:
        """
        Get known prices from the integration.
        
        Returns:
            List of price dicts with keys:
                - start: datetime
                - end: datetime  
                - price: float (p/kWh)
                - is_predicted: False
        """
        pass
    
    @abstractmethod
    def get_current_price(self) -> Optional[float]:
        """
        Get current electricity price.
        
        Returns:
            float: Current price in p/kWh, or None if unavailable
        """
        pass
    
    # ========== IMPLEMENTED METHODS ==========
    
    def get_prices_for_planning(self, hours: int = 24) -> List[Dict]:
        """
        Get prices for planning, filling gaps with predictions.
        
        This is the main method the planner should use. It provides
        a complete price forecast by:
        1. Getting known prices from integration
        2. Filling any gaps with predicted prices
        
        Args:
            hours: Number of hours to get prices for
            
        Returns:
            List of price dicts with keys:
                - start: datetime (30-min slots)
                - end: datetime
                - price: float (p/kWh)
                - is_predicted: bool
                - prediction_method: str (if predicted)
        """
        now = datetime.now().replace(second=0, microsecond=0)
        
        # Align to 30-minute boundary
        if now.minute < 30:
            now = now.replace(minute=0)
        else:
            now = now.replace(minute=30)
        
        # Get known prices
        known_prices = self.get_known_prices()
        
        # Create dict for quick lookup: datetime -> price
        known_prices_dict = {}
        for price in known_prices:
            known_prices_dict[price['start']] = price
        
        # Build complete price list
        complete_prices = []
        current_time = now
        end_time = now + timedelta(hours=hours)
        
        while current_time < end_time:
            slot_end = current_time + timedelta(minutes=30)
            
            if current_time in known_prices_dict:
                # We have known price
                complete_prices.append(known_prices_dict[current_time])
            else:
                # Need to predict
                predicted_price = self.predict_price(current_time)
                complete_prices.append({
                    'start': current_time,
                    'end': slot_end,
                    'price': predicted_price['price'],
                    'is_predicted': True,
                    'prediction_method': predicted_price['method'],
                    'confidence': predicted_price.get('confidence', 'low')
                })
            
            current_time = slot_end
        
        return complete_prices
    
    def predict_price(self, target_time: datetime) -> Dict:
        """
        Predict price for a time when we don't have data.
        
        Uses various methods depending on available data:
        1. Same time yesterday (most recent)
        2. Same time last week
        3. Historical average for this hour
        4. Overall average
        
        Args:
            target_time: Time to predict price for
            
        Returns:
            Dict with keys:
                - price: float
                - method: str
                - confidence: str (high/medium/low)
        """
        # Method 1: Same time yesterday
        yesterday_price = self._get_price_from_history(target_time - timedelta(days=1))
        if yesterday_price is not None:
            return {
                'price': yesterday_price,
                'method': 'yesterday_same_time',
                'confidence': 'medium'
            }
        
        # Method 2: Same time last week
        last_week_price = self._get_price_from_history(target_time - timedelta(days=7))
        if last_week_price is not None:
            return {
                'price': last_week_price,
                'method': 'last_week_same_time',
                'confidence': 'low'
            }
        
        # Method 3: Average for this hour from history
        hour_average = self._get_hour_average(target_time.hour, target_time.minute)
        if hour_average is not None:
            return {
                'price': hour_average,
                'method': 'historical_hour_average',
                'confidence': 'medium'
            }
        
        # Method 4: Overall average (fallback)
        overall_average = self._get_overall_average()
        return {
            'price': overall_average,
            'method': 'overall_average',
            'confidence': 'low'
        }
    
    def record_price(self, timestamp: datetime, price: float):
        """
        Record a price in history for future predictions.
        
        Args:
            timestamp: When this price was active
            price: Price in p/kWh
        """
        self.price_history.append({
            'timestamp': timestamp,
            'price': price,
            'hour': timestamp.hour,
            'minute': timestamp.minute,
            'weekday': timestamp.weekday()
        })
        
        # Keep only last 30 days
        cutoff = datetime.now() - timedelta(days=30)
        self.price_history = [
            p for p in self.price_history
            if p['timestamp'] > cutoff
        ]
    
    def _get_price_from_history(self, target_time: datetime) -> Optional[float]:
        """Get price from history for specific time"""
        # Find price within 30 minutes of target
        for record in self.price_history:
            if abs((record['timestamp'] - target_time).total_seconds()) < 1800:  # 30 min
                return record['price']
        return None
    
    def _get_hour_average(self, hour: int, minute: int) -> Optional[float]:
        """Get average price for this hour/minute from history"""
        # Allow +/- 30 minutes
        matching = [
            p['price'] for p in self.price_history
            if abs(p['hour'] - hour) <= 0 and abs(p['minute'] - minute) <= 30
        ]
        
        if matching:
            return sum(matching) / len(matching)
        return None
    
    def _get_overall_average(self) -> float:
        """Get overall average from history, or sensible default"""
        if self.price_history:
            return sum(p['price'] for p in self.price_history) / len(self.price_history)
        
        # Sensible UK average if no history
        return 24.5  # p/kWh
    
    def get_price_statistics(self, prices: List[Dict]) -> Dict:
        """
        Calculate statistics for a price list.
        
        Args:
            prices: List of price dicts
            
        Returns:
            Dict with min, max, avg, median, predicted_count
        """
        if not prices:
            return {
                'min': 0,
                'max': 0,
                'avg': 0,
                'median': 0,
                'predicted_count': 0
            }
        
        price_values = [p['price'] for p in prices]
        predicted_count = sum(1 for p in prices if p.get('is_predicted', False))
        
        price_values.sort()
        n = len(price_values)
        median = price_values[n // 2] if n % 2 == 1 else (price_values[n // 2 - 1] + price_values[n // 2]) / 2
        
        return {
            'min': min(price_values),
            'max': max(price_values),
            'avg': sum(price_values) / len(price_values),
            'median': median,
            'predicted_count': predicted_count,
            'known_count': len(prices) - predicted_count
        }
    
    def log(self, message: str, level: str = "INFO"):
        """Log a message"""
        if hasattr(self.hass, 'log'):
            self.hass.log(message, level=level)
    
    def get_state(self, entity_id: str, default=None):
        """Get entity state safely"""
        try:
            state = self.hass.get_state(entity_id)
            return state if state not in [None, "unknown", "unavailable"] else default
        except:
            return default
