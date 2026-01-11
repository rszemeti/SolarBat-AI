"""
Load Forecast Provider

Provides AI-powered house consumption forecast.
Wraps the existing LoadForecaster with the DataProvider interface.
"""

from datetime import datetime
from typing import Dict, List

try:
    from .base_provider import DataProvider
except ImportError:
    from base_provider import DataProvider

# Import the existing AI load forecaster
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
try:
    from ..load_forecaster import LoadForecaster
except:
    # For standalone testing
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "load_forecaster",
        os.path.join(os.path.dirname(__file__), "../load_forecaster.py")
    )
    load_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(load_module)
    LoadForecaster = load_module.LoadForecaster


class LoadForecastProvider(DataProvider):
    """
    Provides house load forecast using AI prediction.
    
    Uses historical consumption patterns to predict future load.
    """
    
    def __init__(self, hass):
        super().__init__(hass)
        self.forecaster = LoadForecaster(hass)
    
    def setup(self, config: Dict) -> bool:
        """
        Setup load forecast provider.
        
        Config:
        - load_power: Sensor for house load (watts)
        """
        try:
            success = self.forecaster.setup(config)
            
            if success:
                self.log("Load forecast: AI predictor ready")
                self._health_status = 'healthy'
                self._last_update = datetime.now()
            else:
                self.log("Load forecast: Setup failed", level="WARNING")
                self._health_status = 'degraded'
            
            return success
            
        except Exception as e:
            self.log(f"Failed to setup load forecast: {e}", level="ERROR")
            self._health_status = 'failed'
            return False
    
    def get_data(self, hours: int = 24) -> List[Dict]:
        """
        Get load forecast for next N hours.
        
        Returns:
            List of {'time': datetime, 'kw': float, 'confidence': str} dicts
        """
        try:
            # Use the AI forecaster
            predictions = self.forecaster.predict_loads_24h()
            
            if predictions:
                self._last_update = datetime.now()
                self._health_status = 'healthy'
                
                # Convert to standard format
                forecast = []
                for pred in predictions:
                    forecast.append({
                        'time': pred['time'],
                        'kw': pred['load_kw'],
                        'confidence': pred.get('confidence', 'unknown')
                    })
                
                return forecast
            else:
                self.log("No load forecast available", level="WARNING")
                self._health_status = 'degraded'
                return []
            
        except Exception as e:
            self.log(f"Error getting load forecast: {e}", level="ERROR")
            self._health_status = 'failed'
            return []
    
    def get_health(self) -> Dict:
        """Get health status"""
        return {
            'status': self._health_status,
            'last_update': self._last_update,
            'message': "AI-powered load forecast from historical data",
            'confidence': 'medium'  # AI predictions always have some uncertainty
        }
