"""
Cost Optimizer - Minimize Electricity Costs

Generates optimal charge/discharge schedule based on:
- Import/export prices
- Solar forecast
- Load forecast
- Battery constraints

The optimizer ONLY charges when:
1. It's needed (would otherwise run out of battery)
2. It's profitable (buy cheap, sell expensive)
3. It avoids wastage (don't overfill before solar)
"""

from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional


class CostOptimizer:
    """
    Generates optimal battery charge/discharge schedule to minimize costs.
    
    Uses simple but effective heuristics:
    - Never charge if solar will cover needs
    - Only charge if cheaper than future prices
    - Only discharge if profitable (export > import + margin)
    - Avoid solar wastage (don't fill battery before sunny period)
    """
    
    def __init__(self, hass):
        self.hass = hass
        self.log_func = print
    
    def log(self, message: str, level: str = "INFO"):
        """Log a message"""
        if hasattr(self.hass, 'log'):
            self.hass.log(message, level=level)
        else:
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{timestamp}] {message}")
    
    def optimize(self,
                 prices: List[Dict],
                 solar_forecast: List[Dict],
                 load_forecast: List[Dict],
                 battery_soc: float,
                 battery_capacity: float,
                 max_charge_rate: float,
                 max_discharge_rate: float,
                 export_price: float = 15.0,
                 min_soc: float = 10.0,
                 max_soc: float = 95.0) -> List[Dict]:
        """
        Generate optimal 24-hour plan.
        
        Args:
            prices: Import price forecast (list of dicts with 'start', 'price')
            solar_forecast: Solar generation forecast (list with 'period_end', 'pv_estimate')
            load_forecast: Load forecast (list with 'time', 'load_kw')
            battery_soc: Current battery SOC (%)
            battery_capacity: Battery capacity (kWh)
            max_charge_rate: Max charge power (kW)
            max_discharge_rate: Max discharge power (kW)
            export_price: Export price (p/kWh)
            min_soc: Minimum SOC to maintain (%)
            max_soc: Maximum SOC to charge to (%)
            
        Returns:
            List of plan steps with mode, action, SOC for each slot
        """
        self.log("[OPT] Generating optimal plan...")
        
        plan = []
        current_soc = battery_soc
        
        # Align all forecasts to 30-min slots
        slots = self._align_forecasts(prices, solar_forecast, load_forecast)
        
        self.log(f"[OPT] Planning for {len(slots)} slots")
        self.log(f"[OPT] Starting SOC: {current_soc:.1f}%")
        self.log(f"[OPT] Battery: {battery_capacity}kWh, Charge: {max_charge_rate}kW, Discharge: {max_discharge_rate}kW")
        
        for i, slot in enumerate(slots):
            # Store future slots for clipping analysis
            self._future_slots = slots[i:]
            
            # Calculate energy balance for this slot
            solar_kwh = slot['solar_kw'] * 0.5  # 30 minutes
            load_kwh = slot['load_kw'] * 0.5
            import_price = slot['import_price']
            
            # Look ahead to make smart decisions
            future_deficit = self._calculate_future_deficit(
                slots[i:], current_soc, battery_capacity, min_soc
            )
            future_solar_surplus = self._calculate_future_solar_surplus(slots[i:])
            future_min_price = min((s['import_price'] for s in slots[i:]), default=import_price)
            
            # Decide mode
            mode, action, soc_change = self._decide_mode(
                current_soc=current_soc,
                solar_kwh=solar_kwh,
                load_kwh=load_kwh,
                import_price=import_price,
                export_price=export_price,
                future_deficit=future_deficit,
                future_solar_surplus=future_solar_surplus,
                future_min_price=future_min_price,
                battery_capacity=battery_capacity,
                max_charge_rate=max_charge_rate,
                max_discharge_rate=max_discharge_rate,
                min_soc=min_soc,
                max_soc=max_soc
            )
            
            # Update SOC
            new_soc = max(min_soc, min(max_soc, current_soc + soc_change))
            
            # Calculate cost for this slot
            slot_cost = self._calculate_slot_cost(
                mode=mode,
                soc_change=soc_change,
                solar_kwh=solar_kwh,
                load_kwh=load_kwh,
                import_price=import_price,
                export_price=export_price,
                battery_capacity=battery_capacity
            )
            
            plan.append({
                'time': slot['time'],
                'mode': mode,
                'action': action,
                'soc_start': current_soc,
                'soc_end': new_soc,
                'soc_change': soc_change,
                'solar_kw': slot['solar_kw'],
                'load_kw': slot['load_kw'],
                'import_price': import_price,
                'export_price': export_price,
                'cost': slot_cost,  # Cost in pence for this slot
                'is_predicted_price': slot.get('is_predicted', False),
                'load_confidence': slot.get('load_confidence', 'unknown')
            })
            
            current_soc = new_soc
        
        # Calculate cumulative costs
        cumulative = 0.0
        for step in plan:
            cumulative += step['cost']
            step['cumulative_cost'] = cumulative
        
        # Log summary
        charge_slots = sum(1 for p in plan if p['mode'] == 'Force Charge')
        discharge_slots = sum(1 for p in plan if p['mode'] == 'Force Discharge')
        total_cost = cumulative / 100  # Convert pence to pounds
        
        self.log(f"[OPT] Plan complete: {charge_slots} charge slots, {discharge_slots} discharge slots")
        self.log(f"[OPT] Total estimated cost: £{total_cost:.2f} over 24 hours")
        
        return plan
    
    def _align_forecasts(self, prices, solar_forecast, load_forecast) -> List[Dict]:
        """Align all forecasts to common 30-min time slots"""
        slots = []
        
        for price in prices[:48]:  # 24 hours
            slot_time = price['start']
            
            # Find matching solar
            solar_kw = 0.0
            for sf in solar_forecast:
                if abs((sf['period_end'] - slot_time).total_seconds()) < 1800:  # Within 30 min
                    solar_kw = sf['pv_estimate']
                    break
            
            # Find matching load
            load_kw = 1.0  # Default 1kW if no forecast
            load_confidence = 'unknown'
            for lf in load_forecast:
                if abs((lf['time'] - slot_time).total_seconds()) < 1800:
                    load_kw = lf['load_kw']
                    load_confidence = lf.get('confidence', 'unknown')
                    break
            
            slots.append({
                'time': slot_time,
                'solar_kw': solar_kw,
                'load_kw': load_kw,
                'import_price': price['price'],
                'is_predicted': price.get('is_predicted', False),
                'load_confidence': load_confidence
            })
        
        return slots
    
    def _calculate_future_deficit(self, future_slots, current_soc, battery_capacity, min_soc) -> float:
        """Calculate if we'll run out of battery without charging"""
        available_kwh = (current_soc - min_soc) / 100 * battery_capacity
        deficit_kwh = 0.0
        
        for slot in future_slots:
            net_need = slot['load_kw'] - slot['solar_kw']
            if net_need > 0:
                if available_kwh >= net_need * 0.5:
                    available_kwh -= net_need * 0.5
                else:
                    deficit_kwh += (net_need * 0.5 - available_kwh)
                    available_kwh = 0
            else:
                # Solar surplus could charge battery
                available_kwh += min((-net_need * 0.5), (100 - current_soc) / 100 * battery_capacity)
        
        return deficit_kwh
    
    def _calculate_future_solar_surplus(self, future_slots) -> float:
        """Calculate how much excess solar we'll have"""
        surplus = 0.0
        
        for slot in future_slots[:12]:  # Next 6 hours
            net = slot['solar_kw'] - slot['load_kw']
            if net > 0:
                surplus += net * 0.5
        
        return surplus
    
    def _decide_mode(self, current_soc, solar_kwh, load_kwh, import_price, export_price,
                     future_deficit, future_solar_surplus, future_min_price,
                     battery_capacity, max_charge_rate, max_discharge_rate,
                     min_soc, max_soc) -> Tuple[str, str, float]:
        """
        Decide what to do this slot based on smart analysis.
        
        Returns:
            (mode, action_description, soc_change)
        """
        
        # Check if we have a deficit coming and need to charge
        needs_charging = future_deficit > 0.5  # More than 0.5kWh deficit
        
        # Check if battery is nearly full and solar coming (wastage risk)
        wastage_risk = (current_soc > 80 and future_solar_surplus > 2.0)
        
        # Check for solar clipping risk
        # If we have high solar coming and battery is full, we'll clip (waste) solar
        # Export limit is typically 5kW, so anything above that + load gets clipped
        export_limit = 5.0  # kW - typical DNO limit
        clipping_risk = False
        future_clipping_kwh = 0.0
        slots_until_clipping = 0
        
        # Look ahead to find when clipping will occur and how much
        for i, future_slot in enumerate(self._future_slots if hasattr(self, '_future_slots') else []):
            future_solar = future_slot.get('solar_kw', 0)
            future_load = future_slot.get('load_kw', 0)
            
            # Surplus that would need to go somewhere
            surplus = future_solar - future_load
            
            if surplus > export_limit:
                # We can't export it all - will clip unless battery has space
                potential_clip = surplus - export_limit
                
                # Check if battery will be full by then
                # Estimate: current SOC + any solar charging between now and then
                if current_soc > 85:  # If already high, likely to be full
                    if slots_until_clipping == 0:  # First occurrence
                        slots_until_clipping = i
                    clipping_risk = True
                    future_clipping_kwh += potential_clip * 0.5  # 30 min slot
        
        # Calculate if we need to discharge NOW to make space
        should_discharge_for_clipping = False
        
        if clipping_risk and future_clipping_kwh > 0.1:  # More than 0.1kWh will clip
            # Calculate available battery energy that could be discharged
            available_kwh = (current_soc - 50) / 100 * battery_capacity  # Don't go below 50%
            
            # Calculate how long it takes to discharge what we need
            # We need to clear at least future_clipping_kwh from battery
            kwh_to_discharge = min(future_clipping_kwh, available_kwh)
            
            if kwh_to_discharge > 0:
                # How many 30-min slots needed to discharge this?
                # max_discharge_rate is in kW, so in 30 min we can discharge: rate * 0.5
                kwh_per_slot = max_discharge_rate * 0.5
                slots_needed = int(kwh_to_discharge / kwh_per_slot) + 1
                
                # Should we start discharging now?
                # Start if: slots_until_clipping <= slots_needed
                # This ensures we finish discharging just as clipping period starts
                if slots_until_clipping <= slots_needed:
                    should_discharge_for_clipping = True
        
        # Calculate energy balance for this slot
        net_energy = solar_kwh - load_kwh
        
        # Decision logic
        
        # 0. CLIPPING PREVENTION (HIGHEST PRIORITY): Discharge before high solar if battery full
        # Better to use/export battery power now than waste solar later
        if should_discharge_for_clipping and current_soc > 55:
            mode = 'Force Discharge'
            hours_until = slots_until_clipping * 0.5
            action = f"Preventing {future_clipping_kwh:.1f}kWh solar clipping in {hours_until:.1f}h, clearing battery space"
            # Discharge at max rate
            discharge_kwh = min(
                max_discharge_rate * 0.5,
                (current_soc - 50) / 100 * battery_capacity  # Don't go below 50%
            )
            soc_change = -(discharge_kwh / battery_capacity) * 100
            return mode, action, soc_change
        
        # 1. ARBITRAGE OPPORTUNITY: If we can buy cheap and sell expensive later, do it!
        # With 90% round-trip efficiency:
        # - Buy 1kWh at Xp, store/retrieve at 90% = 0.9kWh
        # - Sell 0.9kWh at Yp = revenue
        # - Need Y > X + (X * 0.11) to profit (covers 10% loss + small margin)
        # Simplified: if export > import + 1p, it's profitable
        arbitrage_margin = 1.0  # Minimum 1p profit after round-trip losses
        profitable_arbitrage = (export_price > import_price + arbitrage_margin)
        
        if profitable_arbitrage and current_soc < 92 and not clipping_risk:  # Allow up to 92% for arbitrage
            mode = 'Force Charge'
            net_profit = export_price - import_price
            action = f"Arbitrage opportunity: buy {import_price:.2f}p, sell {export_price:.2f}p = {net_profit:.2f}p profit/kWh"
            charge_kwh = min(max_charge_rate * 0.5, (max_soc - current_soc) / 100 * battery_capacity)
            soc_change = (charge_kwh / battery_capacity) * 100
            return mode, action, soc_change
        
        # 2. If battery low and deficit coming, charge if price reasonable
        if current_soc < 30 and needs_charging:
            if import_price <= future_min_price * 1.1:  # Within 10% of future minimum
                mode = 'Force Charge'
                action = f"Low SOC + future deficit, charging at {import_price:.2f}p (reasonable vs future {future_min_price:.2f}p)"
                charge_kwh = min(max_charge_rate * 0.5, (max_soc - current_soc) / 100 * battery_capacity)
                soc_change = (charge_kwh / battery_capacity) * 100
                return mode, action, soc_change
        
        # 3. If wastage risk (battery full, solar coming), DON'T charge
        if wastage_risk and current_soc > 70:
            mode = 'Self Use'
            action = f"Avoiding wastage (SOC {current_soc:.0f}%, {future_solar_surplus:.1f}kWh solar coming)"
            # Let battery discharge naturally
            soc_change = -(load_kwh - solar_kwh) / battery_capacity * 100
            return mode, action, max(-2, soc_change)
        
        # 4. If export price > import price + margin, discharge (was already doing this)
        if export_price > import_price + 2.0 and current_soc > 40:
            mode = 'Force Discharge'
            action = f"Profitable export (earn {export_price:.2f}p vs pay {import_price:.2f}p)"
            discharge_kwh = min(max_discharge_rate * 0.5, (current_soc - min_soc) / 100 * battery_capacity)
            soc_change = -(discharge_kwh / battery_capacity) * 100
            return mode, action, soc_change
        
        # 5. Otherwise, self-use mode
        mode = 'Self Use'
        
        if solar_kwh > load_kwh + 0.1:
            # Solar surplus - charging battery
            surplus = solar_kwh - load_kwh
            charge_kwh = min(surplus, (max_soc - current_soc) / 100 * battery_capacity)
            soc_change = (charge_kwh / battery_capacity) * 100
            action = f"Solar surplus {surplus:.2f}kWh, charging battery"
        elif solar_kwh < load_kwh - 0.1:
            # Load exceeds solar - using battery
            deficit = load_kwh - solar_kwh
            discharge_kwh = min(deficit, (current_soc - min_soc) / 100 * battery_capacity)
            soc_change = -(discharge_kwh / battery_capacity) * 100
            action = f"Load {load_kwh:.2f}kWh > Solar {solar_kwh:.2f}kWh, using battery"
        else:
            # Balanced
            soc_change = 0
            action = f"Balanced (solar {solar_kwh:.2f}kWh ≈ load {load_kwh:.2f}kWh)"
        
        return mode, action, soc_change
    
    def _calculate_slot_cost(self, mode, soc_change, solar_kwh, load_kwh, 
                            import_price, export_price, battery_capacity) -> float:
        """
        Calculate the cost (in pence) for this 30-minute slot.
        
        Cost breakdown:
        - Import from grid: positive cost (we pay)
        - Export to grid: negative cost (we earn)
        - Solar: free
        - Battery: conversion losses only
        
        Returns:
            Cost in pence (positive = cost, negative = revenue)
        """
        # Energy flows in this slot
        grid_import_kwh = 0.0
        grid_export_kwh = 0.0
        
        if mode == 'Force Charge':
            # Charging from grid
            battery_kwh = abs(soc_change) / 100 * battery_capacity
            grid_import_kwh = battery_kwh / 0.95  # Account for charge efficiency
            cost = grid_import_kwh * import_price
            
        elif mode == 'Force Discharge':
            # Discharging to grid
            battery_kwh = abs(soc_change) / 100 * battery_capacity
            grid_export_kwh = battery_kwh * 0.95  # Account for discharge efficiency
            cost = -grid_export_kwh * export_price  # Negative = revenue
            
        else:
            # Self-use mode - calculate what we import/export
            net_energy = load_kwh - solar_kwh  # Net requirement
            
            if net_energy > 0:
                # Need energy - use battery or grid
                if soc_change < 0:
                    # Using battery
                    battery_used = abs(soc_change) / 100 * battery_capacity
                    if battery_used >= net_energy:
                        # Battery covers it all
                        cost = 0.0
                    else:
                        # Need some grid too
                        grid_import_kwh = net_energy - battery_used
                        cost = grid_import_kwh * import_price
                else:
                    # Not using battery, must be importing
                    grid_import_kwh = net_energy
                    cost = grid_import_kwh * import_price
            else:
                # Surplus energy - charge battery or export
                surplus = -net_energy
                
                if soc_change > 0:
                    # Charging battery with solar
                    battery_charge = soc_change / 100 * battery_capacity
                    if battery_charge >= surplus:
                        # All solar goes to battery
                        cost = 0.0
                    else:
                        # Some solar exported
                        grid_export_kwh = surplus - battery_charge
                        cost = -grid_export_kwh * export_price
                else:
                    # Not charging battery, export all surplus
                    grid_export_kwh = surplus
                    cost = -grid_export_kwh * export_price
        
        return cost

