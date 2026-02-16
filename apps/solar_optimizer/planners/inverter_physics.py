"""
Inverter Physics Model

Centralised simulation of inverter/battery/grid/load interactions.
All planners use this to ensure consistent energy flow modelling.

Models a typical hybrid inverter system:
- Solar panels → DC bus → inverter
- Battery ↔ DC bus (charge/discharge)
- Grid ↔ AC bus (import/export)
- House load on AC bus

Key constraints:
- DC clipping: inverter has a max DC input (e.g. 13kW for a 6kW inverter with 17kWp array)
- Export limit: DNO-imposed grid export cap (e.g. 5kW)
- Battery charge/discharge rate limits
- Min/max SOC limits
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass
class SlotResult:
    """Result of simulating one 30-minute slot"""
    soc_change: float       # Percentage change in SOC
    grid_import_kwh: float  # Energy imported from grid
    grid_export_kwh: float  # Energy exported to grid
    battery_charge_kwh: float   # Energy into battery
    battery_discharge_kwh: float # Energy out of battery
    solar_used_kwh: float   # Solar consumed (load + battery + export)
    clipped_kwh: float      # Solar energy wasted (couldn't use or export)
    cost_pence: float       # Net cost (positive = cost, negative = revenue)
    action: str             # Human-readable description


class InverterPhysics:
    """
    Models energy flows through a hybrid inverter system.
    
    Usage:
        physics = InverterPhysics(
            battery_capacity=32.0,
            max_charge_rate=8.0,
            max_discharge_rate=3.12,
            charge_efficiency=0.95,
            discharge_efficiency=0.95,
            export_limit=5.0,
            min_soc=10.0,
            max_soc=95.0
        )
        
        result = physics.simulate_self_use(
            solar_kw=10.0, load_kw=1.0, current_soc=50.0
        )
    """
    
    SLOT_HOURS = 0.5  # 30-minute slots
    
    def __init__(self, 
                 battery_capacity: float = 10.0,
                 max_charge_rate: float = 3.0,
                 max_discharge_rate: float = 3.0,
                 charge_efficiency: float = 0.95,
                 discharge_efficiency: float = 0.95,
                 export_limit: float = 5.0,
                 min_soc: float = 10.0,
                 max_soc: float = 95.0):
        self.battery_capacity = battery_capacity
        self.max_charge_rate = max_charge_rate
        self.max_discharge_rate = max_discharge_rate
        self.charge_efficiency = charge_efficiency
        self.discharge_efficiency = discharge_efficiency
        self.export_limit = export_limit
        self.min_soc = min_soc
        self.max_soc = max_soc
    
    @property
    def round_trip_efficiency(self) -> float:
        return self.charge_efficiency * self.discharge_efficiency
    
    def _soc_headroom_kwh(self, current_soc: float) -> float:
        """How much energy can be added to battery (kWh)"""
        return max(0, (self.max_soc - current_soc) / 100 * self.battery_capacity)
    
    def _soc_available_kwh(self, current_soc: float) -> float:
        """How much energy can be drawn from battery (kWh)"""
        return max(0, (current_soc - self.min_soc) / 100 * self.battery_capacity)
    
    def _kwh_to_soc(self, kwh: float) -> float:
        """Convert kWh to SOC percentage change"""
        return (kwh / self.battery_capacity) * 100
    
    def simulate_self_use(self, solar_kw: float, load_kw: float, 
                          current_soc: float, import_price: float = 0,
                          export_price: float = 0) -> SlotResult:
        """
        Self-Use mode: Solar → battery first, overflow → grid export.
        
        Energy flow priority:
        1. Solar serves house load directly
        2. Excess solar charges battery (up to charge rate & headroom)
        3. Remaining excess exports to grid (up to export limit)
        4. Any further excess is clipped
        5. If load > solar, battery serves deficit
        6. If battery can't cover, import from grid
        """
        dt = self.SLOT_HOURS
        
        grid_import = 0.0
        grid_export = 0.0
        battery_charge = 0.0
        battery_discharge = 0.0
        clipped = 0.0
        
        net_solar = solar_kw - load_kw  # Positive = surplus, negative = deficit
        
        if net_solar > 0:
            # Solar surplus: charge battery, then export, then clip
            headroom = self._soc_headroom_kwh(current_soc)
            max_charge_kwh = self.max_charge_rate * dt
            battery_charge = min(net_solar * dt, max_charge_kwh, headroom)
            
            remaining_kw = net_solar - (battery_charge / dt)
            export_kw = min(remaining_kw, self.export_limit)
            grid_export = export_kw * dt
            
            clipped_kw = max(0, remaining_kw - self.export_limit)
            clipped = clipped_kw * dt
            
        else:
            # Load deficit: battery serves, then grid imports
            deficit_kwh = abs(net_solar) * dt
            available = self._soc_available_kwh(current_soc)
            max_discharge_kwh = self.max_discharge_rate * dt
            battery_discharge = min(deficit_kwh, max_discharge_kwh, available)
            
            shortfall = deficit_kwh - battery_discharge
            if shortfall > 0:
                grid_import = shortfall
        
        # Calculate SOC change
        soc_change = self._kwh_to_soc(battery_charge) - self._kwh_to_soc(battery_discharge)
        
        # Calculate cost
        cost = (grid_import * import_price) - (grid_export * export_price)
        
        # Generate action description
        if net_solar > 0:
            if battery_charge > 0.01:
                action = f"Solar surplus {net_solar:.1f}kW: +{battery_charge:.2f}kWh battery"
                if grid_export > 0.01:
                    action += f", {grid_export:.2f}kWh export"
                if clipped > 0.01:
                    action += f", {clipped:.2f}kWh clipped"
            elif grid_export > 0.01:
                action = f"Solar surplus, exporting {grid_export:.2f}kWh"
            else:
                action = f"Balanced (solar {solar_kw:.1f}kW ≈ load {load_kw:.1f}kW)"
        else:
            if battery_discharge > 0.01:
                action = f"Load {load_kw:.2f}kWh > Solar {solar_kw:.2f}kWh, using battery"
                if grid_import > 0.01:
                    action += f" + {grid_import:.2f}kWh grid"
            elif grid_import > 0.01:
                action = f"Importing {grid_import/dt:.2f}kW to meet load"
            else:
                action = f"Balanced"
        
        solar_used = min(solar_kw, load_kw) * dt + battery_charge + grid_export
        
        return SlotResult(
            soc_change=soc_change,
            grid_import_kwh=grid_import,
            grid_export_kwh=grid_export,
            battery_charge_kwh=battery_charge,
            battery_discharge_kwh=battery_discharge,
            solar_used_kwh=solar_used,
            clipped_kwh=clipped,
            cost_pence=cost,
            action=action
        )
    
    def simulate_feed_in_priority(self, solar_kw: float, load_kw: float,
                                   current_soc: float, import_price: float = 0,
                                   export_price: float = 0) -> SlotResult:
        """
        Feed-in Priority mode: Solar → grid first, overflow → battery.
        
        Energy flow priority:
        1. Solar exports to grid first (up to export limit)
        2. Remaining solar serves house load
        3. Any remaining charges battery
        4. If load not met by solar remainder, battery serves deficit
        5. If battery can't cover, import from grid
        """
        dt = self.SLOT_HOURS
        
        grid_import = 0.0
        grid_export = 0.0
        battery_charge = 0.0
        battery_discharge = 0.0
        clipped = 0.0
        
        # Grid gets first priority on solar (up to export limit)
        grid_export_kw = min(solar_kw, self.export_limit)
        grid_export = grid_export_kw * dt
        
        after_grid_kw = max(0, solar_kw - grid_export_kw)
        
        # Remainder serves load
        load_from_solar_kw = min(after_grid_kw, load_kw)
        after_load_kw = max(0, after_grid_kw - load_from_solar_kw)
        
        # Battery charges from overflow
        if after_load_kw > 0:
            headroom = self._soc_headroom_kwh(current_soc)
            max_charge_kwh = self.max_charge_rate * dt
            battery_charge = min(after_load_kw * dt, max_charge_kwh, headroom)
            
            remaining_kw = after_load_kw - (battery_charge / dt)
            clipped = max(0, remaining_kw) * dt
        
        # Load not covered by solar drains battery
        unmet_load_kw = max(0, load_kw - load_from_solar_kw)
        if unmet_load_kw > 0:
            deficit_kwh = unmet_load_kw * dt
            available = self._soc_available_kwh(current_soc)
            max_discharge_kwh = self.max_discharge_rate * dt
            battery_discharge = min(deficit_kwh, max_discharge_kwh, available)
            
            shortfall = deficit_kwh - battery_discharge
            if shortfall > 0:
                grid_import = shortfall
        
        soc_change = self._kwh_to_soc(battery_charge) - self._kwh_to_soc(battery_discharge)
        cost = (grid_import * import_price) - (grid_export * export_price)
        
        action = f"Grid-first: {grid_export_kw:.1f}kW export"
        if battery_charge > 0.01:
            action += f", +{battery_charge:.2f}kWh battery"
        if battery_discharge > 0.01:
            action += f", -{battery_discharge:.2f}kWh battery (load)"
        
        solar_used = load_from_solar_kw * dt + battery_charge + grid_export
        
        return SlotResult(
            soc_change=soc_change,
            grid_import_kwh=grid_import,
            grid_export_kwh=grid_export,
            battery_charge_kwh=battery_charge,
            battery_discharge_kwh=battery_discharge,
            solar_used_kwh=solar_used,
            clipped_kwh=clipped,
            cost_pence=cost,
            action=action
        )
    
    def simulate_force_charge(self, solar_kw: float, load_kw: float,
                               current_soc: float, charge_rate_kw: float = None,
                               import_price: float = 0, export_price: float = 0) -> SlotResult:
        """
        Force Charge: Grid charges battery at specified rate.
        Solar still serves load; excess solar also charges battery.
        """
        dt = self.SLOT_HOURS
        rate = charge_rate_kw or self.max_charge_rate
        
        headroom = self._soc_headroom_kwh(current_soc)
        
        # Solar serves load first
        solar_to_load = min(solar_kw, load_kw)
        grid_for_load = max(0, load_kw - solar_to_load) * dt
        
        # Battery charges from grid + excess solar
        excess_solar_kw = max(0, solar_kw - load_kw)
        total_charge_kw = rate + excess_solar_kw
        charge_kwh = min(total_charge_kw * dt, headroom)
        
        # Grid provides the charge power (minus what solar contributes)
        solar_charge_kwh = min(excess_solar_kw * dt, charge_kwh)
        grid_charge_kwh = charge_kwh - solar_charge_kwh
        
        # Account for charge efficiency loss on grid charging
        grid_import = grid_for_load + (grid_charge_kwh / self.charge_efficiency)
        
        soc_change = self._kwh_to_soc(charge_kwh)
        cost = grid_import * import_price
        
        action = f"Charging at {rate:.2f}kW from grid (import {import_price:.2f}p)"
        
        return SlotResult(
            soc_change=soc_change,
            grid_import_kwh=grid_import,
            grid_export_kwh=0.0,
            battery_charge_kwh=charge_kwh,
            battery_discharge_kwh=0.0,
            solar_used_kwh=(solar_to_load + excess_solar_kw) * dt,
            clipped_kwh=0.0,
            cost_pence=cost,
            action=action
        )
    
    def simulate_force_discharge(self, solar_kw: float, load_kw: float,
                                  current_soc: float, discharge_rate_kw: float = None,
                                  import_price: float = 0, export_price: float = 0,
                                  target_soc: float = None) -> SlotResult:
        """
        Force Discharge: Battery exports to grid at specified rate.
        Solar still serves load.
        """
        dt = self.SLOT_HOURS
        rate = discharge_rate_kw or self.max_discharge_rate
        
        available = self._soc_available_kwh(current_soc)
        if target_soc is not None:
            available = max(0, (current_soc - target_soc) / 100 * self.battery_capacity)
        
        # Solar serves load
        solar_to_load = min(solar_kw, load_kw)
        
        # Battery discharges
        discharge_kwh = min(rate * dt, available)
        
        # After discharge efficiency, this reaches the AC bus
        ac_output_kwh = discharge_kwh * self.discharge_efficiency
        
        # Serve any remaining load from battery output
        remaining_load_kwh = max(0, (load_kw - solar_to_load)) * dt
        battery_to_load = min(ac_output_kwh, remaining_load_kwh)
        
        # Rest goes to grid export
        grid_export = min(ac_output_kwh - battery_to_load, self.export_limit * dt)
        
        soc_change = -self._kwh_to_soc(discharge_kwh)
        cost = -(grid_export * export_price)
        
        action = f"Discharging at {rate:.1f}kW"
        if grid_export > 0.01:
            action += f", exporting {grid_export:.2f}kWh at {export_price:.1f}p"
        
        return SlotResult(
            soc_change=soc_change,
            grid_import_kwh=0.0,
            grid_export_kwh=grid_export,
            battery_charge_kwh=0.0,
            battery_discharge_kwh=discharge_kwh,
            solar_used_kwh=solar_to_load * dt,
            clipped_kwh=0.0,
            cost_pence=cost,
            action=action
        )
