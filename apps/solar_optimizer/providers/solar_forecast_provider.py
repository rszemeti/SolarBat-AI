"""
Solar Forecast Provider

Provides PV generation forecast from Solcast.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os

try:
    from .base_provider import DataProvider
except ImportError:
    from base_provider import DataProvider


class SolarForecastProvider(DataProvider):
    """
    Provides solar PV generation forecast from Solcast.
    """
    
    def __init__(self, hass):
        super().__init__(hass)
        self.solcast_entity = None
        self.solar_scaling = 1.0
    
    def setup(self, config: Dict) -> bool:
        """
        Setup solar forecast provider.
        
        Config:
        - solcast_forecast_today: Entity ID for Solcast forecast
        - solar_scaling: Multiplier for testing (default 1.0)
        """
        try:
            self.solcast_entity = config.get(
                'solcast_forecast_today',
                'sensor.solcast_pv_forecast_forecast_today'
            )
            
            self.solar_scaling = float(config.get('solar_scaling', 1.0))
            
            # Test that entity exists
            test_state = self.hass.get_state(self.solcast_entity, attribute='all')
            if not test_state:
                self.log(f"Warning: Solcast entity {self.solcast_entity} not found", level="WARNING")
                self._health_status = 'degraded'
                return True  # Continue anyway, will fail gracefully
            
            self.log(f"Solar forecast: Using {self.solcast_entity} (scaling: {self.solar_scaling}x)")
            self._health_status = 'healthy'
            self._last_update = datetime.now()
            return True
            
        except Exception as e:
            self.log(f"Failed to setup solar forecast: {e}", level="ERROR")
            self._health_status = 'failed'
            return False
    
    def get_data(self, hours: int = 24) -> List[Dict]:
        """
        Get solar forecast for next N hours.
        
        Returns:
            List of {'time': datetime, 'kw': float} dicts
        """
        try:
            solcast_data = self.hass.get_state(self.solcast_entity, attribute='all')
            
            if not solcast_data or 'attributes' not in solcast_data:
                self.log("No Solcast data available", level="WARNING")
                self._health_status = 'degraded'
                return []
            
            detailed = solcast_data['attributes'].get('detailedForecast', [])
            
            if not detailed:
                self.log("Solcast has no detailedForecast", level="WARNING")
                self._health_status = 'degraded'
                return []
            
            # Parse Solcast forecast
            forecast = []
            now = datetime.now()
            
            for entry in detailed:
                try:
                    if not isinstance(entry, dict):
                        continue
                    
                    # Solcast uses 'period_start'
                    period_start_str = entry.get('period_start')
                    pv_estimate = entry.get('pv_estimate', 0)
                    
                    if not period_start_str:
                        continue
                    
                    # Parse timestamp and add 30 minutes to get period_end
                    period_start = datetime.fromisoformat(
                        str(period_start_str).replace('Z', '+00:00')
                    ).replace(tzinfo=None)
                    period_end = period_start + timedelta(minutes=30)
                    
                    # Only use future forecasts
                    if period_end >= now:
                        # Apply scaling factor
                        scaled_pv = float(pv_estimate) * self.solar_scaling
                        
                        forecast.append({
                            'time': period_end,
                            'kw': scaled_pv
                        })
                
                except Exception as e:
                    continue
            
            if forecast:
                self._last_update = datetime.now()
                self._health_status = 'healthy'
                self.log(f"Loaded {len(forecast)} solar forecast points (scaled {self.solar_scaling}x)")
            else:
                self._health_status = 'degraded'
                self.log("No valid solar forecast data", level="WARNING")
            
            return forecast
            
        except Exception as e:
            self.log(f"Error getting solar forecast: {e}", level="ERROR")
            self._health_status = 'failed'
            return []
    
    def get_health(self) -> Dict:
        """Get health status"""
        message = f"Solar forecast from {self.solcast_entity}"
        if self.solar_scaling != 1.0:
            message += f" (scaled {self.solar_scaling}x)"
        
        return {
            'status': self._health_status,
            'last_update': self._last_update,
            'message': message,
            'confidence': 'high' if self._health_status == 'healthy' else 'low'
        }
