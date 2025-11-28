"""Home Assistant sensor creation and updates."""
import logging
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)


class HASensorManager:
    """Manages Home Assistant sensor entities."""

    def __init__(self, ha_client):
        """Initialize sensor manager."""
        self.ha_client = ha_client

    def update_energy_demand_sensor(self, predictions: List[Dict], next_prediction: float):
        """Update energy demand predictor sensor."""
        # Split into 24h and 24-48h
        predictions_24h = predictions[:48] if len(predictions) > 48 else predictions
        predictions_extended = predictions[48:] if len(predictions) > 48 else []

        attributes = {
            'predictions': predictions_24h,
            'extended_predictions': predictions_extended,
            'last_updated': datetime.now().isoformat(),
            'friendly_name': 'Energy Demand Predictor',
            'icon': 'mdi:flash',
            'unit_of_measurement': 'kW'
        }

        self.ha_client.set_state(
            'sensor.energy_demand_predictor',
            round(next_prediction, 2),
            attributes
        )

    def update_solar_sensor(self, predictions: List[Dict], total_kwh: float):
        """Update solar predictor sensor."""
        predictions_24h = predictions[:48] if len(predictions) > 48 else predictions
        predictions_extended = predictions[48:] if len(predictions) > 48 else []

        current_solar = predictions[0]['predicted_solar_kw'] if predictions else 0.0

        attributes = {
            'predictions': predictions_24h,
            'extended_predictions': predictions_extended,
            'total_48h_kwh': round(total_kwh, 2),
            'last_updated': datetime.now().isoformat(),
            'friendly_name': 'Solar Predictor',
            'icon': 'mdi:solar-power',
            'unit_of_measurement': 'kW'
        }

        self.ha_client.set_state(
            'sensor.solar_predictor',
            round(current_solar, 2),
            attributes
        )

    def update_battery_optimizer_sensor(self, optimization_result: Dict):
        """Update battery optimizer sensor."""
        schedule = optimization_result.get('schedule', [])
        current_action_data = optimization_result.get('current_action', {})

        # Get current action
        current_action = current_action_data.get('action', 'hold')
        current_power = current_action_data.get('power_kw', 0.0)

        # Split schedule
        schedule_24h = schedule[:48] if len(schedule) > 48 else schedule
        schedule_extended = schedule[48:] if len(schedule) > 48 else []

        # Find next action changes
        next_changes = self._find_action_changes(schedule_24h)

        attributes = {
            'target_power_kw': round(current_power, 2),
            'current_soc_percent': optimization_result.get('current_soc', 50.0),
            'schedule': schedule_24h,
            'extended_schedule': schedule_extended,
            'next_action_changes': next_changes,
            'total_cost_48h': optimization_result.get('total_cost', 0.0),
            'optimization_status': optimization_result.get('status', 'unknown'),
            'last_updated': datetime.now().isoformat(),
            'friendly_name': 'Battery Optimizer',
            'icon': 'mdi:battery-charging' if current_action == 'charge' else
                   'mdi:battery-minus' if current_action == 'discharge' else
                   'mdi:battery',
        }

        self.ha_client.set_state(
            'sensor.battery_optimizer',
            current_action,
            attributes
        )

    def update_cost_sensor(self, schedule: List[Dict]):
        """Update energy cost predictor sensor."""
        # Calculate costs
        import_cost = 0.0
        export_revenue = 0.0

        for slot in schedule:
            import_kwh = slot.get('grid_import_kw', 0.0) * 0.5  # 30 min = 0.5h
            export_kwh = slot.get('grid_export_kw', 0.0) * 0.5
            import_rate = slot.get('import_rate_p', 0.0) / 100.0  # p to £
            export_rate = slot.get('export_rate_p', 0.0) / 100.0

            import_cost += import_kwh * import_rate
            export_revenue += export_kwh * export_rate

        total_cost = import_cost - export_revenue

        attributes = {
            'import_cost_48h': round(import_cost, 2),
            'export_revenue_48h': round(export_revenue, 2),
            'net_cost_48h': round(total_cost, 2),
            'last_updated': datetime.now().isoformat(),
            'friendly_name': 'Energy Cost Predictor',
            'icon': 'mdi:currency-gbp',
            'unit_of_measurement': '£'
        }

        self.ha_client.set_state(
            'sensor.energy_cost_predictor',
            round(total_cost, 2),
            attributes
        )

    def _find_action_changes(self, schedule: List[Dict], max_changes: int = 5) -> List[Dict]:
        """Find next action changes in schedule."""
        if not schedule:
            return []

        changes = []
        current_action = schedule[0]['action']

        for slot in schedule[1:]:
            if slot['action'] != current_action:
                changes.append({
                    'time': slot['timestamp'],
                    'action': slot['action'],
                    'power_kw': slot['power_kw']
                })
                current_action = slot['action']

                if len(changes) >= max_changes:
                    break

        return changes

    def update_all_sensors(
        self,
        demand_predictions: List[Dict],
        solar_predictions: List[Dict],
        optimization_result: Dict,
        solar_total_kwh: float
    ):
        """Update all sensors at once."""
        try:
            # Energy demand sensor
            next_demand = demand_predictions[0]['predicted_kw'] if demand_predictions else 0.0
            self.update_energy_demand_sensor(demand_predictions, next_demand)

            # Solar sensor
            self.update_solar_sensor(solar_predictions, solar_total_kwh)

            # Battery optimizer sensor
            self.update_battery_optimizer_sensor(optimization_result)

            # Cost sensor
            schedule = optimization_result.get('schedule', [])
            self.update_cost_sensor(schedule)

            logger.info("✅ All sensors updated successfully")
            return True

        except Exception as e:
            logger.error(f"Error updating sensors: {e}")
            return False
