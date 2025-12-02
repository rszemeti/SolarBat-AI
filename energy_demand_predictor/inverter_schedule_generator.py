"""
Inverter Schedule Generator
Converts MILP optimization results into inverter charge/discharge schedules
with target SOC percentages
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any


def generate_inverter_schedule(optimization_result: Dict[str, Any], config) -> Dict[str, Any]:
    """
    Convert optimization schedule into inverter-compatible commands
    
    Returns:
    {
        'mode': 'self_use' or 'grid_first',
        'charge_periods': [
            {'start': '02:00', 'end': '04:00', 'target_soc': 100, 'power_limit': 8.0},
            ...
        ],
        'discharge_periods': [
            {'start': '16:00', 'end': '18:00', 'target_soc': 20, 'power_limit': 5.0},
            ...
        ],
        'default_mode': 'self_use'
    }
    """
    
    schedule = optimization_result['schedule']
    
    # Analyze the schedule to identify charge/discharge periods
    charge_periods = []
    discharge_periods = []
    
    current_period = None
    
    for i, slot in enumerate(schedule):
        action = slot['action']
        timestamp = datetime.fromisoformat(slot['timestamp'])
        time_str = timestamp.strftime('%H:%M')
        soc_target = slot['soc_percent']
        
        # Detect period changes
        if action == 'charge' and (current_period is None or current_period['type'] != 'charge'):
            # Start new charge period
            if current_period:
                _finalize_period(current_period, charge_periods, discharge_periods)
            
            current_period = {
                'type': 'charge',
                'start': time_str,
                'start_slot': i,
                'max_soc': soc_target,
                'power': slot['power_kw']
            }
        
        elif action in ['discharge', 'export'] and (current_period is None or current_period['type'] != 'discharge'):
            # Start new discharge period
            if current_period:
                _finalize_period(current_period, charge_periods, discharge_periods)
            
            current_period = {
                'type': 'discharge',
                'start': time_str,
                'start_slot': i,
                'min_soc': soc_target,
                'power': slot['power_kw']
            }
        
        elif action == 'hold' and current_period:
            # End current period
            _finalize_period(current_period, charge_periods, discharge_periods)
            current_period = None
        
        # Update period max/min SOC
        if current_period:
            if current_period['type'] == 'charge':
                current_period['max_soc'] = max(current_period['max_soc'], soc_target)
                current_period['end'] = time_str
                current_period['end_slot'] = i
            else:
                current_period['min_soc'] = min(current_period['min_soc'], soc_target)
                current_period['end'] = time_str
                current_period['end_slot'] = i
    
    # Finalize last period
    if current_period:
        _finalize_period(current_period, charge_periods, discharge_periods)
    
    # Determine default mode based on overall strategy
    # If more discharge than charge, prefer grid-first
    # Otherwise prefer self-use
    total_discharge_slots = sum(1 for s in schedule if s['action'] in ['discharge', 'export'])
    total_charge_slots = sum(1 for s in schedule if s['action'] == 'charge')
    
    default_mode = 'grid_first' if total_discharge_slots > total_charge_slots else 'self_use'
    
    # Check for solar curtailment - if high, switch to grid-first during solar hours
    total_curtailed = sum(s.get('solar_curtailment_kw', 0) for s in schedule)
    if total_curtailed > 5.0:  # More than 5 kWh curtailed
        print(f"⚠️  High solar curtailment detected ({total_curtailed:.1f} kWh)")
        print("   Recommendation: Use 'grid_first' mode during solar hours to export excess")
    
    return {
        'charge_periods': charge_periods,
        'discharge_periods': discharge_periods,
        'default_mode': default_mode,
        'total_curtailed_kwh': sum(s.get('solar_curtailment_kw', 0) * 0.5 for s in schedule),
        'summary': {
            'charge_slots': total_charge_slots,
            'discharge_slots': total_discharge_slots,
            'hold_slots': len(schedule) - total_charge_slots - total_discharge_slots
        }
    }


def _finalize_period(period, charge_list, discharge_list):
    """Add completed period to appropriate list"""
    if period['type'] == 'charge':
        charge_list.append({
            'start': period['start'],
            'end': period['end'],
            'target_soc': int(period['max_soc']),
            'power_limit': round(period['power'], 1),
            'duration_slots': period['end_slot'] - period['start_slot'] + 1
        })
    else:
        discharge_list.append({
            'start': period['start'],
            'end': period['end'],
            'target_soc': int(period['min_soc']),
            'power_limit': round(period['power'], 1),
            'duration_slots': period['end_slot'] - period['start_slot'] + 1
        })


def print_inverter_schedule(schedule: Dict[str, Any]):
    """Print human-readable inverter schedule"""
    
    print("\n" + "="*70)
    print("⚙️  INVERTER SCHEDULE")
    print("="*70)
    
    print(f"\n📋 Default Mode: {schedule['default_mode'].upper()}")
    
    if schedule['charge_periods']:
        print(f"\n🔋 CHARGE PERIODS ({len(schedule['charge_periods'])} total):")
        for i, period in enumerate(schedule['charge_periods'], 1):
            duration_hours = period['duration_slots'] * 0.5
            print(f"   {i}. {period['start']} → {period['end']} ({duration_hours:.1f}h)")
            print(f"      Target SOC: {period['target_soc']}%")
            print(f"      Power Limit: {period['power_limit']} kW")
    else:
        print("\n🔋 CHARGE PERIODS: None")
    
    if schedule['discharge_periods']:
        print(f"\n⚡ DISCHARGE PERIODS ({len(schedule['discharge_periods'])} total):")
        for i, period in enumerate(schedule['discharge_periods'], 1):
            duration_hours = period['duration_slots'] * 0.5
            print(f"   {i}. {period['start']} → {period['end']} ({duration_hours:.1f}h)")
            print(f"      Target SOC: {period['target_soc']}%")
            print(f"      Power Limit: {period['power_limit']} kW")
    else:
        print("\n⚡ DISCHARGE PERIODS: None")
    
    if schedule.get('total_curtailed_kwh', 0) > 1.0:
        print(f"\n⚠️  Solar Curtailment: {schedule['total_curtailed_kwh']:.1f} kWh")
        print("   → Consider 'grid_first' mode during solar peak hours")
    
    print("\n" + "="*70)


def export_to_home_assistant_automation(schedule: Dict[str, Any]) -> str:
    """
    Generate Home Assistant automation YAML
    """
    
    yaml_lines = [
        "# Generated Inverter Schedule",
        "# Add this to your automations.yaml",
        "",
        "# Set default mode",
        "- alias: 'Battery - Set Default Mode'",
        "  trigger:",
        "    - platform: time",
        "      at: '00:00:00'",
        "  action:",
        "    - service: select.select_option",
        "      target:",
        "        entity_id: select.battery_mode",
        f"      data:",
        f"        option: '{schedule['default_mode']}'",
        ""
    ]
    
    # Add charge period automations
    for i, period in enumerate(schedule.get('charge_periods', []), 1):
        yaml_lines.extend([
            f"# Charge Period {i}",
            f"- alias: 'Battery - Charge {period['start']}-{period['end']}'",
            "  trigger:",
            "    - platform: time",
            f"      at: '{period['start']}:00'",
            "  action:",
            "    - service: number.set_value",
            "      target:",
            "        entity_id: number.battery_charge_target_soc",
            "      data:",
            f"        value: {period['target_soc']}",
            "    - service: number.set_value",
            "      target:",
            "        entity_id: number.battery_charge_power",
            "      data:",
            f"        value: {period['power_limit']}",
            "    - service: switch.turn_on",
            "      target:",
            "        entity_id: switch.battery_charge_enable",
            ""
        ])
    
    # Add discharge period automations
    for i, period in enumerate(schedule.get('discharge_periods', []), 1):
        yaml_lines.extend([
            f"# Discharge Period {i}",
            f"- alias: 'Battery - Discharge {period['start']}-{period['end']}'",
            "  trigger:",
            "    - platform: time",
            f"      at: '{period['start']}:00'",
            "  action:",
            "    - service: number.set_value",
            "      target:",
            "        entity_id: number.battery_discharge_target_soc",
            "      data:",
            f"        value: {period['target_soc']}",
            "    - service: number.set_value",
            "      target:",
            "        entity_id: number.battery_discharge_power",
            "      data:",
            f"        value: {period['power_limit']}",
            "    - service: switch.turn_on",
            "      target:",
            "        entity_id: switch.battery_discharge_enable",
            ""
        ])
    
    return "\n".join(yaml_lines)


# Example usage:
if __name__ == "__main__":
    # Test with dummy data
    dummy_result = {
        'schedule': [
            {'timestamp': '2025-11-30T02:00:00', 'action': 'charge', 'soc_percent': 50, 'power_kw': 8.0},
            {'timestamp': '2025-11-30T02:30:00', 'action': 'charge', 'soc_percent': 65, 'power_kw': 8.0},
            {'timestamp': '2025-11-30T03:00:00', 'action': 'charge', 'soc_percent': 80, 'power_kw': 8.0},
            {'timestamp': '2025-11-30T03:30:00', 'action': 'charge', 'soc_percent': 95, 'power_kw': 8.0},
            {'timestamp': '2025-11-30T04:00:00', 'action': 'hold', 'soc_percent': 95, 'power_kw': 0},
            # ... more slots
            {'timestamp': '2025-11-30T16:00:00', 'action': 'discharge', 'soc_percent': 90, 'power_kw': 5.0},
            {'timestamp': '2025-11-30T16:30:00', 'action': 'discharge', 'soc_percent': 75, 'power_kw': 5.0},
            {'timestamp': '2025-11-30T17:00:00', 'action': 'discharge', 'soc_percent': 60, 'power_kw': 5.0},
            {'timestamp': '2025-11-30T17:30:00', 'action': 'hold', 'soc_percent': 60, 'power_kw': 0},
        ]
    }
    
    inverter_schedule = generate_inverter_schedule(dummy_result, None)
    print_inverter_schedule(inverter_schedule)
    
    print("\n" + "="*70)
    print("HOME ASSISTANT AUTOMATION YAML:")
    print("="*70)
    print(export_to_home_assistant_automation(inverter_schedule))