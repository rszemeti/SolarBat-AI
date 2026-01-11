"""
Solis Inverter Interface Implementation

Implements control for Solis inverters (S6, etc.) accessed via Solax ModBus integration.
Uses timed charge/discharge slots for precise control.

Works with Solis inverters including:
- Solis S6 Hybrid
- Other Solis models with timed slot support

Accessed via the solax_modbus Home Assistant integration.
"""

from datetime import time
from typing import Dict, Optional

# Handle both AppDaemon (relative) and standalone (absolute) imports
try:
    from .inverter_interface_base import InverterInterface
except ImportError:
    from inverter_interface_base import InverterInterface


class SolisInverterInterface(InverterInterface):
    """
    Solis inverter implementation using timed slots.
    
    Solis inverters (accessed via solax_modbus integration) use time-based 
    charge/discharge scheduling rather than simple mode switching. 
    This provides more precise control over battery behavior.
    
    Tested with: Solis S6 Hybrid via solax_modbus integration
    """
    
    def setup(self, config: Dict) -> bool:
        """
        Setup Solis inverter interface (via solax_modbus integration).
        
        Expected config keys:
            - battery_soc: sensor entity
            - battery_capacity: sensor entity
            - battery_voltage: sensor entity
            - battery_power: sensor entity
            - pv_power: sensor entity
            - grid_power: sensor entity
            - load_power: sensor entity
            - max_charge_current: sensor entity
            - max_discharge_current: sensor entity
            - charge_slot1_start_hour: number entity (e.g., number.solis_inverter_timed_charge_start_hours)
            - charge_slot1_start_minute: number entity
            - charge_slot1_end_hour: number entity
            - charge_slot1_end_minute: number entity
            - charge_slot1_soc: number entity
            - charge_slot1_current: number entity
            - discharge_slot1_start_hour: number entity (e.g., number.solis_inverter_timed_discharge_start_hours)
            - discharge_slot1_start_minute: number entity
            - discharge_slot1_end_hour: number entity
            - discharge_slot1_end_minute: number entity
            - discharge_slot1_soc: number entity
            - discharge_slot1_current: number entity
        """
        try:
            # Store entity IDs
            self.battery_soc_sensor = config.get('battery_soc')
            self.battery_capacity_sensor = config.get('battery_capacity')
            self.battery_voltage_sensor = config.get('battery_voltage')
            self.battery_power_sensor = config.get('battery_power')
            self.pv_power_sensor = config.get('pv_power')
            self.grid_power_sensor = config.get('grid_power')
            self.load_power_sensor = config.get('load_power')
            
            # Capability sensors
            self.max_charge_current_sensor = config.get('max_charge_current')
            self.max_discharge_current_sensor = config.get('max_discharge_current')
            
            # Charge Slot 1 entities
            self.charge_slot1_start_hour = config.get('charge_slot1_start_hour')
            self.charge_slot1_start_minute = config.get('charge_slot1_start_minute')
            self.charge_slot1_end_hour = config.get('charge_slot1_end_hour')
            self.charge_slot1_end_minute = config.get('charge_slot1_end_minute')
            self.charge_slot1_soc = config.get('charge_slot1_soc')
            self.charge_slot1_current = config.get('charge_slot1_current')
            
            # Discharge Slot 1 entities
            self.discharge_slot1_start_hour = config.get('discharge_slot1_start_hour')
            self.discharge_slot1_start_minute = config.get('discharge_slot1_start_minute')
            self.discharge_slot1_end_hour = config.get('discharge_slot1_end_hour')
            self.discharge_slot1_end_minute = config.get('discharge_slot1_end_minute')
            self.discharge_slot1_soc = config.get('discharge_slot1_soc')
            self.discharge_slot1_current = config.get('discharge_slot1_current')
            
            # Verify critical entities exist
            critical_entities = [
                self.battery_soc_sensor,
                self.charge_slot1_start_hour,
                self.discharge_slot1_start_hour
            ]
            
            for entity in critical_entities:
                if not entity:
                    self.log(f"Missing critical entity in config", level="ERROR")
                    return False
                
                state = self.get_state(entity)
                if state is None:
                    self.log(f"Entity {entity} not found in HA", level="ERROR")
                    return False
            
            self.log("Solis inverter interface setup successful (via solax_modbus)")
            return True
            
        except Exception as e:
            self.log(f"Failed to setup Solax interface: {e}", level="ERROR")
            return False
    
    def get_capabilities(self) -> Dict:
        """Get Solis S6 inverter capabilities (via solax_modbus)"""
        try:
            # Battery capacity - could be sensor or hardcoded value
            battery_capacity = float(self.get_value(self.battery_capacity_sensor, 10.0))
            
            # Battery voltage - could be sensor or hardcoded value
            battery_voltage = float(self.get_value(self.battery_voltage_sensor, 51.2))
            
            # Max charge current (Amps) -> convert to kW
            max_charge_current = float(self.get_value(self.max_charge_current_sensor, 40))
            max_charge_rate = (max_charge_current * battery_voltage) / 1000
            
            # Max discharge current (Amps) -> convert to kW
            max_discharge_current = float(self.get_value(self.max_discharge_current_sensor, 60))
            max_discharge_rate = (max_discharge_current * battery_voltage) / 1000
            
            return {
                'max_charge_rate': max_charge_rate,
                'max_discharge_rate': max_discharge_rate,
                'battery_capacity': battery_capacity,
                'battery_voltage': battery_voltage,
                'supports_force_discharge': True,  # Solis supports timed discharge
                'supports_timed_slots': True,
                'num_charge_slots': 6,  # Solis S6 typically has 6 slots
                'num_discharge_slots': 6,
                'charge_efficiency': 0.95,
                'discharge_efficiency': 0.95
            }
            
        except Exception as e:
            self.log(f"Error getting capabilities: {e}", level="ERROR")
            return {
                'max_charge_rate': 2.0,
                'max_discharge_rate': 3.0,
                'battery_capacity': 10.0,
                'battery_voltage': 51.2,
                'supports_force_discharge': True,
                'supports_timed_slots': True,
                'num_charge_slots': 6,
                'num_discharge_slots': 6,
                'charge_efficiency': 0.95,
                'discharge_efficiency': 0.95
            }
    
    def get_current_state(self) -> Dict:
        """Get current Solis inverter state (via solax_modbus)"""
        try:
            # Battery state
            battery_soc = float(self.get_state(self.battery_soc_sensor) or 50)
            battery_power = float(self.get_state(self.battery_power_sensor) or 0) / 1000  # W to kW
            
            # Power flows
            pv_power = float(self.get_state(self.pv_power_sensor) or 0) / 1000
            grid_power = float(self.get_state(self.grid_power_sensor) or 0) / 1000
            load_power = float(self.get_state(self.load_power_sensor) or 0) / 1000
            
            # Read current slot settings
            charge_slot = self._read_charge_slot()
            discharge_slot = self._read_discharge_slot()
            
            active_slots = []
            if charge_slot['enabled']:
                active_slots.append(f"Charge: {charge_slot['start']}-{charge_slot['end']} to {charge_slot['soc']}%")
            if discharge_slot['enabled']:
                active_slots.append(f"Discharge: {discharge_slot['start']}-{discharge_slot['end']} to {discharge_slot['soc']}%")
            
            return {
                'battery_soc': battery_soc,
                'battery_power': battery_power,
                'pv_power': pv_power,
                'grid_power': grid_power,
                'load_power': load_power,
                'active_slots': active_slots,
                'charge_slot': charge_slot,
                'discharge_slot': discharge_slot
            }
            
        except Exception as e:
            self.log(f"Error getting current state: {e}", level="ERROR")
            return {
                'battery_soc': 50,
                'battery_power': 0,
                'pv_power': 0,
                'grid_power': 0,
                'load_power': 0,
                'active_slots': []
            }
    
    def force_charge(self, start_time: time, end_time: time, target_soc: int, current_amps: Optional[float] = None) -> bool:
        """
        Set Solis inverter to charge from grid during time window.
        
        Uses Charge Slot 1 for all timed charging.
        """
        try:
            # Validate inputs
            if not self.validate_time_window(start_time, end_time):
                self.log(f"Invalid time window: {start_time} to {end_time}", level="ERROR")
                return False
            
            if not self.validate_soc(target_soc):
                self.log(f"Invalid SOC: {target_soc}", level="ERROR")
                return False
            
            # Get max current if not specified
            if current_amps is None:
                capabilities = self.get_capabilities()
                battery_voltage = capabilities['battery_voltage']
                max_charge_rate_kw = capabilities['max_charge_rate']
                current_amps = (max_charge_rate_kw * 1000) / battery_voltage
            
            # Set charge slot 1
            success = True
            success &= self.set_value(self.charge_slot1_start_hour, start_time.hour)
            success &= self.set_value(self.charge_slot1_start_minute, start_time.minute)
            success &= self.set_value(self.charge_slot1_end_hour, end_time.hour)
            success &= self.set_value(self.charge_slot1_end_minute, end_time.minute)
            success &= self.set_value(self.charge_slot1_soc, target_soc)
            success &= self.set_value(self.charge_slot1_current, current_amps)
            
            if success:
                self.log(f"Force Charge set: {start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')} to {target_soc}% at {current_amps:.1f}A")
            else:
                self.log(f"Failed to set some charge slot parameters", level="WARNING")
            
            return success
            
        except Exception as e:
            self.log(f"Error setting force charge: {e}", level="ERROR")
            return False
    
    def force_discharge(self, start_time: time, end_time: time, target_soc: int, current_amps: Optional[float] = None) -> bool:
        """
        Set Solis inverter to discharge to grid during time window.
        
        Uses Discharge Slot 1 for all timed discharging.
        """
        try:
            # Validate inputs
            if not self.validate_time_window(start_time, end_time):
                self.log(f"Invalid time window: {start_time} to {end_time}", level="ERROR")
                return False
            
            if not self.validate_soc(target_soc):
                self.log(f"Invalid SOC: {target_soc}", level="ERROR")
                return False
            
            # Get max current if not specified
            if current_amps is None:
                capabilities = self.get_capabilities()
                battery_voltage = capabilities['battery_voltage']
                max_discharge_rate_kw = capabilities['max_discharge_rate']
                current_amps = (max_discharge_rate_kw * 1000) / battery_voltage
            
            # Set discharge slot 1
            success = True
            success &= self.set_value(self.discharge_slot1_start_hour, start_time.hour)
            success &= self.set_value(self.discharge_slot1_start_minute, start_time.minute)
            success &= self.set_value(self.discharge_slot1_end_hour, end_time.hour)
            success &= self.set_value(self.discharge_slot1_end_minute, end_time.minute)
            success &= self.set_value(self.discharge_slot1_soc, target_soc)
            success &= self.set_value(self.discharge_slot1_current, current_amps)
            
            if success:
                self.log(f"Force Discharge set: {start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')} to {target_soc}% at {current_amps:.1f}A")
            else:
                self.log(f"Failed to set some discharge slot parameters", level="WARNING")
            
            return success
            
        except Exception as e:
            self.log(f"Error setting force discharge: {e}", level="ERROR")
            return False
    
    def clear_charge_slots(self) -> bool:
        """Clear charge slot 1 by setting time to 00:00-00:00"""
        try:
            success = True
            success &= self.set_value(self.charge_slot1_start_hour, 0)
            success &= self.set_value(self.charge_slot1_start_minute, 0)
            success &= self.set_value(self.charge_slot1_end_hour, 0)
            success &= self.set_value(self.charge_slot1_end_minute, 0)
            success &= self.set_value(self.charge_slot1_current, 0)
            
            if success:
                self.log("Charge slots cleared")
            
            return success
            
        except Exception as e:
            self.log(f"Error clearing charge slots: {e}", level="ERROR")
            return False
    
    def clear_discharge_slots(self) -> bool:
        """Clear discharge slot 1 by setting time to 00:00-00:00"""
        try:
            success = True
            success &= self.set_value(self.discharge_slot1_start_hour, 0)
            success &= self.set_value(self.discharge_slot1_start_minute, 0)
            success &= self.set_value(self.discharge_slot1_end_hour, 0)
            success &= self.set_value(self.discharge_slot1_end_minute, 0)
            success &= self.set_value(self.discharge_slot1_current, 0)
            
            if success:
                self.log("Discharge slots cleared")
            
            return success
            
        except Exception as e:
            self.log(f"Error clearing discharge slots: {e}", level="ERROR")
            return False
    
    def clear_all_slots(self) -> bool:
        """Clear both charge and discharge slots"""
        charge_success = self.clear_charge_slots()
        discharge_success = self.clear_discharge_slots()
        return charge_success and discharge_success
    
    def _read_charge_slot(self) -> Dict:
        """Read current charge slot 1 settings"""
        try:
            start_hour = int(float(self.get_state(self.charge_slot1_start_hour) or 0))
            start_minute = int(float(self.get_state(self.charge_slot1_start_minute) or 0))
            end_hour = int(float(self.get_state(self.charge_slot1_end_hour) or 0))
            end_minute = int(float(self.get_state(self.charge_slot1_end_minute) or 0))
            soc = int(float(self.get_state(self.charge_slot1_soc) or 0))
            current = float(self.get_state(self.charge_slot1_current) or 0)
            
            # Slot is enabled if time window is set and current > 0
            enabled = (start_hour != end_hour or start_minute != end_minute) and current > 0
            
            return {
                'start': f"{start_hour:02d}:{start_minute:02d}",
                'end': f"{end_hour:02d}:{end_minute:02d}",
                'soc': soc,
                'current': current,
                'enabled': enabled
            }
        except:
            return {'start': '00:00', 'end': '00:00', 'soc': 0, 'current': 0, 'enabled': False}
    
    def _read_discharge_slot(self) -> Dict:
        """Read current discharge slot 1 settings"""
        try:
            start_hour = int(float(self.get_state(self.discharge_slot1_start_hour) or 0))
            start_minute = int(float(self.get_state(self.discharge_slot1_start_minute) or 0))
            end_hour = int(float(self.get_state(self.discharge_slot1_end_hour) or 0))
            end_minute = int(float(self.get_state(self.discharge_slot1_end_minute) or 0))
            soc = int(float(self.get_state(self.discharge_slot1_soc) or 0))
            current = float(self.get_state(self.discharge_slot1_current) or 0)
            
            # Slot is enabled if time window is set and current > 0
            enabled = (start_hour != end_hour or start_minute != end_minute) and current > 0
            
            return {
                'start': f"{start_hour:02d}:{start_minute:02d}",
                'end': f"{end_hour:02d}:{end_minute:02d}",
                'soc': soc,
                'current': current,
                'enabled': enabled
            }
        except:
            return {'start': '00:00', 'end': '00:00', 'soc': 0, 'current': 0, 'enabled': False}
