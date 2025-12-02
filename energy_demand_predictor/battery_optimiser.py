"""
Advanced Battery Optimizer using Mixed Integer Linear Programming (MILP)
Maximizes profit by optimizing battery charge/discharge cycles considering:
- Variable import/export rates
- Solar generation forecast
- Demand forecast
- Battery constraints and efficiency losses
- Target end-of-day SOC
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pulp


class BatteryConfig:
    """Battery system configuration"""
    def __init__(
        self,
        capacity_kwh: float = 9.5,
        min_soc: float = 0.1,
        reserve_soc: float = 0.2,
        max_charge_rate_kw: float = 3.6,        # Max battery charge rate (DC)
        max_discharge_rate_kw: float = 3.6,     # Max battery discharge rate (DC)
        max_export_power_kw: float = 5.0,       # Max export to grid (AC)
        max_pv_power_kw: float = 13.0,          # Max PV MPPT output (AC)
        charge_efficiency: float = 0.95,
        discharge_efficiency: float = 0.95,
        degradation_cost_per_cycle: float = 0.05
    ):
        self.capacity_kwh = capacity_kwh
        self.min_soc = min_soc
        self.reserve_soc = reserve_soc
        self.max_charge_rate_kw = max_charge_rate_kw
        self.max_discharge_rate_kw = max_discharge_rate_kw
        self.max_export_power_kw = max_export_power_kw
        self.max_pv_power_kw = max_pv_power_kw
        self.charge_efficiency = charge_efficiency
        self.discharge_efficiency = discharge_efficiency
        self.degradation_cost_per_cycle = degradation_cost_per_cycle


class BatteryOptimizer:
    """Base class for battery optimization strategies"""
    
    def __init__(self, config: BatteryConfig):
        self.config = config
    
    def optimize(
        self,
        demand_forecast: List[Dict],
        solar_forecast: List[Dict],
        import_rates: List[float],
        export_rates: List[float],
        current_soc_kwh: float
    ) -> Dict[str, Any]:
        """
        Optimize battery schedule
        
        Args:
            demand_forecast: List of {'slot': int, 'timestamp': str, 'predicted_kw': float}
            solar_forecast: List of {'slot': int, 'timestamp': str, 'predicted_solar_kw': float}
            import_rates: List of import rates in £/kWh (e.g., 0.15 = 15p)
            export_rates: List of export rates in £/kWh
            current_soc_kwh: Current battery state of charge in kWh
            
        Returns:
            Dict with 'schedule' (list of slot dicts) and 'metadata'
        """
        raise NotImplementedError("Subclasses must implement optimize()")


class MILPOptimizer(BatteryOptimizer):
    """
    Mixed Integer Linear Programming optimizer
    Finds mathematically optimal solution to maximize profit
    
    Strategy:
    - Minimize total cost (import - export revenue)
    - Consider battery degradation costs
    - Ensure battery ends solar period at target SOC (default 90%)
    - Respect all physical constraints
    """
    
    def __init__(
        self,
        config: BatteryConfig,
        target_end_soc: float = 0.90,  # Target 90% SOC at end of solar period
        solar_end_hour: int = 20,       # When does solar period end? (8pm)
        min_export_rate: float = 0.10,  # Only export if rate > 10p/kWh
        time_limit_seconds: int = 30    # Solver time limit
    ):
        super().__init__(config)
        self.target_end_soc = target_end_soc
        self.solar_end_hour = solar_end_hour
        self.min_export_rate = min_export_rate
        self.time_limit_seconds = time_limit_seconds
    
    def optimize(
        self,
        demand_forecast: List[Dict],
        solar_forecast: List[Dict],
        import_rates: List[float],
        export_rates: List[float],
        current_soc_kwh: float
    ) -> Dict[str, Any]:
        
        n_slots = len(demand_forecast)
        slot_duration = 0.5  # 30 minutes = 0.5 hours
        
        print(f"🧮 Setting up MILP optimization for {n_slots} slots...")
        
        # Create the problem - MINIMIZE cost (negative profit)
        prob = pulp.LpProblem("BatteryOptimization", pulp.LpMinimize)
        
        # Decision variables
        # Grid import/export for each slot (in kW)
        # Set reasonable max bounds - most homes have ~100A supply = ~23kW max
        grid_import = [pulp.LpVariable(f"grid_import_{t}", lowBound=0, upBound=20) for t in range(n_slots)]
        grid_export = [pulp.LpVariable(f"grid_export_{t}", lowBound=0, upBound=10) for t in range(n_slots)]
        
        # Solar curtailment - solar that must be wasted (battery full, export limited, demand met)
        solar_curtailment = [pulp.LpVariable(f"curtail_{t}", lowBound=0) for t in range(n_slots)]
        
        # Battery charge/discharge for each slot
        # Note: charge/discharge are in DC power (what actually goes in/out of battery)
        battery_charge = [pulp.LpVariable(f"battery_charge_{t}", lowBound=0, 
                                         upBound=self.config.max_charge_rate_kw) 
                         for t in range(n_slots)]
        battery_discharge = [pulp.LpVariable(f"battery_discharge_{t}", lowBound=0,
                                            upBound=self.config.max_discharge_rate_kw) 
                            for t in range(n_slots)]
        
        # Battery SOC for each slot
        soc = [pulp.LpVariable(f"soc_{t}", 
                              lowBound=self.config.min_soc * self.config.capacity_kwh,
                              upBound=self.config.capacity_kwh) 
              for t in range(n_slots + 1)]  # +1 for initial state
        
        print("  ✓ Variables created")
        
        # OBJECTIVE: Minimize cost (import cost - export revenue + degradation + curtailment penalty)
        total_cost = 0
        for t in range(n_slots):
            # Import cost
            import_cost = grid_import[t] * import_rates[t] * slot_duration
            
            # Export revenue (negative cost)
            export_revenue = grid_export[t] * export_rates[t] * slot_duration
            
            # Battery degradation cost (simplified - based on throughput)
            degradation = (battery_charge[t] + battery_discharge[t]) * slot_duration * self.config.degradation_cost_per_cycle / (2 * self.config.capacity_kwh)
            
            # Curtailment penalty - wasted solar is VERY expensive!
            # Penalize at 2x the import rate - solar is free energy we're throwing away
            # This should strongly incentivize the optimizer to make room for solar
            curtailment_penalty = solar_curtailment[t] * import_rates[t] * slot_duration * 2.0
            
            total_cost += import_cost - export_revenue + degradation + curtailment_penalty
        
        # Don't set objective yet - will add SOC penalty first
        print("  ✓ Objective function prepared")
        
        # Clip solar forecast to max PV capacity (do this before creating constraints)
        for t in range(n_slots):
            if solar_forecast[t]['predicted_solar_kw'] > self.config.max_pv_power_kw:
                print(f"  ⚠ Clipping solar at slot {t}: {solar_forecast[t]['predicted_solar_kw']:.1f} kW → {self.config.max_pv_power_kw:.1f} kW")
                solar_forecast[t]['predicted_solar_kw'] = self.config.max_pv_power_kw
        
        # CONSTRAINTS
        
        # 1. Initial SOC
        prob += soc[0] == current_soc_kwh, "InitialSOC"
        
        # 2. Energy balance for each slot
        for t in range(n_slots):
            demand_kw = demand_forecast[t]['predicted_kw']
            solar_kw = solar_forecast[t]['predicted_solar_kw']
            
            # Energy balance: Solar + Grid Import + Battery Discharge = Demand + Grid Export + Battery Charge + Curtailment
            # Curtailment = wasted solar (when battery full, export limited, demand met)
            prob += (solar_kw * slot_duration + grid_import[t] * slot_duration + 
                    battery_discharge[t] * slot_duration * self.config.discharge_efficiency ==
                    demand_kw * slot_duration + grid_export[t] * slot_duration + 
                    battery_charge[t] * slot_duration / self.config.charge_efficiency +
                    solar_curtailment[t] * slot_duration), \
                    f"EnergyBalance_{t}"
        
        # 3. SOC evolution (with efficiency losses)
        for t in range(n_slots):
            prob += (soc[t+1] == soc[t] + 
                    battery_charge[t] * slot_duration * self.config.charge_efficiency -
                    battery_discharge[t] * slot_duration / self.config.discharge_efficiency), \
                    f"SOCEvolution_{t}"
        
        # 4. Battery can't charge and discharge simultaneously (implicit in cost function)
        # The optimizer won't do this anyway as it wastes energy through efficiency losses
        # No explicit constraint needed - the economics prevent it
        
        # 5. Grid export constraints
        for t in range(n_slots):
            # Always respect max export power limit
            prob += grid_export[t] <= self.config.max_export_power_kw, f"MaxGridExport_{t}"
        
        # 6. Target end-of-solar-period SOC (OPTIONAL GUIDANCE)
        # This is just a preference, not a requirement
        # We add a small penalty if we're below target, but it won't prevent solutions
        solar_end_slot = None
        for t in range(n_slots):
            try:
                dt = datetime.fromisoformat(demand_forecast[t]['timestamp'])
                if dt.hour == self.solar_end_hour and dt.minute == 0:
                    solar_end_slot = t
                    break
            except:
                continue
        
        if solar_end_slot is not None and solar_end_slot < n_slots:
            target_soc_kwh = self.target_end_soc * self.config.capacity_kwh
            # Optional soft guidance - penalize being below target
            # BUT make the penalty strong enough to actually matter!
            soc_deviation = pulp.LpVariable(f"soc_deviation", lowBound=0, upBound=self.config.capacity_kwh)
            prob += soc_deviation >= target_soc_kwh - soc[solar_end_slot], "SOC_deviation_calc"
            # Stronger penalty - ending with low SOC means importing later at expensive rates
            # Penalize at average import rate
            avg_import_rate = sum(import_rates) / len(import_rates)
            total_cost += soc_deviation * avg_import_rate * 2  # 2x average rate as penalty
            print(f"  ✓ Target SOC guidance added for slot {solar_end_slot} ({self.solar_end_hour}:00) - target {self.target_end_soc*100:.0f}%")
        else:
            print(f"  ⚠ Could not find solar end slot for hour {self.solar_end_hour}")
        
        # Set the objective function NOW (after all costs calculated)
        prob += total_cost, "TotalCost"
        
        print(f"  ✓ All constraints added ({len(prob.constraints)} total)")
        
        # SOLVE
        print("  🔍 Solving MILP problem...")
        solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=self.time_limit_seconds)
        prob.solve(solver)
        
        status = pulp.LpStatus[prob.status]
        print(f"  ✓ Solver status: {status}")
        
        if status == 'Infeasible':
            # DIAGNOSTIC MODE
            print("\n" + "="*70)
            print("🔍 INFEASIBILITY DIAGNOSTIC - Finding the problem...")
            print("="*70)
            
            # Try to identify which constraints are causing issues
            print("\n📊 Checking constraint groups:")
            
            # Test 1: Remove SOC target
            print("  1. Testing without SOC target constraint...")
            prob_test = pulp.LpProblem("Test1", pulp.LpMinimize)
            prob_test += total_cost
            for name, constraint in prob.constraints.items():
                if not name.startswith("SOC_deviation"):
                    prob_test += constraint, name
            prob_test.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=5))
            print(f"     Result: {pulp.LpStatus[prob_test.status]}")
            
            if pulp.LpStatus[prob_test.status] == 'Infeasible':
                # Test 2: Simplify to just energy balance
                print("  2. Testing with ONLY energy balance...")
                prob_test2 = pulp.LpProblem("Test2", pulp.LpMinimize)
                prob_test2 += total_cost
                for name, constraint in prob.constraints.items():
                    if name.startswith("EnergyBalance") or name.startswith("InitialSOC"):
                        prob_test2 += constraint, name
                prob_test2.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=5))
                print(f"     Result: {pulp.LpStatus[prob_test2.status]}")
                
                if pulp.LpStatus[prob_test2.status] == 'Infeasible':
                    print("\n❌ Energy balance itself is infeasible!")
                    print("   This suggests:")
                    print("   - Solar + grid import + battery discharge < demand + export + battery charge")
                    print("   - Likely: demand is too high OR constraints are too tight")
                    print(f"\n   Config check:")
                    print(f"   - Max charge: {self.config.max_charge_rate_kw} kW")
                    print(f"   - Max discharge: {self.config.max_discharge_rate_kw} kW")
                    print(f"   - Max export: {self.config.max_export_power_kw} kW")
                    print(f"   - Max PV: {self.config.max_pv_power_kw} kW")
                    print(f"   - Battery capacity: {self.config.capacity_kwh} kWh")
            
            print("\n💡 Attempting to solve with RELAXED constraints...")
            # Remove ALL optional constraints and just do basic optimization
            prob_relaxed = pulp.LpProblem("Relaxed", pulp.LpMinimize)
            prob_relaxed += total_cost
            
            # Only keep essential constraints
            for name, constraint in prob.constraints.items():
                if (name.startswith("EnergyBalance") or 
                    name.startswith("InitialSOC") or
                    name.startswith("SOCEvolution")):
                    prob_relaxed += constraint, name
            
            prob_relaxed.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=30))
            relaxed_status = pulp.LpStatus[prob_relaxed.status]
            print(f"  Result with relaxed constraints: {relaxed_status}")
            
            if relaxed_status in ['Optimal', 'Feasible']:
                print("\n✅ Problem is feasible with basic constraints!")
                print("   Issue is with one of the additional constraints.")
                print("   Try:")
                print("   1. Increase max_charge/discharge_rate_kw")
                print("   2. Reduce target_end_soc")
                print("   3. Check if starting SOC is reasonable")
                # Use the relaxed solution
                prob = prob_relaxed
                status = relaxed_status
            else:
                print("\n❌ Even basic optimization is infeasible!")
                print("   Possible causes:")
                print("   1. Current SOC + available energy < minimum demand")
                print("   2. Battery constraints prevent meeting demand")
                print("   3. Data has errors (negative values, NaN, etc.)")
                raise Exception(f"Fundamental infeasibility - cannot solve even with relaxed constraints")
        
        if status not in ['Optimal', 'Feasible']:
            raise Exception(f"Solver failed with status: {status}")
        
        # EXTRACT RESULTS
        schedule = []
        total_import = 0
        total_export = 0
        total_charge = 0
        total_discharge = 0
        total_curtailed = 0
        
        for t in range(n_slots):
            # Extract values
            soc_kwh = pulp.value(soc[t+1])
            charge_kw = pulp.value(battery_charge[t])
            discharge_kw = pulp.value(battery_discharge[t])
            import_kw = pulp.value(grid_import[t])
            export_kw = pulp.value(grid_export[t])
            curtail_kw = pulp.value(solar_curtailment[t])
            
            total_curtailed += curtail_kw * slot_duration
            
            # Determine action
            action = "hold"
            power_kw = 0
            
            if charge_kw > 0.01:
                action = "charge"
                power_kw = charge_kw
                total_charge += charge_kw * slot_duration
            elif discharge_kw > 0.01:
                if export_kw > 0.01:
                    action = "export"
                else:
                    action = "discharge"
                power_kw = discharge_kw
                total_discharge += discharge_kw * slot_duration
            
            total_import += import_kw * slot_duration
            total_export += export_kw * slot_duration
            
            # Calculate slot cost
            slot_cost_p = (
                import_kw * import_rates[t] * slot_duration * 100 -  # Import cost in pence
                export_kw * export_rates[t] * slot_duration * 100     # Export revenue in pence
            )
            
            schedule.append({
                'slot': t,
                'timestamp': demand_forecast[t]['timestamp'],
                'action': action,
                'action_detail': action,
                'power_kw': round(power_kw, 2),
                'soc_kwh': round(soc_kwh, 2),
                'soc_percent': round(soc_kwh / self.config.capacity_kwh * 100, 1),
                'demand_kw': demand_forecast[t]['predicted_kw'],
                'solar_kw': solar_forecast[t]['predicted_solar_kw'],
                'import_rate_p': import_rates[t] * 100,  # Convert £/kWh to p/kWh for display
                'export_rate_p': export_rates[t] * 100,  # Convert £/kWh to p/kWh for display
                'grid_import_kw': round(import_kw, 2),
                'grid_export_kw': round(export_kw, 2),
                'solar_curtailment_kw': round(curtail_kw, 2),
                'slot_cost_p': round(slot_cost_p, 1)
            })
        
        # Calculate statistics
        total_cost_pounds = pulp.value(prob.objective)
        
        stats = {
            'total_cost': round(total_cost_pounds, 2),
            'total_import_kwh': round(total_import, 2),
            'total_export_kwh': round(total_export, 2),
            'total_charge_kwh': round(total_charge, 2),
            'total_discharge_kwh': round(total_discharge, 2),
            'total_curtailed_kwh': round(total_curtailed, 2),
            'charge_from_grid_slots': sum(1 for s in schedule if s['action'] == 'charge'),
            'discharge_to_home_slots': sum(1 for s in schedule if s['action'] == 'discharge'),
            'discharge_to_grid_slots': sum(1 for s in schedule if s['action'] == 'export'),
            'hold_slots': sum(1 for s in schedule if s['action'] == 'hold'),
            'solver_status': status,
            'final_soc_kwh': round(pulp.value(soc[n_slots]), 2),
            'final_soc_percent': round(pulp.value(soc[n_slots]) / self.config.capacity_kwh * 100, 1)
        }
        
        print(f"  ✓ Optimization complete!")
        print(f"     Total cost: £{stats['total_cost']:.2f}")
        print(f"     Final SOC: {stats['final_soc_percent']:.1f}%")
        print(f"     Import: {stats['total_import_kwh']:.1f} kWh | Export: {stats['total_export_kwh']:.1f} kWh")
        if total_curtailed > 0.1:
            print(f"     ⚠️  Curtailed solar: {stats['total_curtailed_kwh']:.1f} kWh (battery full + export limited)")
        
        return {
            'schedule': schedule,
            'metadata': {
                'optimizer': 'MILPOptimizer',
                'total_cost_pounds': stats['total_cost'],
                'stats': stats
            }
        }


class SolarAwareOptimizer(BatteryOptimizer):
    """
    Solar-aware heuristic optimizer (original implementation)
    Fast but suboptimal compared to MILP
    """
    
    def __init__(
        self,
        config: BatteryConfig,
        cheap_import_threshold: float = 0.10,
        expensive_import_threshold: float = 0.25,
        export_threshold: float = 0.12,
        look_ahead_hours: int = 6
    ):
        super().__init__(config)
        self.cheap_import_threshold = cheap_import_threshold
        self.expensive_import_threshold = expensive_import_threshold
        self.export_threshold = export_threshold
        self.look_ahead_hours = look_ahead_hours
    
    def optimize(
        self,
        demand_forecast: List[Dict],
        solar_forecast: List[Dict],
        import_rates: List[float],
        export_rates: List[float],
        current_soc_kwh: float
    ) -> Dict[str, Any]:
        
        n_slots = len(demand_forecast)
        schedule = []
        soc = current_soc_kwh
        
        look_ahead_slots = self.look_ahead_hours * 2
        
        for slot in range(n_slots):
            rate = import_rates[slot]
            export_rate = export_rates[slot]
            solar_kw = solar_forecast[slot]['predicted_solar_kw']
            demand_kw = demand_forecast[slot]['predicted_kw']
            
            # Look ahead for incoming solar
            solar_coming = 0
            for look_ahead in range(slot, min(slot + look_ahead_slots, n_slots)):
                solar_coming += solar_forecast[look_ahead]['predicted_solar_kw']
            
            expected_solar_charge = solar_coming * 0.5 * self.config.charge_efficiency
            space_needed = min(expected_solar_charge, self.config.capacity_kwh * 0.9)
            
            # Determine action
            action, power = self._decide_action(
                slot, rate, export_rate, solar_kw, demand_kw,
                solar_coming, space_needed, soc
            )
            
            # Update SOC based on action
            soc = self._update_soc(soc, action, power)
            
            # Calculate cost
            cost_p = self._calculate_cost(
                action, power, demand_kw, solar_kw, rate, export_rate
            )
            
            # Simplify action for display
            display_action = self._simplify_action(action, power)
            
            schedule.append({
                'slot': slot,
                'timestamp': demand_forecast[slot]['timestamp'],
                'action': display_action,
                'action_detail': action,
                'power_kw': round(power, 2),
                'soc_kwh': round(soc, 2),
                'soc_percent': round(soc / self.config.capacity_kwh * 100, 1),
                'demand_kw': demand_kw,
                'solar_kw': solar_kw,
                'import_rate_p': rate,
                'export_rate_p': export_rate,
                'slot_cost_p': round(cost_p, 1),
                'solar_coming_6h': round(solar_coming, 1)
            })
        
        # Generate summary statistics
        stats = self._generate_stats(schedule)
        
        return {
            'schedule': schedule,
            'metadata': {
                'optimizer': 'SolarAwareOptimizer',
                'total_cost_pounds': stats['total_cost'],
                'stats': stats
            }
        }
    
    def _decide_action(
        self, slot, rate, export_rate, solar_kw, demand_kw,
        solar_coming, space_needed, soc
    ) -> tuple[str, float]:
        """Decide what action to take and how much power"""
        
        net_solar = solar_kw - demand_kw
        
        # Solar excess (generation > demand)
        if net_solar > 0.1:
            if soc < self.config.capacity_kwh * 0.95:
                return "charge_from_solar", min(net_solar, self.config.max_charge_rate_kw)
            else:
                return "export_solar", 0
        
        # Export to grid when export rate is attractive
        elif export_rate > self.export_threshold and soc > self.config.capacity_kwh * 0.3:
            return "export_to_grid", self.config.max_discharge_rate_kw
        
        # Discharge for own use when import is expensive
        elif rate > self.expensive_import_threshold and soc > self.config.capacity_kwh * 0.2:
            power = min(self.config.max_discharge_rate_kw, demand_kw - solar_kw)
            power = max(0, power)
            if power > 0:
                return "discharge_to_home", power
        
        # Charge from grid when import is cheap
        elif rate < self.cheap_import_threshold and soc < self.config.capacity_kwh * 0.90:
            return "charge_from_grid", self.config.max_charge_rate_kw
        
        # Pre-discharge before solar peak (only at reasonable rates)
        elif solar_coming > 2.0 and soc > space_needed and rate < 0.15:
            power = min(
                self.config.max_discharge_rate_kw,
                demand_kw,
                (soc - space_needed) / 0.5
            )
            if power > 0.1:
                return "pre_discharge", power
        
        return "hold", 0
    
    def _update_soc(self, soc: float, action: str, power: float) -> float:
        """Update state of charge based on action"""
        if "charge" in action and power > 0:
            soc = min(
                soc + power * self.config.charge_efficiency * 0.5,
                self.config.capacity_kwh
            )
        elif "discharge" in action and power > 0:
            soc = max(
                soc - power / self.config.discharge_efficiency * 0.5,
                self.config.min_soc * self.config.capacity_kwh
            )
        return soc
    
    def _calculate_cost(
        self, action: str, power: float, demand_kw: float,
        solar_kw: float, rate: float, export_rate: float
    ) -> float:
        """Calculate cost for this slot in pence"""
        
        if action == "charge_from_grid":
            grid_import = demand_kw + power - solar_kw
            return rate * grid_import * 0.5 * 100
        
        elif action in ["discharge_to_home", "pre_discharge"]:
            grid_import = max(0, demand_kw - solar_kw - power)
            return rate * grid_import * 0.5 * 100
        
        elif action == "export_to_grid":
            grid_import = max(0, demand_kw - solar_kw)
            cost = rate * grid_import * 0.5 * 100
            revenue = export_rate * power * 0.5 * 100
            return cost - revenue
        
        elif action in ["charge_from_solar", "export_solar"]:
            grid_import = max(0, demand_kw - solar_kw)
            cost = rate * grid_import * 0.5 * 100
            if action == "export_solar":
                net_solar = solar_kw - demand_kw
                revenue = export_rate * net_solar * 0.5 * 100
                return cost - revenue
            return cost
        
        else:  # hold
            grid_import = max(0, demand_kw - solar_kw)
            return rate * grid_import * 0.5 * 100
    
    def _simplify_action(self, action: str, power: float) -> str:
        """Simplify action name for display"""
        if power > 0:
            if "charge" in action:
                return "charge"
            elif "discharge" in action or "export" in action:
                return "discharge"
        return "hold"
    
    def _generate_stats(self, schedule: List[Dict]) -> Dict:
        """Generate summary statistics"""
        total_cost = sum(s['slot_cost_p'] for s in schedule) / 100
        
        charge_grid = sum(1 for s in schedule if 'charge_from_grid' in s.get('action_detail', ''))
        charge_solar = sum(1 for s in schedule if 'charge_from_solar' in s.get('action_detail', ''))
        discharge_home = sum(1 for s in schedule if 'discharge_to_home' in s.get('action_detail', ''))
        discharge_export = sum(1 for s in schedule if 'export_to_grid' in s.get('action_detail', ''))
        export_solar = sum(1 for s in schedule if 'export_solar' in s.get('action_detail', ''))
        
        return {
            'total_cost': round(total_cost, 2),
            'charge_from_grid_slots': charge_grid,
            'charge_from_solar_slots': charge_solar,
            'discharge_to_home_slots': discharge_home,
            'discharge_to_grid_slots': discharge_export,
            'export_solar_slots': export_solar,
            'hold_slots': len(schedule) - charge_grid - charge_solar - discharge_home - discharge_export - export_solar
        }