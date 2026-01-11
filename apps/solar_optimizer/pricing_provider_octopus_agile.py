"""
Octopus Agile Pricing Provider Implementation

Handles Octopus Agile import pricing, including prediction when prices
aren't available yet (before 4pm update).
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# Handle both AppDaemon (relative) and standalone (absolute) imports
try:
    from .pricing_provider_base import PricingProvider
except ImportError:
    from pricing_provider_base import PricingProvider


class OctopusAgilePricingProvider(PricingProvider):
    """
    Octopus Agile pricing implementation.
    
    Octopus Agile provides:
    - 30-minute pricing slots
    - Prices published around 4pm each day for next day
    - Current day prices are always available
    - Next day prices may not be available until ~4pm
    
    This provider handles the gap by predicting missing prices.
    """
    
    def setup(self, config: Dict) -> bool:
        """
        Setup Octopus Agile pricing provider.
        
        Expected config:
            - current_rate_sensor: sensor.octopus_energy_electricity_xxxxx_current_rate (optional - will auto-discover)
            - rates_event: event.octopus_energy_electricity_xxxxx_current_day_rates (optional - will auto-discover)
            - export_rate_sensor: sensor.octopus_energy_electricity_export_current_rate (optional)
        """
        try:
            # Try to get from config first
            self.current_rate_sensor = config.get('current_rate_sensor')
            self.rates_event = config.get('rates_event')
            self.export_rate_sensor = config.get('export_rate_sensor')
            
            # Auto-discover if not provided (like Predbat does with regex)
            if not self.current_rate_sensor or not self.rates_event:
                self.log("Auto-discovering Octopus Agile entities...")
                discovered = self._auto_discover_entities()
                
                if not self.current_rate_sensor and discovered.get('current_rate'):
                    self.current_rate_sensor = discovered['current_rate']
                    self.log(f"Auto-discovered import rate: {self.current_rate_sensor}")
                
                if not self.rates_event and discovered.get('rates_event'):
                    self.rates_event = discovered['rates_event']
                    self.log(f"Auto-discovered rates event: {self.rates_event}")
                
                if not self.export_rate_sensor and discovered.get('export_rate'):
                    self.export_rate_sensor = discovered['export_rate']
                    self.log(f"Auto-discovered export rate: {self.export_rate_sensor}")
            
            # Verify we have minimum required entities
            if not self.current_rate_sensor or not self.rates_event:
                self.log("Missing Octopus Agile entities (could not auto-discover)", level="ERROR")
                return False
            
            # Test entities exist
            current_rate = self.get_state(self.current_rate_sensor)
            if current_rate is None:
                self.log(f"Cannot find entity: {self.current_rate_sensor}", level="ERROR")
                return False
            
            # Load historical prices from entity
            self._load_historical_prices()
            
            self.log("Octopus Agile pricing provider setup successful")
            return True
            
        except Exception as e:
            self.log(f"Failed to setup Octopus Agile provider: {e}", level="ERROR")
            return False
    
    def _auto_discover_entities(self) -> Dict:
        """
        Auto-discover Octopus Agile entities using pattern matching.
        
        Mimics Predbat's regex approach:
        re:(sensor.(octopus_energy_|)electricity_[0-9a-z]+_[0-9a-z]+_current_rate)
        """
        discovered = {
            'current_rate': None,
            'rates_event': None,
            'export_rate': None
        }
        
        try:
            # Get all entity IDs from Home Assistant
            # Try get_all_states() first (test harness), fall back to get_state() (AppDaemon)
            if hasattr(self.hass, 'get_all_states'):
                states = self.hass.get_all_states()
                entity_ids = list(states.keys()) if states else []
            else:
                # AppDaemon's get_state() with no args returns all states
                states = self.hass.get_state()
                entity_ids = list(states.keys()) if states else []
            
            # Pattern matching (similar to Predbat regex)
            for entity_id in entity_ids:
                # Match import rate: sensor.octopus_energy_electricity_*_current_rate
                if ('octopus_energy_electricity' in entity_id and 
                    entity_id.endswith('_current_rate') and 
                    'export' not in entity_id):
                    discovered['current_rate'] = entity_id
                
                # Match rates event: event.octopus_energy_electricity_*_current_day_rates
                elif ('octopus_energy_electricity' in entity_id and 
                      entity_id.endswith('_current_day_rates') and 
                      'export' not in entity_id):
                    discovered['rates_event'] = entity_id
                
                # Match export rate: sensor.octopus_energy_electricity_*_export_current_rate
                elif ('octopus_energy_electricity' in entity_id and 
                      'export' in entity_id and 
                      entity_id.endswith('_current_rate')):
                    discovered['export_rate'] = entity_id
        
        except Exception as e:
            self.log(f"Error during auto-discovery: {e}", level="WARNING")
        
        return discovered
    
    def get_known_prices(self) -> List[Dict]:
        """
        Get known Agile prices from Octopus integration.
        
        Returns prices for current day and next day (if available).
        Typically next day becomes available around 4pm.
        """
        try:
            rates_attr = self.hass.get_state(self.rates_event, attribute="all")
            
            if not rates_attr or 'rates' not in rates_attr.get('attributes', {}):
                self.log("No rates available from Octopus integration", level="WARNING")
                return []
            
            rates = rates_attr['attributes']['rates']
            now = datetime.now().replace(second=0, microsecond=0)
            
            # Convert to our format
            known_prices = []
            for rate in rates:
                try:
                    # Octopus provides ISO format with Z timezone
                    rate_start = datetime.fromisoformat(rate['start'].replace('Z', '+00:00'))
                    
                    # Convert to local time if needed
                    rate_start = rate_start.replace(tzinfo=None)
                    
                    # Only include future prices
                    # Octopus value_inc_vat is in POUNDS, convert to pence
                    if rate_start >= now:
                        known_prices.append({
                            'start': rate_start,
                            'end': rate_start + timedelta(minutes=30),
                            'price': rate['value_inc_vat'] * 100,  # Convert £ to p
                            'is_predicted': False
                        })
                except Exception as e:
                    self.log(f"Error parsing rate: {e}", level="WARNING")
                    continue
            
            known_prices.sort(key=lambda x: x['start'])
            
            # Log how many hours we have
            if known_prices:
                hours_available = len(known_prices) / 2
                last_time = known_prices[-1]['start']
                self.log(f"Octopus Agile: {hours_available:.1f} hours of prices available until {last_time.strftime('%H:%M %d/%m')}")
            
            return known_prices
            
        except Exception as e:
            self.log(f"Error getting known prices: {e}", level="ERROR")
            return []
    
    def get_current_price(self) -> Optional[float]:
        """Get current Agile price (in pence)"""
        try:
            # Octopus integration returns prices in POUNDS
            price_pounds = float(self.get_state(self.current_rate_sensor))
            price_pence = price_pounds * 100  # Convert £ to p
            
            # Record for history
            now = datetime.now().replace(second=0, microsecond=0)
            self.record_price(now, price_pence)
            
            return price_pence
        except:
            return None
    
    def get_export_price(self) -> Optional[float]:
        """Get current export price (in pence, if on Agile Export)"""
        if not self.export_rate_sensor:
            return None
        
        try:
            # Octopus integration returns prices in POUNDS
            price_pounds = float(self.get_state(self.export_rate_sensor))
            return price_pounds * 100  # Convert £ to p
        except:
            return None
    
    def _load_historical_prices(self):
        """
        Load recent historical prices from Octopus integration.
        
        This helps with prediction when future prices aren't available.
        """
        try:
            rates_attr = self.hass.get_state(self.rates_event, attribute="all")
            
            if not rates_attr or 'rates' not in rates_attr.get('attributes', {}):
                return
            
            rates = rates_attr['attributes']['rates']
            now = datetime.now()
            
            for rate in rates:
                try:
                    rate_start = datetime.fromisoformat(rate['start'].replace('Z', '+00:00'))
                    rate_start = rate_start.replace(tzinfo=None)
                    
                    # Only load recent history (last 7 days)
                    # Octopus value_inc_vat is in POUNDS, convert to pence
                    if rate_start > now - timedelta(days=7) and rate_start < now:
                        price_pence = rate['value_inc_vat'] * 100
                        self.record_price(rate_start, price_pence)
                        
                except:
                    continue
            
            if self.price_history:
                self.log(f"Loaded {len(self.price_history)} historical prices for prediction")
                
        except Exception as e:
            self.log(f"Could not load historical prices: {e}", level="WARNING")
    
    def get_prices_with_confidence(self, hours: int = 24) -> Dict:
        """
        Get prices with confidence indicators.
        
        Returns:
            Dict with:
                - prices: List of price dicts
                - hours_known: How many hours of known prices
                - hours_predicted: How many hours are predicted
                - confidence: overall/high/medium/low
                - predicted_from: Time when predictions start
        """
        prices = self.get_prices_for_planning(hours)
        
        known_count = sum(1 for p in prices if not p.get('is_predicted', False))
        predicted_count = len(prices) - known_count
        
        hours_known = known_count / 2
        hours_predicted = predicted_count / 2
        
        # Determine overall confidence
        if hours_predicted == 0:
            confidence = 'high'
        elif hours_predicted < 6:
            confidence = 'medium'
        else:
            confidence = 'low'
        
        # Find where predictions start
        predicted_from = None
        for price in prices:
            if price.get('is_predicted', False):
                predicted_from = price['start']
                break
        
        return {
            'prices': prices,
            'hours_known': hours_known,
            'hours_predicted': hours_predicted,
            'confidence': confidence,
            'predicted_from': predicted_from,
            'statistics': self.get_price_statistics(prices)
        }
    
    def is_price_update_expected_soon(self) -> bool:
        """
        Check if Octopus price update is expected soon.
        
        Prices typically update around 4pm.
        Returns True if it's after 3pm and we don't have tomorrow's prices.
        """
        now = datetime.now()
        
        # After 3pm, expect prices soon
        if now.hour < 15:
            return False
        
        # Check if we have prices for tomorrow
        known_prices = self.get_known_prices()
        
        if not known_prices:
            return True
        
        # Check if last known price is today
        last_price_time = known_prices[-1]['start']
        tomorrow = datetime.now().date() + timedelta(days=1)
        
        # If last price is before tomorrow, we're waiting for update
        return last_price_time.date() < tomorrow
    
    def get_pricing_gaps(self, hours: int = 24) -> List[Tuple[datetime, datetime]]:
        """
        Identify gaps in pricing data.
        
        Returns:
            List of (start, end) tuples for gaps
        """
        prices = self.get_prices_for_planning(hours)
        
        gaps = []
        gap_start = None
        
        for price in prices:
            if price.get('is_predicted', False):
                if gap_start is None:
                    gap_start = price['start']
            else:
                if gap_start is not None:
                    gaps.append((gap_start, price['start']))
                    gap_start = None
        
        # Close final gap if exists
        if gap_start is not None:
            gaps.append((gap_start, prices[-1]['end']))
        
        return gaps
