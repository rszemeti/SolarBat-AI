"""Energy tariff provider (Octopus Energy)."""
import logging
from datetime import datetime, timedelta
from typing import List, Dict

logger = logging.getLogger(__name__)


class TariffProvider:
    """Provides import/export tariff rates."""

    def __init__(self, config, ha_client):
        """Initialize tariff provider."""
        self.config = config
        self.ha_client = ha_client

    def _get_rates_for_slots(self, rates: List[Dict], slots: int) -> List[float]:
        """Convert rate data to per-slot rates."""
        if not rates:
            logger.warning("No rates available, using defaults")
            return [15.0] * slots  # Default 15p/kWh

        # Create timestamp-indexed rates
        rate_dict = {}
        for rate in rates:
            try:
                start = datetime.fromisoformat(rate['start'].replace('Z', '+00:00'))
                end = datetime.fromisoformat(rate['end'].replace('Z', '+00:00'))
                value = rate['value_inc_vat']

                # Fill all 30-min slots in this period
                current = start
                while current < end:
                    rate_dict[current] = value
                    current += timedelta(minutes=30)
            except Exception as e:
                logger.error(f"Error parsing rate: {e}")
                continue

        # Generate rates for each slot
        result = []
        now = datetime.now()

        # Round to next 30-minute interval
        minutes = (now.minute // 30 + 1) * 30
        if minutes == 60:
            start_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            start_time = now.replace(minute=minutes, second=0, microsecond=0)

        for i in range(slots):
            timestamp = start_time + timedelta(minutes=30 * i)

            # Find rate for this timestamp
            if timestamp in rate_dict:
                result.append(rate_dict[timestamp])
            else:
                # Use last known rate or default
                if result:
                    result.append(result[-1])
                else:
                    result.append(15.0)

        return result

    def get_import_rates(self, slots: int = 96) -> List[float]:
        """
        Get import tariff rates in pence/kWh.

        Args:
            slots: Number of 30-minute slots

        Returns:
            List of import rates (p/kWh)
        """
        if not self.config.enable_octopus or not self.config.octopus_import_entity:
            # No Octopus integration - use flat rate
            logger.info("Using flat import rate")
            return [15.0] * slots

        try:
            rates = self.ha_client.get_octopus_rates(self.config.octopus_import_entity)
            return self._get_rates_for_slots(rates, slots)
        except Exception as e:
            logger.error(f"Error fetching import rates: {e}")
            return [15.0] * slots

    def get_export_rates(self, slots: int = 96) -> List[float]:
        """
        Get export tariff rates in pence/kWh.

        Args:
            slots: Number of 30-minute slots

        Returns:
            List of export rates (p/kWh)
        """
        if not self.config.enable_octopus or not self.config.octopus_export_entity:
            # No export tariff
            logger.info("Using flat export rate")
            return [4.0] * slots

        try:
            rates = self.ha_client.get_octopus_rates(self.config.octopus_export_entity)
            return self._get_rates_for_slots(rates, slots)
        except Exception as e:
            logger.error(f"Error fetching export rates: {e}")
            return [4.0] * slots

    def get_rates_summary(self, import_rates: List[float], export_rates: List[float]) -> Dict:
        """Get summary of rates."""
        return {
            'import_min_p': round(min(import_rates), 2),
            'import_max_p': round(max(import_rates), 2),
            'import_avg_p': round(sum(import_rates) / len(import_rates), 2),
            'export_min_p': round(min(export_rates), 2),
            'export_max_p': round(max(export_rates), 2),
            'export_avg_p': round(sum(export_rates) / len(export_rates), 2),
        }
