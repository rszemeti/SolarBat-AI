"""Home Assistant API client."""
import requests
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from config import Config

logger = logging.getLogger(__name__)


class HomeAssistantClient:
    """Client for Home Assistant API."""

    def __init__(self, config: Config):
        """Initialize HA client."""
        self.config = config
        self.headers = {
            'Authorization': f'Bearer {config.supervisor_token}',
            'Content-Type': 'application/json'
        }
        self.base_url = config.ha_url

    def get_history(self, entity_id: str, days: int = 7) -> List[Dict]:
        """Get historical data for entity."""
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)

        url = f"{self.base_url}/api/history/period/{start_time.isoformat()}"
        params = {'filter_entity_id': entity_id}

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data and len(data) > 0:
                return data[0]  # First entity's history
            return []
        except Exception as e:
            logger.error(f"Error fetching history for {entity_id}: {e}")
            return []

    def get_state(self, entity_id: str) -> Optional[Dict]:
        """Get current state of entity."""
        url = f"{self.base_url}/api/states/{entity_id}"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching state for {entity_id}: {e}")
            return None

    def set_state(self, entity_id: str, state: Any, attributes: Dict = None) -> bool:
        """Set state of entity."""
        url = f"{self.base_url}/api/states/{entity_id}"

        data = {
            'state': state,
            'attributes': attributes or {}
        }

        try:
            response = requests.post(url, headers=self.headers, json=data, timeout=10)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Error setting state for {entity_id}: {e}")
            return False

    def get_octopus_rates(self, entity_id: str) -> List[Dict]:
        """Get Octopus Energy rates from event entity."""
        state = self.get_state(entity_id)

        if not state:
            return []

        # Octopus rates are in attributes.rates
        rates = state.get('attributes', {}).get('rates', [])

        # Convert to our format
        result = []
        for rate in rates:
            result.append({
                'start': rate.get('start'),
                'end': rate.get('end'),
                'value_inc_vat': rate.get('value_inc_vat', 0)
            })

        return result

    def get_solcast_forecast(self) -> Dict:
        """Get Solcast solar forecast."""
        today_entity = self.config.solcast_entity
        tomorrow_entity = today_entity.replace('_today', '_tomorrow')

        today_state = self.get_state(today_entity)
        tomorrow_state = self.get_state(tomorrow_entity)

        result = {'forecasts': []}

        # Get forecast mode
        mode = self.config.solar_mode

        # Extract today's forecasts
        if today_state and 'attributes' in today_state:
            detailedForecast = today_state['attributes'].get('detailedForecast', [])
            for forecast in detailedForecast:
                result['forecasts'].append({
                    'period_end': forecast.get('period_end'),
                    'pv_estimate': forecast.get(f'pv_{mode}', forecast.get('pv_estimate', 0)) / 1000  # W to kW
                })

        # Extract tomorrow's forecasts
        if tomorrow_state and 'attributes' in tomorrow_state:
            detailedForecast = tomorrow_state['attributes'].get('detailedForecast', [])
            for forecast in detailedForecast:
                result['forecasts'].append({
                    'period_end': forecast.get('period_end'),
                    'pv_estimate': forecast.get(f'pv_{mode}', forecast.get('pv_estimate', 0)) / 1000
                })

        return result
