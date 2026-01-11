"""
Test Harness for SolarBat-AI - Windows Edition

Allows running and testing the optimizer locally in VS Code on Windows
by connecting to your Home Assistant instance via the API.

Usage:
1. Copy this file to your local dev environment
2. Create .env file with your HA credentials (see .env.example)
3. Run in VS Code terminal: python test_harness.py
"""

import os
import sys
import json
import requests
from datetime import datetime, time, timedelta
from typing import Dict, Optional, Any

# Try to load dotenv, but don't fail if not installed yet
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️  python-dotenv not installed. Install with: pip install python-dotenv requests")
    print("Or set environment variables manually")


class HomeAssistantAPI:
    """
    Mock hassapi.Hass interface that uses HA REST API
    
    Provides same interface as AppDaemon's hass object
    but works via HTTP API for local testing on Windows.
    """
    
    def __init__(self, url: str, token: str):
        """
        Initialize HA API connection.
        
        Args:
            url: Home Assistant URL (e.g., http://192.168.1.100:8123)
            token: Long-lived access token from HA
        """
        self.url = url.rstrip('/')
        self.token = token
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Test connection
        print(f"🔌 Connecting to {url}...")
        try:
            response = requests.get(f'{self.url}/api/', headers=self.headers, timeout=10)
            response.raise_for_status()
            print(f"✅ Connected to Home Assistant!")
        except requests.exceptions.ConnectionError:
            print(f"❌ Cannot connect to {url}")
            print(f"   Check:")
            print(f"   - Is Home Assistant running?")
            print(f"   - Is the URL correct? (include http:// and port)")
            print(f"   - Can you access {url} in a web browser?")
            sys.exit(1)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                print(f"❌ Authentication failed - check your token")
            else:
                print(f"❌ HTTP Error: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Failed to connect: {e}")
            sys.exit(1)
    
    def get_state(self, entity_id: str, attribute: Optional[str] = None, default: Any = None):
        """Get entity state (compatible with hassapi)"""
        try:
            response = requests.get(
                f'{self.url}/api/states/{entity_id}',
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 404:
                return default
            
            response.raise_for_status()
            data = response.json()
            
            if attribute == "all":
                return data
            elif attribute:
                return data.get('attributes', {}).get(attribute, default)
            else:
                state = data.get('state')
                if state in ['unknown', 'unavailable']:
                    return default
                return state
                
        except Exception as e:
            return default
    
    def get_all_states(self):
        """Get all entity states - returns dict of entity_id: state"""
        try:
            response = requests.get(
                f'{self.url}/api/states',
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            all_states = response.json()
            
            # Return as dict with entity_id as key
            return {state['entity_id']: state for state in all_states}
        except Exception as e:
            return {}
    
    def get_value(self, value_or_entity: Any, default=None) -> Any:
        """
        Smart helper that handles both hardcoded values and entity references.
        Same as the real inverter interface base class.
        """
        if value_or_entity is None:
            return default
        
        value_str = str(value_or_entity)
        
        # If it looks like an entity ID, fetch from HA
        if '.' in value_str and ('sensor.' in value_str or 'number.' in value_str or 
                                  'binary_sensor.' in value_str or 'switch.' in value_str):
            state = self.get_state(value_str, default)
            try:
                return float(state) if state is not None else default
            except (ValueError, TypeError):
                return state if state is not None else default
        
        # Otherwise return the literal value
        return value_or_entity
    
    def set_state(self, entity_id: str, state: Any, attributes: Optional[Dict] = None):
        """Set entity state (for sensors we create)"""
        try:
            payload = {
                'state': state,
                'attributes': attributes or {}
            }
            
            response = requests.post(
                f'{self.url}/api/states/{entity_id}',
                headers=self.headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            
        except Exception as e:
            print(f"❌ Error setting state for {entity_id}: {e}")
    
    def call_service(self, service: str, **kwargs):
        """Call a service"""
        try:
            domain, service_name = service.split('/')
            
            response = requests.post(
                f'{self.url}/api/services/{domain}/{service_name}',
                headers=self.headers,
                json=kwargs,
                timeout=10
            )
            response.raise_for_status()
            
        except Exception as e:
            print(f"❌ Error calling service {service}: {e}")
    
    def log(self, message: str, level: str = "INFO"):
        """Log a message"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"[{timestamp}] {message}")
    
    # Mock scheduling methods (don't actually schedule in test mode)
    def run_in(self, callback, delay):
        pass
    
    def run_minutely(self, callback, start):
        pass
    
    def run_hourly(self, callback, start):
        pass
    
    def run_daily(self, callback, start):
        pass
    
    def listen_state(self, callback, entity_id):
        pass


def load_config_from_env() -> Dict:
    """
    Load configuration from environment variables or .env file.
    
    Create a .env file with (minimum):
        HA_URL=http://192.168.1.100:8123
        HA_TOKEN=your_long_lived_access_token_here
    """
    config = {
        'ha_url': os.getenv('HA_URL'),
        'ha_token': os.getenv('HA_TOKEN'),
        
        # Battery & Inverter
        'battery_soc': os.getenv('BATTERY_SOC', 'sensor.solis8_battery_soc'),
        'battery_capacity': os.getenv('BATTERY_CAPACITY', '32'),
        'battery_voltage': os.getenv('BATTERY_VOLTAGE', '52'),
        'battery_power': os.getenv('BATTERY_POWER', 'sensor.solis8_battery_power'),
        'max_charge_current': os.getenv('MAX_CHARGE_CURRENT', 'sensor.solis8_battery_charge_max_current'),
        'max_discharge_current': os.getenv('MAX_DISCHARGE_CURRENT', 'sensor.solis8_battery_discharge_max_current'),
        
        # Power sensors
        'pv_power': os.getenv('PV_POWER', 'sensor.solis8_pv_total_power'),
        'grid_power': os.getenv('GRID_POWER', 'sensor.solis8_meter_active_power_total'),
        'load_power': os.getenv('LOAD_POWER', 'sensor.solis8_house_load'),
        
        # Charge Slot 1
        'charge_slot1_start_hour': os.getenv('CHARGE_SLOT1_START_HOUR', 'number.solis8_timed_charge_start_hours'),
        'charge_slot1_start_minute': os.getenv('CHARGE_SLOT1_START_MINUTE', 'number.solis8_timed_charge_start_minutes'),
        'charge_slot1_end_hour': os.getenv('CHARGE_SLOT1_END_HOUR', 'number.solis8_timed_charge_end_hours'),
        'charge_slot1_end_minute': os.getenv('CHARGE_SLOT1_END_MINUTE', 'number.solis8_timed_charge_end_minutes'),
        'charge_slot1_soc': os.getenv('CHARGE_SLOT1_SOC', 'number.solis8_timed_charge_soc'),
        'charge_slot1_current': os.getenv('CHARGE_SLOT1_CURRENT', 'number.solis8_timed_charge_current'),
        
        # Discharge Slot 1
        'discharge_slot1_start_hour': os.getenv('DISCHARGE_SLOT1_START_HOUR', 'number.solis8_timed_discharge_start_hours'),
        'discharge_slot1_start_minute': os.getenv('DISCHARGE_SLOT1_START_MINUTE', 'number.solis8_timed_discharge_start_minutes'),
        'discharge_slot1_end_hour': os.getenv('DISCHARGE_SLOT1_END_HOUR', 'number.solis8_timed_discharge_end_hours'),
        'discharge_slot1_end_minute': os.getenv('DISCHARGE_SLOT1_END_MINUTE', 'number.solis8_timed_discharge_end_minutes'),
        'discharge_slot1_soc': os.getenv('DISCHARGE_SLOT1_SOC', 'number.solis8_timed_discharge_soc'),
        'discharge_slot1_current': os.getenv('DISCHARGE_SLOT1_CURRENT', 'number.solis8_timed_discharge_current'),
        
        # Testing/simulation parameters
        'solar_scaling': float(os.getenv('SOLAR_SCALING', '1.0')),
    }
    
    if not config['ha_url'] or not config['ha_token']:
        print("\n❌ Missing configuration!")
        print("\nOption 1: Create a .env file with:")
        print("  HA_URL=http://192.168.1.100:8123")
        print("  HA_TOKEN=your_token_here")
        print("\nOption 2: Set environment variables:")
        print("  set HA_URL=http://192.168.1.100:8123")
        print("  set HA_TOKEN=your_token_here")
        print("\nTo get a token:")
        print("  1. Open Home Assistant")
        print("  2. Click your profile (bottom left)")
        print("  3. Scroll to 'Long-Lived Access Tokens'")
        print("  4. Click 'Create Token'")
        sys.exit(1)
    
    return config


def find_octopus_agile_entities(hass):
    """Auto-discover Octopus Agile entities by pattern matching"""
    print("\n🔍 Searching for Octopus Agile entities...")
    
    try:
        # Get all states
        response = requests.get(
            f'{hass.url}/api/states',
            headers=hass.headers,
            timeout=10
        )
        response.raise_for_status()
        all_entities = response.json()
        
        # Search for Octopus patterns
        current_rate = None
        rates_event = None
        export_rate = None
        
        for entity in all_entities:
            entity_id = entity.get('entity_id', '')
            
            # Find current rate sensor (ends with _current_rate)
            if 'octopus_energy_electricity' in entity_id and entity_id.endswith('_current_rate'):
                if 'export' not in entity_id:
                    current_rate = entity_id
                    print(f"  ✅ Found import rate: {entity_id}")
                else:
                    export_rate = entity_id
                    print(f"  ✅ Found export rate: {entity_id}")
            
            # Find rates event (ends with _current_day_rates)
            if 'octopus_energy_electricity' in entity_id and entity_id.endswith('_current_day_rates'):
                if 'export' not in entity_id:
                    rates_event = entity_id
                    print(f"  ✅ Found rates event: {entity_id}")
        
        return {
            'current_rate': current_rate,
            'rates_event': rates_event,
            'export_rate': export_rate
        }
        
    except Exception as e:
        print(f"  ⚠️  Error searching: {e}")
        return None


def find_solis_entities(hass):
    """Auto-discover Solis/Solax entities by pattern matching"""
    print("\n🔍 Searching for Solis inverter entities...")
    
    try:
        response = requests.get(
            f'{hass.url}/api/states',
            headers=hass.headers,
            timeout=10
        )
        response.raise_for_status()
        all_entities = response.json()
        
        found = {
            'battery': [],
            'power': [],
            'slots': []
        }
        
        for entity in all_entities:
            entity_id = entity.get('entity_id', '')
            
            # Battery sensors
            if any(x in entity_id for x in ['solis', 'solax']):
                if 'battery' in entity_id:
                    found['battery'].append(entity_id)
                elif any(x in entity_id for x in ['pv_power', 'measured_power', 'house_load']):
                    found['power'].append(entity_id)
                elif 'timed_charge' in entity_id or 'timed_discharge' in entity_id:
                    found['slots'].append(entity_id)
        
        # Display findings
        if found['battery']:
            print(f"\n  📊 Battery sensors ({len(found['battery'])} found):")
            for e in found['battery'][:5]:  # Show first 5
                print(f"    • {e}")
        
        if found['power']:
            print(f"\n  ⚡ Power sensors ({len(found['power'])} found):")
            for e in found['power'][:5]:
                print(f"    • {e}")
        
        if found['slots']:
            print(f"\n  🕐 Time slot entities ({len(found['slots'])} found):")
            for e in found['slots'][:8]:
                print(f"    • {e}")
        
        return found
        
    except Exception as e:
        print(f"  ⚠️  Error searching: {e}")
        return None


def test_connection():
    """Test basic connection to Home Assistant"""
    print("\n" + "=" * 60)
    print("Test 1: Connection Test")
    print("=" * 60)
    
    config = load_config_from_env()
    hass = HomeAssistantAPI(config['ha_url'], config['ha_token'])
    
    print("✅ Connection test passed!")
    return hass


def test_read_entities(hass):
    """Test reading some basic entities"""
    print("\n" + "=" * 60)
    print("Test 2: Auto-Discovery")
    print("=" * 60)
    
    # Auto-discover Octopus Agile
    print("\n🔍 Searching for Octopus Agile entities...")
    octopus = find_octopus_agile_entities(hass)
    
    if octopus and octopus['current_rate']:
        price = hass.get_state(octopus['current_rate'])
        print(f"\n💰 Current Import Price: {price}p/kWh")
        print(f"   Entity: {octopus['current_rate']}")
    else:
        print("\n⚠️  No Octopus Agile entities found")
        print("   Make sure Octopus Energy integration is installed")
    
    if octopus and octopus['export_rate']:
        export_price = hass.get_state(octopus['export_rate'])
        print(f"💰 Current Export Price: {export_price}p/kWh")
        print(f"   Entity: {octopus['export_rate']}")
    
    # Auto-discover Solis entities
    print("\n🔍 Searching for Solis/Solax entities...")
    solis = find_solis_entities(hass)
    
    if solis and solis['battery']:
        print(f"\n📊 Found {len(solis['battery'])} battery sensors")
        print(f"⚡ Found {len(solis['power'])} power sensors")
        print(f"🕐 Found {len(solis['slots'])} time slot entities")
        
        # Show some current values
        print("\n📈 Current readings:")
        for entity in solis['battery'][:3]:
            value = hass.get_state(entity)
            if value:
                print(f"  {entity} = {value}")
    else:
        print("\n⚠️  No Solis entities found")
        print("   Make sure solax_modbus integration is installed")
    
    return True


def test_pricing_provider(hass):
    """Test the Octopus Agile pricing provider with auto-discovery"""
    print("\n" + "=" * 60)
    print("Test: Octopus Agile Pricing Provider")
    print("=" * 60)
    
    # Add apps directory to path
    import sys
    import importlib.util
    
    sys.path.insert(0, './apps/solar_optimizer')
    
    try:
        # Load modules directly to avoid relative import issues
        
        # Load base class first
        spec_base = importlib.util.spec_from_file_location(
            "pricing_provider_base", 
            "./apps/solar_optimizer/pricing_provider_base.py"
        )
        base_module = importlib.util.module_from_spec(spec_base)
        spec_base.loader.exec_module(base_module)
        sys.modules['pricing_provider_base'] = base_module
        
        # Load import pricing provider (v2.3)
        spec_octopus = importlib.util.spec_from_file_location(
            "import_pricing_provider",
            "apps/solar_optimizer/providers/import_pricing_provider.py"
        )
        octopus_module = importlib.util.module_from_spec(spec_octopus)
        spec_octopus.loader.exec_module(octopus_module)
        
        ImportPricingProvider = octopus_module.ImportPricingProvider
        
        # Create provider
        pricing = ImportPricingProvider(hass)
        
        # Setup with empty config - let it auto-discover
        success = pricing.setup({})
        
        if not success:
            print("❌ Pricing provider setup failed (auto-discovery didn't find entities)")
            print("   Make sure Octopus Energy integration is installed")
            return False
        
        # Get current price
        current = pricing.get_current_price()
        if current:
            print(f"\n💰 Current Import Price: {current:.2f}p/kWh")
        
        # Get export if available
        export = pricing.get_export_price()
        if export:
            print(f"💰 Current Export Price: {export:.2f}p/kWh")
        
        # Get 24 hours of prices
        print("\n📊 Getting 24 hours of prices (known + predicted)...")
        price_data = pricing.get_prices_with_confidence(hours=24)
        
        print(f"  Known hours: {price_data['hours_known']:.1f}h")
        print(f"  Predicted hours: {price_data['hours_predicted']:.1f}h")
        print(f"  Overall confidence: {price_data['confidence']}")
        
        if price_data['predicted_from']:
            print(f"  Predictions start: {price_data['predicted_from'].strftime('%H:%M %d/%m')}")
        
        # Show statistics
        stats = price_data['statistics']
        print(f"\n📈 Price Statistics:")
        print(f"  Min: {stats['min']:.2f}p")
        print(f"  Max: {stats['max']:.2f}p")
        print(f"  Avg: {stats['avg']:.2f}p")
        
        print("\n✅ Pricing provider test complete")
        return True
        
    except Exception as e:
        print(f"❌ Error testing pricing provider: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_inverter_interface(hass):
    """Test the Solis S6 inverter interface"""
    print("\n" + "=" * 60)
    print("Test: Solis S6 Inverter Interface")
    print("=" * 60)
    
    import sys
    import importlib.util
    
    sys.path.insert(0, './apps/solar_optimizer')
    
    try:
        # Load base interface first
        spec_base = importlib.util.spec_from_file_location(
            "inverter_interface_base",
            "./apps/solar_optimizer/inverter_interface_base.py"
        )
        base_module = importlib.util.module_from_spec(spec_base)
        spec_base.loader.exec_module(base_module)
        sys.modules['inverter_interface_base'] = base_module
        
        # Load Solis interface
        spec_solis = importlib.util.spec_from_file_location(
            "inverter_interface_solis6",
            "./apps/solar_optimizer/inverter_interface_solis6.py"
        )
        solis_module = importlib.util.module_from_spec(spec_solis)
        spec_solis.loader.exec_module(solis_module)
        
        SolisInverterInterface = solis_module.SolisInverterInterface
        
        # Create interface
        interface = SolisInverterInterface(hass)
        
        # Setup with config
        config = load_config_from_env()
        success = interface.setup(config)
        
        if not success:
            print("❌ Interface setup failed")
            return False
        
        # Get capabilities
        print("\n📊 Inverter Capabilities:")
        caps = interface.get_capabilities()
        for key, value in caps.items():
            print(f"  {key}: {value}")
        
        # Get current state
        print("\n📊 Current State:")
        state = interface.get_current_state()
        print(f"  Battery SOC: {state['battery_soc']:.1f}%")
        print(f"  Battery Power: {state['battery_power']:.2f}kW")
        print(f"  PV Power: {state['pv_power']:.2f}kW")
        print(f"  Grid Power: {state['grid_power']:.2f}kW")
        print(f"  Active Slots: {state['active_slots']}")
        
        print("\n✅ Inverter interface test complete")
        return True
        
    except Exception as e:
        print(f"❌ Error testing inverter: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run test sequence"""
    print("\n" + "=" * 70)
    print("  SolarBat-AI Test Harness - Windows Edition")
    print("=" * 70)
    print(f"  Testing at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    try:
        # Test 1: Connection
        hass = test_connection()
        
        # Test 2: Auto-discover with quick scan
        test_read_entities(hass)
        
        # Test 3: Pricing provider (uses real code)
        print("\n" + "=" * 60)
        print("Testing with actual provider code...")
        print("=" * 60)
        test_pricing_provider(hass)
        
        # Test 4: Inverter interface (uses real code)
        test_inverter_interface(hass)
        
        print("\n" + "=" * 70)
        print("  ✅ All tests complete!")
        print("=" * 70)
        
        # Ask if user wants to run the planner
        print("\n💡 Would you like to run the planner and view the plan?")
        print("   This will generate a 24-hour optimization plan and")
        print("   display it in your browser.")
        
        response = input("\nRun planner? (y/n): ").strip().lower()
        
        if response == 'y':
            plan = run_planner_and_generate_plan(hass)
            if plan:
                start_web_server(plan)
        else:
            print("\n💡 The pricing provider and inverter interface")
            print("   will auto-discover entities when running in AppDaemon!")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted")
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()



def run_planner_and_generate_plan(hass):
    """Run the actual planner and generate a 24-hour plan"""
    print("\n" + "=" * 60)
    print("Running Solar Optimizer Planner")
    print("=" * 60)
    
    import sys
    import importlib.util
    
    sys.path.insert(0, './apps/solar_optimizer')
    
    try:
        # Load pricing provider
        spec_pricing_base = importlib.util.spec_from_file_location(
            "pricing_provider_base",
            "./apps/solar_optimizer/pricing_provider_base.py"
        )
        pricing_base_module = importlib.util.module_from_spec(spec_pricing_base)
        spec_pricing_base.loader.exec_module(pricing_base_module)
        
        # Load base provider first (v2.3)
        spec_base_prov = importlib.util.spec_from_file_location(
            "base_provider",
            "apps/solar_optimizer/providers/base_provider.py"
        )
        base_prov_module = importlib.util.module_from_spec(spec_base_prov)
        spec_base_prov.loader.exec_module(base_prov_module)
        sys.modules['base_provider'] = base_prov_module
        
        spec_pricing = importlib.util.spec_from_file_location(
            "import_pricing_provider",
            "apps/solar_optimizer/providers/import_pricing_provider.py"
        )
        pricing_module = importlib.util.module_from_spec(spec_pricing)
        spec_pricing.loader.exec_module(pricing_module)
        
        # Load inverter interface
        spec_inv_base = importlib.util.spec_from_file_location(
            "inverter_interface_base",
            "./apps/solar_optimizer/inverter_interface_base.py"
        )
        inv_base_module = importlib.util.module_from_spec(spec_inv_base)
        spec_inv_base.loader.exec_module(inv_base_module)
        sys.modules['inverter_interface_base'] = inv_base_module
        
        spec_inv = importlib.util.spec_from_file_location(
            "inverter_interface_solis6",
            "./apps/solar_optimizer/inverter_interface_solis6.py"
        )
        inv_module = importlib.util.module_from_spec(spec_inv)
        spec_inv.loader.exec_module(inv_module)
        
        # Create instances
        pricing = pricing_module.ImportPricingProvider(hass)
        pricing.setup({})
        
        config = load_config_from_env()
        inverter = inv_module.SolisInverterInterface(hass)
        inverter.setup(config)
        
        # Get 24 hours of prices
        print("\n[PLAN] Getting pricing data...")
        price_data = pricing.get_prices_with_confidence(hours=24)
        
        # Get inverter state
        print("[PLAN] Getting inverter state...")
        inv_state = inverter.get_current_state()
        inv_caps = inverter.get_capabilities()
        
        # Get solar forecast from Solcast - REQUIRED
        print("[PLAN] Getting solar forecast from Solcast...")
        solar_forecast = []
        
        try:
            # Get Solcast detailed forecast
            solcast_entity = config.get('solcast_forecast_today', 'sensor.solcast_pv_forecast_forecast_today')
            print(f"[PLAN] Reading from: {solcast_entity}")
            
            solcast_data = hass.get_state(solcast_entity, attribute='all')
            
            if not solcast_data:
                print(f"[ERROR] Could not read Solcast entity: {solcast_entity}")
                print(f"[ERROR] Check entity exists in Developer Tools → States")
                return None
            
            if 'attributes' not in solcast_data:
                print(f"[ERROR] Solcast entity has no attributes")
                print(f"[ERROR] State: {solcast_data}")
                return None
            
            detailed = solcast_data['attributes'].get('detailedForecast', [])
            
            if not detailed:
                print(f"[ERROR] Solcast has no detailedForecast data")
                print(f"[ERROR] Available attributes: {list(solcast_data['attributes'].keys())}")
                return None
            
            print(f"[PLAN] Found Solcast forecast with {len(detailed)} entries")
            
            now = datetime.now()
            
            for entry in detailed:
                try:
                    if not isinstance(entry, dict):
                        continue
                    
                    # Solcast uses 'period_start', not 'period_end'
                    period_start_str = entry.get('period_start')
                    pv_estimate = entry.get('pv_estimate', 0)
                    
                    if not period_start_str:
                        continue
                    
                    # Parse the timestamp and add 30 minutes to get period_end
                    period_start = datetime.fromisoformat(str(period_start_str).replace('Z', '+00:00')).replace(tzinfo=None)
                    period_end = period_start + timedelta(minutes=30)
                    
                    # Only use future forecasts
                    if period_end >= now:
                        solar_forecast.append({
                            'period_end': period_end,
                            'pv_estimate': float(pv_estimate)
                        })
                except Exception as e:
                    print(f"[WARN] Skipping Solcast entry: {e}")
                    continue
            
            if not solar_forecast:
                print(f"[ERROR] No future solar forecast data available")
                return None
            
            # Apply solar scaling factor (for testing)
            solar_scaling = float(os.getenv('SOLAR_SCALING', '1.0'))
            if solar_scaling != 1.0:
                print(f"[PLAN] Applying solar scaling factor: {solar_scaling}x")
                for sf in solar_forecast:
                    sf['pv_estimate'] = sf['pv_estimate'] * solar_scaling
            
            print(f"[PLAN] Loaded {len(solar_forecast)} solar forecast points")
            
            # Show first few for verification
            print(f"[PLAN] Solar forecast sample (scaled {solar_scaling}x):")
            for i, sf in enumerate(solar_forecast[:6]):
                print(f"       {sf['period_end'].strftime('%H:%M %d/%m')}: {sf['pv_estimate']:.2f}kW")
                
        except Exception as e:
            print(f"[ERROR] Failed to load Solcast data: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        # Get export price
        export_price = 15.0  # Default from .env
        try:
            export_config = os.getenv('EXPORT_RATE', '15.0')
            if '.' in export_config and 'sensor.' in export_config:
                # It's a sensor
                export_price = float(hass.get_state(export_config) or 15.0)
            else:
                # It's a hardcoded value
                export_price = float(export_config)
        except:
            export_price = 15.0
        
        print(f"[PLAN] Export price: {export_price}p/kWh")
        
        # Load the AI components
        print("[PLAN] Loading AI load forecaster and cost optimizer...")
        
        # Load load forecaster
        spec_load = importlib.util.spec_from_file_location(
            "load_forecaster",
            "./apps/solar_optimizer/load_forecaster.py"
        )
        load_module = importlib.util.module_from_spec(spec_load)
        spec_load.loader.exec_module(load_module)
        
        # Load plan creator (v2.3)
        spec_plan = importlib.util.spec_from_file_location(
            "plan_creator",
            "./apps/solar_optimizer/plan_creator.py"
        )
        plan_module = importlib.util.module_from_spec(spec_plan)
        spec_plan.loader.exec_module(plan_module)
        
        # Create load forecaster
        load_forecaster = load_module.LoadForecaster(hass)
        if not load_forecaster.setup(config):
            print("[ERROR] Load forecaster setup failed")
            return None
        
        # Get load forecast
        print("[PLAN] Predicting load for next 24 hours using AI...")
        load_forecast = load_forecaster.predict_loads_24h()
        
        # Create plan creator (v2.3 - pure optimization engine)
        plan_creator = plan_module.PlanCreator()
        
        # Prepare provider data format for plan creator
        import_prices = [{'time': p['start'], 'price': p['price'], 'is_predicted': p.get('is_predicted', False)} 
                        for p in price_data['prices']]
        export_prices = [{'time': p['start'], 'price': price_data.get('export_price', 15.0)} 
                        for p in price_data['prices']]
        solar_data = [{'time': s['period_end'], 'kw': s['pv_estimate']} for s in solar_forecast]
        
        system_state = {
            'current_state': inv_state,
            'capabilities': inv_caps,
            'active_slots': {'charge': [], 'discharge': []}
        }
        
        # Generate optimal plan using v2.3 architecture
        print("[PLAN] Running plan creator (v2.3)...")
        plan = plan_creator.create_plan(
            import_prices=import_prices,
            export_prices=export_prices,
            solar_forecast=solar_data,
            load_forecast=load_forecast,
            system_state=system_state
        )
        
        # Extract plan steps from v2.3 plan object
        plan_steps = plan['slots']
        
        # Build compatible plan dict for visualization
        plan_dict = {
            'timestamp': datetime.now(),
            'battery_soc': inv_state['battery_soc'],
            'battery_capacity': inv_caps['battery_capacity'],
            'prices': price_data['prices'],
            'solar_forecast': solar_forecast,
            'plan_steps': plan_steps,
            'statistics': price_data['statistics'],
            'confidence': price_data.get('confidence', plan['metadata'].get('confidence', 'unknown')),
            'hours_known': price_data['hours_known'],
            'hours_predicted': price_data['hours_predicted'],
            'total_cost': plan_steps[-1].get('cumulative_cost', 0) / 100 if plan_steps else 0.0  # In pounds
        }
        
        print(f"\n[PLAN] Plan generated successfully!")
        print(f"       Battery: {inv_state['battery_soc']:.1f}% ({inv_caps['battery_capacity']}kWh)")
        print(f"       Prices: {price_data['hours_known']:.1f}h known, {price_data['hours_predicted']:.1f}h predicted")
        print(f"       Price range: {price_data['statistics']['min']:.2f}p - {price_data['statistics']['max']:.2f}p")
        
        return plan_dict
        
    except Exception as e:
        print(f"[ERROR] Error running planner: {e}")
        import traceback
        traceback.print_exc()
        return None


def simulate_plan(prices, solar_forecast, inv_state, inv_caps, export_price=15.0):
    """
    Simulate battery SOC and determine modes for each 30-min slot.
    
    This is a simplified planner - real version would be much more sophisticated.
    
    Args:
        prices: Import prices from grid
        solar_forecast: Solar PV forecast
        inv_state: Current inverter state
        inv_caps: Inverter capabilities
        export_price: Export price (p/kWh) - default 15p fixed
    """
    plan_steps = []
    
    # Starting conditions
    current_soc = inv_state['battery_soc']
    battery_capacity = inv_caps['battery_capacity']
    max_charge_rate = inv_caps['max_charge_rate']
    max_discharge_rate = inv_caps['max_discharge_rate']
    
    # Calculate thresholds from actual price data
    import_prices = [p['price'] for p in prices[:48]]
    min_import = min(import_prices)
    max_import = max(import_prices)
    avg_import = sum(import_prices) / len(import_prices)
    
    # Strategy:
    # - Force charge when import price is in bottom 20% of range and SOC < 90%
    # - Force discharge when export > import AND import is in top 30% of range and SOC > 30%
    # - Otherwise self-use
    
    price_range = max_import - min_import
    cheap_import_threshold = min_import + (price_range * 0.2)  # Bottom 20%
    expensive_import_threshold = min_import + (price_range * 0.7)  # Top 30%
    
    # Also require minimum profit margin for discharge
    min_profit_margin = 1.0  # Need at least 1p profit to bother discharging
    
    min_discharge_soc = 30  # Don't discharge below this
    max_charge_soc = 90  # Don't charge above this
    
    for i, price in enumerate(prices[:48]):  # 24 hours
        # Get solar for this slot
        solar_pv = 0
        if i < len(solar_forecast):
            solar_pv = solar_forecast[i]['pv_estimate']
        
        import_price = price['price']
        
        # Determine mode and simulate SOC change
        mode = 'Self Use'
        soc_change = 0
        action = 'Self-consumption'
        
        # Decision logic
        if import_price <= cheap_import_threshold and current_soc < max_charge_soc:
            # Cheap import - force charge from grid
            mode = 'Force Charge'
            action = f'Charging from grid ({import_price:.2f}p <= {cheap_import_threshold:.2f}p threshold)'
            # Charge for 30 minutes at max rate
            energy_charged = (max_charge_rate * 0.5) * 0.95  # 95% efficiency
            soc_change = (energy_charged / battery_capacity) * 100
            
        elif (export_price > import_price + min_profit_margin and 
              import_price >= expensive_import_threshold and 
              current_soc > min_discharge_soc):
            # Export price beats import price with margin AND import is expensive - discharge to grid
            mode = 'Force Discharge'
            profit_margin = export_price - import_price
            action = f'Exporting to grid (earn {export_price:.2f}p vs pay {import_price:.2f}p = +{profit_margin:.2f}p profit)'
            # Discharge for 30 minutes
            energy_discharged = (max_discharge_rate * 0.5) * 0.95
            soc_change = -(energy_discharged / battery_capacity) * 100
            
        else:
            # Normal self-use
            mode = 'Self Use'
            if solar_pv > 1.0:
                # Solar charging battery
                action = f'Solar charging ({solar_pv:.1f}kW PV)'
                soc_change = min(2, (solar_pv * 0.5 * 0.3) / battery_capacity * 100)
            elif solar_pv > 0.2:
                action = f'Solar self-consumption ({solar_pv:.1f}kW PV)'
                soc_change = 0  # Balanced
            else:
                # Slight discharge for house load (assume 0.5kW average)
                action = 'Powering house from battery'
                soc_change = -((0.5 * 0.5) / battery_capacity * 100)
        
        # Update SOC (clamp to 0-100%)
        new_soc = max(0, min(100, current_soc + soc_change))
        
        plan_steps.append({
            'time': price['start'],
            'import_price': import_price,
            'export_price': export_price,
            'is_predicted': price.get('is_predicted', False),
            'solar_pv': solar_pv,
            'mode': mode,
            'action': action,
            'soc_start': current_soc,
            'soc_end': new_soc,
            'soc_change': soc_change
        })
        
        current_soc = new_soc
    
    # Add metadata about thresholds used
    print(f"[PLAN] Import price range: {min_import:.2f}p - {max_import:.2f}p (avg {avg_import:.2f}p)")
    print(f"[PLAN] Charge threshold: <= {cheap_import_threshold:.2f}p (bottom 20%)")
    print(f"[PLAN] Discharge threshold: >= {expensive_import_threshold:.2f}p (top 30%)")
    print(f"[PLAN] Min profit margin: {min_profit_margin:.2f}p")
    
    return plan_steps


def generate_plan_html(plan):
    """Generate HTML visualization using templates"""
    if not plan:
        return "<html><body><h1>Error: No plan generated</h1></body></html>"
    
    import json
    
    # Build chart data from plan steps
    time_labels = []
    import_price_values = []
    export_price_values = []
    soc_values = []
    solar_values = []
    
    for step in plan['plan_steps']:
        time_labels.append(step['time'].strftime('%H:%M'))
        import_price_values.append(step['import_price'])
        export_price_values.append(step['export_price'])
        soc_values.append(step['soc_end'])
        solar_values.append(step.get('solar_kw', 0))
    
    # Load templates
    try:
        with open('./templates/plan.html', 'r', encoding='utf-8') as f:
            html_template = f.read()
        with open('./templates/plan.css', 'r', encoding='utf-8') as f:
            css_content = f.read()
        with open('./templates/plan.js', 'r', encoding='utf-8') as f:
            js_content = f.read()
    except FileNotFoundError:
        return "<html><body><h1>Error: Template files not found in ./templates/</h1></body></html>"
    
    # Build summary stats HTML
    summary_stats = f"""
        <div class="stat-box">
            <div class="stat-label">Current SOC</div>
            <div class="stat-value">{plan['battery_soc']:.1f}%</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">Battery Size</div>
            <div class="stat-value">{plan['battery_capacity']:.1f} kWh</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">Min Price</div>
            <div class="stat-value">{plan['statistics']['min']:.2f}p</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">Max Price</div>
            <div class="stat-value">{plan['statistics']['max']:.2f}p</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">Avg Price</div>
            <div class="stat-value">{plan['statistics']['avg']:.2f}p</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">Confidence</div>
            <div class="stat-value">{plan['confidence'].upper()}</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">24h Cost</div>
            <div class="stat-value">£{plan.get('total_cost', 0):.2f}</div>
        </div>
    """
    
    # Count modes for summary
    mode_counts = {
        'Self Use': 0,
        'Force Charge': 0,
        'Force Discharge': 0,
        'Feed-in Priority': 0
    }
    for step in plan['plan_steps']:
        mode = step['mode']
        if mode in mode_counts:
            mode_counts[mode] += 1
    
    # Build plan rows HTML
    plan_rows = ""
    for step in plan['plan_steps']:
        mode_class = f"mode-{step['mode'].lower().replace(' ', '-')}"
        pred_marker = " *" if step.get('is_predicted_price', False) else ""
        
        # Format cost
        slot_cost = step.get('cost', 0)
        cost_str = f"{slot_cost:.2f}p" if slot_cost >= 0 else f"{abs(slot_cost):.2f}p"
        cost_class = "cost-positive" if slot_cost >= 0 else "cost-negative"
        
        # Format cumulative
        cumulative = step.get('cumulative_cost', 0) / 100
        cumulative_str = f"£{cumulative:.2f}" if cumulative >= 0 else f"-£{abs(cumulative):.2f}"
        
        # Add icon for Feed-in Priority mode
        mode_display = step['mode']
        if step['mode'] == 'Feed-in Priority':
            mode_display = '⚡ Feed-in Priority'
        
        plan_rows += f"""
            <tr class="{mode_class}">
                <td><strong>{step['time'].strftime('%H:%M')}</strong></td>
                <td><strong>{mode_display}</strong></td>
                <td>{step['action']}</td>
                <td>{step['soc_end']:.1f}%</td>
                <td>{step.get('solar_kw', 0):.2f}</td>
                <td>{step['import_price']:.2f}p{pred_marker}</td>
                <td>{step['export_price']:.2f}p</td>
                <td class="{cost_class}">{cost_str}</td>
                <td><strong>{cumulative_str}</strong></td>
            </tr>
        """
    
    # Build info summary
    info_summary = f"""
        <strong>Plan Summary:</strong><br>
        Known prices: {plan['hours_known']:.1f} hours<br>
        Predicted prices: {plan['hours_predicted']:.1f} hours<br>
        Data confidence: {plan['confidence']}<br>
        Total estimated cost: £{plan.get('total_cost', 0):.2f}<br><br>
        
        <strong>Mode Breakdown:</strong><br>
        Self Use: {mode_counts['Self Use']} slots<br>
        Force Charge: {mode_counts['Force Charge']} slots<br>
        Force Discharge: {mode_counts['Force Discharge']} slots<br>
        ⚡ Feed-in Priority: {mode_counts['Feed-in Priority']} slots (clipping prevention)<br><br>
        <strong>Legend:</strong><br>
        <span style="background: #d4edda; padding: 3px 8px; border-radius: 3px;">Self Use</span> = Normal operation<br>
        <span style="background: #fff3cd; padding: 3px 8px; border-radius: 3px;">Force Charge</span> = Charging from grid (cheap period)<br>
        <span style="background: #f8d7da; padding: 3px 8px; border-radius: 3px;">Force Discharge</span> = Selling to grid (expensive period)
    """
    
    # Build chart data JSON
    chart_data = {
        'timeLabels': time_labels,
        'socValues': soc_values,
        'importPrices': import_price_values,
        'exportPrices': export_price_values,
        'solarValues': solar_values
    }
    
    # Replace template placeholders
    html = html_template.replace('{{timestamp}}', plan['timestamp'].strftime('%Y-%m-%d %H:%M:%S'))
    html = html.replace('{{summary_stats}}', summary_stats)
    html = html.replace('{{plan_rows}}', plan_rows)
    html = html.replace('{{info_summary}}', info_summary)
    html = html.replace('{{chart_data}}', json.dumps(chart_data))
    
    # Inline CSS and JS (for single-file serving)
    html = html.replace('<link rel="stylesheet" href="plan.css">', f'<style>{css_content}</style>')
    html = html.replace('<script src="plan.js"></script>', f'<script>{js_content}</script>')
    
    return html
    """Generate HTML visualization of the plan"""
    if not plan:
        return "<html><body><h1>Error: No plan generated</h1></body></html>"
    
def start_web_server(plan):
    """Start a simple web server to display the plan"""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import webbrowser
    
    html_content = generate_plan_html(plan)
    
    class PlanHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html_content.encode('utf-8'))
        
        def log_message(self, format, *args):
            pass  # Suppress server logs
    
    port = 8765
    server = HTTPServer(('localhost', port), PlanHandler)
    
    print(f"\n[WEB] Starting web server at http://localhost:{port}")
    print(f"[WEB] Opening plan in your browser...")
    print(f"[WEB] Press Ctrl+C to stop the server\n")
    
    # Open browser
    webbrowser.open(f'http://localhost:{port}')
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n[WEB] Server stopped")
        server.shutdown()


if __name__ == '__main__':
    main()
