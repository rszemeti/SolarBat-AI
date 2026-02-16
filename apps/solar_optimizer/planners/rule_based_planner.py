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
        # STRATEGIC DECISIONS: Feed-in Priority + Pre-sunrise Discharge
        # These are interdependent:
        # - Feed-in Priority needs to know post-discharge SOC
        # - Pre-sunrise discharge needs to know if we're using Feed-in Priority
        # Solution: Run feed-in first (may be wrong), then pre-sunrise, then re-run feed-in
        # ============================================
        
        # First pass: check feed-in with current SOC
        feed_in_priority_strategy = self._should_use_feed_in_priority_strategy(
            slots, current_soc, battery_capacity, export_limit=5.0, max_charge_rate=max_charge_rate
        )
        
        # Calculate pre-sunrise discharge
        presunrise_discharge_strategy = self._calculate_presunrise_discharge_strategy(
            slots, current_soc, battery_capacity, max_discharge_rate, feed_in_priority_strategy
        )
        
        # If pre-sunrise discharge will happen, re-run feed-in with post-discharge SOC
        if presunrise_discharge_strategy['use_strategy']:
            post_discharge_soc = presunrise_discharge_strategy['target_soc']
            if post_discharge_soc != current_soc:
                feed_in_priority_strategy = self._should_use_feed_in_priority_strategy(
                    slots, post_discharge_soc, battery_capacity, export_limit=5.0, max_charge_rate=max_charge_rate
                )
        
        if feed_in_priority_strategy['use_strategy']:
            self.log(f"📊 STRATEGIC DECISION: Feed-in Priority mode {feed_in_priority_strategy['start_time'].strftime('%H:%M')}-{feed_in_priority_strategy['end_time'].strftime('%H:%M')}")
            self.log(f"   Reason: {feed_in_priority_strategy['reason']}")
        
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
                                               battery_capacity: float, export_limit: float = 5.0,
                                               max_charge_rate: float = None) -> Dict:
        """
        Strategic decision: Should we use Feed-in Priority to maximise energy harvest?
        
        INVERTER PHYSICS (Solis with solax_modbus):
        - DC clipping limit: ~13kW (inverter max)
        - Grid export limit: 5kW
        - Battery charge rate: ~8kW max
        
        THE PROBLEM:
        In Self-Use, battery charges first (up to 8kW), grid gets overflow (up to 5kW).
        Battery fills quickly. Once full: total harvest = 5kW + load. Rest is CLIPPED.
        
        In Feed-in Priority, grid gets first 5kW, battery gets (solar - 5kW - load).
        Battery fills slowly → stays not-full longer → more total energy harvested.
        
        STRATEGY:
        1. Forward sim in Self-Use: does battery ever hit 95%? If not, no clipping risk.
        2. If yes, use Feed-in Priority from first solar to delay battery filling.
        3. Find transition point (Feed-in → Self-Use) by working BACKWARDS from end
           of solar window: simulate Self-Use backwards, find where SOC would hit 95%.
           Everything before that = Feed-in Priority, everything after = Self-Use.
        4. This ensures battery fills to exactly 95% right at end of solar, not before.
        
        ADAPTIVE: When re-planning mid-day (e.g. cloudy morning, SOC still low),
        the backwards sim finds an earlier transition or no Feed-in at all.
        
        Returns:
            Dict with use_strategy, start_time, end_time, reason
        """
        if not slots:
            return {'use_strategy': False, 'start_time': None, 'end_time': None, 
                    'reason': 'No slots to analyze'}
        
        max_soc = 95.0
        max_charge_rate_kw = max_charge_rate if max_charge_rate else battery_capacity / 4
        
        # ── Step 1: Quick forward sim in Self-Use to check if clipping occurs ──
        sim_soc = current_soc
        clipped_kwh = 0
        su_full_at_idx = None
        
        for i, slot in enumerate(slots):
            solar_kw = slot.get('solar_kw', 0)
            load_kw = slot.get('load_kw', 0)
            
            net_solar = max(0, solar_kw - load_kw)
            
            # Battery charges from net solar (capped at charge rate and headroom)
            headroom_kwh = max(0, (max_soc - sim_soc) / 100 * battery_capacity)
            battery_charge_kwh = min(net_solar * 0.5, max_charge_rate_kw * 0.5, headroom_kwh)
            
            # Remaining goes to grid (capped at export limit)
            remaining_kw = net_solar - (battery_charge_kwh * 2)  # Back to kW
            grid_export_kw = min(remaining_kw, export_limit)
            clipped_kw = max(0, remaining_kw - export_limit)
            
            sim_soc = min(max_soc, sim_soc + (battery_charge_kwh / battery_capacity) * 100)
            clipped_kwh += clipped_kw * 0.5
            
            # Battery drains from load when solar < load
            if solar_kw < load_kw:
                drain_kwh = min((load_kw - solar_kw) * 0.5, (sim_soc - 10) / 100 * battery_capacity)
                sim_soc = max(10, sim_soc - (drain_kwh / battery_capacity) * 100)
            
            if sim_soc >= max_soc and su_full_at_idx is None and net_solar > 0.5:
                su_full_at_idx = i
        
        # No clipping in Self-Use? No need for Feed-in Priority
        if clipped_kwh < 1.0:
            return {
                'use_strategy': False,
                'start_time': None,
                'end_time': None,
                'reason': f"No clipping risk: only {clipped_kwh:.1f}kWh clipped in Self-Use"
            }
        
        # ── Step 2: Find Feed-in Priority window ──
        # Start: first slot with meaningful solar
        fi_start_idx = None
        for i, slot in enumerate(slots):
            if slot.get('solar_kw', 0) > 0.5:
                fi_start_idx = i
                break
        
        if fi_start_idx is None:
            return {'use_strategy': False, 'start_time': None, 'end_time': None,
                    'reason': 'No solar slots found'}
        
        # End of solar window: last slot with meaningful solar
        fi_solar_end_idx = fi_start_idx
        for i, slot in enumerate(slots):
            if slot.get('solar_kw', 0) > 0.5:
                fi_solar_end_idx = i
        
        # ── Step 3: Backwards simulation to find transition point ──
        # Start at end of solar window with target SOC = 95% (we want battery full by then)
        # Work backwards in Self-Use mode
        # When SOC exceeds 95% going backwards (meaning it would overflow), that's where
        # we need to stop Self-Use and switch to Feed-in Priority
        
        backward_soc = max_soc  # Battery should be full at end of solar
        transition_idx = fi_start_idx  # Default: Feed-in Priority the whole solar window
        
        for i in range(fi_solar_end_idx, fi_start_idx - 1, -1):
            slot = slots[i]
            solar_kw = slot.get('solar_kw', 0)
            load_kw = slot.get('load_kw', 0)
            
            net_solar = solar_kw - load_kw
            
            if net_solar > 0:
                # Going backwards: Self-Use would charge battery, so we subtract
                # (in forward time this slot would add to SOC)
                charge_kwh = min(net_solar * 0.5, max_charge_rate_kw * 0.5)
                soc_change = (charge_kwh / battery_capacity) * 100
                potential_soc = backward_soc - soc_change  # Remove this slot's contribution
                
                if potential_soc < current_soc:
                    # We've unwound back to current SOC - transition here
                    transition_idx = i
                    break
                    
                backward_soc = potential_soc
            else:
                # Net consumption: in forward time battery drains, going backwards we add
                drain_kwh = abs(net_solar) * 0.5
                soc_change = (drain_kwh / battery_capacity) * 100
                backward_soc = min(max_soc, backward_soc + soc_change)
            
            transition_idx = i
        
        # ── Step 4: Validate - simulate Feed-in Priority forward to check improvement ──
        fi_soc = current_soc
        fi_clipped = 0
        fi_full_at_idx = None
        
        for i in range(fi_start_idx, fi_solar_end_idx + 1):
            slot = slots[i]
            solar_kw = slot.get('solar_kw', 0)
            load_kw = slot.get('load_kw', 0)
            
            if i < transition_idx:
                # Feed-in Priority: grid gets first 5kW, remainder to load+battery
                grid_kw = min(solar_kw, export_limit)
                after_grid = solar_kw - grid_kw
                load_from_solar = min(after_grid, load_kw)
                after_load = after_grid - load_from_solar
                
                # Battery charges from remainder
                headroom = max(0, (max_soc - fi_soc) / 100 * battery_capacity)
                charge_kwh = min(after_load * 0.5, max_charge_rate_kw * 0.5, headroom)
                fi_soc = min(max_soc, fi_soc + (charge_kwh / battery_capacity) * 100)
                fi_clipped += max(0, after_load * 0.5 - charge_kwh)
                
                # Load not covered by solar drains battery
                if load_from_solar < load_kw:
                    drain = min((load_kw - load_from_solar) * 0.5, (fi_soc - 10) / 100 * battery_capacity)
                    fi_soc = max(10, fi_soc - (drain / battery_capacity) * 100)
            else:
                # Self-Use: battery charges first
                net_solar = max(0, solar_kw - load_kw)
                headroom = max(0, (max_soc - fi_soc) / 100 * battery_capacity)
                charge_kwh = min(net_solar * 0.5, max_charge_rate_kw * 0.5, headroom)
                remaining = net_solar - charge_kwh * 2
                grid_kw = min(remaining, export_limit)
                fi_clipped += max(0, remaining - export_limit) * 0.5
                fi_soc = min(max_soc, fi_soc + (charge_kwh / battery_capacity) * 100)
                
                if solar_kw < load_kw:
                    drain = min((load_kw - solar_kw) * 0.5, (fi_soc - 10) / 100 * battery_capacity)
                    fi_soc = max(10, fi_soc - (drain / battery_capacity) * 100)
            
            if fi_soc >= max_soc and fi_full_at_idx is None:
                fi_full_at_idx = i
        
        clip_saved = clipped_kwh - fi_clipped
        
        if clip_saved < 2.0:  # Need at least 2kWh savings to justify Feed-in Priority mode
            return {
                'use_strategy': False,
                'start_time': None,
                'end_time': None,
                'reason': f"Feed-in Priority only saves {clip_saved:.1f}kWh - not worth it"
            }
        
        start_time = slots[fi_start_idx]['time']
        transition_time = slots[transition_idx]['time']
        su_full_time = slots[su_full_at_idx]['time'].strftime('%H:%M') if su_full_at_idx is not None else 'never'
        fi_full_time = slots[fi_full_at_idx]['time'].strftime('%H:%M') if fi_full_at_idx is not None else 'never'
        
        return {
            'use_strategy': True,
            'start_time': start_time,
            'end_time': transition_time,
            'reason': (f"Saves {clip_saved:.1f}kWh: "
                      f"battery full at {su_full_time} (Self-Use) vs {fi_full_time} (Feed-in) → "
                      f"Feed-in {start_time.strftime('%H:%M')}-{transition_time.strftime('%H:%M')}, "
                      f"then Self-Use")
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
        
        # Calculate how much the battery will actually absorb
        # In Feed-in Priority: grid gets first 5kW, load from remainder, battery gets overflow
        # In Self-Use: battery gets first, grid gets overflow
        # We need space for what the battery will actually receive, not total solar
        export_limit = 5.0
        battery_absorption_kwh = 0
        
        for slot in slots:
            solar_kw = slot.get('solar_kw', 0)
            load_kw = slot.get('load_kw', 0)
            
            if solar_kw < 0.5:
                continue
            
            if feed_in_strategy['use_strategy']:
                slot_time = slot['time']
                if feed_in_strategy['start_time'] <= slot_time <= feed_in_strategy['end_time']:
                    # Feed-in Priority: grid gets 5kW first, then load, battery gets rest
                    after_grid = max(0, solar_kw - export_limit)
                    after_load = max(0, after_grid - load_kw)
                    battery_absorption_kwh += after_load * 0.5
                else:
                    # Self-Use slots: battery gets solar - load
                    net = max(0, solar_kw - load_kw)
                    battery_absorption_kwh += net * 0.5
            else:
                # All Self-Use: battery gets solar - load
                net = max(0, solar_kw - load_kw)
                battery_absorption_kwh += net * 0.5
        
        # Calculate current battery space (current to 95%)
        current_space_kwh = ((95 - current_soc) / 100) * battery_capacity
        
        # Do we need to create more space?
        space_shortfall = battery_absorption_kwh - current_space_kwh
        
        if space_shortfall <= 1.0:  # 1kWh margin
            return {'use_strategy': False, 'reason': f'Sufficient space: {current_space_kwh:.1f}kWh available for {battery_absorption_kwh:.1f}kWh absorption'}
        
        # Calculate target SOC - only discharge what we need + small buffer
        # We already have current_space_kwh, we only need space_shortfall more
        needed_discharge_kwh = space_shortfall + 2.0  # 2kWh buffer
        # Don't discharge below 15% SOC
        max_discharge_kwh = ((current_soc - 15.0) / 100) * battery_capacity
        actual_discharge_kwh = min(needed_discharge_kwh, max_discharge_kwh)
        target_soc = max(15.0, current_soc - (actual_discharge_kwh / battery_capacity * 100))
        
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
        
        # 0b. STRATEGIC FEED-IN PRIORITY MODE (maximise harvest on big solar days)
        # Grid gets first 5kW, load from remainder, battery gets overflow
        # CRITICAL: Only use when there's actual solar to route - pointless with 0kW solar
        if feed_in_priority_strategy['use_strategy']:
            slot_time = slot['time']
            solar_kw = solar_kwh * 2  # Convert back to kW
            if (feed_in_priority_strategy['start_time'] <= slot_time <= 
                feed_in_priority_strategy['end_time'] and solar_kw > 0.5):
                mode = 'Feed-in Priority'
                reason = feed_in_priority_strategy['reason']
                short_reason = reason.split('→')[0] if '→' in reason else reason[:80]
                action = f"Grid-first solar routing ({short_reason})"
                
                # SOC simulation: grid gets first export_limit, then load, battery gets rest
                grid_kw = min(solar_kw, 5.0)
                after_grid_kw = max(0, solar_kw - grid_kw)
                load_from_solar_kw = min(after_grid_kw, load_kwh * 2)
                battery_charge_kw = max(0, after_grid_kw - load_from_solar_kw)
                
                # Battery charges from overflow
                charge_kwh = min(battery_charge_kw * 0.5, 
                               (max_soc - current_soc) / 100 * battery_capacity)
                soc_change = (charge_kwh / battery_capacity) * 100
                
                # Load not covered by solar drains battery
                if load_from_solar_kw < load_kwh * 2:
                    drain_kw = load_kwh * 2 - load_from_solar_kw
                    drain_kwh = min(drain_kw * 0.5, (current_soc - min_soc) / 100 * battery_capacity)
                    soc_change -= (drain_kwh / battery_capacity) * 100
                
                return mode, action, soc_change
        
        # 1. ARBITRAGE OPPORTUNITY: If we can buy cheap and sell expensive later, do it!
        # Round-trip efficiency is roughly 85-90%:
        # - Charge efficiency: ~95% (AC → DC → battery)
        # - Discharge efficiency: ~95% (battery → DC → AC)
        # - Combined: ~90%, but real-world with inverter standby, BMS etc. closer to 85%
        # 
        # Example: Buy 1kWh at 15p, retrieve 0.85kWh, sell at 15p = 12.75p revenue
        # Loss: 2.25p per kWh stored. Need export > import / 0.85 to break even.
        # Simplified: export must be at least 20% higher than import to profit.
        round_trip_efficiency = 0.85
        min_profit_margin = 2.0  # Minimum 2p/kWh clear profit after losses
        break_even_export = import_price / round_trip_efficiency
        profitable_arbitrage = (export_price > break_even_export + min_profit_margin)
        
        if profitable_arbitrage and current_soc < 92:  # Allow up to 92% for arbitrage
            mode = 'Force Charge'
            net_profit = (export_price * round_trip_efficiency) - import_price
            action = f"Arbitrage: buy {import_price:.1f}p, sell {export_price:.1f}p × {round_trip_efficiency:.0%} eff = {net_profit:.1f}p/kWh profit"
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
        
        # 4. PROFITABLE EXPORT: Discharge battery to grid if export price is high enough
        # Only worth it if export revenue > cost of recharging later (accounting for losses)
        # We'll need to buy back at ~import_price, losing ~15% round-trip
        # So: export_price * efficiency must exceed what we'd pay to refill
        discharge_profit = export_price * round_trip_efficiency - import_price
        if discharge_profit > min_profit_margin and current_soc > 40:
            mode = 'Force Discharge'
            action = f"Profitable export: {export_price:.1f}p × {round_trip_efficiency:.0%} - {import_price:.1f}p refill = {discharge_profit:.1f}p/kWh profit"
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

