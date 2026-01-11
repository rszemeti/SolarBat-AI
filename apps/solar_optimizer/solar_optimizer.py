"""
Solar Battery Optimizer for Home Assistant
Intelligent battery management for solar + storage with Octopus Agile pricing

Version: 2.0.0
Author: Built with Claude AI
License: MIT
"""

import hassapi as hass
from datetime import datetime, timedelta
import json
import statistics


class SmartSolarOptimizer(hass.Hass):
    """Main optimizer class for solar battery management"""
    
    def initialize(self):
        """Initialize the optimizer"""
        self.log("=" * 80)
        self.log("Solar Battery Optimizer v2.0 - Initializing...")
        self.log("=" * 80)
        
        # Basic configuration
        self.battery_soc_sensor = self.args.get("battery_soc", "sensor.battery_soc")
        self.battery_capacity_sensor = self.args.get("battery_capacity", "sensor.battery_capacity")
        self.inverter_mode_select = self.args.get("inverter_mode", "select.solax_charger_use_mode")
        
        # Inverter mode names (configurable for different inverters)
        self.mode_self_use = self.args.get("mode_self_use", "Self Use")
        self.mode_grid_first = self.args.get("mode_grid_first", "Grid First")
        self.mode_force_charge = self.args.get("mode_force_charge", "Force Charge")
        self.mode_force_discharge = self.args.get("mode_force_discharge", None)  # May not be supported
        
        # Inverter capability sensors (read actual limits from inverter)
        self.max_charge_rate_sensor = self.args.get("max_charge_rate", "sensor.solax_battery_charge_max_current")
        self.max_discharge_rate_sensor = self.args.get("max_discharge_rate", "sensor.solax_battery_discharge_max_current")
        self.inverter_max_power_sensor = self.args.get("inverter_max_power", "sensor.solax_inverter_power")
        self.battery_voltage_sensor = self.args.get("battery_voltage", "sensor.solax_battery_voltage")
        
        # Grid/export sensors
        self.grid_export_limit_sensor = self.args.get("grid_export_limit", "sensor.solax_export_control_user_limit")
        self.current_export_power_sensor = self.args.get("current_export_power", "sensor.solax_measured_power")
        
        # Real-time power sensors
        self.pv_power_sensor = self.args.get("pv_power", "sensor.solax_pv_power")
        self.battery_power_sensor = self.args.get("battery_power", "sensor.solax_battery_power")
        self.load_power_sensor = self.args.get("load_power", "sensor.solax_house_load")
        self.grid_power_sensor = self.args.get("grid_power", "sensor.solax_measured_power")
        
        # Solar forecasting
        self.solcast_remaining = self.args.get("solcast_remaining", "sensor.solcast_pv_forecast_forecast_remaining_today")
        self.solcast_tomorrow = self.args.get("solcast_tomorrow", "sensor.solcast_pv_forecast_forecast_tomorrow")
        self.solcast_forecast_today = self.args.get("solcast_forecast_today", "sensor.solcast_pv_forecast_forecast_today")
        
        # Agile pricing
        self.agile_current_rate = self.args.get("agile_current", "sensor.octopus_energy_electricity_current_rate")
        self.agile_rates = self.args.get("agile_rates", "event.octopus_energy_electricity_current_day_rates")
        
        # Pre-emptive discharge settings
        self.enable_preemptive_discharge = self.args.get("enable_preemptive_discharge", True)
        self.min_wastage_threshold = float(self.args.get("min_wastage_threshold", 1.0))
        self.min_benefit_threshold = float(self.args.get("min_benefit_threshold", 0.50))
        self.preemptive_discharge_min_soc = float(self.args.get("preemptive_discharge_min_soc", 50))
        self.preemptive_discharge_max_price = float(self.args.get("preemptive_discharge_max_price", 20))
        
        # Export settings
        self.has_export = self.args.get("has_export", False)
        self.export_rate_sensor = self.args.get("export_rate_sensor", None)
        
        # Cached inverter capabilities (refreshed periodically)
        self.inverter_capabilities = None
        self.capabilities_last_updated = None
        
        # State tracking
        self.last_mode = None
        self.last_change_time = None
        self.min_change_interval = int(self.args.get("min_change_interval", 3600))
        
        # Historical data
        self.history_file = self.args.get("history_file", "/config/appdaemon/solar_optimizer_history.json")
        self.load_history()
        
        # Planning
        self.current_plan = None
        self.plan_sensor = "sensor.solar_optimizer_plan"
        self.wastage_sensor = "sensor.solar_wastage_risk"
        self.capabilities_sensor = "sensor.solar_optimizer_capabilities"
        
        # Create sensors
        self.create_sensors()
        
        # Read inverter capabilities on startup
        self.update_inverter_capabilities()
        
        # Refresh capabilities every hour
        self.run_hourly(self.update_inverter_capabilities, datetime.now())
        
        # Schedule tasks - use 30-minute intervals for execution
        self.listen_state(self.on_agile_update, self.agile_rates)
        
        # Execute plan every 30 minutes (aligned to Agile slots)
        self.run_minutely(self.execute_plan_if_time, 1)
        
        self.run_hourly(self.record_metrics, datetime.now().replace(minute=55))
        self.listen_state(self.check_replan, self.solcast_remaining)
        self.run_daily(self.analyze_history, "02:00:00")
        self.run_in(self.generate_new_plan, 10)
        
        self.log("Smart Solar Optimizer initialized successfully")
        self.log(f"Pre-emptive discharge: {'ENABLED' if self.enable_preemptive_discharge else 'DISABLED'}")
        self.log(f"Export tariff: {'ENABLED' if self.has_export else 'DISABLED'}")
        self.log(f"Force Discharge mode: {'AVAILABLE' if self.mode_force_discharge else 'NOT AVAILABLE (will use Self Use)'}")
        self.log("=" * 80)
    
    def execute_plan_if_time(self, kwargs):
        """Execute plan only at :00 and :30 minutes (Agile pricing slots)"""
        now = datetime.now()
        if now.minute in [0, 30]:
            self.execute_plan(kwargs)
    
    # ========== SENSOR CREATION ==========
    
    def create_sensors(self):
        """Create HA sensors for plan and wastage display"""
        self.set_state(self.plan_sensor,
            state="initialized",
            attributes={
                "friendly_name": "Solar Optimizer 24h Plan",
                "icon": "mdi:calendar-clock",
                "plan": [],
                "generated_at": None,
                "next_action": None,
                "wastage_alert": False
            }
        )
        
        self.set_state(self.wastage_sensor,
            state="0",
            attributes={
                "friendly_name": "Solar Wastage Risk",
                "icon": "mdi:solar-power-variant",
                "unit_of_measurement": "kWh",
                "wastage_kwh": 0,
                "wastage_value": 0,
                "discharge_plan": []
            }
        )
        
        self.set_state(self.capabilities_sensor,
            state="unknown",
            attributes={
                "friendly_name": "Inverter Capabilities",
                "icon": "mdi:information"
            }
        )
    
    # ========== INVERTER CAPABILITY DETECTION ==========
    
    def update_inverter_capabilities(self, kwargs=None):
        """Read actual inverter capabilities from sensors"""
        try:
            capabilities = {}
            
            # Battery capacity (kWh)
            if self.battery_capacity_sensor:
                battery_capacity = self.get_state(self.battery_capacity_sensor)
                if battery_capacity:
                    capabilities['battery_capacity'] = float(battery_capacity)
                    self.battery_capacity = float(battery_capacity)
                else:
                    capabilities['battery_capacity'] = float(self.args.get("battery_capacity", 10.0))
                    self.battery_capacity = capabilities['battery_capacity']
            else:
                capabilities['battery_capacity'] = float(self.args.get("battery_capacity", 10.0))
                self.battery_capacity = capabilities['battery_capacity']
            
            # Battery voltage (V)
            battery_voltage = self.get_state(self.battery_voltage_sensor)
            if battery_voltage:
                capabilities['battery_voltage'] = float(battery_voltage)
            else:
                capabilities['battery_voltage'] = 51.2  # Typical 48V battery
            
            # Max charge current (A) -> convert to power (kW)
            max_charge_current = self.get_state(self.max_charge_rate_sensor)
            if max_charge_current:
                max_charge_power = float(max_charge_current) * capabilities['battery_voltage'] / 1000
                capabilities['max_charge_rate'] = max_charge_power
            else:
                capabilities['max_charge_rate'] = 2.0  # kW conservative default
            
            # Max discharge current (A) -> convert to power (kW)
            max_discharge_current = self.get_state(self.max_discharge_rate_sensor)
            if max_discharge_current:
                max_discharge_power = float(max_discharge_current) * capabilities['battery_voltage'] / 1000
                capabilities['max_discharge_rate'] = max_discharge_power
            else:
                capabilities['max_discharge_rate'] = 3.0  # kW conservative default
            
            # Inverter max power (kW)
            inverter_max = self.get_state(self.inverter_max_power_sensor)
            if inverter_max:
                capabilities['inverter_max_power'] = abs(float(inverter_max)) / 1000
            else:
                capabilities['inverter_max_power'] = 3.6  # Typical 3.6kW
            
            # Grid export limit (kW)
            export_limit = self.get_state(self.grid_export_limit_sensor)
            if export_limit:
                capabilities['grid_export_limit'] = float(export_limit) / 1000
            else:
                capabilities['grid_export_limit'] = 3.68  # UK G99 limit
            
            # Efficiency assumptions
            capabilities['charge_efficiency'] = 0.95
            capabilities['discharge_efficiency'] = 0.95
            
            self.inverter_capabilities = capabilities
            self.capabilities_last_updated = datetime.now()
            
            # Publish to sensor
            self.set_state(self.capabilities_sensor,
                state="detected",
                attributes={
                    "friendly_name": "Inverter Capabilities",
                    "icon": "mdi:information",
                    **capabilities,
                    "last_updated": self.capabilities_last_updated.isoformat()
                }
            )
            
            self.log(f"Inverter capabilities: Battery={capabilities['battery_capacity']}kWh, "
                    f"Charge={capabilities['max_charge_rate']:.1f}kW, "
                    f"Discharge={capabilities['max_discharge_rate']:.1f}kW")
            
        except Exception as e:
            self.log(f"Error reading inverter capabilities: {e}", level="ERROR")
            # Use safe defaults
            self.inverter_capabilities = {
                'battery_capacity': 10.0,
                'battery_voltage': 51.2,
                'max_charge_rate': 2.0,
                'max_discharge_rate': 3.0,
                'inverter_max_power': 3.6,
                'grid_export_limit': 3.68,
                'charge_efficiency': 0.95,
                'discharge_efficiency': 0.95
            }
            self.battery_capacity = 10.0
    
    def get_actual_battery_performance(self):
        """Get real-time battery performance from sensors"""
        try:
            battery_power = float(self.get_state(self.battery_power_sensor) or 0) / 1000  # W to kW
            battery_soc = float(self.get_state(self.battery_soc_sensor) or 50)
            
            if battery_power > 0.1:
                actual_charge_rate = battery_power
            elif battery_power < -0.1:
                actual_discharge_rate = abs(battery_power)
            else:
                actual_charge_rate = 0
                actual_discharge_rate = 0
            
            return {
                'current_charge_rate': actual_charge_rate if battery_power > 0 else 0,
                'current_discharge_rate': actual_discharge_rate if battery_power < 0 else 0,
                'current_soc': battery_soc,
                'battery_power': battery_power
            }
        except Exception as e:
            self.log(f"Error reading battery performance: {e}", level="WARNING")
            return None
    
    def is_currently_exporting(self):
        """Check if currently exporting to grid"""
        try:
            grid_power = float(self.get_state(self.grid_power_sensor) or 0)
            return grid_power < -100  # -100W threshold
        except:
            return False
    
    def get_current_export_rate(self):
        """Get current export rate in kW"""
        try:
            grid_power = float(self.get_state(self.grid_power_sensor) or 0)
            if grid_power < 0:
                return abs(grid_power) / 1000
            return 0
        except:
            return 0
    
    # ========== HISTORY MANAGEMENT ==========
    
    def load_history(self):
        """Load historical data from file"""
        try:
            with open(self.history_file, 'r') as f:
                self.history = json.load(f)
            self.log(f"Loaded history from {self.history_file}")
        except FileNotFoundError:
            self.history = {
                'hourly_consumption': {},
                'solcast_accuracy': [],
                'mode_changes': [],
                'daily_stats': [],
                'wastage_events': []
            }
            self.log("Created new history file")
    
    def save_history(self):
        """Save historical data to file"""
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            self.log(f"Failed to save history: {e}", level="ERROR")
    
    def record_metrics(self, kwargs):
        """Record current state every hour for learning"""
        try:
            now = datetime.now()
            hour_key = f"{now.hour:02d}"
            day_type = 'weekday' if now.weekday() < 5 else 'weekend'
            
            # Get current consumption
            grid_import = float(self.get_state("sensor.solax_grid_import_power") or 0)
            battery_discharge = float(self.get_state("sensor.solax_battery_discharge_power") or 0)
            consumption = (grid_import + battery_discharge) / 1000  # W to kW
            
            # Get solar generation
            solar_now = float(self.get_state("sensor.solax_pv_power") or 0) / 1000
            
            # Get battery state
            battery_soc = float(self.get_state(self.battery_soc_sensor) or 0)
            
            # Get price
            current_price = float(self.get_state(self.agile_current_rate) or 0)
            
            # Store hourly consumption pattern
            consumption_key = f"{day_type}_{hour_key}"
            if consumption_key not in self.history['hourly_consumption']:
                self.history['hourly_consumption'][consumption_key] = []
            
            self.history['hourly_consumption'][consumption_key].append({
                'timestamp': now.isoformat(),
                'consumption': consumption,
                'solar': solar_now,
                'battery_soc': battery_soc,
                'price': current_price
            })
            
            # Keep only last 30 days
            cutoff = (now - timedelta(days=30)).isoformat()
            self.history['hourly_consumption'][consumption_key] = [
                x for x in self.history['hourly_consumption'][consumption_key]
                if x['timestamp'] > cutoff
            ]
            
            # Check for wastage
            if battery_soc > 98 and solar_now > consumption:
                wasted = solar_now - consumption
                self.log(f"WARNING: Potentially wasting {wasted:.2f}kW of solar!", level="WARNING")
                
                self.history['wastage_events'].append({
                    'timestamp': now.isoformat(),
                    'wasted_kw': wasted,
                    'battery_soc': battery_soc,
                    'solar': solar_now,
                    'consumption': consumption
                })
            
            self.save_history()
            
        except Exception as e:
            self.log(f"Error recording metrics: {e}", level="WARNING")
    
    def get_historical_consumption(self, hour, day_type, lookback_days=14):
        """Get average consumption for specific hour/day type"""
        consumption_key = f"{day_type}_{hour:02d}"
        
        if consumption_key not in self.history['hourly_consumption']:
            # Default patterns
            if 0 <= hour < 6:
                return 0.3  # 300W overnight
            elif 6 <= hour < 9:
                return 0.8  # 800W morning
            elif 9 <= hour < 17:
                return 0.5  # 500W daytime
            elif 17 <= hour < 23:
                return 1.2  # 1.2kW evening
            else:
                return 0.4
        
        cutoff = (datetime.now() - timedelta(days=lookback_days)).isoformat()
        recent_data = [
            x['consumption'] for x in self.history['hourly_consumption'][consumption_key]
            if x['timestamp'] > cutoff
        ]
        
        if not recent_data:
            return 0.5
        
        return statistics.median(recent_data)
    
    def get_solcast_accuracy_ratio(self, days=7):
        """Calculate Solcast accuracy"""
        if not self.history.get('solcast_accuracy'):
            return 1.0
        
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        recent_accuracy = [
            x for x in self.history['solcast_accuracy']
            if x['date'] > cutoff
        ]
        
        if len(recent_accuracy) < 3:
            return 1.0
        
        ratios = [x['actual'] / x['predicted'] for x in recent_accuracy if x['predicted'] > 0]
        
        if not ratios:
            return 1.0
        
        return statistics.median(ratios)
    
    def analyze_history(self, kwargs):
        """Daily analysis"""
        try:
            yesterday = datetime.now() - timedelta(days=1)
            yesterday_str = yesterday.strftime('%Y-%m-%d')
            
            # Analyze wastage events
            yesterday_wastage = [
                w for w in self.history.get('wastage_events', [])
                if w['timestamp'].startswith(yesterday_str)
            ]
            
            if yesterday_wastage:
                total_wasted = sum(w['wasted_kw'] for w in yesterday_wastage)
                self.log(f"Yesterday wasted ~{total_wasted:.1f}kWh across {len(yesterday_wastage)} periods")
            
        except Exception as e:
            self.log(f"Error analyzing history: {e}", level="WARNING")
    
    # ========== PRICE HANDLING (30-MINUTE SLOTS) ==========
    
    def get_full_price_forecast(self):
        """Get all available Agile prices in 30-minute slots"""
        try:
            rates_attr = self.get_state(self.agile_rates, attribute="all")
            if not rates_attr or 'rates' not in rates_attr.get('attributes', {}):
                return None
            
            rates = rates_attr['attributes']['rates']
            now = datetime.now()
            
            upcoming_rates = []
            for r in rates:
                rate_start = datetime.fromisoformat(r['start'].replace('Z', '+00:00'))
                if rate_start >= now.replace(second=0, microsecond=0):
                    upcoming_rates.append({
                        'start': rate_start,
                        'end': rate_start + timedelta(minutes=30),
                        'price': r['value_inc_vat']
                    })
            
            upcoming_rates.sort(key=lambda x: x['start'])
            
            return upcoming_rates[:48]  # 24 hours
            
        except Exception as e:
            self.log(f"Error getting prices: {e}", level="WARNING")
            return None
    
    def get_current_agile_slot(self):
        """Get current 30-minute Agile slot"""
        now = datetime.now()
        if now.minute < 30:
            slot_start = now.replace(minute=0, second=0, microsecond=0)
        else:
            slot_start = now.replace(minute=30, second=0, microsecond=0)
        
        slot_end = slot_start + timedelta(minutes=30)
        
        return {
            'start': slot_start,
            'end': slot_end,
            'price': float(self.get_state(self.agile_current_rate) or 0)
        }
    
    # ========== SOLAR FORECASTING ==========
    
    def get_solar_forecast(self):
        """Get solar forecast data"""
        try:
            remaining_today = float(self.get_state(self.solcast_remaining) or 0)
            tomorrow = float(self.get_state(self.solcast_tomorrow) or 0)
            forecast_today = float(self.get_state(self.solcast_forecast_today) or 0)
            
            return {
                'remaining_today': remaining_today,
                'tomorrow': tomorrow,
                'forecast_today': forecast_today
            }
        except (ValueError, TypeError):
            self.log("Invalid solar forecast", level="WARNING")
            return None
    
    def get_hourly_solar_forecast(self, solar_forecast):
        """Convert Solcast to hourly values"""
        now = datetime.now()
        current_hour = now.hour
        
        hourly = {}
        remaining = solar_forecast.get('remaining_today', 0)
        
        # Adjust for accuracy
        accuracy_ratio = self.get_solcast_accuracy_ratio(days=7)
        remaining = remaining * accuracy_ratio
        
        # Bell curve distribution
        daylight_hours = []
        for offset in range(24):
            hour = (current_hour + offset) % 24
            if 6 <= hour <= 18:
                distance_from_noon = abs(hour - 12.5)
                weight = max(0, 1.0 - (distance_from_noon / 6.0))
                daylight_hours.append((offset, weight))
        
        total_weight = sum(w for _, w in daylight_hours)
        
        for offset in range(24):
            hour = (current_hour + offset) % 24
            matching = [w for o, w in daylight_hours if o == offset]
            if matching and total_weight > 0:
                hourly[offset] = (matching[0] / total_weight) * remaining
            else:
                hourly[offset] = 0
        
        return hourly
    
    def get_solar_remaining_after_hour(self, hour):
        """Get expected solar from specific hour onwards"""
        hourly_forecast = self.get_hourly_solar_forecast(self.get_solar_forecast())
        current_hour = datetime.now().hour
        
        total = 0
        for offset, solar_kwh in hourly_forecast.items():
            forecast_hour = (current_hour + offset) % 24
            if forecast_hour >= hour or offset > 12:
                total += solar_kwh
        
        return total
    
    # ========== WASTAGE CALCULATION ==========
    
    def calculate_solar_wastage_risk(self, hour, battery_kwh):
        """Calculate potential solar wastage"""
        if not self.inverter_capabilities:
            self.update_inverter_capabilities()
        
        caps = self.inverter_capabilities
        battery_soc = battery_kwh / caps['battery_capacity'] * 100
        
        solar_remaining = self.get_solar_remaining_after_hour(hour)
        
        hours_until_sunset = max(0, 19 - hour) if hour < 19 else 0
        total_consumption = 0
        day_type = 'weekday' if datetime.now().weekday() < 5 else 'weekend'
        
        for h in range(hours_until_sunset):
            future_hour = (hour + h) % 24
            total_consumption += self.get_historical_consumption(future_hour, day_type)
        
        battery_space = caps['battery_capacity'] - battery_kwh
        
        # Account for export limit
        max_export_per_hour = caps['grid_export_limit']
        total_export_capacity = max_export_per_hour * hours_until_sunset
        
        absorption_capacity = battery_space + total_consumption + total_export_capacity
        
        wastage = max(0, solar_remaining - absorption_capacity)
        
        if not self.has_export:
            wastage = max(0, solar_remaining - (battery_space + total_consumption))
        
        # Value
        if self.has_export and self.export_rate_sensor:
            export_rate = float(self.get_state(self.export_rate_sensor) or 15)
        else:
            export_rate = 15
        
        wastage_value = wastage * export_rate
        
        # Recommendation
        discharge_recommendation = min(
            wastage,
            battery_kwh - (caps['battery_capacity'] * self.preemptive_discharge_min_soc / 100),
            caps['max_discharge_rate'] * 4
        )
        discharge_recommendation = max(0, discharge_recommendation)
        
        return wastage, wastage_value, discharge_recommendation
    
    def should_preemptive_discharge(self, hour, battery_kwh, current_price, upcoming_prices):
        """Determine if pre-emptive discharge is beneficial"""
        if not self.enable_preemptive_discharge:
            return False, ""
        
        if not self.inverter_capabilities:
            self.update_inverter_capabilities()
        
        caps = self.inverter_capabilities
        battery_soc = battery_kwh / caps['battery_capacity'] * 100
        
        if not (5 <= hour <= 10):
            return False, ""
        
        if battery_soc < self.preemptive_discharge_min_soc:
            return False, ""
        
        if current_price > self.preemptive_discharge_max_price:
            return False, ""
        
        if self.is_currently_exporting():
            current_export = self.get_current_export_rate()
            if current_export > caps['grid_export_limit'] * 0.9:
                return False, f"Already at export limit ({current_export:.1f}kW)"
        
        wastage_kwh, wastage_value, recommended_discharge = self.calculate_solar_wastage_risk(hour, battery_kwh)
        
        if wastage_kwh < self.min_wastage_threshold:
            return False, ""
        
        if recommended_discharge < 0.5:
            return False, ""
        
        # Cost analysis
        discharge_duration_slots = min(8, len(upcoming_prices))
        avg_discharge_price = statistics.mean(upcoming_prices[:discharge_duration_slots]) if upcoming_prices else current_price
        
        round_trip_efficiency = caps['charge_efficiency'] * caps['discharge_efficiency']
        effective_grid_cost = avg_discharge_price / round_trip_efficiency
        
        cost_of_grid = effective_grid_cost * recommended_discharge
        benefit_solar_saved = wastage_value
        
        # Evening benefit
        evening_slot_offset = max(0, (18 - hour) * 2)
        if evening_slot_offset < len(upcoming_prices):
            evening_slots = upcoming_prices[evening_slot_offset:evening_slot_offset+6]
            avg_evening_price = statistics.mean(evening_slots) if evening_slots else current_price
        else:
            avg_evening_price = current_price * 1.5
        
        benefit_evening_saving = (avg_evening_price - effective_grid_cost) * recommended_discharge
        
        total_benefit = benefit_solar_saved + max(0, benefit_evening_saving)
        net_benefit = total_benefit - cost_of_grid
        
        if net_benefit > self.min_benefit_threshold * 100:
            return True, (
                f"Discharge {recommended_discharge:.1f}kWh over {discharge_duration_slots/2:.1f}h "
                f"to avoid wasting {wastage_kwh:.1f}kWh. Net benefit: £{net_benefit/100:.2f}"
            )
        
        if battery_soc > 75 and wastage_kwh > 3 and avg_discharge_price < 12:
            return True, (
                f"High battery ({battery_soc:.0f}%), {wastage_kwh:.1f}kWh will waste, "
                f"cheap grid (avg {avg_discharge_price:.1f}p)"
            )
        
        return False, ""
    
    def update_wastage_sensor(self, hour, battery_kwh):
        """Update wastage risk sensor"""
        wastage_kwh, wastage_value, recommended_discharge = self.calculate_solar_wastage_risk(hour, battery_kwh)
        
        self.set_state(self.wastage_sensor,
            state=f"{wastage_kwh:.1f}",
            attributes={
                "friendly_name": "Solar Wastage Risk",
                "icon": "mdi:solar-power-variant" if wastage_kwh < 1 else "mdi:alert",
                "unit_of_measurement": "kWh",
                "wastage_kwh": round(wastage_kwh, 2),
                "wastage_value": f"£{wastage_value/100:.2f}",
                "recommended_discharge": round(recommended_discharge, 2),
                "battery_soc": round(battery_kwh / self.battery_capacity * 100, 1),
                "alert_level": "high" if wastage_kwh > 3 else ("medium" if wastage_kwh > 1 else "low")
            }
        )
    
    # ========== BATTERY SIMULATION ==========
    
    def simulate_battery_change(self, mode, solar, consumption, battery_kwh):
        """Simulate battery for one hour using actual inverter limits"""
        if not self.inverter_capabilities:
            self.update_inverter_capabilities()
        
        caps = self.inverter_capabilities
        net_solar = solar - consumption
        space_available = caps['battery_capacity'] - battery_kwh
        
        if mode == self.mode_force_charge:
            # Force Charge mode
            max_grid_charge = caps['max_charge_rate']
            effective_charge_rate = max_grid_charge * caps['charge_efficiency']
            total_charge = effective_charge_rate + max(0, net_solar)
            actual_charge = min(total_charge, space_available, caps['max_charge_rate'])
            return actual_charge
        
        elif mode == self.mode_force_discharge:
            # Force Discharge mode - discharge to grid at max rate
            max_grid_discharge = caps['max_discharge_rate']
            # Discharge regardless of consumption
            actual_discharge = min(battery_kwh, max_grid_discharge) * caps['discharge_efficiency']
            return -actual_discharge
        
        elif mode == self.mode_grid_first:
            # Grid First mode
            if net_solar > 0:
                actual_charge = min(net_solar, space_available, caps['max_charge_rate'])
                return actual_charge
            else:
                return 0
        
        else:  # Self Use (default)
            if net_solar > 0:
                actual_charge = min(net_solar, space_available, caps['max_charge_rate'])
                return actual_charge
            else:
                discharge_needed = abs(net_solar)
                max_discharge = min(
                    battery_kwh,
                    caps['max_discharge_rate'],
                    caps['inverter_max_power']
                )
                actual_discharge = min(discharge_needed, max_discharge) * caps['discharge_efficiency']
                return -actual_discharge
    
    def calculate_hour_cost(self, mode, solar, consumption, battery_delta, price):
        """Estimate cost for one hour"""
        if not self.inverter_capabilities:
            self.update_inverter_capabilities()
        
        caps = self.inverter_capabilities
        
        if mode == self.mode_force_charge:
            # Force Charge - import for consumption AND charging
            if battery_delta > 0:
                grid_for_charging = battery_delta / caps['charge_efficiency']
            else:
                grid_for_charging = 0
            grid_import = (consumption - solar) + grid_for_charging
            grid_import = max(0, grid_import)
        
        elif mode == self.mode_force_discharge:
            # Force Discharge - export battery energy to grid
            grid_import = max(0, consumption - solar)  # Still meet house load
            # Battery discharge goes to export (negative import)
            if battery_delta < 0:
                export_to_grid = abs(battery_delta)  # kWh being exported
            else:
                export_to_grid = 0
        
        elif mode == self.mode_grid_first:
            # Grid First - import to meet any shortfall
            grid_import = max(0, consumption - solar)
        
        else:  # Self Use (default)
            if battery_delta < 0:
                available_from_battery = abs(battery_delta)
            else:
                available_from_battery = 0
            
            available = solar + available_from_battery
            grid_import = max(0, consumption - available)
        
        # Calculate export
        export = 0
        
        if mode == self.mode_force_discharge:
            # Force discharge exports to grid
            if 'export_to_grid' in locals():
                export = min(export_to_grid, caps['grid_export_limit'])
        elif solar > consumption and battery_delta >= 0:
            # Normal excess solar export
            potential_export = solar - consumption - max(0, battery_delta)
            export = max(0, min(potential_export, caps['grid_export_limit']))
        
        # Costs
        import_cost = grid_import * price / 100
        
        if self.has_export and self.export_rate_sensor and export > 0:
            export_rate = float(self.get_state(self.export_rate_sensor) or 0)
            export_value = export * export_rate / 100
        else:
            export_value = 0
        
        net_cost = import_cost - export_value
        return net_cost
    
    # ========== PLANNING ==========
    
    def generate_new_plan(self, kwargs=None):
        """Generate 24-hour optimization plan"""
        self.log("Generating new 24-hour plan...")
        
        battery_soc = self.get_battery_soc()
        solar_forecast = self.get_solar_forecast()
        price_data = self.get_full_price_forecast()
        
        if None in [battery_soc, solar_forecast, price_data]:
            self.log("Cannot generate plan - missing data", level="WARNING")
            return
        
        plan = self.optimize_24h_plan(battery_soc, solar_forecast, price_data)
        
        self.current_plan = plan
        self.publish_plan(plan)
        
        battery_kwh = self.battery_capacity * battery_soc / 100
        self.update_wastage_sensor(datetime.now().hour, battery_kwh)
        
        self.log(f"Plan generated: {self.summarize_plan(plan)}")
    
    def optimize_24h_plan(self, starting_soc, solar_forecast, price_slots):
        """Create optimal 24-hour plan"""
        plan = []
        now = datetime.now()
        battery_kwh = self.battery_capacity * starting_soc / 100
        
        hourly_solar = self.get_hourly_solar_forecast(solar_forecast)
        
        # Pre-scan for wastage
        total_solar_today = sum(hourly_solar.values())
        total_consumption_today = sum(
            self.get_historical_consumption(
                (now.hour + i) % 24,
                'weekday' if (now + timedelta(hours=i)).weekday() < 5 else 'weekend'
            )
            for i in range(24)
        )
        battery_space = self.battery_capacity - battery_kwh
        potential_wastage = total_solar_today - (battery_space + total_consumption_today)
        has_wastage_risk = potential_wastage > self.min_wastage_threshold
        
        if has_wastage_risk:
            self.log(f"WASTAGE ALERT: {potential_wastage:.1f}kWh may be wasted", level="WARNING")
        
        # Group 30-min slots into hours
        hourly_price_slots = []
        for i in range(0, min(len(price_slots), 48), 2):
            if i + 1 < len(price_slots):
                hour_avg_price = (price_slots[i]['price'] + price_slots[i+1]['price']) / 2
                hour_start = price_slots[i]['start']
            else:
                hour_avg_price = price_slots[i]['price']
                hour_start = price_slots[i]['start']
            
            hourly_price_slots.append({
                'start': hour_start,
                'price': hour_avg_price,
                'slot_1': price_slots[i],
                'slot_2': price_slots[i+1] if i+1 < len(price_slots) else None
            })
        
        # Create plan
        for hour_offset in range(min(24, len(hourly_price_slots))):
            hour_slot = hourly_price_slots[hour_offset]
            timestamp = hour_slot['start']
            hour = timestamp.hour
            day_type = 'weekday' if timestamp.weekday() < 5 else 'weekend'
            
            expected_consumption = self.get_historical_consumption(hour, day_type)
            expected_solar = hourly_solar.get(hour_offset, 0)
            
            upcoming_slots = price_slots[hour_offset*2:hour_offset*2+12]
            upcoming_prices = [s['price'] for s in upcoming_slots]
            
            mode_decision = self.decide_hour_mode(
                hour=hour,
                battery_kwh=battery_kwh,
                expected_consumption=expected_consumption,
                expected_solar=expected_solar,
                current_price=hour_slot['price'],
                upcoming_prices=upcoming_prices,
                hours_ahead=hour_offset,
                has_wastage_risk=has_wastage_risk,
                current_slot=hour_slot
            )
            
            battery_before = battery_kwh
            battery_delta = self.simulate_battery_change(
                mode=mode_decision['mode'],
                solar=expected_solar,
                consumption=expected_consumption,
                battery_kwh=battery_kwh
            )
            
            battery_kwh = max(0, min(self.battery_capacity, battery_kwh + battery_delta))
            
            estimated_cost = self.calculate_hour_cost(
                mode=mode_decision['mode'],
                solar=expected_solar,
                consumption=expected_consumption,
                battery_delta=battery_delta,
                price=hour_slot['price']
            )
            
            plan.append({
                'timestamp': timestamp.isoformat(),
                'hour': hour,
                'mode': mode_decision['mode'],
                'reason': mode_decision['reason'],
                'battery_soc_start': battery_before / self.battery_capacity * 100,
                'battery_soc_end': battery_kwh / self.battery_capacity * 100,
                'battery_delta': battery_delta,
                'expected_solar': round(expected_solar, 2),
                'expected_consumption': round(expected_consumption, 2),
                'price_avg': round(hour_slot['price'], 2),
                'price_slot_1': round(hour_slot['slot_1']['price'], 2),
                'price_slot_2': round(hour_slot['slot_2']['price'], 2) if hour_slot['slot_2'] else None,
                'estimated_cost': round(estimated_cost, 4),
                'is_preemptive_discharge': 'pre-emptive discharge' in mode_decision['reason'].lower()
            })
        
        return plan
    
    def decide_hour_mode(self, hour, battery_kwh, expected_consumption, 
                        expected_solar, current_price, upcoming_prices, 
                        hours_ahead, has_wastage_risk=False, current_slot=None):
        """Decide optimal mode for hour"""
        battery_soc = battery_kwh / self.battery_capacity * 100
        battery_space = self.battery_capacity - battery_kwh
        
        # Price stats
        if len(upcoming_prices) >= 12:
            avg_next_6h = statistics.mean(upcoming_prices[:12])
            min_next_6h = min(upcoming_prices[:12])
            max_next_6h = max(upcoming_prices[:12])
        else:
            avg_next_6h = current_price
            min_next_6h = current_price
            max_next_6h = current_price
        
        median_price = 15.0
        
        # PRIORITY 1: Pre-emptive discharge
        if self.enable_preemptive_discharge and has_wastage_risk:
            should_discharge, discharge_reason = self.should_preemptive_discharge(
                hour, battery_kwh, current_price, upcoming_prices
            )
            
            if should_discharge:
                # Use Force Discharge if available, otherwise Self Use (drain via consumption)
                discharge_mode = self.mode_force_discharge if self.mode_force_discharge else self.mode_self_use
                discharge_note = " (Force Discharge)" if self.mode_force_discharge else " (via load)"
                
                return {
                    'mode': discharge_mode,
                    'reason': f'PRE-EMPTIVE DISCHARGE{discharge_note}: {discharge_reason}'
                }
        
        # PRIORITY 2: Force Charge
        if current_price < 0 and battery_soc < 95:
            return {
                'mode': self.mode_force_charge,
                'reason': f'Negative pricing ({current_price:.1f}p)'
            }
        
        if min_next_6h < 0 and battery_soc < 90:
            return {
                'mode': self.mode_force_charge,
                'reason': f'Negative pricing coming (min {min_next_6h:.1f}p)'
            }
        
        if current_price < 3 and battery_soc < 90 and battery_space > 1:
            return {
                'mode': self.mode_force_charge,
                'reason': f'Very cheap ({current_price:.1f}p)'
            }
        
        if battery_soc < 30 and avg_next_6h > 25 and current_price < 10:
            return {
                'mode': self.mode_force_charge,
                'reason': f'Pre-charge for expensive period (avg {avg_next_6h:.1f}p)'
            }
        
        # PRIORITY 3: Grid First
        if 6 <= hour < 12 and expected_solar > expected_consumption * 2:
            return {
                'mode': self.mode_grid_first,
                'reason': f'Morning: abundant solar ({expected_solar:.1f}kWh)'
            }
        
        if expected_solar > battery_space * 2 and hours_ahead < 12:
            return {
                'mode': self.mode_grid_first,
                'reason': f'Excess solar ({expected_solar:.1f}kWh vs {battery_space:.1f}kWh space)'
            }
        
        if current_price < median_price * 0.7 and battery_soc > 30:
            if min_next_6h < current_price - 2:
                return {
                    'mode': self.mode_self_use,
                    'reason': f'Cheaper slot coming (min {min_next_6h:.1f}p)'
                }
            else:
                return {
                    'mode': self.mode_grid_first,
                    'reason': f'Cheap grid ({current_price:.1f}p)'
                }
        
        # PRIORITY 4: Self Use
        if current_price > median_price * 1.5 and battery_soc > 20:
            return {
                'mode': self.mode_self_use,
                'reason': f'Expensive ({current_price:.1f}p)'
            }
        
        if max_next_6h > 30 and battery_soc > 30:
            return {
                'mode': self.mode_self_use,
                'reason': f'Peak pricing coming (max {max_next_6h:.1f}p)'
            }
        
        if expected_solar < expected_consumption * 0.3 and battery_soc > 25:
            return {
                'mode': self.mode_self_use,
                'reason': f'Limited solar ({expected_solar:.1f}kWh)'
            }
        
        if 17 <= hour <= 20 and battery_soc > 30:
            return {
                'mode': self.mode_self_use,
                'reason': 'Evening peak'
            }
        
        return {
            'mode': self.mode_self_use,
            'reason': 'Standard self-consumption'
        }
    
    def publish_plan(self, plan):
        """Publish plan to sensor"""
        if not plan:
            return
        
        total_cost = sum(h['estimated_cost'] for h in plan)
        mode_summary = {}
        for hour in plan:
            mode = hour['mode']
            mode_summary[mode] = mode_summary.get(mode, 0) + 1
        
        next_action = plan[0] if plan else None
        
        wastage_hours = [h for h in plan if h.get('is_preemptive_discharge')]
        has_wastage_alert = len(wastage_hours) > 0
        
        self.set_state(self.plan_sensor,
            state=f"{len(plan)} hours",
            attributes={
                "friendly_name": "Solar Optimizer 24h Plan",
                "icon": "mdi:calendar-clock",
                "plan": plan,
                "generated_at": datetime.now().isoformat(),
                "next_action": next_action,
                "wastage_alert": has_wastage_alert,
                "preemptive_discharge_hours": len(wastage_hours),
                "summary": {
                    "total_estimated_cost": f"£{total_cost:.2f}",
                    "mode_hours": mode_summary,
                    "min_battery_soc": round(min(h['battery_soc_end'] for h in plan), 1),
                    "max_battery_soc": round(max(h['battery_soc_end'] for h in plan), 1),
                    "total_solar_expected": round(sum(h['expected_solar'] for h in plan), 1),
                    "total_consumption_expected": round(sum(h['expected_consumption'] for h in plan), 1)
                }
            }
        )
    
    def summarize_plan(self, plan):
        """Create text summary"""
        mode_counts = {}
        for hour in plan:
            mode = hour['mode']
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
        
        total_cost = sum(h['estimated_cost'] for h in plan)
        wastage_hours = sum(1 for h in plan if h.get('is_preemptive_discharge'))
        
        summary = f"Cost: £{total_cost:.2f}, "
        summary += ", ".join([f"{mode}={count}h" for mode, count in mode_counts.items()])
        
        if wastage_hours > 0:
            summary += f" | PRE-DISCHARGE: {wastage_hours}h"
        
        return summary
    
    # ========== EXECUTION ==========
    
    def execute_plan(self, kwargs):
        """Execute plan"""
        if not self.current_plan:
            self.log("No plan available", level="WARNING")
            self.generate_new_plan()
            return
        
        now = datetime.now()
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        
        current_step = None
        for step in self.current_plan:
            step_time = datetime.fromisoformat(step['timestamp']).replace(minute=0, second=0, microsecond=0)
            if step_time == current_hour:
                current_step = step
                break
        
        if not current_step:
            self.log("Hour not in plan, regenerating", level="WARNING")
            self.generate_new_plan()
            return
        
        current_slot = self.get_current_agile_slot()
        
        should_override, override_reason = self.check_plan_override(current_step, current_slot)
        
        if should_override:
            self.log(f"OVERRIDE: {override_reason}", level="WARNING")
            self.generate_new_plan()
            return
        
        planned_mode = current_step['mode']
        current_mode = self.get_state(self.inverter_mode_select)
        
        if planned_mode != current_mode:
            if self.last_change_time:
                time_since_change = (datetime.now() - self.last_change_time).total_seconds()
                if time_since_change < self.min_change_interval:
                    self.log(f"Rate limited: {time_since_change/60:.0f}min since last change")
                    return
            
            slot_indicator = "first half" if now.minute < 30 else "second half"
            
            self.log(f"Executing ({slot_indicator}): {current_mode} -> {planned_mode}")
            self.log(f"Reason: {current_step['reason']}")
            self.log(f"Slot price: {current_slot['price']:.2f}p (hour avg: {current_step['price_avg']:.2f}p)")
            
            if current_step.get('is_preemptive_discharge'):
                self.log("*** PRE-EMPTIVE DISCHARGE ACTIVE ***", level="WARNING")
            
            self.set_mode(planned_mode)
        else:
            if now.minute in [0, 30]:
                self.log(f"Maintaining {current_mode}, slot price: {current_slot['price']:.2f}p")
    
    def check_plan_override(self, planned_step, current_slot=None):
        """Check if conditions changed significantly"""
        current_soc = self.get_battery_soc()
        planned_soc = planned_step['battery_soc_start']
        
        if abs(current_soc - planned_soc) > 20:
            return True, f"SOC deviation: planned {planned_soc:.0f}%, actual {current_soc:.0f}%"
        
        if current_slot:
            current_price = current_slot['price']
            planned_avg_price = planned_step['price_avg']
            
            if abs(current_price - planned_avg_price) > 15:
                return True, f"Price deviation: current {current_price:.1f}p vs planned {planned_avg_price:.1f}p"
            
            if current_price < 0 and planned_avg_price > 5:
                return True, f"Unexpected negative pricing ({current_price:.1f}p)"
        
        return False, ""
    
    def set_mode(self, mode):
        """Set inverter mode"""
        try:
            self.call_service("select/select_option",
                entity_id=self.inverter_mode_select,
                option=mode
            )
            
            self.last_mode = mode
            self.last_change_time = datetime.now()
            
            self.history['mode_changes'].append({
                'timestamp': datetime.now().isoformat(),
                'mode': mode
            })
            
            self.history['mode_changes'] = self.history['mode_changes'][-100:]
            self.save_history()
            
        except Exception as e:
            self.log(f"Failed to set mode: {e}", level="ERROR")
    
    # ========== EVENT HANDLERS ==========
    
    def on_agile_update(self, entity, attribute, old, new, kwargs):
        """New Agile rates received"""
        self.log("New Agile rates received, regenerating plan...")
        self.generate_new_plan()
    
    def check_replan(self, entity, attribute, old, new, kwargs):
        """Solar forecast changed significantly"""
        if not self.current_plan:
            return
        
        try:
            old_val = float(old) if old else 0
            new_val = float(new) if new else 0
            
            if old_val > 0 and abs(new_val - old_val) / old_val > 0.2:
                self.log(f"Solar forecast changed {old_val:.1f} -> {new_val:.1f} kWh, replanning")
                self.generate_new_plan()
        except (ValueError, TypeError):
            pass
    
    # ========== UTILITY FUNCTIONS ==========
    
    def get_battery_soc(self):
        """Get battery SOC"""
        try:
            return float(self.get_state(self.battery_soc_sensor))
        except (ValueError, TypeError):
            self.log("Invalid battery SOC", level="WARNING")
            return None
