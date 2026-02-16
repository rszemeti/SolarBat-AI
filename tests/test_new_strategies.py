#!/usr/bin/env python3
"""
Test the new backwards simulation strategies:
1. Feed-in Priority with backwards simulation
2. Pre-sunrise discharge strategy
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add apps directory to path
apps_path = Path(__file__).parent.parent / 'apps' / 'solar_optimizer'
sys.path.insert(0, str(apps_path))
sys.path.insert(0, str(apps_path / 'planners'))

# Import modules directly to avoid package issues
import importlib.util

# Load base_planner
spec = importlib.util.spec_from_file_location("base_planner", apps_path / "planners" / "base_planner.py")
base_planner = importlib.util.module_from_spec(spec)
sys.modules['base_planner'] = base_planner
spec.loader.exec_module(base_planner)

# Load rule_based_planner
spec = importlib.util.spec_from_file_location("rule_based_planner", apps_path / "planners" / "rule_based_planner.py")
rule_based_planner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rule_based_planner)

RuleBasedPlanner = rule_based_planner.RuleBasedPlanner


def create_massive_solar_day():
    """Create a scenario with massive solar that needs pre-sunrise discharge"""
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Simulate midnight to next midnight
    import_prices = []
    export_prices = []
    solar_forecast = []
    load_forecast = []
    
    for hour in range(24):
        for minute in [0, 30]:
            time = now + timedelta(hours=hour, minutes=minute)
            
            # Cheap night, expensive day prices
            if 2 <= hour < 5:
                price = 5.0  # Very cheap
            elif 16 <= hour < 19:
                price = 35.0  # Peak
            else:
                price = 20.0  # Normal
            
            # MASSIVE solar day: 50kWh total!
            if 6 <= hour < 18:
                # Bell curve peaking at noon
                hour_from_noon = abs(hour - 12)
                solar_kw = 15.0 * (1 - hour_from_noon / 6.0) ** 2
            else:
                solar_kw = 0.0
            
            # Normal load pattern
            if 7 <= hour < 9 or 18 <= hour < 22:
                load_kw = 1.5  # Peak usage
            elif 0 <= hour < 6:
                load_kw = 0.5  # Night
            else:
                load_kw = 0.8  # Day
            
            import_prices.append({'time': time, 'price': price, 'is_predicted': False})
            export_prices.append({'time': time, 'price': 15.0})
            solar_forecast.append({'time': time, 'kw': solar_kw})
            load_forecast.append({'time': time, 'load_kw': load_kw, 'confidence': 'high'})
    
    return import_prices, export_prices, solar_forecast, load_forecast


def create_high_solar_day():
    """Create a scenario needing Feed-in Priority but not pre-sunrise discharge"""
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    import_prices = []
    export_prices = []
    solar_forecast = []
    load_forecast = []
    
    for hour in range(24):
        for minute in [0, 30]:
            time = now + timedelta(hours=hour, minutes=minute)
            
            if 2 <= hour < 5:
                price = 5.0
            elif 16 <= hour < 19:
                price = 35.0
            else:
                price = 20.0
            
            # High solar: 35kWh total
            if 6 <= hour < 18:
                hour_from_noon = abs(hour - 12)
                solar_kw = 10.0 * (1 - hour_from_noon / 6.0) ** 2
            else:
                solar_kw = 0.0
            
            if 7 <= hour < 9 or 18 <= hour < 22:
                load_kw = 1.5
            elif 0 <= hour < 6:
                load_kw = 0.5
            else:
                load_kw = 0.8
            
            import_prices.append({'time': time, 'price': price, 'is_predicted': False})
            export_prices.append({'time': time, 'price': 15.0})
            solar_forecast.append({'time': time, 'kw': solar_kw})
            load_forecast.append({'time': time, 'load_kw': load_kw, 'confidence': 'high'})
    
    return import_prices, export_prices, solar_forecast, load_forecast


def create_normal_day():
    """Create a normal day needing neither strategy"""
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    import_prices = []
    export_prices = []
    solar_forecast = []
    load_forecast = []
    
    for hour in range(24):
        for minute in [0, 30]:
            time = now + timedelta(hours=hour, minutes=minute)
            
            if 2 <= hour < 5:
                price = 5.0
            elif 16 <= hour < 19:
                price = 35.0
            else:
                price = 20.0
            
            # Normal solar: 20kWh total
            if 6 <= hour < 18:
                hour_from_noon = abs(hour - 12)
                solar_kw = 6.0 * (1 - hour_from_noon / 6.0) ** 2
            else:
                solar_kw = 0.0
            
            if 7 <= hour < 9 or 18 <= hour < 22:
                load_kw = 1.5
            elif 0 <= hour < 6:
                load_kw = 0.5
            else:
                load_kw = 0.8
            
            import_prices.append({'time': time, 'price': price, 'is_predicted': False})
            export_prices.append({'time': time, 'price': 15.0})
            solar_forecast.append({'time': time, 'kw': solar_kw})
            load_forecast.append({'time': time, 'load_kw': load_kw, 'confidence': 'high'})
    
    return import_prices, export_prices, solar_forecast, load_forecast


def test_scenario(name, import_prices, export_prices, solar_forecast, load_forecast, starting_soc=45.0):
    """Test a scenario"""
    print(f"\n{'='*70}")
    print(f"  {name}")
    print(f"{'='*70}")
    
    # Calculate total solar
    total_solar = sum(s['kw'] * 0.5 for s in solar_forecast)
    total_load = sum(l['load_kw'] * 0.5 for l in load_forecast)
    print(f"Total Solar: {total_solar:.1f}kWh")
    print(f"Total Load: {total_load:.1f}kWh")
    print(f"Net Surplus: {total_solar - total_load:.1f}kWh")
    print(f"Starting SOC: {starting_soc}%")
    print()
    
    # Create system state
    system_state = {
        'battery_soc': starting_soc,
        'battery_capacity': 32.0,
        'max_charge_rate': 2.08,
        'max_discharge_rate': 3.12,
        'min_soc': 15.0,
        'max_soc': 95.0,
        'export_limit': 5.0
    }
    
    # Create planner and plan
    planner = RuleBasedPlanner()
    
    print("Running planner...")
    plan = planner.create_plan(
        import_prices=import_prices,
        export_prices=export_prices,
        solar_forecast=solar_forecast,
        load_forecast=load_forecast,
        system_state=system_state
    )
    
    print(f"\n✅ Plan created!")
    print(f"   Charge slots: {plan['charge_count']}")
    print(f"   Discharge slots: {plan['discharge_count']}")
    print(f"   Estimated cost: £{plan['total_cost']:.2f}")
    
    # Show key actions
    print(f"\n📋 Key Actions:")
    discharge_slots = [s for s in plan['slots'] if s['mode'] == 'Force Discharge']
    feedin_slots = [s for s in plan['slots'] if s['mode'] == 'Feed-in Priority']
    
    if discharge_slots:
        print(f"   🌙 Pre-sunrise discharge: {len(discharge_slots)} slots")
        print(f"      {discharge_slots[0]['time'].strftime('%H:%M')} - {discharge_slots[-1]['time'].strftime('%H:%M')}")
    
    if feedin_slots:
        print(f"   ☀️ Feed-in Priority: {len(feedin_slots)} slots")
        print(f"      {feedin_slots[0]['time'].strftime('%H:%M')} - {feedin_slots[-1]['time'].strftime('%H:%M')}")
    
    # Show SOC trajectory
    print(f"\n📊 SOC Trajectory:")
    key_times = [0, 6, 12, 18, 23]  # Midnight, 6am, noon, 6pm, 11pm
    for hour in key_times:
        slot_idx = hour * 2
        if slot_idx < len(plan['slots']):
            slot = plan['slots'][slot_idx]
            print(f"   {slot['time'].strftime('%H:%M')}: {slot['soc']:.0f}% ({slot['mode']})")
    
    return plan


if __name__ == '__main__':
    print("\n" + "="*70)
    print("  TESTING NEW BACKWARDS SIMULATION STRATEGIES")
    print("="*70)
    
    # Test 1: Normal day (no special strategies needed)
    import_prices, export_prices, solar_forecast, load_forecast = create_normal_day()
    test_scenario(
        "TEST 1: Normal Day (20kWh solar)",
        import_prices, export_prices, solar_forecast, load_forecast,
        starting_soc=45.0
    )
    
    # Test 2: High solar day (needs Feed-in Priority)
    import_prices, export_prices, solar_forecast, load_forecast = create_high_solar_day()
    test_scenario(
        "TEST 2: High Solar Day (35kWh solar)",
        import_prices, export_prices, solar_forecast, load_forecast,
        starting_soc=45.0
    )
    
    # Test 3: Massive solar day (needs pre-sunrise discharge)
    import_prices, export_prices, solar_forecast, load_forecast = create_massive_solar_day()
    test_scenario(
        "TEST 3: Massive Solar Day (50kWh solar) - Starting at 80% SOC",
        import_prices, export_prices, solar_forecast, load_forecast,
        starting_soc=80.0
    )
    
    print("\n" + "="*70)
    print("  TESTS COMPLETE!")
    print("="*70)
