"""
Base Planner Interface

Abstract base class that all planners must implement.
Ensures consistent interface across rule-based, ML, and LP planners.
"""

from abc import ABC, abstractmethod
from typing import Dict, List
from datetime import datetime


class BasePlanner(ABC):
    """
    Abstract base class for all battery optimization planners.
    
    All planners (rule-based, ML, LP) must implement this interface
    to ensure consistent behavior and interchangeability.
    """
    
    # ── Battery efficiency defaults ──
    # These can be overridden via system_state['capabilities'] or constructor
    DEFAULT_CHARGE_EFFICIENCY = 0.95      # AC → battery: 5% loss
    DEFAULT_DISCHARGE_EFFICIENCY = 0.95   # Battery → AC: 5% loss
    # Round-trip = charge × discharge = 0.95 × 0.95 = 0.9025 ≈ 90%
    
    # Arbitrage thresholds
    DEFAULT_MIN_PROFIT_MARGIN = 2.0       # pence per kWh minimum profit after losses
    
    def __init__(self, charge_efficiency=None, discharge_efficiency=None, min_profit_margin=None):
        self.charge_efficiency = charge_efficiency or self.DEFAULT_CHARGE_EFFICIENCY
        self.discharge_efficiency = discharge_efficiency or self.DEFAULT_DISCHARGE_EFFICIENCY
        self.min_profit_margin = min_profit_margin or self.DEFAULT_MIN_PROFIT_MARGIN
        self.round_trip_efficiency = self.charge_efficiency * self.discharge_efficiency
    
    @abstractmethod
    def create_plan(self,
                   import_prices: List[Dict],
                   export_prices: List[Dict],
                   solar_forecast: List[Dict],
                   load_forecast: List[Dict],
                   system_state: Dict) -> Dict:
        """
        Create an optimal battery plan.
        
        Args:
            import_prices: List of dicts with {'time': datetime, 'price': float}
            export_prices: List of dicts with {'time': datetime, 'price': float}
            solar_forecast: List of dicts with {'time': datetime, 'kw': float}
            load_forecast: List of dicts with {'time': datetime, 'load_kw': float, 'confidence': str}
            system_state: Dict with:
                - 'current_state': {'battery_soc': float, ...}
                - 'capabilities': {'battery_capacity': float, 'max_charge_rate': float, ...}
                - 'active_slots': {'charge': [], 'discharge': []}
                - 'mode_switch': {'entity': str, 'current_mode': str}
        
        Returns:
            Dict with:
                - 'timestamp': datetime
                - 'slots': List[Dict] - Plan for each 30-min slot
                - 'metadata': Dict - Plan statistics and info
        """
        pass
    
    def log(self, message: str):
        """
        Log a message (can be overridden by subclasses).
        
        Args:
            message: Message to log
        """
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"[{timestamp}] [{self.__class__.__name__}] {message}")
    
    def validate_inputs(self,
                       import_prices: List[Dict],
                       export_prices: List[Dict],
                       solar_forecast: List[Dict],
                       load_forecast: List[Dict],
                       system_state: Dict) -> bool:
        """
        Validate input data format.
        
        Returns:
            True if inputs are valid, raises ValueError otherwise
        """
        # Check lists are not empty
        if not import_prices:
            raise ValueError("import_prices cannot be empty")
        if not export_prices:
            raise ValueError("export_prices cannot be empty")
        if not solar_forecast:
            raise ValueError("solar_forecast cannot be empty")
        if not load_forecast:
            raise ValueError("load_forecast cannot be empty")
        
        # Check all lists have same length
        n_slots = len(import_prices)
        if len(export_prices) != n_slots:
            raise ValueError(f"export_prices length {len(export_prices)} != import_prices length {n_slots}")
        if len(solar_forecast) != n_slots:
            raise ValueError(f"solar_forecast length {len(solar_forecast)} != import_prices length {n_slots}")
        if len(load_forecast) != n_slots:
            raise ValueError(f"load_forecast length {len(load_forecast)} != import_prices length {n_slots}")
        
        # Check required fields in system_state
        if 'current_state' not in system_state:
            raise ValueError("system_state must contain 'current_state'")
        if 'capabilities' not in system_state:
            raise ValueError("system_state must contain 'capabilities'")
        
        if 'battery_soc' not in system_state['current_state']:
            raise ValueError("current_state must contain 'battery_soc'")
        
        required_capabilities = ['battery_capacity', 'max_charge_rate', 'max_discharge_rate']
        for cap in required_capabilities:
            if cap not in system_state['capabilities']:
                raise ValueError(f"capabilities must contain '{cap}'")
        
        return True
    
    def get_planner_info(self) -> Dict:
        """
        Get information about this planner.
        
        Returns:
            Dict with planner metadata
        """
        return {
            'name': self.__class__.__name__,
            'type': 'unknown',
            'version': '2.3',
            'description': 'Base planner interface'
        }
