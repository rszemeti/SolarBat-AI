"""Battery optimization using linear programming."""
import logging
from typing import List, Dict, Tuple
from datetime import datetime, timedelta
import pulp

logger = logging.getLogger(__name__)


class BatteryOptimizer:
    """Optimizes battery charge/discharge schedule."""

    def __init__(self, config, ha_client):
        """Initialize optimizer."""
        self.config = config
        self.ha_client = ha_client

    def _get_current_soc(self) -> float:
        """Get current battery state of charge (0-1)."""
        if not self.config.battery_soc_entity:
            return 0.5  # Default 50%

        state = self.ha_client.get_state(self.config.battery_soc_entity)
        if state:
            try:
                soc_percent = float(state['state'])
                return soc_percent / 100.0
            except (ValueError, KeyError):
                pass

        return 0.5

    def optimize(
        self,
        demand_predictions: List[Dict],
        solar_predictions: List[Dict],
        import_rates: List[float],
        export_rates: List[float]
    ) -> Dict:
        """
        Optimize battery schedule to minimize cost.

        Args:
            demand_predictions: Energy demand forecasts (kW)
            solar_predictions: Solar generation forecasts (kW)
            import_rates: Import tariff rates (p/kWh)
            export_rates: Export tariff rates (p/kWh)

        Returns:
            Optimization results with schedule
        """
        slots = len(demand_predictions)
        logger.info(f"Optimizing battery schedule for {slots} slots")

        # Create optimization problem
        prob = pulp.LpProblem("Battery_Optimization", pulp.LpMinimize)

        # Decision variables
        grid_import = [pulp.LpVariable(f"import_{i}", lowBound=0) for i in range(slots)]
        grid_export = [pulp.LpVariable(f"export_{i}", lowBound=0) for i in range(slots)]
        battery_charge = [pulp.LpVariable(f"charge_{i}", lowBound=0) for i in range(slots)]
        battery_discharge = [pulp.LpVariable(f"discharge_{i}", lowBound=0) for i in range(slots)]
        soc = [pulp.LpVariable(f"soc_{i}", lowBound=0, upBound=1) for i in range(slots)]

        # Binary variables for charge/discharge (can't do both simultaneously)
        charging = [pulp.LpVariable(f"charging_{i}", cat='Binary') for i in range(slots)]

        # Extract predictions
        demand = [p['predicted_kw'] for p in demand_predictions]
        solar = [p['predicted_solar_kw'] for p in solar_predictions]

        # Get current SOC
        current_soc = self._get_current_soc()

        # Parameters
        battery_capacity = self.config.battery_capacity_kwh
        max_charge = self.config.max_charge_rate_kw * 0.5  # kWh per 30-min slot
        max_discharge = self.config.max_discharge_rate_kw * 0.5
        charge_eff = self.config.charge_efficiency
        discharge_eff = self.config.discharge_efficiency
        min_soc = self.config.battery_min_soc
        reserve_soc = self.config.battery_reserve_soc
        degradation_cost = self.config.degradation_cost_per_cycle
        max_export = self.config.max_export_rate_kw * 0.5 if self.config.allow_grid_export else 0

        # Objective: minimize cost
        # Cost = import costs - export revenue + degradation
        import_cost = pulp.lpSum([
            grid_import[i] * import_rates[i] / 100.0  # Convert p to £
            for i in range(slots)
        ])

        export_revenue = pulp.lpSum([
            grid_export[i] * export_rates[i] / 100.0
            for i in range(slots)
        ])

        # Degradation cost (based on battery usage)
        degradation = pulp.lpSum([
            (battery_charge[i] + battery_discharge[i]) * degradation_cost / (2 * battery_capacity)
            for i in range(slots)
        ])

        prob += import_cost - export_revenue + degradation

        # Constraints
        for i in range(slots):
            # Energy balance: demand = solar + battery_discharge + grid_import - battery_charge - grid_export
            prob += demand[i] == (
                solar[i] +
                battery_discharge[i] * discharge_eff +
                grid_import[i] -
                battery_charge[i] / charge_eff -
                grid_export[i]
            ), f"energy_balance_{i}"

            # Charge/discharge rate limits
            prob += battery_charge[i] <= max_charge * charging[i], f"charge_limit_{i}"
            prob += battery_discharge[i] <= max_discharge * (1 - charging[i]), f"discharge_limit_{i}"

            # Export limit
            prob += grid_export[i] <= max_export, f"export_limit_{i}"

            # SOC constraints
            prob += soc[i] >= min_soc, f"min_soc_{i}"
            prob += soc[i] <= 1.0, f"max_soc_{i}"

            # SOC evolution
            if i == 0:
                prob += soc[i] == current_soc + (battery_charge[i] - battery_discharge[i]) / battery_capacity
            else:
                prob += soc[i] == soc[i-1] + (battery_charge[i] - battery_discharge[i]) / battery_capacity

        # Reserve SOC at end
        prob += soc[slots-1] >= reserve_soc, "reserve_soc"

        # Solve
        solver = pulp.PULP_CBC_CMD(msg=0)
        status = prob.solve(solver)

        if status != pulp.LpStatusOptimal:
            logger.error(f"Optimization failed with status: {pulp.LpStatus[status]}")
            return self._create_fallback_schedule(demand_predictions, solar_predictions, current_soc)

        # Extract results
        schedule = self._extract_schedule(
            demand_predictions,
            grid_import,
            grid_export,
            battery_charge,
            battery_discharge,
            soc,
            import_rates,
            export_rates
        )

        total_cost = pulp.value(prob.objective)

        logger.info(f"✅ Optimization complete! Total cost: £{total_cost:.2f}")

        return {
            'status': 'optimal',
            'total_cost': round(total_cost, 2),
            'schedule': schedule,
            'current_soc': round(current_soc * 100, 1)
        }

    def _extract_schedule(
        self,
        demand_predictions,
        grid_import,
        grid_export,
        battery_charge,
        battery_discharge,
        soc,
        import_rates,
        export_rates
    ) -> List[Dict]:
        """Extract schedule from optimization results."""
        schedule = []

        for i, pred in enumerate(demand_predictions):
            charge_kw = pulp.value(battery_charge[i]) * 2  # Convert kWh per 30min to kW
            discharge_kw = pulp.value(battery_discharge[i]) * 2
            soc_val = pulp.value(soc[i])

            # Determine action
            if charge_kw > 0.1:
                action = 'charge'
                power_kw = charge_kw
            elif discharge_kw > 0.1:
                action = 'discharge'
                power_kw = discharge_kw
            else:
                action = 'hold'
                power_kw = 0.0

            schedule.append({
                'timestamp': pred['timestamp'],
                'slot': i,
                'action': action,
                'power_kw': round(power_kw, 2),
                'soc_percent': round(soc_val * 100, 1),
                'grid_import_kw': round(pulp.value(grid_import[i]) * 2, 2),
                'grid_export_kw': round(pulp.value(grid_export[i]) * 2, 2),
                'import_rate_p': round(import_rates[i], 2),
                'export_rate_p': round(export_rates[i], 2)
            })

        return schedule

    def _create_fallback_schedule(self, demand_predictions, solar_predictions, current_soc) -> Dict:
        """Create fallback schedule if optimization fails."""
        logger.warning("Using fallback schedule (hold battery)")

        schedule = []
        soc_percent = current_soc * 100

        for i, pred in enumerate(demand_predictions):
            schedule.append({
                'timestamp': pred['timestamp'],
                'slot': i,
                'action': 'hold',
                'power_kw': 0.0,
                'soc_percent': round(soc_percent, 1),
                'grid_import_kw': 0.0,
                'grid_export_kw': 0.0,
                'import_rate_p': 15.0,
                'export_rate_p': 4.0
            })

        return {
            'status': 'fallback',
            'total_cost': 0.0,
            'schedule': schedule,
            'current_soc': round(soc_percent, 1)
        }

    def get_current_action(self, schedule: List[Dict]) -> Dict:
        """Get current battery action from schedule."""
        if not schedule:
            return {'action': 'hold', 'power_kw': 0.0}

        # Return first slot (current action)
        current = schedule[0]
        return {
            'action': current['action'],
            'power_kw': current['power_kw'],
            'soc_percent': current['soc_percent'],
            'timestamp': current['timestamp'],
            'import_rate_p': current['import_rate_p'],
            'export_rate_p': current['export_rate_p']
        }
