#!/usr/bin/env python3
"""
Standalone Battery Optimizer - Runs on your laptop
Connects to remote Home Assistant to fetch data and publish results
Includes web dashboard for visualization
Uses external BatteryOptimizer class for clean separation of concerns
"""

import requests
import json
from datetime import datetime, timedelta
import statistics
from collections import defaultdict
import time
import threading
from flask import Flask, render_template
from battery_optimiser import BatteryConfig, SolarAwareOptimizer, MILPOptimizer
import os

# Import inverter schedule generator if available
try:
    from inverter_schedule_generator import generate_inverter_schedule, print_inverter_schedule
    INVERTER_SCHEDULE_AVAILABLE = True
except ImportError:
    INVERTER_SCHEDULE_AVAILABLE = False
    print("⚠️  inverter_schedule_generator.py not found - inverter schedules disabled")

# ============================================================================
# CONFIGURATION - EDIT THESE
# ============================================================================

# Home Assistant Connection
HA_URL = "http://homeassistant.local:8123"  # Or use IP: http://192.168.1.x:8123
HA_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI0NDMxMzdhYTUzYzY0YzUxOWJiY2FlZGVkNDQ3MDE2OCIsImlhdCI6MTc2NDQ1MjkzNCwiZXhwIjoyMDc5ODEyOTM0fQ.ULn71oeb1956rnk-N15o1DRMmscQx1b_hXpS9RiIlqk"

# Energy Sensor
ENTITY_ID = "sensor.solis8_house_load"
PREDICTION_SLOTS = 48  # 24 hours in 30-min slots

# Octopus Energy
OCTOPUS_IMPORT_RATE_ENTITY = "event.octopus_energy_electricity_20l3324094_1411093291008_current_day_rates"
OCTOPUS_EXPORT_RATE_ENTITY = "event.octopus_energy_electricity_20l3324094_1470001909841_export_current_day_rates"

# Solcast
SOLCAST_FORECAST_ENTITY = "sensor.solcast_pv_forecast_forecast_today"
ENABLE_SOLAR = True  # Enable solar forecasting

# Battery Configuration
BATTERY_CONFIG = BatteryConfig(
    capacity_kwh=32.0,
    min_soc=0.1,
    reserve_soc=0.2,
    max_charge_rate_kw=8.0,              # Battery max charge rate
    max_discharge_rate_kw=8.0,           # Battery max discharge rate
    max_export_power_kw=5.0,             # Max export to grid
    max_pv_power_kw=13.0,                # Max PV MPPT output
    charge_efficiency=0.95,
    discharge_efficiency=0.95,
    degradation_cost_per_cycle=0.05
)

BATTERY_SOC_ENTITY = "sensor.battery_soc"

# Optimizer Configuration
USE_MILP_OPTIMIZER = True  # Use MILP for optimal solution (slower but better)

# Heuristic optimizer config (fast but suboptimal)
HEURISTIC_CONFIG = {
    'cheap_import_threshold': 0.10,
    'expensive_import_threshold': 0.25,
    'export_threshold': 0.12,
    'look_ahead_hours': 6
}

# MILP optimizer config (optimal solution)
MILP_CONFIG = {
    'target_end_soc': 0.90,         # Target 90% SOC at end of solar period
    'solar_end_hour': 20,            # 8pm - when solar period ends
    'min_export_rate': 0.10,         # Only export if rate > 10p/kWh
    'time_limit_seconds': 30         # Max solver time
}

# How often to run optimization (seconds)
UPDATE_INTERVAL = 3600  # 1 hour

# ============================================================================
# WEB DASHBOARD
# ============================================================================

web_app = Flask(__name__)

# Global variable to store latest results
latest_results = {
    'schedule': [],
    'metadata': {},
    'last_update': None
}

# Web app setup
web_app = Flask(__name__, template_folder=os.path.dirname(os.path.abspath(__file__)) or '.')

@web_app.route('/')
def dashboard():
    """Display the optimization schedule"""
    if not latest_results['schedule']:
        return "<h1 style='color: #00ff00; text-align: center; font-family: monospace;'>No data yet - waiting for first optimization cycle...</h1>"
    
    # Prepare data for template
    schedule_display = []
    total_cost = 0
    prev_soc = None
    
    for i, slot in enumerate(latest_results['schedule']):
        total_cost += slot.get('slot_cost_p', 0) / 100  # Convert pence to pounds
        
        # Calculate SOC change
        soc_change = 0
        if prev_soc is not None:
            soc_change = int(slot['soc_percent'] - prev_soc)
        prev_soc = slot['soc_percent']
        
        # Determine cost trend
        cost_trend = 'same'
        if i > 0:
            prev_total = sum(s.get('slot_cost_p', 0) / 100 for s in latest_results['schedule'][:i])
            if total_cost < prev_total:
                cost_trend = 'down'
            elif total_cost > prev_total:
                cost_trend = 'up'
        
        # Format time
        try:
            dt = datetime.fromisoformat(slot['timestamp'])
            time_str = dt.strftime('%a %H:%M')
        except:
            time_str = f"Slot {i}"
        
        schedule_display.append({
            'time': time_str,
            'import_rate': slot.get('import_rate_p', 15),
            'export_rate': slot.get('export_rate_p', 4),
            'action': slot.get('action', 'hold'),
            'power': slot.get('power_kw', 0),
            'grid_import': slot.get('grid_import_kw', 0),
            'grid_export': slot.get('grid_export_kw', 0),
            'solar': slot.get('solar_kw', 0),
            'demand': slot.get('demand_kw', 0),
            'soc_percent': int(slot.get('soc_percent', 50)),
            'soc_change': soc_change,
            'cost': slot.get('slot_cost_p', 0) / 100,
            'total_cost': total_cost,
            'cost_trend': cost_trend,
            'is_current': i == 0
        })
    
    return render_template(
        'dashboard.html',
        schedule=schedule_display,
        last_update=latest_results['last_update'] or 'Never',
        optimizer_name=latest_results['metadata'].get('optimizer', 'Unknown'),
        stats=latest_results['metadata'].get('stats')
    )

def start_web_server(port=5000):
    """Start the Flask web server in a background thread"""
    web_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_ha_headers():
    """Get headers for HA API calls"""
    return {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json"
    }

def get_entity_state(entity_id):
    """Get state of an entity"""
    try:
        url = f"{HA_URL}/api/states/{entity_id}"
        response = requests.get(url, headers=get_ha_headers(), timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Error fetching {entity_id}: {e}")
    return None

def set_entity_state(entity_id, state, attributes=None):
    """Set state of an entity"""
    try:
        url = f"{HA_URL}/api/states/{entity_id}"
        payload = {'state': state}
        if attributes:
            payload['attributes'] = attributes
        response = requests.post(url, json=payload, headers=get_ha_headers(), timeout=10)
        return response.status_code in [200, 201]
    except Exception as e:
        print(f"Error setting {entity_id}: {e}")
    return False

# ============================================================================
# DATA COLLECTION
# ============================================================================

def fetch_historical_data(days=7):
    """Fetch historical demand data"""
    print(f"📊 Fetching {days} days of historical data...")
    
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)
    
    url = f"{HA_URL}/api/history/period/{start_time.isoformat()}"
    params = {
        "filter_entity_id": ENTITY_ID,
        "end_time": end_time.isoformat()
    }
    
    response = requests.get(url, params=params, headers=get_ha_headers(), timeout=30)
    
    if response.status_code != 200:
        raise Exception(f"Error fetching data: {response.status_code}")
    
    data = response.json()
    
    if not data or not data[0]:
        raise Exception("No data returned")
    
    processed = []
    for item in data[0]:
        if item['state'] not in ['unavailable', 'unknown', 'None']:
            try:
                timestamp = datetime.fromisoformat(item['last_changed'].replace('Z', '+00:00'))
                timestamp = timestamp.replace(tzinfo=None)
                value = float(item['state'])
                
                # Convert Watts to kW if value is large
                if value > 100:
                    value = value / 1000
                
                processed.append({
                    'timestamp': timestamp,
                    'value': value,
                    'hour': timestamp.hour
                })
            except:
                continue
    
    print(f"  ✓ Got {len(processed)} data points")
    return processed

def generate_demand_forecast(data):
    """Simple statistical demand forecast"""
    print("🔮 Generating demand forecast...")
    
    # Calculate hourly averages
    hourly_stats = defaultdict(list)
    for point in data:
        hourly_stats[point['hour']].append(point['value'])
    
    hourly_avg = {h: statistics.mean(v) for h, v in hourly_stats.items()}
    overall_avg = statistics.mean([p['value'] for p in data])
    
    # Generate predictions for PREDICTION_SLOTS
    now = datetime.now()
    if now.minute < 30:
        start_time = now.replace(minute=30, second=0, microsecond=0)
    else:
        start_time = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    
    predictions = []
    for slot in range(PREDICTION_SLOTS):
        future_time = start_time + timedelta(minutes=slot * 30)
        predicted_value = hourly_avg.get(future_time.hour, overall_avg)
        
        predictions.append({
            'slot': slot,
            'timestamp': future_time.isoformat(),
            'predicted_kw': round(predicted_value, 2)
        })
    
    print(f"  ✓ Generated {len(predictions)} demand predictions")
    return predictions

def fetch_solar_forecast():
    """Fetch Solcast solar forecast"""
    if not ENABLE_SOLAR or not SOLCAST_FORECAST_ENTITY:
        print("☀️  Solar forecasting disabled")
        return [{'slot': i, 'timestamp': '', 'predicted_solar_kw': 0} for i in range(PREDICTION_SLOTS)]
    
    print("☀️  Fetching Solcast solar forecast...")
    
    forecasts = []
    for day in ['today', 'tomorrow', 'day_3']:
        entity_id = SOLCAST_FORECAST_ENTITY.replace('today', day)
        entity_data = get_entity_state(entity_id)
        
        if entity_data:
            detailed = entity_data.get('attributes', {}).get('detailedForecast', [])
            if not detailed:
                detailed = entity_data.get('attributes', {}).get('forecasts', [])
            
            for item in detailed:
                timestamp = item.get('period_end') or item.get('period_start') or item.get('timestamp')
                pv_value = item.get('pv_estimate') or item.get('pv_estimate50') or item.get('value', 0)
                
                if timestamp:
                    forecasts.append({
                        'timestamp': timestamp,
                        'pv_estimate': pv_value
                    })
    
    # Convert to PREDICTION_SLOTS
    now = datetime.now()
    if now.minute < 30:
        start_time = now.replace(minute=30, second=0, microsecond=0)
    else:
        start_time = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    
    solar_predictions = []
    for slot in range(PREDICTION_SLOTS):
        slot_time = start_time + timedelta(minutes=slot * 30)
        
        # Find matching forecast
        pv_kw = 0
        for fc in forecasts:
            try:
                fc_time = datetime.fromisoformat(fc['timestamp'].replace('Z', '+00:00'))
                fc_time = fc_time.replace(tzinfo=None)
                if abs((fc_time - slot_time).total_seconds()) < 1800:
                    pv_kw = fc['pv_estimate']
                    break
            except:
                continue
        
        solar_predictions.append({
            'slot': slot,
            'timestamp': slot_time.isoformat(),
            'predicted_solar_kw': round(pv_kw, 3)
        })
    
    total_solar = sum(s['predicted_solar_kw'] * 0.5 for s in solar_predictions)
    print(f"  ✓ Solar forecast: {total_solar:.1f} kWh over {PREDICTION_SLOTS//2}h")
    return solar_predictions

def fetch_octopus_rates():
    """Fetch Octopus Energy rates"""
    print("⚡ Fetching Octopus Energy rates...")
    
    if not OCTOPUS_IMPORT_RATE_ENTITY:
        print("  ⚠ Using default rates (15p import, 4p export)")
        return [0.15] * PREDICTION_SLOTS, [0.04] * PREDICTION_SLOTS
    
    # Get current time and round to next 30-min slot
    now = datetime.now()
    if now.minute < 30:
        start_time = now.replace(minute=30, second=0, microsecond=0)
    else:
        start_time = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    
    # Fetch both current_day and next_day rates for import
    import_rate_lookup = {}
    
    # Fetch current day rates
    current_day_entity = OCTOPUS_IMPORT_RATE_ENTITY
    entity_data = get_entity_state(current_day_entity)
    if entity_data:
        rates_data = entity_data.get('attributes', {}).get('rates', [])
        for rate in rates_data:
            try:
                rate_start = datetime.fromisoformat(rate['start'].replace('Z', '+00:00')).replace(tzinfo=None)
                import_rate_lookup[rate_start] = rate['value_inc_vat']
            except:
                continue
        print(f"  ✓ Loaded {len(rates_data)} current day import rates")
    
    # Fetch next day rates
    next_day_entity = current_day_entity.replace('current_day_rates', 'next_day_rates')
    entity_data = get_entity_state(next_day_entity)
    if entity_data:
        rates_data = entity_data.get('attributes', {}).get('rates', [])
        for rate in rates_data:
            try:
                rate_start = datetime.fromisoformat(rate['start'].replace('Z', '+00:00')).replace(tzinfo=None)
                import_rate_lookup[rate_start] = rate['value_inc_vat']
            except:
                continue
        print(f"  ✓ Loaded {len(rates_data)} next day import rates")
    
    # Fetch export rates (current and next day)
    export_rate_lookup = {}
    
    if OCTOPUS_EXPORT_RATE_ENTITY:
        # Current day export
        entity_data = get_entity_state(OCTOPUS_EXPORT_RATE_ENTITY)
        if entity_data:
            rates_data = entity_data.get('attributes', {}).get('rates', [])
            for rate in rates_data:
                try:
                    rate_start = datetime.fromisoformat(rate['start'].replace('Z', '+00:00')).replace(tzinfo=None)
                    export_rate_lookup[rate_start] = rate['value_inc_vat']
                except:
                    continue
            print(f"  ✓ Loaded {len(rates_data)} current day export rates")
        
        # Next day export
        next_day_export = OCTOPUS_EXPORT_RATE_ENTITY.replace('current_day_rates', 'next_day_rates')
        entity_data = get_entity_state(next_day_export)
        if entity_data:
            rates_data = entity_data.get('attributes', {}).get('rates', [])
            for rate in rates_data:
                try:
                    rate_start = datetime.fromisoformat(rate['start'].replace('Z', '+00:00')).replace(tzinfo=None)
                    export_rate_lookup[rate_start] = rate['value_inc_vat']
                except:
                    continue
            print(f"  ✓ Loaded {len(rates_data)} next day export rates")
    
    # Match rates to our slots
    import_rates = []
    export_rates = []
    
    for slot in range(PREDICTION_SLOTS):
        slot_time = start_time + timedelta(minutes=slot * 30)
        
        # Find import rate
        if slot_time in import_rate_lookup:
            import_rates.append(import_rate_lookup[slot_time])
        else:
            # Find closest rate within 30 minutes
            closest_rate = 0.15
            min_diff = float('inf')
            for rate_time, rate_value in import_rate_lookup.items():
                diff = abs((rate_time - slot_time).total_seconds())
                if diff < min_diff and diff < 1800:
                    min_diff = diff
                    closest_rate = rate_value
            import_rates.append(closest_rate)
        
        # Find export rate
        if slot_time in export_rate_lookup:
            export_rates.append(export_rate_lookup[slot_time])
        else:
            closest_rate = 0.04
            min_diff = float('inf')
            for rate_time, rate_value in export_rate_lookup.items():
                diff = abs((rate_time - slot_time).total_seconds())
                if diff < min_diff and diff < 1800:
                    min_diff = diff
                    closest_rate = rate_value
            export_rates.append(closest_rate)
    
    # Ensure exactly correct number of slots
    while len(import_rates) < PREDICTION_SLOTS:
        import_rates.append(0.15)
    while len(export_rates) < PREDICTION_SLOTS:
        export_rates.append(0.04)
    
    import_rates = import_rates[:PREDICTION_SLOTS]
    export_rates = export_rates[:PREDICTION_SLOTS]
    
    print(f"  ✓ Import rates: {min(import_rates):.2f} - {max(import_rates):.2f} £/kWh")
    print(f"  ✓ Export rates: {min(export_rates):.2f} - {max(export_rates):.2f} £/kWh")
    
    return import_rates, export_rates

def get_current_battery_soc():
    """Get current battery SOC"""
    if not BATTERY_SOC_ENTITY:
        return BATTERY_CONFIG.capacity_kwh * 0.5
    
    entity_data = get_entity_state(BATTERY_SOC_ENTITY)
    if entity_data:
        try:
            soc_percent = float(entity_data['state'])
            return (soc_percent / 100) * BATTERY_CONFIG.capacity_kwh
        except:
            pass
    
    return BATTERY_CONFIG.capacity_kwh * 0.5

# ============================================================================
# PUBLISH TO HOME ASSISTANT
# ============================================================================

def publish_results(demand, solar, result):
    """Publish results to HA sensors"""
    print("📤 Publishing results to Home Assistant...")
    
    schedule = result['schedule']
    metadata = result['metadata']
    
    # Demand predictor sensor
    set_entity_state(
        'sensor.energy_demand_predictor',
        demand[0]['predicted_kw'],
        {
            'predictions': demand,
            'unit_of_measurement': 'kW',
            'friendly_name': 'Energy Demand Predictor'
        }
    )
    
    # Solar predictor sensor
    if ENABLE_SOLAR:
        total_solar = sum(s['predicted_solar_kw'] * 0.5 for s in solar)
        set_entity_state(
            'sensor.solar_predictor',
            solar[0]['predicted_solar_kw'],
            {
                'predictions': solar,
                'total_forecast_kwh': round(total_solar, 2),
                'unit_of_measurement': 'kW',
                'friendly_name': 'Solar Predictor'
            }
        )
    
    # Battery optimizer sensor
    next_action = schedule[0]
    action_changes = []
    for i in range(1, min(24, len(schedule))):
        if schedule[i]['action'] != schedule[i-1]['action']:
            action_changes.append({
                'time': schedule[i]['timestamp'],
                'action': schedule[i]['action'],
                'power_kw': schedule[i]['power_kw']
            })
    
    set_entity_state(
        'sensor.battery_optimizer',
        next_action['action'],
        {
            'current_action': next_action['action'],
            'target_power_kw': next_action['power_kw'],
            'current_soc_percent': next_action['soc_percent'],
            'next_action_changes': action_changes[:5],
            'schedule': schedule,
            'optimizer': metadata.get('optimizer'),
            'total_cost_pounds': metadata.get('total_cost_pounds'),
            'stats': metadata.get('stats'),
            'friendly_name': 'Battery Optimizer'
        }
    )
    
    print("  ✓ Published to Home Assistant sensors")

# ============================================================================
# MAIN LOOP
# ============================================================================

def run_optimization():
    """Run one optimization cycle"""
    global latest_results
    
    try:
        print("\n" + "="*70)
        print("🔋 BATTERY OPTIMIZATION CYCLE")
        print("="*70)
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Fetch all data
        historical_data = fetch_historical_data(days=7)
        demand_forecast = generate_demand_forecast(historical_data)
        solar_forecast = fetch_solar_forecast()
        import_rates, export_rates = fetch_octopus_rates()
        current_soc = get_current_battery_soc()
        
        print(f"🔋 Current battery SOC: {current_soc:.1f} kWh ({current_soc/BATTERY_CONFIG.capacity_kwh*100:.1f}%)")
        
        # Create optimizer instance
        if USE_MILP_OPTIMIZER:
            optimizer = MILPOptimizer(BATTERY_CONFIG, **MILP_CONFIG)
        else:
            optimizer = SolarAwareOptimizer(BATTERY_CONFIG, **HEURISTIC_CONFIG)
        
        # Run optimization
        print(f"🎯 Running {optimizer.__class__.__name__}...")
        result = optimizer.optimize(
            demand_forecast=demand_forecast,
            solar_forecast=solar_forecast,
            import_rates=import_rates,
            export_rates=export_rates,
            current_soc_kwh=current_soc
        )
        
        battery_schedule = result['schedule']
        metadata = result['metadata']
        
        # Print statistics
        print("\n📊 Optimization Statistics:")
        stats = metadata.get('stats', {})
        print(f"  Total Cost (48h): £{stats.get('total_cost', 0):.2f}")
        print(f"  Grid Charging: {stats.get('charge_from_grid_slots', 0)} slots")
        print(f"  Solar Charging: {stats.get('charge_from_solar_slots', 0)} slots")
        print(f"  Home Discharge: {stats.get('discharge_to_home_slots', 0)} slots")
        print(f"  Grid Export: {stats.get('discharge_to_grid_slots', 0)} slots")
        print(f"  Hold: {stats.get('hold_slots', 0)} slots")
        
        # Publish
        publish_results(demand_forecast, solar_forecast, result)
        
        # Generate inverter schedule (if available)
        if INVERTER_SCHEDULE_AVAILABLE:
            try:
                inverter_schedule = generate_inverter_schedule(result, BATTERY_CONFIG)
                print_inverter_schedule(inverter_schedule)
                
                # Save inverter schedule to file
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                with open(f'inverter_schedule_{timestamp}.json', 'w') as f:
                    json.dump(inverter_schedule, f, indent=2)
                print(f"\n💾 Saved inverter schedule to inverter_schedule_{timestamp}.json")
            except Exception as e:
                print(f"\n⚠️  Could not generate inverter schedule: {e}")
        
        # Find next action changes for summary
        action_changes = []
        for i in range(1, min(24, len(battery_schedule))):
            if battery_schedule[i]['action'] != battery_schedule[i-1]['action']:
                action_changes.append({
                    'time': battery_schedule[i]['timestamp'],
                    'action': battery_schedule[i]['action']
                })
        
        # Summary
        print("\n" + "="*70)
        print("✅ OPTIMIZATION COMPLETE")
        print(f"   Next action: {battery_schedule[0]['action'].upper()}")
        print(f"   Power: {battery_schedule[0]['power_kw']:.1f} kW")
        print(f"   Next change: {action_changes[0]['time'] if action_changes else 'No changes planned'}")
        print("="*70 + "\n")
        
        # Save to file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        with open(f'optimization_{timestamp}.json', 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'demand': demand_forecast,
                'solar': solar_forecast,
                'result': result
            }, f, indent=2)
        print(f"💾 Saved results to optimization_{timestamp}.json")
        
        # Update global results for web dashboard
        latest_results = {
            'schedule': battery_schedule,
            'metadata': metadata,
            'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main entry point"""
    print("="*70)
    print("🔋 STANDALONE BATTERY OPTIMIZER WITH WEB DASHBOARD")
    print("="*70)
    print(f"Home Assistant: {HA_URL}")
    print(f"Entity: {ENTITY_ID}")
    print(f"Battery: {BATTERY_CONFIG.capacity_kwh} kWh")
    print(f"Solar: {'Enabled' if ENABLE_SOLAR else 'Disabled'}")
    print(f"Optimizer: {'MILPOptimizer (Optimal)' if USE_MILP_OPTIMIZER else 'SolarAwareOptimizer (Heuristic)'}")
    print(f"Web Dashboard: http://localhost:5000")
    print(f"Update interval: {UPDATE_INTERVAL}s ({UPDATE_INTERVAL//60} minutes)")
    print("="*70)
    
    # Test connection
    print("\n🔍 Testing connection to Home Assistant...")
    try:
        test = get_entity_state(ENTITY_ID)
        if test:
            print(f"  ✓ Connected! Current value: {test['state']}")
        else:
            print("  ❌ Could not fetch entity - check HA_TOKEN and ENTITY_ID")
            return
    except Exception as e:
        print(f"  ❌ Connection failed: {e}")
        print("\nCheck:")
        print("1. HA_URL is correct")
        print("2. HA_TOKEN is valid (create in HA Profile)")
        print("3. Home Assistant is accessible")
        return
    
    # Start web server in background
    print("\n🌐 Starting web dashboard...")
    web_thread = threading.Thread(target=start_web_server, args=(5000,), daemon=True)
    web_thread.start()
    print("  ✓ Dashboard running at http://localhost:5000")
    
    # Run optimization loop
    print("\n▶️  Starting optimization loop (Ctrl+C to stop)...\n")
    
    while True:
        try:
            run_optimization()
            print(f"⏰ Next run in {UPDATE_INTERVAL//60} minutes...")
            time.sleep(UPDATE_INTERVAL)
        except KeyboardInterrupt:
            print("\n\n👋 Stopped by user")
            break
        except Exception as e:
            print(f"\n❌ Error in main loop: {e}")
            print(f"⏰ Retrying in 60 seconds...")
            time.sleep(60)

if __name__ == "__main__":
    main()