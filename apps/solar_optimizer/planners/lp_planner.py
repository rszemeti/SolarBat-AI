"""
Linear Programming Planner

Uses linear programming to find mathematically optimal battery strategy.

Advantages:
- Guaranteed optimal solution (given perfect information)
- Fast (<1ms per scenario)
- Explainable decisions
- No training needed

Limitations:
- Assumes perfect future knowledge
- Can't learn from experience
- Linear cost model only

Inherits from BasePlanner to ensure consistent interface.

Requires: pip install pulp
"""

from datetime import datetime, timedelta
from typing import Dict, List
import sys
from pathlib import Path

# Import base planner
from .base_planner import BasePlanner

try:
    from pulp import *
except ImportError:
    raise ImportError("PuLP not installed. Install with: pip install pulp")


class LinearProgrammingPlanner(BasePlanner):
    """
    Optimal battery planner using linear programming.
    
    Formulation:
        Minimize: total_cost = sum(import_cost - export_revenue)
        
        Subject to:
            1. Battery constraints: min_soc ≤ SOC(t) ≤ max_soc
            2. Power limits: |charge_rate| ≤ max_charge, |discharge_rate| ≤ max_discharge
            3. Energy balance: SOC(t+1) = SOC(t) + (charge - discharge + solar - load)
            4. Mode exclusivity: Only one mode active per slot
    """
    
    def __init__(self, charge_efficiency=None, discharge_efficiency=None, min_profit_margin=None):
        super().__init__(charge_efficiency, discharge_efficiency, min_profit_margin)
        self.solver = PULP_CBC_CMD(msg=0)  # Silent solver
    
    def log(self, message: str):
        """Log a message"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"[{timestamp}] [LP] {message}")
    
    def create_plan(self,
                   import_prices: List[Dict],
                   export_prices: List[Dict],
                   solar_forecast: List[Dict],
                   load_forecast: List[Dict],
                   system_state: Dict) -> Dict:
        """
        Create optimal plan using linear programming.
        
        Returns same format as PlanCreator for compatibility.
        """
        self.log("Creating optimal plan using Linear Programming...")
        
        # Extract system state
        current_state = system_state.get('current_state', {})
        capabilities = system_state.get('capabilities', {})
        
        battery_soc = current_state.get('battery_soc', 50.0)
        battery_capacity = capabilities.get('battery_capacity', 10.0)
        max_charge_rate = capabilities.get('max_charge_rate', 3.0)
        max_discharge_rate = capabilities.get('max_discharge_rate', 3.0)
        
        min_soc = 10.0
        max_soc = 95.0
        
        # Number of time slots
        n_slots = len(import_prices)
        
        # Handle case where initial SOC might exceed max_soc (e.g. 97% when max is 95%)
        effective_max_soc = max(max_soc, battery_soc)  # Allow starting above max
        
        self.log(f"Optimizing {n_slots} slots with LP solver...")
        self.log(f"Battery: {battery_capacity}kWh, SOC: {battery_soc}%, Charge: {max_charge_rate}kW, Discharge: {max_discharge_rate}kW")
        
        # Create LP problem
        prob = LpProblem("Battery_Optimization", LpMinimize)
        
        # Decision variables for each slot
        # SOC at start of each slot (%)
        # First slot can be above max_soc if battery is already charged beyond that
        soc = [LpVariable(f"soc_0", min_soc, effective_max_soc)] + \
              [LpVariable(f"soc_{t}", min_soc, max_soc) for t in range(1, n_slots + 1)]
        
        # Grid import/export (kW)
        grid_import = [LpVariable(f"import_{t}", 0, 10) for t in range(n_slots)]  # Max 10kW import
        grid_export = [LpVariable(f"export_{t}", 0, 20) for t in range(n_slots)]  # Max 20kW export (will be constrained by mode)
        
        # Battery charge/discharge (kW)
        battery_charge = [LpVariable(f"charge_{t}", 0, max_charge_rate) for t in range(n_slots)]
        battery_discharge = [LpVariable(f"discharge_{t}", 0, max_discharge_rate) for t in range(n_slots)]
        
        # Binary variable: 1 if charging, 0 if discharging (prevents simultaneous)
        is_charging = [LpVariable(f"is_charging_{t}", cat='Binary') for t in range(n_slots)]
        
        # NEW: Binary variable for Grid-First mode
        # 1 = Grid-First (Feed-in Priority): Solar goes to grid first, no 5kW export limit
        # 0 = Self-Use: Solar goes to load/battery first, 5kW export limit applies
        use_grid_first = [LpVariable(f"grid_first_{t}", cat='Binary') for t in range(n_slots)]
        
        # Clipping (wasted solar) - we want to minimize this!
        clipped_solar = [LpVariable(f"clipped_{t}", 0, 20) for t in range(n_slots)]  # Max 20kW clipping
        
        # Get export price for battery valuation
        export_price_pkwh = export_prices[0]['price'] if export_prices else 15.0
        
        # Objective: Minimize actual out-of-pocket costs + encourage high final SOC
        # - Import costs (what we pay to grid)
        # - Export revenue (what grid pays us)
        # - Clipping penalty (wasted solar)
        # - Terminal SOC penalty (encourages ending with charged battery)
        
        clipping_penalty = 50.0  # Pence per kWh clipped
        
        # Terminal SOC target: Penalize ending below 80% SOC
        # This encourages: maximize solar charging, minimize unnecessary discharge
        # Value: If you end below 80%, you'll likely need to import later at avg price
        avg_import_price = sum(p['price'] for p in import_prices) / len(import_prices)
        target_soc = 80.0
        
        # Penalty increases linearly with SOC shortfall
        # e.g., ending at 50% with 10kWh battery: (80-50)/100 * 10 * 20p / 100 = £0.60 penalty
        soc_shortfall = (target_soc - soc[n_slots]) / 100 * battery_capacity * avg_import_price / 100
        
        total_cost = lpSum([
            import_prices[t]['price'] * grid_import[t] * 0.5 / 100  # Import cost (£)
            - export_prices[t]['price'] * grid_export[t] * 0.5 / 100  # Export revenue (£)
            + clipping_penalty * clipped_solar[t] * 0.5 / 100  # Clipping penalty (£)
            for t in range(n_slots)
        ]) + soc_shortfall  # Penalty for ending below target SOC
        
        prob += total_cost, "Total_Cost"
        
        # Constraints
        
        # 0. Terminal SOC target - don't end with empty battery!
        # Require ending at least 40% SOC (keeps battery ready for next day)
        min_final_soc = 40.0
        prob += soc[n_slots] >= min_final_soc, "Minimum_Final_SOC"
        
        # Constraints
        
        # 1. Initial SOC
        prob += soc[0] == battery_soc, "Initial_SOC"
        
        # 2. Energy balance for each slot
        # Round-trip efficiency from base class settings
        charge_efficiency = self.charge_efficiency
        discharge_efficiency = self.discharge_efficiency
        
        for t in range(n_slots):
            solar_kw = solar_forecast[t]['kw']
            load_kw = load_forecast[t]['load_kw']
            
            # Battery energy change (30 min = 0.5h)
            # Charging: only charge_efficiency of input reaches battery
            # Discharging: only discharge_efficiency of stored energy reaches output
            battery_kwh_in = battery_charge[t] * charge_efficiency * 0.5
            battery_kwh_out = battery_discharge[t] * 0.5  # Full kW drawn from battery
            
            # SOC change (as percentage) - what actually enters/leaves the battery
            soc_change = ((battery_kwh_in - battery_kwh_out) / battery_capacity) * 100
            
            prob += soc[t+1] == soc[t] + soc_change, f"SOC_Balance_{t}"
            
            # CORRECT Energy balance (AC side):
            # Energy IN: solar + grid_import + battery_discharge * discharge_efficiency
            # Energy OUT: load + battery_charge + grid_export + clipping
            # 
            # Discharge efficiency: only 95% of battery output reaches AC bus
            # Charge: full kW drawn from AC side (losses are on battery side, handled in SOC)
            prob += (grid_import[t] + battery_discharge[t] * discharge_efficiency 
                    - battery_charge[t] - grid_export[t] == 
                    load_kw + clipped_solar[t] - solar_kw), f"Grid_Balance_{t}"
        
        # 3. Can't charge and discharge simultaneously
        # Use binary variable: if is_charging=1, can charge but not discharge
        #                      if is_charging=0, can discharge but not charge
        M = 10  # Big number (max possible power)
        for t in range(n_slots):
            # If is_charging=1: charge can be up to max_charge_rate, discharge must be 0
            # If is_charging=0: discharge can be up to max_discharge_rate, charge must be 0
            prob += battery_charge[t] <= M * is_charging[t], f"Charge_If_Charging_{t}"
            prob += battery_discharge[t] <= M * (1 - is_charging[t]), f"Discharge_If_Not_Charging_{t}"
        
        # 4. NEW: Export limit depends on mode (Self-Use vs Grid-First)
        # If use_grid_first=0 (Self-Use): export limited to 5kW (DNO limit)
        # If use_grid_first=1 (Grid-First): export limited to 20kW (no practical limit)
        # Constraint: grid_export[t] <= 5 + 15 * use_grid_first[t]
        for t in range(n_slots):
            prob += grid_export[t] <= 5.0 + 15.0 * use_grid_first[t], f"Export_Limit_{t}"
        
        # 5. Only use Grid-First when there's actual solar to export
        # Add soft constraint: Grid-First should only be 1 when solar > 3kW
        # This prevents wasteful Grid-First mode during night/low-solar periods
        for t in range(n_slots):
            solar_kw = solar_forecast[t]['kw']
            if solar_kw < 3.0:  # Low/no solar
                # Strongly discourage Grid-First mode (but allow if really needed)
                prob += use_grid_first[t] <= 0.1, f"Discourage_GridFirst_NoSolar_{t}"
        
        # 6. Clipping only happens when solar exceeds what can be used
        # In Grid-First mode, clipping should be minimal since export limit is higher
        # The objective function already penalizes clipping heavily
        
        # 7. Discourage simultaneous charge/discharge (soft constraint via objective)
        # Already handled by making both expensive in the objective
        
        # Solve
        prob.solve(self.solver)
        
        # Check if optimal solution found
        status = LpStatus[prob.status]
        if status != 'Optimal':
            self.log(f"ERROR: Solver status: {status}")
            self.log(f"Falling back to simple Self-Use plan")
            
            # Return a simple self-use plan instead of empty
            fallback_slots = []
            current_soc = battery_soc
            
            for t in range(n_slots):
                time = import_prices[t]['time']
                
                fallback_slots.append({
                    'time': time,
                    'mode': 'Self Use',
                    'action': f"LP solver failed ({status}), using Self-Use fallback",
                    'soc_end': current_soc,
                    'solar_kw': solar_forecast[t]['kw'] if t < len(solar_forecast) else 0,
                    'load_kw': load_forecast[t]['load_kw'] if t < len(load_forecast) else 1.0,
                    'import_price': import_prices[t]['price'],
                    'export_price': export_prices[t]['price'] if export_prices else 15.0,
                    'soc_change': 0.0,
                    'cumulative_cost': 0.0
                })
            
            error_plan = {
                'timestamp': datetime.now(),
                'slots': fallback_slots,
                'metadata': {
                    'total_cost': 0.0,
                    'solver_status': status,
                    'error': f'LP solver failed with status: {status}, using Self-Use fallback',
                    'confidence': 'low',
                    'charge_slots': 0,
                    'discharge_slots': 0,
                    'planner_type': 'lp_fallback'
                }
            }
            return error_plan
        
        # Extract solution (all values should be valid now)
        plan_slots = []
        
        for t in range(n_slots):
            time = import_prices[t]['time']
            
            soc_start = soc[t].varValue
            soc_end = soc[t+1].varValue
            
            charge_kw = battery_charge[t].varValue
            discharge_kw = battery_discharge[t].varValue
            import_kw = grid_import[t].varValue
            export_kw = grid_export[t].varValue
            clipped_kw = clipped_solar[t].varValue
            is_grid_first = use_grid_first[t].varValue  # NEW: Read the mode decision
            
            # Determine mode from LP solution
            solar_kw = solar_forecast[t]['kw']
            
            # Check Grid-First mode (LP's decision)
            if is_grid_first > 0.5:  # Binary variable is 1
                mode = 'Feed-in Priority'
                action = f"Grid-first routing (export {export_kw:.2f}kW)"
            elif charge_kw > 0.1:
                # Charging battery
                if import_kw > 0.1:
                    mode = 'Force Charge'
                    action = f"Charging at {charge_kw:.2f}kW from grid (import {import_prices[t]['price']:.2f}p)"
                else:
                    mode = 'Self Use'
                    action = f"Charging at {charge_kw:.2f}kW from solar"
            elif discharge_kw > 0.1:
                # Discharging battery
                if export_kw > 0.1:
                    mode = 'Force Discharge'
                    action = f"Discharging at {discharge_kw:.2f}kW (exporting {export_kw:.2f}kW at {export_prices[t]['price']:.2f}p)"
                else:
                    mode = 'Self Use'
                    action = f"Discharging at {discharge_kw:.2f}kW to meet load"
            elif import_kw > 0.1:
                # Importing but not charging battery (direct to load)
                mode = 'Self Use'
                action = f"Importing {import_kw:.2f}kW to meet load"
            elif export_kw > 0.1:
                # Exporting surplus solar
                mode = 'Self Use'
                action = f"Exporting {export_kw:.2f}kW surplus solar"
            else:
                # Solar covering load exactly, or very low activity
                mode = 'Self Use'
                action = f"Self-sufficient (solar ≈ load)"
            
            # Calculate cost for this slot (matching LP objective exactly)
            import_cost = import_prices[t]['price'] * import_kw * 0.5 / 100  # £
            export_revenue = export_prices[t]['price'] * export_kw * 0.5 / 100  # £
            clipping_cost = (clipping_penalty * clipped_kw * 0.5 / 100) if clipped_kw > 0 else 0  # £
            
            # Total slot cost (matching LP objective)
            slot_cost = import_cost - export_revenue + clipping_cost
            
            # Cumulative cost in pence (slot costs are already in £, so convert)
            cumulative_cost_pence = sum(plan_slots[i]['cost'] for i in range(len(plan_slots))) + (slot_cost * 100) if plan_slots else (slot_cost * 100)
            
            plan_slots.append({
                'time': time,
                'mode': mode,
                'action': action,
                'soc_start': soc_start,
                'soc_end': soc_end,
                'solar_kw': solar_forecast[t]['kw'],
                'load_kw': load_forecast[t]['load_kw'],
                'import_price': import_prices[t]['price'],
                'export_price': export_prices[t]['price'],
                'import_kw': import_kw,  # NEW: Actual grid import
                'export_kw': export_kw,  # NEW: Actual grid export
                'charge_kw': charge_kw,  # NEW: Actual battery charge
                'discharge_kw': discharge_kw,  # NEW: Actual battery discharge
                'cost': slot_cost * 100,  # Convert to pence
                'cumulative_cost': cumulative_cost_pence  # Already in pence
            })
        
        # Use LP objective value as the true cost (already accounts for everything)
        total_cost = value(prob.objective)
        
        # Calculate total clipping
        total_clipping_kwh = sum(clipped_solar[t].varValue * 0.5 for t in range(n_slots))
        
        # Count modes
        mode_counts = {}
        for slot in plan_slots:
            mode_counts[slot['mode']] = mode_counts.get(slot['mode'], 0) + 1
        
        plan = {
            'timestamp': datetime.now(),
            'slots': plan_slots,
            'metadata': {
                'total_cost': total_cost,
                'total_clipping_kwh': round(total_clipping_kwh, 2),
                'solver_status': LpStatus[prob.status],
                'objective_value': value(prob.objective),
                'confidence': 'optimal' if LpStatus[prob.status] == 'Optimal' else 'suboptimal',
                'data_sources': {
                    'import_prices': len(import_prices),
                    'export_prices': len(export_prices),
                    'solar_forecast': len(solar_forecast),
                    'load_forecast': len(load_forecast)
                },
                'charge_slots': mode_counts.get('Force Charge', 0),
                'discharge_slots': mode_counts.get('Force Discharge', 0),
                'feed_in_slots': mode_counts.get('Feed-in Priority', 0)
            }
        }
        
        self.log(f"LP solution: {mode_counts.get('Force Charge', 0)} charge, "
                f"{mode_counts.get('Force Discharge', 0)} discharge, "
                f"{mode_counts.get('Feed-in Priority', 0)} feed-in, "
                f"clipping: {total_clipping_kwh:.2f}kWh, "
                f"cost: £{total_cost:.2f}")
        
        return plan


# Standalone test
if __name__ == '__main__':
    print("\n" + "="*70)
    print("  Linear Programming Planner Test")
    print("="*70)
    
    # Simple test scenario
    start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Mock data
    import_prices = [
        {'time': start_time + timedelta(minutes=30*t), 'price': 15.0} 
        for t in range(48)
    ]
    
    export_prices = [
        {'time': start_time + timedelta(minutes=30*t), 'price': 15.0}
        for t in range(48)
    ]
    
    solar_forecast = [
        {'time': start_time + timedelta(minutes=30*t), 'kw': 5.0 if 6 <= (t//2) <= 18 else 0.0}
        for t in range(48)
    ]
    
    load_forecast = [
        {'time': start_time + timedelta(minutes=30*t), 'load_kw': 1.0, 'confidence': 'high'}
        for t in range(48)
    ]
    
    system_state = {
        'current_state': {'battery_soc': 50.0},
        'capabilities': {
            'battery_capacity': 10.0,
            'max_charge_rate': 3.0,
            'max_discharge_rate': 3.0
        }
    }
    
    # Create planner and run
    planner = LinearProgrammingPlanner()
    plan = planner.create_plan(import_prices, export_prices, solar_forecast, load_forecast, system_state)
    
    print(f"\n✅ LP Planner test complete!")
    print(f"   Total cost: £{plan['metadata']['total_cost']:.2f}")
    print(f"   Solver status: {plan['metadata']['solver_status']}")
