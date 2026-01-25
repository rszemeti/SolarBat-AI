"""
Rule-Based Planner - Heuristic Battery Optimization

Uses expert-designed heuristic rules to create optimal battery plans:
- Strategic Feed-in Priority for clipping prevention
- Arbitrage opportunities (buy cheap, sell expensive)
- Deficit prevention
- Wastage avoidance

Originally PlanCreator, renamed for clarity.
Inherits from BasePlanner to ensure consistent interface.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import sys
from pathlib import Path

# Import base planner
from .base_planner import BasePlanner


class RuleBasedPlanner(BasePlanner):
    """
    Rule-based battery optimization planner.
    
    Uses heuristic rules to optimize battery usage based on:
    - Solar forecast (prevent clipping)
    - Price forecast (arbitrage opportunities)
    - Load forecast (prevent deficit)
    - Battery state (SOC management)
    """
    """
    Creates optimal battery plan from provider data.
    
    No HA access - pure optimization engine.
    All data comes from providers.
    """
    
    def __init__(self):
        """Initialize plan creator (stateless)"""
        self.log_func = print
    
    def log(self, message: str, level: str = "INFO"):
        """Log a message"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"[{timestamp}] [PLAN] {message}")
    
    def create_plan(self,
                   import_prices: List[Dict],
                   export_prices: List[Dict],
                   solar_forecast: List[Dict],
                   load_forecast: List[Dict],
                   system_state: Dict) -> Dict:
        """
        Create optimal plan from provider data.
        
        Args:
            import_prices: [{'time': datetime, 'price': float, 'is_predicted': bool}]
            export_prices: [{'time': datetime, 'price': float}]
            solar_forecast: [{'time': datetime, 'kw': float}]
            load_forecast: [{'time': datetime, 'kw': float, 'confidence': str}]
            system_state: {'current_state': {...}, 'capabilities': {...}}
            
        Returns:
            Plan dict with slots and metadata
        """
        self.log("Creating optimal plan from provider data...")
        
        # Extract system state
        current_state = system_state.get('current_state', {})
        capabilities = system_state.get('capabilities', {})
        
        battery_soc = current_state.get('battery_soc', 50.0)
        battery_capacity = capabilities.get('battery_capacity', 10.0)
        max_charge_rate = capabilities.get('max_charge_rate', 3.0)
        max_discharge_rate = capabilities.get('max_discharge_rate', 3.0)
        
        # Get export price (use first from list, they should all be same if fixed)
        export_price_value = export_prices[0]['price'] if export_prices else 15.0
        
        self.log(f"Starting SOC: {battery_soc:.1f}%")
        self.log(f"Battery: {battery_capacity}kWh, Charge: {max_charge_rate}kW, Discharge: {max_discharge_rate}kW")
        
        # Convert provider format to internal format for _optimize
        # Import prices: {'time': dt, 'price': float} -> {'start': dt, 'price': float}
        prices_internal = [{'start': p['time'], 'price': p['price'], 'is_predicted': p.get('is_predicted', False)} 
                          for p in import_prices]
        
        # Solar: {'time': dt, 'kw': float} -> {'period_end': dt, 'pv_estimate': float}
        solar_internal = [{'period_end': s['time'], 'pv_estimate': s['kw']} 
                         for s in solar_forecast]
        
        # Load: already correct format {'time': dt, 'load_kw': float}
        load_internal = load_forecast
        
        # Call internal optimizer (existing logic)
        plan_slots = self._optimize_internal(
            prices=prices_internal,
            solar_forecast=solar_internal,
            load_forecast=load_internal,
            battery_soc=battery_soc,
            battery_capacity=battery_capacity,
            max_charge_rate=max_charge_rate,
            max_discharge_rate=max_discharge_rate,
            export_price=export_price_value,
            min_soc=10.0,
            max_soc=95.0
        )
        
        # Build proper plan object
        total_cost = plan_slots[-1].get('cumulative_cost', 0) / 100 if plan_slots else 0.0
        
        plan = {
            'timestamp': datetime.now(),
            'slots': plan_slots,
            'metadata': {
                'total_cost': total_cost,
                'confidence': self._calculate_confidence(import_prices, load_forecast),
                'data_sources': {
                    'import_prices': len(import_prices),
                    'export_prices': len(export_prices),
                    'solar_forecast': len(solar_forecast),
                    'load_forecast': len(load_forecast)
                },
                'charge_slots': sum(1 for s in plan_slots if s['mode'] == 'Force Charge'),
                'discharge_slots': sum(1 for s in plan_slots if s['mode'] == 'Force Discharge')
            }
        }
        
        self.log(f"Plan complete: {plan['metadata']['charge_slots']} charge, "
                f"{plan['metadata']['discharge_slots']} discharge, cost: £{total_cost:.2f}")
        
        return plan
    
    def _calculate_confidence(self, import_prices: List[Dict], load_forecast: List[Dict]) -> str:
        """Calculate overall confidence"""
        predicted = sum(1 for p in import_prices if p.get('is_predicted', False))
        if predicted < 10:
            return 'high'
        elif predicted < 20:
            return 'medium'
        else:
            return 'low'
    
    def _optimize_internal(self,
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
        Internal optimization logic with strategic Feed-in Priority mode.
        """
        self.log("Generating optimal plan...")
        
        plan = []
        current_soc = battery_soc
        
        # Align all forecasts to 30-min slots
        slots = self._align_forecasts(prices, solar_forecast, load_forecast)
        
        self.log(f"Planning for {len(slots)} slots")
        self.log(f"Starting SOC: {current_soc:.1f}%")
        self.log(f"Battery: {battery_capacity}kWh, Charge: {max_charge_rate}kW, Discharge: {max_discharge_rate}kW")
        
        # ============================================
        # STRATEGIC DECISION: Should we use Feed-in Priority mode today?
        # ============================================
        feed_in_priority_strategy = self._should_use_feed_in_priority_strategy(
            slots, current_soc, battery_capacity, export_limit=5.0
        )
        
        if feed_in_priority_strategy['use_strategy']:
            self.log(f"📊 STRATEGIC DECISION: Feed-in Priority mode {feed_in_priority_strategy['start_time'].strftime('%H:%M')}-{feed_in_priority_strategy['end_time'].strftime('%H:%M')}")
            self.log(f"   Reason: {feed_in_priority_strategy['reason']}")
        
        # ============================================
        # STRATEGIC DECISION: Do we need pre-sunrise discharge?
        # ============================================
        presunrise_discharge_strategy = self._calculate_presunrise_discharge_strategy(
            slots, current_soc, battery_capacity, max_discharge_rate, feed_in_priority_strategy
        )
        
        if presunrise_discharge_strategy['use_strategy']:
            self.log(f"🌅 PRE-SUNRISE DISCHARGE: {presunrise_discharge_strategy['start_time'].strftime('%H:%M')}-{presunrise_discharge_strategy['end_time'].strftime('%H:%M')}")
            self.log(f"   Target: {presunrise_discharge_strategy['target_soc']:.0f}% SOC")
            self.log(f"   Reason: {presunrise_discharge_strategy['reason']}")
        
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
                slot=slot,
                feed_in_priority_strategy=feed_in_priority_strategy,
                presunrise_discharge_strategy=presunrise_discharge_strategy,
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
    
        
        return plan
    
    def _should_use_feed_in_priority_strategy(self, slots: List[Dict], current_soc: float, 
                                               battery_capacity: float, export_limit: float = 5.0) -> Dict:
        """
        Strategic decision: Should we use Feed-in Priority, and when to transition to Self-Use?
        
        NEW APPROACH: Work backwards from midnight to find optimal transition point.
        This ensures battery doesn't run out in the evening while maximizing feed-in revenue.
        
        Logic:
        1. Start at midnight (tomorrow) with target SOC (e.g., 15%)
        2. Work backwards, simulating Self-Use mode
        3. Find the point where battery would overflow if we continued Self-Use earlier
        4. That's our Feed-in Priority → Self-Use transition point
        
        Returns:
            Dict with:
                - use_strategy: bool
                - start_time: datetime (when to start Feed-in Priority)
                - end_time: datetime (when to transition to Self-Use)
                - reason: str (explanation)
        """
        # Use the first slot's time as "now" for scenario planning
        # (handles both real-time and test scenarios with arbitrary dates)
        now = slots[0]['time'] if slots else datetime.now()
        morning_start = now.replace(hour=6, minute=0, second=0, microsecond=0)
        if now.hour >= 6:
            morning_start = now
        
        evening_end = now.replace(hour=18, minute=0, second=0, microsecond=0)
        
        total_solar_kwh = 0
        total_load_kwh = 0
        peak_solar_kw = 0
        
        for slot in slots:
            slot_time = slot['time']
            if morning_start <= slot_time <= evening_end:
                solar_kw = slot.get('solar_kw', 0)
                load_kw = slot.get('load_kw', 0)
                total_solar_kwh += solar_kw * 0.5
                total_load_kwh += load_kw * 0.5
                peak_solar_kw = max(peak_solar_kw, solar_kw)
        
        battery_headroom_kwh = ((95 - current_soc) / 100) * battery_capacity
        net_solar_surplus = total_solar_kwh - total_load_kwh
        
        # Quick bailout: If no clipping risk, no need for Feed-in Priority
        # Trigger if either:
        # 1. Net surplus exceeds battery space by 2kWh+ (will clip battery)
        # 2. Peak solar exceeds export limit (will clip export)
        will_overflow_battery = net_solar_surplus > battery_headroom_kwh + 2.0
        will_clip_export = peak_solar_kw > export_limit
        
        will_clip = will_overflow_battery or will_clip_export
        
        if not will_clip:
            return {
                'use_strategy': False,
                'start_time': None,
                'end_time': None,
                'reason': f"No clipping risk: {total_solar_kwh:.1f}kWh solar fits in {battery_headroom_kwh:.1f}kWh space"
            }
        
        # BACKWARDS SIMULATION: Find optimal transition point
        target_soc_midnight = 15.0  # Want battery at 15% by midnight
        simulated_soc = target_soc_midnight
        transition_slot_idx = None
        
        # Work backwards from end of day
        for i in range(len(slots) - 1, -1, -1):
            slot = slots[i]
            slot_time = slot['time']
            solar_kw = slot.get('solar_kw', 0)
            load_kw = slot.get('load_kw', 0)
            
            # Only simulate daytime hours (before 10pm)
            if slot_time.hour >= 22:
                # Evening/night: always Self-Use, battery supplies load
                net_kw = solar_kw - load_kw  # Usually negative at night
                kwh_change = net_kw * 0.5
                soc_change = (kwh_change / battery_capacity) * 100
                simulated_soc -= soc_change  # Going backwards!
                continue
            
            # Daytime: Check if Self-Use would cause overflow
            net_kw = solar_kw - load_kw
            
            if net_kw > 0:  # Net generation
                kwh_change = net_kw * 0.5
                soc_change = (kwh_change / battery_capacity) * 100
                potential_soc = simulated_soc + soc_change
                
                # Would battery overflow if we used Self-Use?
                if potential_soc > 95.0:
                    # Found it! This is where we need Feed-in Priority
                    transition_slot_idx = i
                    break
                else:
                    # Self-Use is safe, battery won't overflow
                    simulated_soc = potential_soc
            else:
                # Net consumption - battery drains (going backwards = charging)
                kwh_change = net_kw * 0.5
                soc_change = (kwh_change / battery_capacity) * 100
                simulated_soc -= soc_change
        
        if transition_slot_idx is not None:
            # Found transition point - use Feed-in Priority before this, Self-Use after
            transition_slot = slots[transition_slot_idx]
            
            # Find start of solar (first slot > 1kW)
            strategy_start = None
            for slot in slots:
                if slot.get('solar_kw', 0) > 1.0:
                    strategy_start = slot['time']
                    break
            
            # Transition time
            strategy_end = transition_slot['time']
            
            # Calculate what SOC we'd end up at midnight with this strategy
            final_soc_estimate = simulated_soc
            
            return {
                'use_strategy': True,
                'start_time': strategy_start or morning_start,
                'end_time': strategy_end,
                'reason': f"High solar day: {total_solar_kwh:.1f}kWh solar, {battery_headroom_kwh:.1f}kWh space, {net_solar_surplus:.1f}kWh surplus → Feed-in Priority until {strategy_end.strftime('%H:%M')}, then Self-Use (ends ~{final_soc_estimate:.0f}% SOC)"
            }
        else:
            # Entire day can be Self-Use without overflow
            return {
                'use_strategy': False,
                'start_time': None,
                'end_time': None,
                'reason': f"Battery can handle all solar with Self-Use (simulated EOD SOC: {simulated_soc:.0f}%)"
            }
    
    def _calculate_presunrise_discharge_strategy(self, slots: List[Dict], current_soc: float,
                                                  battery_capacity: float, max_discharge_rate: float,
                                                  feed_in_strategy: Dict) -> Dict:
        """
        Pre-sunrise discharge strategy: Create battery space BEFORE solar arrives.
        
        Used when even Feed-in Priority all day won't prevent clipping.
        Works backwards from sunrise to calculate how much to discharge.
        
        Logic:
        1. Calculate total solar surplus (after load and Feed-in Priority)
        2. Calculate current battery space
        3. If surplus > space, we need to discharge before sunrise
        4. Work backwards from sunrise to find discharge window
        
        Returns:
            Dict with:
                - use_strategy: bool
                - start_time: datetime (when to start discharging)
                - end_time: datetime (when to stop - at sunrise)
                - target_soc: float (what SOC to reach)
                - discharge_rate: float (kW to discharge at)
                - reason: str
        """
        now = slots[0]['time'] if slots else datetime.now()
        
        # Find sunrise (first slot with solar > 0.5kW)
        sunrise_time = None
        for slot in slots:
            if slot.get('solar_kw', 0) > 0.5:
                sunrise_time = slot['time']
                break
        
        if not sunrise_time or sunrise_time <= now:
            return {'use_strategy': False, 'reason': 'No sunrise time found or already past'}
        
        # Calculate total solar that will arrive during Feed-in Priority window
        # (or all day if no Feed-in Priority)
        total_solar_kwh = 0
        total_load_kwh = 0
        
        if feed_in_strategy['use_strategy']:
            # Only count solar during Feed-in Priority window
            for slot in slots:
                slot_time = slot['time']
                if (feed_in_strategy['start_time'] <= slot_time <= feed_in_strategy['end_time']):
                    total_solar_kwh += slot.get('solar_kw', 0) * 0.5
                    total_load_kwh += slot.get('load_kw', 0) * 0.5
        else:
            # Count all daytime solar (6am-6pm)
            morning = now.replace(hour=6, minute=0)
            evening = now.replace(hour=18, minute=0)
            for slot in slots:
                slot_time = slot['time']
                if morning <= slot_time <= evening:
                    total_solar_kwh += slot.get('solar_kw', 0) * 0.5
                    total_load_kwh += slot.get('load_kw', 0) * 0.5
        
        # Calculate net solar that needs battery space
        net_solar_kwh = total_solar_kwh - total_load_kwh
        
        # Calculate current battery space (current to 95%)
        current_space_kwh = ((95 - current_soc) / 100) * battery_capacity
        
        # Do we need to create more space?
        space_shortfall = net_solar_kwh - current_space_kwh
        
        if space_shortfall <= 1.0:  # 1kWh margin
            return {'use_strategy': False, 'reason': f'Sufficient space: {current_space_kwh:.1f}kWh available, {net_solar_kwh:.1f}kWh needed'}
        
        # Calculate target SOC
        # We need to discharge enough to fit the solar
        # But don't go below 15% (min_soc)
        target_space_kwh = min(net_solar_kwh + 2.0, battery_capacity * 0.80)  # Up to 80% space (down to 15% SOC)
        target_soc = max(15.0, 95 - (target_space_kwh / battery_capacity * 100))
        
        discharge_needed_kwh = ((current_soc - target_soc) / 100) * battery_capacity
        
        # Calculate discharge window
        # Work backwards from sunrise
        # Discharge at max rate to minimize time
        discharge_hours = discharge_needed_kwh / max_discharge_rate
        discharge_slots = int(discharge_hours * 2)  # 30-min slots
        
        # Find discharge start time (working backwards from sunrise)
        sunrise_slot_idx = None
        for i, slot in enumerate(slots):
            if slot['time'] >= sunrise_time:
                sunrise_slot_idx = i
                break
        
        if sunrise_slot_idx is None or sunrise_slot_idx < discharge_slots:
            return {'use_strategy': False, 'reason': 'Not enough time before sunrise'}
        
        discharge_start_idx = sunrise_slot_idx - discharge_slots
        discharge_start_time = slots[discharge_start_idx]['time']
        
        # Make sure discharge starts after current time
        if discharge_start_time <= now:
            discharge_start_time = now
        
        return {
            'use_strategy': True,
            'start_time': discharge_start_time,
            'end_time': sunrise_time,
            'target_soc': target_soc,
            'discharge_rate': max_discharge_rate,
            'reason': f"Pre-sunrise discharge: {space_shortfall:.1f}kWh space needed, discharging from {current_soc:.0f}% to {target_soc:.0f}% ({discharge_needed_kwh:.1f}kWh) before sunrise at {sunrise_time.strftime('%H:%M')}"
        }
    
    def _align_forecasts(self, prices, solar_forecast, load_forecast) -> List[Dict]:
        """Align all forecasts to common 30-min time slots"""
        slots = []
        
        for price in prices[:48]:  # 24 hours
            slot_time = price['start']
            
            # Find matching solar
            # Solar forecast 'period_end' is actually the slot time (despite the name)
            # Match within 5 minutes to handle slight timing differences
            solar_kw = 0.0
            for sf in solar_forecast:
                time_diff = abs((sf['period_end'] - slot_time).total_seconds())
                if time_diff < 300:  # Within 5 minutes
                    solar_kw = sf['pv_estimate']
                    break
            
            # Find matching load
            load_kw = 1.0  # Default 1kW if no forecast
            load_confidence = 'unknown'
            for lf in load_forecast:
                time_diff = abs((lf['time'] - slot_time).total_seconds())
                if time_diff < 300:  # Within 5 minutes
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
    
    def _decide_mode(self, slot, feed_in_priority_strategy, presunrise_discharge_strategy,
                     current_soc, solar_kwh, load_kwh, import_price, export_price,
                     future_deficit, future_solar_surplus, future_min_price,
                     battery_capacity, max_charge_rate, max_discharge_rate,
                     min_soc, max_soc) -> Tuple[str, str, float]:
        """
        Decide what to do this slot based on smart analysis.
        
        Args:
            slot: Current time slot dict
            feed_in_priority_strategy: Strategic decision dict from _should_use_feed_in_priority_strategy
            presunrise_discharge_strategy: Pre-sunrise discharge strategy dict
            ... (other parameters)
        
        Returns:
            (mode, action_description, soc_change)
        """
        
        # Check if we have a deficit coming and need to charge
        needs_charging = future_deficit > 0.5  # More than 0.5kWh deficit
        
        # Check if battery is nearly full and solar coming (wastage risk)
        wastage_risk = (current_soc > 80 and future_solar_surplus > 2.0)
        
        # Calculate energy balance for this slot
        net_energy = solar_kwh - load_kwh
        
        # Decision logic
        
        # 0a. PRE-SUNRISE DISCHARGE (Create battery space before solar arrives)
        # Check if this slot falls within the pre-sunrise discharge window
        if presunrise_discharge_strategy['use_strategy']:
            slot_time = slot['time']
            if (presunrise_discharge_strategy['start_time'] <= slot_time < 
                presunrise_discharge_strategy['end_time']):
                mode = 'Force Discharge'
                target_soc = presunrise_discharge_strategy['target_soc']
                discharge_rate = presunrise_discharge_strategy['discharge_rate']
                
                # Calculate discharge amount (limit to what's needed to reach target)
                soc_deficit = current_soc - target_soc
                max_discharge_kwh = (soc_deficit / 100) * battery_capacity
                discharge_kwh = min(discharge_rate * 0.5, max_discharge_kwh)
                soc_change = -(discharge_kwh / battery_capacity) * 100
                
                action = f"Pre-sunrise discharge to {target_soc:.0f}% (creating space for {presunrise_discharge_strategy['reason'].split('kWh')[0]}kWh solar)"
                return mode, action, soc_change
        
        # 0b. STRATEGIC FEED-IN PRIORITY MODE (Morning strategy for high solar days)
        # Check if this slot falls within the Feed-in Priority window
        if feed_in_priority_strategy['use_strategy']:
            slot_time = slot['time']
            if (feed_in_priority_strategy['start_time'] <= slot_time <= 
                feed_in_priority_strategy['end_time']):
                mode = 'Feed-in Priority'
                action = f"Grid-first solar routing ({feed_in_priority_strategy['reason'].split('→')[0]})"
                # Let solar go to grid first, battery fills from overflow only
                # Don't force any SOC change - let it happen naturally
                soc_change = 0
                return mode, action, soc_change
        
        # 1. ARBITRAGE OPPORTUNITY: If we can buy cheap and sell expensive later, do it!
        # With 90% round-trip efficiency:
        # - Buy 1kWh at Xp, store/retrieve at 90% = 0.9kWh
        # - Sell 0.9kWh at Yp = revenue
        # - Need Y > X + (X * 0.11) to profit (covers 10% loss + small margin)
        # Simplified: if export > import + 1p, it's profitable
        arbitrage_margin = 1.0  # Minimum 1p profit after round-trip losses
        profitable_arbitrage = (export_price > import_price + arbitrage_margin)
        
        if profitable_arbitrage and current_soc < 92:  # Allow up to 92% for arbitrage
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

