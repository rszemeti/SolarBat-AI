"""Coordinator for all energy optimization components."""
import logging
from datetime import datetime
from typing import Dict
from config import Config
from ha_client import HomeAssistantClient
from energy_predictor import EnergyDemandPredictor
from solar_forecaster import SolarForecaster
from tariff_provider import TariffProvider
from battery_optimizer import BatteryOptimizer
from ha_sensors import HASensorManager

logger = logging.getLogger(__name__)


class EnergyCoordinator:
    """Coordinates all optimization components."""

    def __init__(self, config: Config):
        """Initialize coordinator."""
        self.config = config

        # Initialize components
        self.ha_client = HomeAssistantClient(config)
        self.energy_predictor = EnergyDemandPredictor(config, self.ha_client)
        self.solar_forecaster = SolarForecaster(config, self.ha_client)
        self.tariff_provider = TariffProvider(config, self.ha_client)
        self.battery_optimizer = BatteryOptimizer(config, self.ha_client)
        self.sensor_manager = HASensorManager(self.ha_client)

        # Latest data cache
        self.latest_data = {
            'last_update': None,
            'model_trained': False,
            'demand_predictions': [],
            'solar_predictions': [],
            'optimization_result': {},
            'solar_total_kwh': 0.0
        }

    def train_model(self) -> bool:
        """Train the energy demand model."""
        logger.info("Training energy demand model...")
        success = self.energy_predictor.train()
        self.latest_data['model_trained'] = success
        return success

    def update(self):
        """Run full update cycle."""
        logger.info("=" * 60)
        logger.info("Starting optimization update cycle")
        logger.info("=" * 60)

        try:
            # 1. Get energy demand predictions
            logger.info("📊 Getting energy demand predictions...")
            demand_predictions = self.energy_predictor.predict(
                slots=self.config.prediction_slots
            )

            if not demand_predictions:
                logger.error("No demand predictions available")
                return False

            logger.info(f"✅ Got {len(demand_predictions)} demand predictions")

            # 2. Get solar forecast
            logger.info("☀️ Getting solar forecast...")
            solar_predictions = self.solar_forecaster.get_forecast(
                slots=self.config.prediction_slots
            )
            solar_total_kwh = self.solar_forecaster.get_total_generation(solar_predictions)
            logger.info(f"✅ Got solar forecast: {solar_total_kwh:.2f} kWh total")

            # 3. Get tariff rates
            logger.info("💰 Getting tariff rates...")
            import_rates = self.tariff_provider.get_import_rates(
                slots=self.config.prediction_slots
            )
            export_rates = self.tariff_provider.get_export_rates(
                slots=self.config.prediction_slots
            )

            rates_summary = self.tariff_provider.get_rates_summary(import_rates, export_rates)
            logger.info(f"✅ Import: {rates_summary['import_min_p']}-{rates_summary['import_max_p']}p, "
                       f"Export: {rates_summary['export_min_p']}-{rates_summary['export_max_p']}p")

            # 4. Optimize battery schedule
            logger.info("🔋 Optimizing battery schedule...")
            optimization_result = self.battery_optimizer.optimize(
                demand_predictions,
                solar_predictions,
                import_rates,
                export_rates
            )

            # Get current action
            current_action = self.battery_optimizer.get_current_action(
                optimization_result.get('schedule', [])
            )
            optimization_result['current_action'] = current_action

            logger.info(f"✅ Optimization complete: {optimization_result['status']}")
            logger.info(f"   Total cost (48h): £{optimization_result['total_cost']:.2f}")
            logger.info(f"   Current action: {current_action['action'].upper()}")
            if current_action['power_kw'] > 0:
                logger.info(f"   Power: {current_action['power_kw']:.2f} kW")

            # 5. Update Home Assistant sensors
            logger.info("📡 Updating Home Assistant sensors...")
            self.sensor_manager.update_all_sensors(
                demand_predictions,
                solar_predictions,
                optimization_result,
                solar_total_kwh
            )

            # 6. Cache latest data
            self.latest_data = {
                'last_update': datetime.now().isoformat(),
                'model_trained': self.energy_predictor.is_trained,
                'demand_predictions': demand_predictions,
                'solar_predictions': solar_predictions,
                'optimization_result': optimization_result,
                'solar_total_kwh': solar_total_kwh
            }

            logger.info("=" * 60)
            logger.info("✅ Update cycle complete!")
            logger.info("=" * 60)
            return True

        except Exception as e:
            logger.error(f"Error in update cycle: {e}", exc_info=True)
            return False

    def get_latest_data(self) -> Dict:
        """Get latest cached data."""
        return self.latest_data
