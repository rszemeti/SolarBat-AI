"""
Abstract Base Class for Inverter Interfaces

Defines the interface that all inverter implementations must follow.
This allows the planner to be completely agnostic about the specific inverter hardware.
"""

from abc import ABC, abstractmethod
from datetime import datetime, time
from typing import Dict, Optional, Tuple, Any


class InverterInterface(ABC):
    """
    Abstract base class for inverter control interfaces.
    
    All inverter-specific implementations should inherit from this class
    and implement all abstract methods.
    """
    
    def __init__(self, hass):
        """
        Initialize the inverter interface.
        
        Args:
            hass: Home Assistant API object (from hassapi)
        """
        self.hass = hass
    
    # ========== ABSTRACT METHODS (Must be implemented) ==========
    
    @abstractmethod
    def setup(self, config: Dict) -> bool:
        """
        Setup the inverter interface with configuration.
        
        Args:
            config: Configuration dictionary with entity IDs and settings
            
        Returns:
            bool: True if setup successful, False otherwise
        """
        pass
    
    @abstractmethod
    def get_capabilities(self) -> Dict:
        """
        Get inverter capabilities.
        
        Returns:
            Dict with keys:
                - max_charge_rate: float (kW)
                - max_discharge_rate: float (kW)
                - battery_capacity: float (kWh)
                - supports_force_discharge: bool
                - supports_timed_slots: bool
                - num_charge_slots: int
                - num_discharge_slots: int
        """
        pass
    
    @abstractmethod
    def get_current_state(self) -> Dict:
        """
        Get current inverter state.
        
        Returns:
            Dict with keys:
                - battery_soc: float (%)
                - battery_power: float (kW, positive=charging, negative=discharging)
                - pv_power: float (kW)
                - grid_power: float (kW, positive=importing, negative=exporting)
                - load_power: float (kW)
                - active_slots: list of active charge/discharge slots
        """
        pass
    
    @abstractmethod
    def force_charge(self, start_time: time, end_time: time, target_soc: int, current_amps: Optional[float] = None) -> bool:
        """
        Set inverter to charge from grid during specified time window.
        
        Args:
            start_time: When to start charging
            end_time: When to stop charging
            target_soc: Target SOC percentage (0-100)
            current_amps: Charge current in Amps (None = maximum)
            
        Returns:
            bool: True if command successful
        """
        pass
    
    @abstractmethod
    def force_discharge(self, start_time: time, end_time: time, target_soc: int, current_amps: Optional[float] = None) -> bool:
        """
        Set inverter to discharge to grid during specified time window.
        
        Args:
            start_time: When to start discharging
            end_time: When to stop discharging
            target_soc: Target SOC percentage (0-100) - discharge until this level
            current_amps: Discharge current in Amps (None = maximum)
            
        Returns:
            bool: True if command successful
        """
        pass
    
    @abstractmethod
    def clear_charge_slots(self) -> bool:
        """
        Clear/disable all charge time slots.
        
        Returns:
            bool: True if successful
        """
        pass
    
    @abstractmethod
    def clear_discharge_slots(self) -> bool:
        """
        Clear/disable all discharge time slots.
        
        Returns:
            bool: True if successful
        """
        pass
    
    @abstractmethod
    def clear_all_slots(self) -> bool:
        """
        Clear/disable all timed charge and discharge slots.
        
        Returns:
            bool: True if successful
        """
        pass
    
    # ========== HELPER METHODS (Can be overridden if needed) ==========
    
    def validate_time_window(self, start_time: time, end_time: time) -> bool:
        """
        Validate that time window is reasonable.
        
        Args:
            start_time: Start time
            end_time: End time
            
        Returns:
            bool: True if valid
        """
        # Check times are different
        if start_time == end_time:
            return False
        
        # Both times should be valid
        if not (0 <= start_time.hour <= 23 and 0 <= start_time.minute <= 59):
            return False
        if not (0 <= end_time.hour <= 23 and 0 <= end_time.minute <= 59):
            return False
        
        return True
    
    def validate_soc(self, soc: int) -> bool:
        """
        Validate SOC percentage.
        
        Args:
            soc: State of charge (%)
            
        Returns:
            bool: True if valid
        """
        return 0 <= soc <= 100
    
    def log(self, message: str, level: str = "INFO"):
        """
        Log a message.
        
        Args:
            message: Message to log
            level: Log level (INFO, WARNING, ERROR)
        """
        log_func = getattr(self.hass, "log", None)
        if log_func:
            log_func(message, level=level)
    
    def get_state(self, entity_id: str, default=None):
        """
        Get entity state safely.
        
        Args:
            entity_id: Entity ID
            default: Default value if entity doesn't exist
            
        Returns:
            Entity state or default
        """
        try:
            state = self.hass.get_state(entity_id)
            return state if state not in [None, "unknown", "unavailable"] else default
        except:
            return default
    
    def get_value(self, value_or_entity: Any, default=None) -> Any:
        """
        Smart helper that handles both hardcoded values and entity references.
        
        If value_or_entity looks like a sensor name (contains '.'), fetch from HA.
        Otherwise, treat as a literal value (number, string, etc.)
        
        Args:
            value_or_entity: Either a literal value (32, "hello") or entity ID ("sensor.battery_soc")
            default: Default if entity not found
            
        Returns:
            The value (either literal or from entity state)
            
        Examples:
            get_value(32) -> 32
            get_value("sensor.battery_capacity") -> 10.0 (from HA)
            get_value("hello") -> "hello"
        """
        if value_or_entity is None:
            return default
        
        # Convert to string to check
        value_str = str(value_or_entity)
        
        # If it contains a dot and looks like an entity ID, fetch from HA
        if '.' in value_str and ('sensor.' in value_str or 'number.' in value_str or 
                                  'binary_sensor.' in value_str or 'switch.' in value_str):
            state = self.get_state(value_str, default)
            # Try to convert to number if possible
            try:
                return float(state) if state is not None else default
            except (ValueError, TypeError):
                return state if state is not None else default
        
        # Otherwise return the literal value
        # Try to keep original type (int, float, str, etc.)
        return value_or_entity
    
    def set_value(self, entity_id: str, value, service: str = "set_value") -> bool:
        """
        Set entity value safely.
        
        Args:
            entity_id: Entity ID
            value: Value to set
            service: Service to call (set_value, select_option, etc.)
            
        Returns:
            bool: True if successful
        """
        try:
            domain = entity_id.split('.')[0]
            
            if service == "set_value":
                self.hass.call_service(f"{domain}/set_value", 
                    entity_id=entity_id, 
                    value=value
                )
            elif service == "select_option":
                self.hass.call_service(f"{domain}/select_option",
                    entity_id=entity_id,
                    option=value
                )
            else:
                self.hass.call_service(service,
                    entity_id=entity_id,
                    **value if isinstance(value, dict) else {"value": value}
                )
            
            return True
        except Exception as e:
            self.log(f"Failed to set {entity_id} to {value}: {e}", level="ERROR")
            return False


class InverterCommand:
    """
    Data class representing a command to execute on the inverter.
    Used by the controller to pass commands to the interface.
    """
    
    def __init__(self, action: str, start_time: Optional[time] = None, 
                 end_time: Optional[time] = None, target_soc: Optional[int] = None,
                 current_amps: Optional[float] = None):
        """
        Create an inverter command.
        
        Args:
            action: Action type ('force_charge', 'force_discharge', 'clear_slots', 'idle')
            start_time: Start time for timed action
            end_time: End time for timed action
            target_soc: Target SOC for charge/discharge
            current_amps: Charge/discharge current
        """
        self.action = action
        self.start_time = start_time
        self.end_time = end_time
        self.target_soc = target_soc
        self.current_amps = current_amps
        self.timestamp = datetime.now()
    
    def __repr__(self):
        if self.action == 'force_charge':
            return f"ForceCharge({self.start_time}-{self.end_time}, SOC={self.target_soc}%)"
        elif self.action == 'force_discharge':
            return f"ForceDischarge({self.start_time}-{self.end_time}, SOC={self.target_soc}%)"
        elif self.action == 'clear_slots':
            return "ClearSlots()"
        else:
            return f"Idle()"
    
    def to_dict(self) -> Dict:
        """Convert command to dictionary"""
        return {
            'action': self.action,
            'start_time': self.start_time.strftime('%H:%M') if self.start_time else None,
            'end_time': self.end_time.strftime('%H:%M') if self.end_time else None,
            'target_soc': self.target_soc,
            'current_amps': self.current_amps,
            'timestamp': self.timestamp.isoformat()
        }
