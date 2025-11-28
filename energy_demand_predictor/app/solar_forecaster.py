"""Solar generation forecasting."""
import logging
from datetime import datetime, timedelta
from typing import List, Dict
import numpy as np

logger = logging.getLogger(__name__)


class SolarForecaster:
    """Solar generation forecaster using Solcast."""

    def __init__(self, config, ha_client):
        """Initialize solar forecaster."""
        self.config = config
        self.ha_client = ha_client

    def _interpolate_forecasts(self, forecasts: List[Dict], slots: int = 96) -> List[Dict]:
        """
        Interpolate solar forecasts to 30-minute slots.

        Solcast provides forecasts in 30-min intervals, but we ensure
        we have exactly the slots we need.
        """
        if not forecasts:
            # No solar data - return zeros
            logger.warning("No solar forecast data available")
            return self._zero_forecast(slots)

        # Convert to timestamp-indexed dict
        forecast_dict = {}
        for f in forecasts:
            try:
                ts = datetime.fromisoformat(f['period_end'].replace('Z', '+00:00'))
                forecast_dict[ts] = f['pv_estimate']
            except Exception as e:
                logger.error(f"Error parsing forecast: {e}")
                continue

        # Generate predictions for each slot
        results = []
        now = datetime.now()

        # Round to next 30-minute interval
        minutes = (now.minute // 30 + 1) * 30
        if minutes == 60:
            start_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            start_time = now.replace(minute=minutes, second=0, microsecond=0)

        for i in range(slots):
            timestamp = start_time + timedelta(minutes=30 * i)

            # Find closest forecast
            closest_forecast = 0.0
            min_diff = timedelta(days=999)

            for forecast_time, value in forecast_dict.items():
                diff = abs(forecast_time - timestamp)
                if diff < min_diff:
                    min_diff = diff
                    closest_forecast = value

            results.append({
                'timestamp': timestamp.isoformat(),
                'predicted_solar_kw': round(max(0, closest_forecast), 3),
                'slot': i
            })

        return results

    def _zero_forecast(self, slots: int) -> List[Dict]:
        """Generate zero solar forecast."""
        results = []
        now = datetime.now()

        minutes = (now.minute // 30 + 1) * 30
        if minutes == 60:
            start_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            start_time = now.replace(minute=minutes, second=0, microsecond=0)

        for i in range(slots):
            timestamp = start_time + timedelta(minutes=30 * i)
            results.append({
                'timestamp': timestamp.isoformat(),
                'predicted_solar_kw': 0.0,
                'slot': i
            })

        return results

    def get_forecast(self, slots: int = 96) -> List[Dict]:
        """
        Get solar generation forecast.

        Args:
            slots: Number of 30-minute slots

        Returns:
            List of solar predictions
        """
        if self.config.solar_provider == 'none':
            return self._zero_forecast(slots)

        if self.config.solar_provider == 'solcast':
            return self._get_solcast_forecast(slots)

        logger.warning(f"Unknown solar provider: {self.config.solar_provider}")
        return self._zero_forecast(slots)

    def _get_solcast_forecast(self, slots: int) -> List[Dict]:
        """Get forecast from Solcast integration."""
        try:
            forecast_data = self.ha_client.get_solcast_forecast()
            forecasts = forecast_data.get('forecasts', [])

            return self._interpolate_forecasts(forecasts, slots)

        except Exception as e:
            logger.error(f"Error getting Solcast forecast: {e}")
            return self._zero_forecast(slots)

    def get_total_generation(self, predictions: List[Dict]) -> float:
        """Calculate total generation in kWh."""
        total = sum(p['predicted_solar_kw'] for p in predictions)
        # Each slot is 30 minutes = 0.5 hours
        return total * 0.5
