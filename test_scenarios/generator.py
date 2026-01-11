"""
Test Scenario Generator

Creates JSON test scenarios covering various conditions:
- Typical days (sunny, cloudy, winter)
- Edge cases (negative pricing, battery full, no solar)
- Stress tests (extreme conditions)

Usage:
    python generator.py --generate-all
    python generator.py --generate-typical
    python generator.py --generate-edge-cases
"""

import json
import os
from datetime import datetime
from typing import Dict, List
import math


class ScenarioGenerator:
    """Generates test scenarios in JSON format"""
    
    def __init__(self, output_dir: str = "./scenarios"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    @staticmethod
    def generate_solar_profile(peak_kw: float, sunrise: float, sunset: float, 
                               efficiency: float = 0.8, variability: float = 0.02) -> Dict:
        """Generate parametric solar profile"""
        day_length = sunset - sunrise
        total_kwh = peak_kw * efficiency * day_length * 0.637  # Bell curve integral approximation
        
        return {
            "type": "parametric_bell_curve",
            "peak_kw": peak_kw,
            "sunrise_hour": sunrise,
            "sunset_hour": sunset,
            "efficiency": efficiency,
            "variability": variability,
            "total_kwh": round(total_kwh, 1),
            "description": f"Bell curve, {day_length}h daylight, {efficiency*100:.0f}% efficiency"
        }
    
    @staticmethod
    def generate_load_profile(base_kw: float, morning_peak: float, 
                              evening_peak: float) -> Dict:
        """Generate parametric load profile"""
        # Rough estimation: 24h * base + peaks
        total_kwh = base_kw * 24 + (morning_peak * 3) + (evening_peak * 6)
        
        return {
            "type": "parametric_daily",
            "base_kw": base_kw,
            "morning_peak_kw": morning_peak,
            "evening_peak_kw": evening_peak,
            "total_kwh": round(total_kwh, 1),
            "description": f"Base {base_kw}kW, peaks {morning_peak}/{evening_peak}kW"
        }
    
    @staticmethod
    def generate_pricing_profile(overnight: float, day: float, 
                                 peak: float, export: float = 15.0) -> Dict:
        """Generate typical Agile pricing profile"""
        avg = (overnight * 7 + day * 11 + peak * 6) / 24
        
        return {
            "type": "agile_typical",
            "overnight_avg_p": overnight,
            "day_avg_p": day,
            "peak_avg_p": peak,
            "export_fixed_p": export,
            "daily_avg_p": round(avg, 2),
            "description": f"Overnight {overnight}p, day {day}p, peak {peak}p"
        }
    
    def save_scenario(self, scenario: Dict, category: str):
        """Save scenario to JSON file"""
        filepath = os.path.join(self.output_dir, category, f"{scenario['name']}.json")
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'w') as f:
            json.dump(scenario, f, indent=2)
        
        print(f"✓ Generated: {category}/{scenario['name']}.json")
    
    def generate_typical_scenarios(self):
        """Generate typical day scenarios"""
        print("\n" + "="*60)
        print("Generating TYPICAL scenarios...")
        print("="*60)
        
        scenarios = [
            # 1. Sunny summer day
            {
                "name": "sunny_summer_day",
                "description": "17kWp array, perfect sunny summer day, typical load",
                "date": "2026-07-15",
                "battery": {
                    "soc_start": 70.0,
                    "capacity_kwh": 10.0,
                    "max_charge_kw": 3.0,
                    "max_discharge_kw": 3.0
                },
                "solar_profile": self.generate_solar_profile(17.0, 5.0, 21.0, 0.8),
                "load_profile": self.generate_load_profile(0.3, 1.5, 2.5),
                "pricing": self.generate_pricing_profile(12.0, 18.0, 28.0, 15.0),
                "expected_outcomes": {
                    "feed_in_priority_hours": ">6",
                    "total_cost_max": 2.50,
                    "clipping_kwh": 0.0,
                    "notes": "Should use Feed-in Priority mode to prevent clipping"
                }
            },
            
            # 2. Cloudy summer day
            {
                "name": "cloudy_summer_day",
                "description": "17kWp array, cloudy day, reduced solar",
                "date": "2026-07-16",
                "battery": {
                    "soc_start": 65.0,
                    "capacity_kwh": 10.0,
                    "max_charge_kw": 3.0,
                    "max_discharge_kw": 3.0
                },
                "solar_profile": self.generate_solar_profile(17.0, 5.0, 21.0, 0.35, 0.3),
                "load_profile": self.generate_load_profile(0.3, 1.5, 2.5),
                "pricing": self.generate_pricing_profile(12.0, 18.0, 28.0, 15.0),
                "expected_outcomes": {
                    "feed_in_priority_hours": 0,
                    "total_cost_max": 3.50,
                    "notes": "No Feed-in Priority needed, opportunistic charging"
                }
            },
            
            # 3. Winter sunny day
            {
                "name": "winter_sunny_day",
                "description": "17kWp array, winter sun, short daylight",
                "date": "2026-01-15",
                "battery": {
                    "soc_start": 80.0,
                    "capacity_kwh": 10.0,
                    "max_charge_kw": 3.0,
                    "max_discharge_kw": 3.0
                },
                "solar_profile": self.generate_solar_profile(17.0, 8.0, 16.0, 0.6),
                "load_profile": self.generate_load_profile(0.5, 2.0, 3.5),
                "pricing": self.generate_pricing_profile(12.0, 18.0, 30.0, 15.0),
                "expected_outcomes": {
                    "feed_in_priority_hours": 0,
                    "discharge_during_peak": True,
                    "notes": "Should discharge during expensive evening peak"
                }
            },
            
            # 4. Spring moderate day
            {
                "name": "spring_moderate_day",
                "description": "17kWp array, spring conditions, balanced",
                "date": "2026-04-15",
                "battery": {
                    "soc_start": 60.0,
                    "capacity_kwh": 10.0,
                    "max_charge_kw": 3.0,
                    "max_discharge_kw": 3.0
                },
                "solar_profile": self.generate_solar_profile(17.0, 6.0, 19.0, 0.7),
                "load_profile": self.generate_load_profile(0.4, 1.5, 2.0),
                "pricing": self.generate_pricing_profile(12.0, 17.0, 26.0, 15.0),
                "expected_outcomes": {
                    "total_cost_max": 2.00,
                    "notes": "Balanced day, self-use with some arbitrage"
                }
            },
            
            # 5. Autumn partial cloud
            {
                "name": "autumn_partial_cloud",
                "description": "17kWp array, variable clouds, moderate load",
                "date": "2026-10-15",
                "battery": {
                    "soc_start": 55.0,
                    "capacity_kwh": 10.0,
                    "max_charge_kw": 3.0,
                    "max_discharge_kw": 3.0
                },
                "solar_profile": self.generate_solar_profile(17.0, 7.0, 18.0, 0.65, 0.15),
                "load_profile": self.generate_load_profile(0.35, 1.5, 2.2),
                "pricing": self.generate_pricing_profile(11.0, 17.0, 27.0, 15.0),
                "expected_outcomes": {
                    "total_cost_max": 2.20,
                    "notes": "Variable generation, smart self-use"
                }
            }
        ]
        
        for scenario in scenarios:
            self.save_scenario(scenario, "typical")
    
    def generate_edge_case_scenarios(self):
        """Generate edge case scenarios"""
        print("\n" + "="*60)
        print("Generating EDGE CASE scenarios...")
        print("="*60)
        
        scenarios = [
            # 1. Negative pricing
            {
                "name": "negative_pricing_overnight",
                "description": "Negative overnight prices, should charge and get paid!",
                "date": "2026-08-20",
                "battery": {
                    "soc_start": 30.0,
                    "capacity_kwh": 10.0,
                    "max_charge_kw": 3.0,
                    "max_discharge_kw": 3.0
                },
                "solar_profile": self.generate_solar_profile(17.0, 5.0, 21.0, 0.75),
                "load_profile": self.generate_load_profile(0.3, 1.5, 2.5),
                "pricing": {
                    "type": "agile_negative",
                    "overnight_avg_p": -5.0,  # NEGATIVE!
                    "day_avg_p": 18.0,
                    "peak_avg_p": 28.0,
                    "export_fixed_p": 15.0,
                    "description": "Negative overnight pricing (wind surplus)"
                },
                "expected_outcomes": {
                    "charge_at_negative": True,
                    "total_cost_max": -0.50,  # Should EARN money!
                    "notes": "Should charge aggressively during negative prices"
                }
            },
            
            # 2. Battery full at dawn
            {
                "name": "battery_full_at_dawn",
                "description": "Battery 95% at dawn, huge solar coming",
                "date": "2026-07-21",
                "battery": {
                    "soc_start": 95.0,  # Nearly full!
                    "capacity_kwh": 10.0,
                    "max_charge_kw": 3.0,
                    "max_discharge_kw": 3.0
                },
                "solar_profile": self.generate_solar_profile(17.0, 5.0, 21.0, 0.82),
                "load_profile": self.generate_load_profile(0.25, 1.2, 2.0),
                "pricing": self.generate_pricing_profile(12.0, 18.0, 28.0, 15.0),
                "expected_outcomes": {
                    "feed_in_priority_hours": ">8",
                    "clipping_kwh": 0.0,
                    "notes": "CRITICAL: Must use Feed-in Priority from dawn"
                }
            },
            
            # 3. No solar (night testing)
            {
                "name": "zero_solar_day",
                "description": "Complete solar system failure, pure arbitrage",
                "date": "2026-05-10",
                "battery": {
                    "soc_start": 50.0,
                    "capacity_kwh": 10.0,
                    "max_charge_kw": 3.0,
                    "max_discharge_kw": 3.0
                },
                "solar_profile": {
                    "type": "zero",
                    "peak_kw": 0.0,
                    "total_kwh": 0.0,
                    "description": "No solar generation (fault or testing)"
                },
                "load_profile": self.generate_load_profile(0.3, 1.5, 2.5),
                "pricing": self.generate_pricing_profile(10.0, 20.0, 35.0, 15.0),
                "expected_outcomes": {
                    "arbitrage_only": True,
                    "charge_overnight": True,
                    "discharge_evening": True,
                    "notes": "Pure arbitrage test: buy cheap, sell expensive"
                }
            },
            
            # 4. Low battery emergency
            {
                "name": "low_battery_emergency",
                "description": "Start at 15% SOC, expensive prices ahead",
                "date": "2026-11-05",
                "battery": {
                    "soc_start": 15.0,  # Very low!
                    "capacity_kwh": 10.0,
                    "max_charge_kw": 3.0,
                    "max_discharge_kw": 3.0
                },
                "solar_profile": self.generate_solar_profile(17.0, 7.0, 17.0, 0.5),
                "load_profile": self.generate_load_profile(0.4, 1.8, 3.0),
                "pricing": self.generate_pricing_profile(15.0, 25.0, 40.0, 15.0),
                "expected_outcomes": {
                    "charge_immediately": True,
                    "avoid_deficit": True,
                    "notes": "Should charge early despite prices to avoid deficit"
                }
            },
            
            # 5. Extreme arbitrage opportunity
            {
                "name": "extreme_arbitrage",
                "description": "Huge price spread, 10p overnight vs 45p peak",
                "date": "2026-12-15",
                "battery": {
                    "soc_start": 40.0,
                    "capacity_kwh": 10.0,
                    "max_charge_kw": 3.0,
                    "max_discharge_kw": 3.0
                },
                "solar_profile": self.generate_solar_profile(17.0, 8.0, 16.0, 0.55),
                "load_profile": self.generate_load_profile(0.5, 2.0, 3.5),
                "pricing": {
                    "type": "agile_extreme",
                    "overnight_avg_p": 8.0,
                    "day_avg_p": 22.0,
                    "peak_avg_p": 45.0,  # EXTREME!
                    "export_fixed_p": 15.0,
                    "description": "Extreme arbitrage opportunity"
                },
                "expected_outcomes": {
                    "arbitrage_profit": ">£3.00",
                    "charge_overnight": True,
                    "discharge_peak": True,
                    "notes": "Should maximize arbitrage: 37p spread!"
                }
            }
        ]
        
        for scenario in scenarios:
            self.save_scenario(scenario, "edge_cases")
    
    def generate_stress_test_scenarios(self):
        """Generate stress test scenarios"""
        print("\n" + "="*60)
        print("Generating STRESS TEST scenarios...")
        print("="*60)
        
        scenarios = [
            # 1. Volatile pricing
            {
                "name": "volatile_pricing",
                "description": "Prices swinging wildly every 30 minutes",
                "date": "2026-09-10",
                "battery": {
                    "soc_start": 60.0,
                    "capacity_kwh": 10.0,
                    "max_charge_kw": 3.0,
                    "max_discharge_kw": 3.0
                },
                "solar_profile": self.generate_solar_profile(17.0, 6.0, 20.0, 0.75),
                "load_profile": self.generate_load_profile(0.3, 1.5, 2.5),
                "pricing": {
                    "type": "agile_volatile",
                    "volatility": "extreme",
                    "range_p": [5.0, 50.0],
                    "export_fixed_p": 15.0,
                    "description": "Extremely volatile pricing"
                },
                "expected_outcomes": {
                    "handle_volatility": True,
                    "no_thrashing": True,
                    "notes": "Should handle rapid price changes gracefully"
                }
            },
            
            # 2. Maximum solar (perfect conditions)
            {
                "name": "maximum_solar_generation",
                "description": "17kWp reaching 95% efficiency, extreme clipping risk",
                "date": "2026-06-21",  # Summer solstice
                "battery": {
                    "soc_start": 90.0,
                    "capacity_kwh": 10.0,
                    "max_charge_kw": 3.0,
                    "max_discharge_kw": 3.0
                },
                "solar_profile": self.generate_solar_profile(17.0, 4.5, 21.5, 0.95),
                "load_profile": self.generate_load_profile(0.2, 1.0, 1.8),
                "pricing": self.generate_pricing_profile(12.0, 18.0, 28.0, 15.0),
                "expected_outcomes": {
                    "feed_in_priority_hours": ">10",
                    "clipping_kwh": 0.0,
                    "export_maximized": True,
                    "notes": "Extreme test: 90% start + max solar"
                }
            },
            
            # 3. Minimum battery capacity
            {
                "name": "tiny_battery",
                "description": "Only 3kWh battery, limited capacity",
                "date": "2026-07-15",
                "battery": {
                    "soc_start": 70.0,
                    "capacity_kwh": 3.0,  # Tiny!
                    "max_charge_kw": 1.5,
                    "max_discharge_kw": 1.5
                },
                "solar_profile": self.generate_solar_profile(17.0, 5.0, 21.0, 0.8),
                "load_profile": self.generate_load_profile(0.3, 1.5, 2.5),
                "pricing": self.generate_pricing_profile(12.0, 18.0, 28.0, 15.0),
                "expected_outcomes": {
                    "feed_in_priority_hours": ">8",
                    "work_with_limits": True,
                    "notes": "Must work with tiny battery capacity"
                }
            }
        ]
        
        for scenario in scenarios:
            self.save_scenario(scenario, "stress_tests")
    
    def generate_all(self):
        """Generate all scenarios"""
        print("\n" + "="*60)
        print("Test Scenario Generator")
        print("="*60)
        print(f"Output directory: {self.output_dir}")
        
        self.generate_typical_scenarios()
        self.generate_edge_case_scenarios()
        self.generate_stress_test_scenarios()
        
        print("\n" + "="*60)
        print("✓ All scenarios generated!")
        print("="*60)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate test scenarios')
    parser.add_argument('--output-dir', default='./scenarios', 
                       help='Output directory for scenarios')
    parser.add_argument('--generate-all', action='store_true',
                       help='Generate all scenarios')
    parser.add_argument('--generate-typical', action='store_true',
                       help='Generate typical scenarios only')
    parser.add_argument('--generate-edge-cases', action='store_true',
                       help='Generate edge case scenarios only')
    parser.add_argument('--generate-stress-tests', action='store_true',
                       help='Generate stress test scenarios only')
    
    args = parser.parse_args()
    
    generator = ScenarioGenerator(args.output_dir)
    
    if args.generate_all or not any([args.generate_typical, args.generate_edge_cases, 
                                     args.generate_stress_tests]):
        generator.generate_all()
    else:
        if args.generate_typical:
            generator.generate_typical_scenarios()
        if args.generate_edge_cases:
            generator.generate_edge_case_scenarios()
        if args.generate_stress_tests:
            generator.generate_stress_test_scenarios()


if __name__ == '__main__':
    main()
