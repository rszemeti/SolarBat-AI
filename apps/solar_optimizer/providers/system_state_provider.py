"""
System State Provider

Provides current battery and inverter state.
Wraps the existing InverterInterface with the DataProvider interface.
"""

from datetime import datetime
from typing import Dict

try:
    from .base_provider import DataProvider
except ImportError:
    from base_provider import DataProvider

# Import the existing inverter interface
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
try:
    from ..inverter_interface_solis6 import SolisInverterInterface
except:
    # For standalone testing
    import importlib.util
    
    # Load base first
    spec_base = importlib.util.spec_from_file_location(
        "inverter_interface_base",
        os.path.join(os.path.dirname(__file__), "../inverter_interface_base.py")
    )
    base_module = importlib.util.module_from_spec(spec_base)
    spec_base.loader.exec_module(base_module)
    sys.modules['inverter_interface_base'] = base_module
    
    # Load Solis interface
    spec = importlib.util.spec_from_file_location(
        "inverter_interface_solis6",
        os.path.join(os.path.dirname(__file__), "../inverter_interface_solis6.py")
    )
    solis_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(solis_module)
    SolisInverterInterface = solis_module.SolisInverterInterface


class SystemStateProvider(DataProvider):
    """
    Provides current system state (battery SOC, power, capabilities, mode).
    
    Uses the inverter interface to read real-time data.
    """
    
    def __init__(self, hass):
        super().__init__(hass)
        self.inverter = SolisInverterInterface(hass)
        self.mode_switch_entity = None  # Energy Storage Control Switch
    
    def setup(self, config: Dict) -> bool:
        """
        Setup system state provider.
        
        Config:
        - All inverter configuration (battery sensors, time slots, etc.)
        - mode_switch: Energy Storage Control Switch entity (optional)
        """
        try:
            # Get mode switch entity
            self.mode_switch_entity = config.get(
                'mode_switch',
                'select.solis8_inverter_energy_storage_control_switch'
            )
            
            success = self.inverter.setup(config)
            
            if success:
                self.log("System state: Inverter interface ready")
                self._health_status = 'healthy'
                self._last_update = datetime.now()
            else:
                self.log("System state: Setup failed", level="WARNING")
                self._health_status = 'degraded'
            
            return success
            
        except Exception as e:
            self.log(f"Failed to setup system state: {e}", level="ERROR")
            self._health_status = 'failed'
            return False
    
    def get_data(self) -> Dict:
        """
        Get current system state including mode switch.
        
        Returns:
            Dict with:
                - current_state: {battery_soc, battery_power, pv_power, current_mode, etc.}
                - capabilities: {battery_capacity, max_charge_rate, etc.}
                - active_slots: {charge_slots, discharge_slots}
        """
        try:
            # Get current mode from switch
            current_mode = None
            if self.mode_switch_entity:
                try:
                    current_mode = self.hass.get_state(self.mode_switch_entity)
                except:
                    pass
            
            current_state = self.inverter.get_current_state()
            current_state['current_mode'] = current_mode  # Add mode to state
            
            state = {
                'current_state': current_state,
                'capabilities': self.inverter.get_capabilities(),
                'active_slots': {
                    'charge': self.inverter.get_active_charge_slots(),
                    'discharge': self.inverter.get_active_discharge_slots()
                },
                'mode_switch': {
                    'entity': self.mode_switch_entity,
                    'current_mode': current_mode
                }
            }
            
            self._last_update = datetime.now()
            self._health_status = 'healthy'
            
            return state
            
        except Exception as e:
            self.log(f"Error getting system state: {e}", level="ERROR")
            self._health_status = 'failed'
            return {
                'current_state': {},
                'capabilities': {},
                'active_slots': {'charge': [], 'discharge': []}
            }
    
    def get_health(self) -> Dict:
        """Get health status"""
        return {
            'status': self._health_status,
            'last_update': self._last_update,
            'message': f"Inverter: {self.inverter.inverter_type if hasattr(self.inverter, 'inverter_type') else 'Solis'}",
            'confidence': 'high'  # Real-time data is reliable
        }
