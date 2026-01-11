"""
Test Data Generator for SolarBat-AI

Provides realistic mock data for testing different scenarios:
- Daily load patterns (typical house consumption)
- Solar generation profiles (sunny, cloudy, winter days)
- Various system configurations
"""

from datetime import datetime, timedelta
from typing import Dict, List
import math


class TestDataGenerator:
    """Generates realistic test data for optimization testing"""
    
    @staticmethod
    def generate_daily_load_pattern(base_load_kw: float = 0.3,
                                   peak_morning: float = 1.5,
                                   peak_evening: float = 2.0,
                                   start_time: datetime = None) -> List[Dict]:
        """
        Generate realistic daily load pattern.
        
        Typical UK household pattern:
        - 00:00-06:00: Low base load (0.3-0.5kW) - sleeping
        - 06:00-09:00: Morning peak (1.5-2.0kW) - breakfast, showers
        - 09:00-16:00: Moderate (0.5-1.0kW) - daytime usage
        - 16:00-23:00: Evening peak (1.5-3.0kW) - cooking, TV, etc.
        
        Args:
            base_load_kw: Minimum load during night
            peak_morning: Peak load in morning
            peak_evening: Peak load in evening
            start_time: Start time (default: now at midnight)
        """
        if start_time is None:
            start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        load_pattern = []
        
        for slot in range(48):  # 48 x 30-min slots = 24 hours
            time = start_time + timedelta(minutes=30 * slot)
            hour = time.hour + (time.minute / 60.0)
            
            # Calculate load based on time of day
            if 0 <= hour < 6:
                # Night: low base load
                load_kw = base_load_kw + 0.1 * math.sin(hour * math.pi / 6)
                
            elif 6 <= hour < 9:
                # Morning peak: rising from base to peak
                progress = (hour - 6) / 3.0
                load_kw = base_load_kw + progress * peak_morning
                
            elif 9 <= hour < 16:
                # Daytime: moderate with variations
                load_kw = 0.5 + 0.3 * math.sin((hour - 9) * math.pi / 7)
                
            elif 16 <= hour < 22:
                # Evening peak: highest usage
                progress = (hour - 16) / 6.0
                peak_now = peak_evening * math.sin(progress * math.pi)
                load_kw = base_load_kw + peak_now
                
            else:  # 22:00-24:00
                # Late evening: declining to base
                progress = (hour - 22) / 2.0
                load_kw = peak_evening * (1 - progress) + base_load_kw * progress
            
            # Add some random variation (±10%)
            import random
            load_kw *= (0.9 + random.random() * 0.2)
            
            load_pattern.append({
                'time': time,
                'load_kw': round(load_kw, 3),
                'confidence': 'high'
            })
        
        return load_pattern
    
    @staticmethod
    def generate_solar_profile(peak_kw: float = 17.0,
                               profile_type: str = 'sunny_summer',
                               start_time: datetime = None) -> List[Dict]:
        """
        Generate solar generation profile.
        
        Profile types:
        - sunny_summer: Full generation, 17kWp array
        - sunny_winter: Lower angle, 12kWp peak
        - cloudy: Variable, 5-8kWp peak
        - partial_cloud: 10-13kWp with dips
        
        For 17kWp array on sunny day:
        - Peak ~13-14kW (75-80% of rated)
        - Total generation: 60-80kWh/day
        
        Args:
            peak_kw: Peak generation (kW)
            profile_type: Type of solar day
            start_time: Start time
        """
        if start_time is None:
            start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        solar_pattern = []
        
        # Profile-specific parameters
        profiles = {
            'sunny_summer': {
                'peak_factor': 0.8,      # 80% of rated (13.6kW from 17kWp)
                'sunrise': 5.0,          # 05:00
                'sunset': 21.0,          # 21:00
                'variability': 0.02      # 2% variation
            },
            'sunny_winter': {
                'peak_factor': 0.6,      # 60% (lower sun angle)
                'sunrise': 8.0,          # 08:00
                'sunset': 16.0,          # 16:00
                'variability': 0.05
            },
            'cloudy': {
                'peak_factor': 0.35,     # 35% (heavy clouds)
                'sunrise': 6.0,
                'sunset': 20.0,
                'variability': 0.3       # 30% variation (clouds)
            },
            'partial_cloud': {
                'peak_factor': 0.65,     # 65% (some clouds)
                'sunrise': 6.0,
                'sunset': 20.0,
                'variability': 0.15      # 15% variation
            }
        }
        
        params = profiles.get(profile_type, profiles['sunny_summer'])
        actual_peak = peak_kw * params['peak_factor']
        
        for slot in range(48):
            time = start_time + timedelta(minutes=30 * slot)
            hour = time.hour + (time.minute / 60.0)
            
            # Solar generation follows bell curve between sunrise and sunset
            if params['sunrise'] <= hour <= params['sunset']:
                # Position in the day (0 to 1)
                day_length = params['sunset'] - params['sunrise']
                position = (hour - params['sunrise']) / day_length
                
                # Bell curve (peaks at solar noon)
                solar_kw = actual_peak * math.sin(position * math.pi)
                
                # Add variability (cloud variations)
                import random
                variation = 1.0 + (random.random() - 0.5) * 2 * params['variability']
                solar_kw *= variation
                
                # Can't be negative or exceed rated
                solar_kw = max(0, min(solar_kw, peak_kw))
            else:
                solar_kw = 0.0
            
            solar_pattern.append({
                'time': time,
                'kw': round(solar_kw, 3)
            })
        
        return solar_pattern
    
    @staticmethod
    def generate_test_scenario(scenario: str = 'high_solar_day') -> Dict:
        """
        Generate complete test scenario with all data.
        
        Scenarios:
        - high_solar_day: 17kWp sunny day, typical load, test clipping prevention
        - winter_day: Low solar, high evening load
        - cloudy_day: Variable solar, moderate load
        - low_battery_start: Start at 20% SOC, test charging strategy
        """
        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        scenarios = {
            'high_solar_day': {
                'description': '17kWp array, sunny summer day - tests Feed-in Priority strategy',
                'battery_soc': 70.0,
                'battery_capacity': 10.0,
                'solar_profile': 'sunny_summer',
                'solar_peak': 17.0,
                'load_base': 0.3,
                'load_morning': 1.5,
                'load_evening': 2.5,
                'expected_behavior': 'Should use Feed-in Priority mode 06:00-14:00 to prevent clipping'
            },
            'winter_day': {
                'description': 'Low solar, high heating load',
                'battery_soc': 85.0,
                'battery_capacity': 10.0,
                'solar_profile': 'sunny_winter',
                'solar_peak': 17.0,
                'load_base': 0.5,
                'load_morning': 2.0,
                'load_evening': 3.5,
                'expected_behavior': 'Battery should discharge during expensive evening peak'
            },
            'cloudy_day': {
                'description': 'Variable solar, moderate load',
                'battery_soc': 60.0,
                'battery_capacity': 10.0,
                'solar_profile': 'cloudy',
                'solar_peak': 17.0,
                'load_base': 0.4,
                'load_morning': 1.5,
                'load_evening': 2.0,
                'expected_behavior': 'Opportunistic charging during cheap periods'
            },
            'low_battery_start': {
                'description': 'Start day at 20% SOC',
                'battery_soc': 20.0,
                'battery_capacity': 10.0,
                'solar_profile': 'sunny_summer',
                'solar_peak': 17.0,
                'load_base': 0.3,
                'load_morning': 1.5,
                'load_evening': 2.0,
                'expected_behavior': 'Should charge early if cheap prices available'
            }
        }
        
        config = scenarios.get(scenario, scenarios['high_solar_day'])
        
        # Generate patterns
        load_pattern = TestDataGenerator.generate_daily_load_pattern(
            base_load_kw=config['load_base'],
            peak_morning=config['load_morning'],
            peak_evening=config['load_evening'],
            start_time=now
        )
        
        solar_pattern = TestDataGenerator.generate_solar_profile(
            peak_kw=config['solar_peak'],
            profile_type=config['solar_profile'],
            start_time=now
        )
        
        # Calculate totals
        total_solar = sum(s['kw'] * 0.5 for s in solar_pattern)
        total_load = sum(l['load_kw'] * 0.5 for l in load_pattern)
        net_surplus = total_solar - total_load
        
        return {
            'scenario': scenario,
            'description': config['description'],
            'expected_behavior': config['expected_behavior'],
            'battery_soc': config['battery_soc'],
            'battery_capacity': config['battery_capacity'],
            'max_charge_rate': 3.0,
            'max_discharge_rate': 3.0,
            'load_forecast': load_pattern,
            'solar_forecast': solar_pattern,
            'totals': {
                'solar_kwh': round(total_solar, 1),
                'load_kwh': round(total_load, 1),
                'net_surplus_kwh': round(net_surplus, 1)
            }
        }
    
    @staticmethod
    def print_scenario_summary(scenario_data: Dict):
        """Print a summary of the test scenario"""
        print("\n" + "="*60)
        print(f"TEST SCENARIO: {scenario_data['scenario'].upper()}")
        print("="*60)
        print(f"Description: {scenario_data['description']}")
        print(f"Expected: {scenario_data['expected_behavior']}")
        print(f"\nStarting Conditions:")
        print(f"  Battery SOC: {scenario_data['battery_soc']}%")
        print(f"  Battery Capacity: {scenario_data['battery_capacity']}kWh")
        print(f"\nDaily Totals:")
        print(f"  Solar Generation: {scenario_data['totals']['solar_kwh']}kWh")
        print(f"  House Load: {scenario_data['totals']['load_kwh']}kWh")
        print(f"  Net Surplus: {scenario_data['totals']['net_surplus_kwh']}kWh")
        print("="*60 + "\n")
