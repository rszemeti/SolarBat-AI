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
        self.solcast_entity_tomorrow = None
        self.solar_scaling = 1.0
    
    def setup(self, config: Dict) -> bool:
        """
        Setup solar forecast provider.
        
        Config:
        - solcast_forecast_today: Entity ID for Solcast forecast (today)
        - solcast_forecast_tomorrow: Entity ID for Solcast forecast (tomorrow)
        - solar_scaling: Multiplier for testing (default 1.0)
        """
        try:
            self.solcast_entity = config.get(
                'solcast_forecast_today',
                'sensor.solcast_pv_forecast_forecast_today'
            )
            
            self.solcast_entity_tomorrow = config.get(
                'solcast_forecast_tomorrow',
                'sensor.solcast_pv_forecast_forecast_tomorrow'
            )
            
            self.solar_scaling = float(config.get('solar_scaling', 1.0))
            
            # Test that today entity exists
            test_state = self.hass.get_state(self.solcast_entity, attribute='all')
            if not test_state:
                self.log(f"Warning: Solcast today entity {self.solcast_entity} not found", level="WARNING")
                self._health_status = 'degraded'
                return True  # Continue anyway, will fail gracefully
            
            # Test tomorrow entity (optional)
            test_tomorrow = self.hass.get_state(self.solcast_entity_tomorrow, attribute='all')
            if not test_tomorrow:
                self.log(f"Info: Solcast tomorrow entity {self.solcast_entity_tomorrow} not found (will only use today)", level="INFO")
            
            self.log(f"Solar forecast: Using {self.solcast_entity} + {self.solcast_entity_tomorrow} (scaling: {self.solar_scaling}x)")
            self._health_status = 'healthy'
            self._last_update = datetime.now()
            return True
            
        except Exception as e:
            self.log(f"Failed to setup solar forecast: {e}", level="ERROR")
            self._health_status = 'failed'
            return False
    
    def get_data(self, hours: int = 24) -> List[Dict]:
        """
        Get solar forecast for next N hours (includes tomorrow).
        
        Returns:
            List of {'time': datetime, 'kw': float} dicts
        """
        try:
            forecast = []
            now = datetime.now()
            
            # Round down to current half-hour boundary for filtering
            # This ensures we include the current 30-min slot
            now_rounded = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0)
            
            # Fetch today's forecast
            self.log(f"[SOLAR] Fetching today from: {self.solcast_entity}")
            solcast_data_today = self.hass.get_state(self.solcast_entity, attribute='all')
            
            if solcast_data_today and 'attributes' in solcast_data_today:
                detailed_today = solcast_data_today['attributes'].get('detailedForecast', [])
                self.log(f"[SOLAR] Today has {len(detailed_today)} raw entries")
                today_parsed = self._parse_solcast_data(detailed_today, now_rounded)
                self.log(f"[SOLAR] Today parsed to {len(today_parsed)} future points")
                forecast.extend(today_parsed)
            else:
                self.log("[SOLAR] ❌ No Solcast today data available", level="WARNING")
            
            # ALWAYS fetch tomorrow's forecast (we need it for overnight planning)
            self.log(f"[SOLAR] Fetching tomorrow from: {self.solcast_entity_tomorrow}")
            solcast_data_tomorrow = self.hass.get_state(self.solcast_entity_tomorrow, attribute='all')
            
            if solcast_data_tomorrow:
                self.log(f"[SOLAR] Tomorrow entity state: {solcast_data_tomorrow.get('state', 'NO STATE')}")
                if 'attributes' in solcast_data_tomorrow:
                    detailed_tomorrow = solcast_data_tomorrow['attributes'].get('detailedForecast', [])
                    self.log(f"[SOLAR] Tomorrow has {len(detailed_tomorrow)} raw entries")
                    
                    if detailed_tomorrow:
                        # Show first entry for debugging
                        first_entry = detailed_tomorrow[0] if detailed_tomorrow else None
                        if first_entry:
                            self.log(f"[SOLAR] Tomorrow first entry: {first_entry.get('period_start', 'NO TIME')}")
                        
                        tomorrow_data = self._parse_solcast_data(detailed_tomorrow, now_rounded)
                        self.log(f"[SOLAR] Tomorrow parsed to {len(tomorrow_data)} future points")
                        
                        if tomorrow_data:
                            forecast.extend(tomorrow_data)
                            self.log(f"[SOLAR] ✅ Added {len(tomorrow_data)} tomorrow forecast points")
                        else:
                            self.log("[SOLAR] ⚠️ Tomorrow forecast returned no future data", level="WARNING")
                    else:
                        self.log("[SOLAR] ⚠️ Tomorrow detailedForecast is empty", level="WARNING")
                else:
                    self.log("[SOLAR] ❌ Tomorrow has no attributes", level="WARNING")
            else:
                self.log("[SOLAR] ❌ Tomorrow entity returned None", level="ERROR")
            
            # Sort by time and limit to requested hours
            forecast.sort(key=lambda x: x['time'])
            
            if forecast:
                self.log(f"[SOLAR] Total before trim: {len(forecast)} points")
                self.log(f"[SOLAR] Time range: {forecast[0]['time']} to {forecast[-1]['time']}")
            
            # Trim to requested hours
            cutoff = now + timedelta(hours=hours)
            self.log(f"[SOLAR] Cutoff time: {cutoff} (now + {hours}h)")
            forecast = [f for f in forecast if f['time'] <= cutoff]
            
            if forecast:
                self._last_update = datetime.now()
                self._health_status = 'healthy'
                span_hours = (forecast[-1]['time'] - forecast[0]['time']).total_seconds() / 3600
                self.log(f"[SOLAR] ✅ Final: {len(forecast)} points spanning {span_hours:.1f}h (scaled {self.solar_scaling}x)")
            else:
                self.log("[SOLAR] ❌ No solar forecast data available", level="WARNING")
                self._health_status = 'degraded'
            
            return forecast
            
        except Exception as e:
            self.log(f"[SOLAR] ❌ Error getting solar forecast: {e}", level="ERROR")
            import traceback
            self.log(f"[SOLAR] Traceback: {traceback.format_exc()}", level="ERROR")
            self._health_status = 'error'
            return []
    
    def _parse_solcast_data(self, detailed: List, now: datetime) -> List[Dict]:
        """Parse Solcast detailedForecast data"""
        forecast = []
        
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
                
                # Include current and future periods
                # now is already rounded to current half-hour slot
                if period_end >= now:
                    # Apply scaling factor
                    scaled_pv = float(pv_estimate) * self.solar_scaling
                    
                    forecast.append({
                        'time': period_end,
                        'kw': scaled_pv
                    })
            
            except Exception as e:
                continue
        
        return forecast
    
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
