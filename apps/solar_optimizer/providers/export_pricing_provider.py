"""
Export Pricing Provider

Provides future export electricity prices.
Supports both dynamic (Octopus Agile Export) and fixed export rates.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

try:
    from .base_provider import DataProvider
except ImportError:
    from base_provider import DataProvider


class ExportPricingProvider(DataProvider):
    """
    Provides export electricity pricing.
    
    Supports:
    - Octopus Agile Export (dynamic, half-hourly)
    - Fixed export rate (e.g., 15p/kWh SEG)
    """
    
    def __init__(self, hass):
        super().__init__(hass)
        self.export_rate_sensor = None
        self.fixed_rate = None
        self.is_dynamic = False
    
    def setup(self, config: Dict) -> bool:
        """
        Setup export pricing provider.
        
        Config can contain:
        - export_rate: Fixed rate in pence (e.g., 15.0)
        - export_rate_sensor: Sensor for dynamic rates (Agile Export)
        """
        try:
            # Check for fixed rate first
            export_config = config.get('export_rate')
            
            if export_config:
                # Is it a sensor or a fixed value?
                if isinstance(export_config, str) and 'sensor.' in export_config:
                    # Dynamic export (sensor)
                    self.export_rate_sensor = export_config
                    self.is_dynamic = True
                    self.log(f"Export pricing: Dynamic from {export_config}")
                else:
                    # Fixed export rate
                    self.fixed_rate = float(export_config)
                    self.is_dynamic = False
                    self.log(f"Export pricing: Fixed at {self.fixed_rate}p/kWh")
            else:
                # Default to 15p fixed (typical SEG rate)
                self.fixed_rate = 15.0
                self.is_dynamic = False
                self.log(f"Export pricing: Default fixed at {self.fixed_rate}p/kWh")
            
            self._health_status = 'healthy'
            self._last_update = datetime.now()
            return True
            
        except Exception as e:
            self.log(f"Failed to setup export pricing: {e}", level="ERROR")
            self._health_status = 'failed'
            return False
    
    def get_data(self, hours: int = 24) -> List[Dict]:
        """
        Get export prices for next N hours.
        
        Args:
            hours: Number of hours to forecast
            
        Returns:
            List of {'time': datetime, 'price': float} dicts
        """
        try:
            if self.is_dynamic:
                # Get dynamic export prices from sensor
                return self._get_dynamic_export(hours)
            else:
                # Generate fixed rate forecast
                return self._get_fixed_export(hours)
                
        except Exception as e:
            self.log(f"Error getting export prices: {e}", level="ERROR")
            self._health_status = 'degraded'
            return []
    
    def _get_dynamic_export(self, hours: int) -> List[Dict]:
        """Get dynamic export prices from sensor (Agile Export)"""
        prices = []
        
        try:
            # For Agile Export, we'd query the sensor's attributes
            # Similar to import pricing
            # For now, fall back to current rate repeated
            current_rate = float(self.hass.get_state(self.export_rate_sensor) or self.fixed_rate or 15.0)
            
            # Convert pounds to pence if needed
            if current_rate < 1.0:
                current_rate = current_rate * 100
            
            # Generate forecast (all same for now - would need Agile Export API)
            now = datetime.now()
            start = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0)
            
            for i in range(hours * 2):  # 30-min slots
                slot_time = start + timedelta(minutes=30 * i)
                prices.append({
                    'time': slot_time,
                    'price': current_rate
                })
            
            self._last_update = datetime.now()
            self._health_status = 'healthy'
            
        except Exception as e:
            self.log(f"Error getting dynamic export: {e}", level="WARNING")
            # Fall back to fixed
            return self._get_fixed_export(hours)
        
        return prices
    
    def _get_fixed_export(self, hours: int) -> List[Dict]:
        """Generate fixed export rate forecast"""
        prices = []
        
        rate = self.fixed_rate if self.fixed_rate is not None else 15.0
        
        now = datetime.now()
        start = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0)
        
        for i in range(hours * 2):  # 30-min slots
            slot_time = start + timedelta(minutes=30 * i)
            prices.append({
                'time': slot_time,
                'price': rate
            })
        
        self._last_update = datetime.now()
        self._health_status = 'healthy'
        
        return prices
    
    def get_health(self) -> Dict:
        """Get health status"""
        return {
            'status': self._health_status,
            'last_update': self._last_update,
            'message': f"Export pricing: {'Dynamic' if self.is_dynamic else 'Fixed'} at {self.fixed_rate if not self.is_dynamic else 'variable'} p/kWh",
            'confidence': 'high' if not self.is_dynamic else 'medium'
        }
