"""
Test Runner for Mock Data Scenarios

Standalone script to test SolarBat-AI optimization with realistic mock data.
No Home Assistant required!

Usage:
    python test_with_mock_data.py [scenario]
    
Scenarios:
    high_solar_day     - 17kWp sunny day (default)
    winter_day         - Low solar, high load
    cloudy_day         - Variable solar
    low_battery_start  - Start at 20% SOC
"""

import sys
import os
from datetime import datetime, timedelta

# Add parent directory and apps to path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, 'apps', 'solar_optimizer'))

from test_data import TestDataGenerator
from apps.solar_optimizer.plan_creator import PlanCreator


def create_mock_pricing(hours: int = 24) -> list:
    """
    Generate mock Octopus Agile pricing (typical pattern).
    
    Low overnight (00:00-07:00): 10-15p
    High morning (07:00-09:00): 20-25p
    Moderate day (09:00-16:00): 15-20p
    Peak evening (16:00-19:00): 25-35p
    Moderate evening (19:00-00:00): 15-20p
    """
    import random
    
    prices = []
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    for slot in range(hours * 2):  # 30-min slots
        time = now + timedelta(minutes=30 * slot)
        hour = time.hour
        
        # Time-of-use pattern
        if 0 <= hour < 7:
            # Overnight cheap
            base = 12.0
            variation = 3.0
        elif 7 <= hour < 9:
            # Morning peak
            base = 22.0
            variation = 3.0
        elif 9 <= hour < 16:
            # Daytime moderate
            base = 17.0
            variation = 2.0
        elif 16 <= hour < 19:
            # Evening peak (most expensive!)
            base = 30.0
            variation = 5.0
        else:
            # Late evening moderate
            base = 18.0
            variation = 2.0
        
        price = base + (random.random() - 0.5) * variation
        
        prices.append({
            'time': time,
            'price': round(price, 2),
            'is_predicted': False
        })
    
    return prices


def run_test_scenario(scenario_name: str = 'high_solar_day'):
    """Run optimization test with mock data"""
    
    print("\n" + "="*70)
    print("  SolarBat-AI v2.3 - Mock Data Test Runner")
    print("="*70)
    
    # Generate test scenario
    print(f"\n📊 Loading scenario: {scenario_name}")
    scenario = TestDataGenerator.generate_test_scenario(scenario_name)
    TestDataGenerator.print_scenario_summary(scenario)
    
    # Generate pricing
    print("💷 Generating mock Octopus Agile pricing...")
    import_prices = create_mock_pricing(hours=24)
    export_prices = [{'time': p['time'], 'price': 15.0} for p in import_prices]  # Fixed export
    
    # Show pricing summary
    price_values = [p['price'] for p in import_prices]
    print(f"   Price range: {min(price_values):.2f}p - {max(price_values):.2f}p")
    print(f"   Average: {sum(price_values)/len(price_values):.2f}p")
    
    # Build system state
    system_state = {
        'current_state': {
            'battery_soc': scenario['battery_soc'],
            'battery_power': 0.0,
            'pv_power': 0.0,
            'current_mode': 'Self-Use'
        },
        'capabilities': {
            'battery_capacity': scenario['battery_capacity'],
            'max_charge_rate': scenario['max_charge_rate'],
            'max_discharge_rate': scenario['max_discharge_rate']
        },
        'active_slots': {
            'charge': [],
            'discharge': []
        },
        'mode_switch': {
            'entity': 'select.solis_inverter_energy_storage_control_switch',
            'current_mode': 'Self-Use - No Timed Charge/Discharge'
        }
    }
    
    # Create plan
    print("\n🧠 Running PlanCreator optimization...")
    plan_creator = PlanCreator()
    
    plan = plan_creator.create_plan(
        import_prices=import_prices,
        export_prices=export_prices,
        solar_forecast=scenario['solar_forecast'],
        load_forecast=scenario['load_forecast'],
        system_state=system_state
    )
    
    # Analyze results
    print("\n" + "="*70)
    print("  OPTIMIZATION RESULTS")
    print("="*70)
    
    slots = plan['slots']
    
    # Count modes
    mode_counts = {}
    feed_in_slots = []
    charge_slots = []
    discharge_slots = []
    
    for slot in slots:
        mode = slot['mode']
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
        
        if mode == 'Feed-in Priority':
            feed_in_slots.append(slot['time'].strftime('%H:%M'))
        elif mode == 'Force Charge':
            charge_slots.append(slot['time'].strftime('%H:%M'))
        elif mode == 'Force Discharge':
            discharge_slots.append(slot['time'].strftime('%H:%M'))
    
    print(f"\n📊 Mode Distribution:")
    for mode, count in sorted(mode_counts.items()):
        hours = count * 0.5
        print(f"   {mode}: {count} slots ({hours:.1f} hours)")
    
    if feed_in_slots:
        print(f"\n⚡ Feed-in Priority Mode:")
        print(f"   Window: {feed_in_slots[0]} - {feed_in_slots[-1]}")
        print(f"   Duration: {len(feed_in_slots) * 0.5:.1f} hours")
        print(f"   Strategy: Grid-first solar routing")
    
    if charge_slots:
        print(f"\n🔌 Force Charge Slots:")
        for slot_time in charge_slots[:5]:  # Show first 5
            print(f"   {slot_time}")
        if len(charge_slots) > 5:
            print(f"   ... and {len(charge_slots)-5} more")
    
    if discharge_slots:
        print(f"\n⚡ Force Discharge Slots:")
        for slot_time in discharge_slots[:5]:
            print(f"   {slot_time}")
        if len(discharge_slots) > 5:
            print(f"   ... and {len(discharge_slots)-5} more")
    
    # Show cost
    total_cost = plan['metadata'].get('total_cost', 0)
    print(f"\n💰 Estimated 24h Cost: £{total_cost:.2f}")
    
    # Battery trajectory
    print(f"\n🔋 Battery Trajectory:")
    start_soc = slots[0]['soc_start']
    end_soc = slots[-1]['soc_end']
    print(f"   Start: {start_soc:.1f}%")
    print(f"   End: {end_soc:.1f}%")
    print(f"   Change: {end_soc - start_soc:+.1f}%")
    
    # Validation against expected behavior
    print(f"\n✅ Expected Behavior:")
    print(f"   {scenario['expected_behavior']}")
    
    if scenario_name == 'high_solar_day' and feed_in_slots:
        print(f"\n   ✓ PASS: Feed-in Priority mode activated for clipping prevention!")
    elif scenario_name == 'high_solar_day' and not feed_in_slots:
        print(f"\n   ✗ FAIL: Feed-in Priority mode NOT activated - check logic!")
    
    print("\n" + "="*70)
    
    return plan


def main():
    """Main entry point"""
    
    # Get scenario from command line or use default
    scenario = sys.argv[1] if len(sys.argv) > 1 else 'high_solar_day'
    
    available_scenarios = [
        'high_solar_day',
        'winter_day',
        'cloudy_day',
        'low_battery_start'
    ]
    
    if scenario not in available_scenarios:
        print(f"\n❌ Unknown scenario: {scenario}")
        print(f"\n Available scenarios:")
        for s in available_scenarios:
            print(f"   - {s}")
        sys.exit(1)
    
    try:
        plan = run_test_scenario(scenario)
        
        print(f"\n💡 Tip: You can test different scenarios:")
        print(f"   python test_with_mock_data.py high_solar_day")
        print(f"   python test_with_mock_data.py winter_day")
        print(f"   python test_with_mock_data.py cloudy_day")
        print(f"   python test_with_mock_data.py low_battery_start")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted")
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
