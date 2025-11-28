"""Configuration management for the add-on."""
import json
import os
from typing import Dict, Any


class Config:
    """Configuration handler for the add-on."""

    def __init__(self):
        """Initialize configuration from Home Assistant options."""
        config_path = os.getenv('CONFIG_PATH', '/data/options.json')

        with open(config_path, 'r') as f:
            self.options = json.load(f)

        # Home Assistant access
        self.supervisor_token = os.getenv('SUPERVISOR_TOKEN')
        self.ha_url = 'http://supervisor/core'

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self.options.get(key, default)

    @property
    def entity_id(self) -> str:
        """Energy consumption entity ID."""
        return self.get('entity_id', 'sensor.house_load')

    @property
    def prediction_slots(self) -> int:
        """Number of 30-min prediction slots (96 = 48 hours)."""
        return self.get('prediction_slots', 96)

    @property
    def max_training_days(self) -> int:
        """Maximum days of historical data for training."""
        return self.get('max_training_days', 30)

    @property
    def api_port(self) -> int:
        """API server port."""
        return self.get('api_port', 8099)

    @property
    def auto_update_interval(self) -> int:
        """Auto-update interval in seconds."""
        return self.get('auto_update_interval', 3600)

    # Octopus Energy
    @property
    def enable_octopus(self) -> bool:
        """Enable Octopus Energy integration."""
        return self.get('enable_octopus_integration', True)

    @property
    def octopus_import_entity(self) -> str:
        """Octopus import rate entity."""
        return self.get('octopus_import_rate_entity', '')

    @property
    def octopus_export_entity(self) -> str:
        """Octopus export rate entity."""
        return self.get('octopus_export_rate_entity', '')

    # Solar
    @property
    def solar_provider(self) -> str:
        """Solar forecast provider."""
        return self.get('solar_forecast_provider', 'solcast')

    @property
    def solcast_entity(self) -> str:
        """Solcast forecast entity."""
        return self.get('solcast_forecast_entity', 'sensor.solcast_pv_forecast_forecast_today')

    @property
    def solar_mode(self) -> str:
        """Solar forecast mode (estimate, estimate10, estimate90)."""
        return self.get('solar_forecast_mode', 'estimate')

    # Battery
    @property
    def battery_capacity_kwh(self) -> float:
        """Battery capacity in kWh."""
        return float(self.get('battery_capacity_kwh', 9.5))

    @property
    def battery_min_soc(self) -> float:
        """Minimum state of charge (0-1)."""
        return float(self.get('battery_min_soc', 0.1))

    @property
    def battery_reserve_soc(self) -> float:
        """Reserve SOC at end of period (0-1)."""
        return float(self.get('battery_reserve_soc', 0.2))

    @property
    def max_charge_rate_kw(self) -> float:
        """Maximum charge rate in kW."""
        return float(self.get('max_charge_rate_kw', 3.6))

    @property
    def max_discharge_rate_kw(self) -> float:
        """Maximum discharge rate in kW."""
        return float(self.get('max_discharge_rate_kw', 3.6))

    @property
    def charge_efficiency(self) -> float:
        """Charge efficiency (0-1)."""
        return float(self.get('charge_efficiency', 0.95))

    @property
    def discharge_efficiency(self) -> float:
        """Discharge efficiency (0-1)."""
        return float(self.get('discharge_efficiency', 0.95))

    @property
    def degradation_cost_per_cycle(self) -> float:
        """Battery degradation cost per full cycle."""
        return float(self.get('battery_degradation_cost_per_cycle', 0.05))

    @property
    def battery_soc_entity(self) -> str:
        """Battery state of charge entity."""
        return self.get('battery_soc_entity', 'sensor.battery_soc')

    # Grid
    @property
    def allow_grid_export(self) -> bool:
        """Allow exporting to grid."""
        return self.get('allow_grid_export', True)

    @property
    def max_export_rate_kw(self) -> float:
        """Maximum export rate in kW."""
        return float(self.get('max_export_rate_kw', 5.0))
