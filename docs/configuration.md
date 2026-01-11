# Configuration Guide

Complete guide to configuring SolarBat-AI v2.0

## Required Configuration

### 1. Battery Sensors

```yaml
battery_soc: sensor.solax_battery_soc           # Battery state of charge (%)
battery_capacity: sensor.solax_battery_capacity # Battery capacity (kWh)
inverter_mode: select.solax_charger_use_mode    # Inverter mode selector
```

**Finding your entity IDs:**
1. Go to Developer Tools → States
2. Search for "battery" or "solax"
3. Copy the exact entity ID

### 2. Inverter Capability Sensors

These are automatically read to determine your inverter's limits:

```yaml
max_charge_rate: sensor.solax_battery_charge_max_current     # Amps
max_discharge_rate: sensor.solax_battery_discharge_max_current # Amps
inverter_max_power: sensor.solax_inverter_power              # Watts
battery_voltage: sensor.solax_battery_voltage                # Volts
grid_export_limit: sensor.solax_export_control_user_limit   # Watts
```

**Note:** The system converts Amps to kW using the battery voltage automatically.

### 3. Real-time Power Sensors

```yaml
pv_power: sensor.solax_pv_power            # Solar generation (Watts)
battery_power: sensor.solax_battery_power  # Battery power (Watts, + charging, - discharging)
load_power: sensor.solax_house_load        # House load (Watts)
grid_power: sensor.solax_measured_power    # Grid power (Watts, - exporting, + importing)
```

### 4. Solar Forecasting (Solcast)

```yaml
solcast_remaining: sensor.solcast_pv_forecast_forecast_remaining_today
solcast_tomorrow: sensor.solcast_pv_forecast_forecast_tomorrow
solcast_forecast_today: sensor.solcast_pv_forecast_forecast_today
```

**Installing Solcast:**
1. Install from HACS
2. Get free API key from https://solcast.com
3. Add your rooftop details
4. Configure in Home Assistant

### 5. Octopus Agile

```yaml
agile_current: sensor.octopus_energy_electricity_xxxxx_current_rate
agile_rates: event.octopus_energy_electricity_xxxxx_current_day_rates
```

**Finding your MPAN:**
1. Check your Octopus account
2. Or look in Home Assistant → Octopus Energy integration
3. Replace `xxxxx` with your actual MPAN number

## Optional Configuration

### Export Tariff

If you have Agile Export or similar:

```yaml
has_export: true
export_rate_sensor: sensor.octopus_energy_electricity_export_current_rate
```

### Pre-emptive Discharge Settings

Fine-tune when battery discharges to prevent solar wastage:

```yaml
enable_preemptive_discharge: true  # Enable/disable feature
min_wastage_threshold: 1.0         # Minimum kWh of wastage to trigger (lower = more aggressive)
min_benefit_threshold: 0.50        # Minimum £ benefit required (lower = more aggressive)
preemptive_discharge_min_soc: 50  # Don't discharge below this % (higher = more conservative)
preemptive_discharge_max_price: 20 # Don't discharge if grid price above this p/kWh
```

**Example scenarios:**

**Conservative (prevent only major wastage):**
```yaml
min_wastage_threshold: 3.0
min_benefit_threshold: 1.00
preemptive_discharge_min_soc: 60
```

**Aggressive (maximize solar utilization):**
```yaml
min_wastage_threshold: 0.5
min_benefit_threshold: 0.25
preemptive_discharge_min_soc: 40
```

### Behavior Settings

```yaml
min_change_interval: 3600  # Seconds between mode changes (3600 = 1 hour)
```

**Recommendations:**
- **Start with 3600** (1 hour) to prevent inverter spam
- **Increase to 7200** (2 hours) if still seeing too many changes
- **Never go below 1800** (30 minutes)

### Data Storage

```yaml
history_file: /config/appdaemon/solar_optimizer_history.json
```

**Note:** This file grows over time. It's automatically cleaned to keep only 30 days of data.

## Complete Example Configuration

```yaml
solar_optimizer:
  module: solar_optimizer
  class: SmartSolarOptimizer
  
  # Battery
  battery_soc: sensor.solax_battery_soc
  battery_capacity: sensor.solax_battery_capacity
  inverter_mode: select.solax_charger_use_mode
  
  # Inverter capabilities
  max_charge_rate: sensor.solax_battery_charge_max_current
  max_discharge_rate: sensor.solax_battery_discharge_max_current
  inverter_max_power: sensor.solax_inverter_power
  battery_voltage: sensor.solax_battery_voltage
  grid_export_limit: sensor.solax_export_control_user_limit
  
  # Real-time power
  pv_power: sensor.solax_pv_power
  battery_power: sensor.solax_battery_power
  load_power: sensor.solax_house_load
  grid_power: sensor.solax_measured_power
  
  # Solar forecast
  solcast_remaining: sensor.solcast_pv_forecast_forecast_remaining_today
  solcast_tomorrow: sensor.solcast_pv_forecast_forecast_tomorrow
  solcast_forecast_today: sensor.solcast_pv_forecast_forecast_today
  
  # Agile pricing
  agile_current: sensor.octopus_energy_electricity_12345678_current_rate
  agile_rates: event.octopus_energy_electricity_12345678_current_day_rates
  
  # Export (if applicable)
  has_export: true
  export_rate_sensor: sensor.octopus_energy_electricity_export_current_rate
  
  # Pre-emptive discharge
  enable_preemptive_discharge: true
  min_wastage_threshold: 1.0
  min_benefit_threshold: 0.50
  preemptive_discharge_min_soc: 50
  preemptive_discharge_max_price: 20
  
  # Behavior
  min_change_interval: 3600
  
  # Storage
  history_file: /config/appdaemon/solar_optimizer_history.json
```

## Validation

After configuration, check AppDaemon logs:

```bash
tail -f /config/appdaemon/appdaemon.log | grep "Solar"
```

You should see:
```
Smart Solar Optimizer initialized successfully
Inverter capabilities: Battery=10.0kWh, Charge=2.5kW, Discharge=3.0kW
Pre-emptive discharge: ENABLED
Export tariff: ENABLED
Generating new 24-hour plan...
```

## Troubleshooting Configuration

### "Cannot generate plan - missing data"

Check each sensor exists:
```bash
ha states sensor.solax_battery_soc
ha states sensor.octopus_energy_electricity_xxxxx_current_rate
```

### "Error reading inverter capabilities"

One or more capability sensors is missing. Check:
```bash
ha states sensor.solax_battery_charge_max_current
ha states sensor.solax_battery_voltage
```

If these don't exist, you can provide fallback values:
```yaml
battery_capacity: 10.0  # kWh - your actual battery size
```

### Mode changes not happening

1. Check the inverter_mode entity accepts the mode names
2. Verify modes are case-sensitive (e.g., "Self Use" not "self use")
3. Test manually via Developer Tools

## Advanced Configuration

### Multiple Batteries

Not yet supported in v2.0. Coming in v2.2.

### Custom Consumption Patterns

The system learns automatically, but you can reset learning:
```bash
rm /config/appdaemon/solar_optimizer_history.json
```

### Integration with Other Systems

The optimizer creates sensors that can trigger automations:

```yaml
automation:
  - alias: "Notify on Wastage Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.solar_wastage_risk
        above: 2
    action:
      - service: notify.mobile_app
        data:
          message: "{{ states('sensor.solar_wastage_risk') }}kWh solar will be wasted!"
```
