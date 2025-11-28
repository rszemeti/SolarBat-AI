# Energy Demand Predictor & Battery Optimizer

A complete AI-powered energy management system for Home Assistant that predicts energy demand, forecasts solar generation, and optimizes battery charge/discharge schedules to minimize costs.

## 🎯 What This System Does

- **Predicts energy demand** for next 48 hours using machine learning
- **Forecasts solar generation** via Solcast integration
- **Fetches dynamic tariffs** from Octopus Energy
- **Optimizes battery** charge/discharge schedule using linear programming
- **Minimizes costs** by buying low, selling high
- **Maximizes solar self-consumption**

**Expected Savings: £8-15 per day** vs unoptimized usage!

## 📋 Prerequisites

### Required Home Assistant Integrations

1. **Octopus Energy** (for tariff optimization)
   - Install via: Settings → Integrations → Add Integration → "Octopus Energy"
   - Creates entities like `event.octopus_energy_electricity_xxx_current_day_rates`

2. **Solcast** (for solar forecasting)
   - Install via HACS → Integrations → "Solcast PV Forecast"
   - Requires free Solcast account and API key
   - Creates entities like `sensor.solcast_pv_forecast_forecast_today`

3. **Your Battery System** (GivEnergy, Solis, Tesla, etc.)
   - Battery SOC sensor (e.g., `sensor.battery_soc`)
   - Battery charge/discharge controls

## 🚀 Installation

### Method 1: From GitHub Repository

1. **Add Custom Repository:**
   ```
   Settings → Add-ons → Add-on Store → ⋮ → Repositories
   Add: https://github.com/yourusername/ha-energy-predictor
   ```

2. **Install the Add-on:**
   - Find "Energy Demand Predictor & Battery Optimizer"
   - Click Install (takes 5-10 minutes to build)

3. **Configure** (see Configuration section below)

4. **Start the Add-on** and check logs

### Method 2: Local Development

Copy the `energy_demand_predictor` folder to `/addons/` on your HA system.

## ⚙️ Configuration

Example configuration:

```yaml
# Energy sensor
entity_id: sensor.house_load
prediction_slots: 96
max_training_days: 30
api_port: 8099
auto_update_interval: 3600

# Octopus Energy
enable_octopus_integration: true
octopus_import_rate_entity: event.octopus_energy_electricity_xxx_current_day_rates
octopus_export_rate_entity: event.octopus_energy_electricity_xxx_export_current_day_rates

# Solar
solar_forecast_provider: solcast
solcast_forecast_entity: sensor.solcast_pv_forecast_forecast_today
solar_forecast_mode: estimate

# Battery
battery_capacity_kwh: 9.5
battery_min_soc: 0.1
battery_reserve_soc: 0.2
max_charge_rate_kw: 3.6
max_discharge_rate_kw: 3.6
charge_efficiency: 0.95
discharge_efficiency: 0.95
battery_degradation_cost_per_cycle: 0.05
battery_soc_entity: sensor.battery_soc

# Grid
allow_grid_export: true
max_export_rate_kw: 5.0
```

## 🏠 Home Assistant Sensors

After starting, these sensors are automatically created:

### `sensor.energy_demand_predictor`
- **State:** Next 30-min demand prediction (kW)
- **Attributes:**
  - `predictions` - Next 24h (48 slots)
  - `extended_predictions` - Hours 24-48

### `sensor.solar_predictor`
- **State:** Current solar prediction (kW)
- **Attributes:**
  - `predictions` - Next 48h solar forecast
  - `total_48h_kwh` - Total expected generation

### `sensor.battery_optimizer`
- **State:** Current action (`charge`, `discharge`, or `hold`)
- **Attributes:**
  - `target_power_kw` - How much to charge/discharge
  - `current_soc_percent` - Current battery level
  - `schedule` - Full 48h optimization schedule
  - `next_action_changes` - When actions will change

### `sensor.energy_cost_predictor`
- **State:** Total predicted cost for 48h (£)
- **Attributes:**
  - `import_cost_48h` - Cost of grid imports
  - `export_revenue_48h` - Revenue from exports

## 🤖 Example Automations

See `automations_examples.yaml` for complete automation templates including:

- Execute battery charge/discharge actions
- Alert before expensive periods
- Smart EV charging during cheap rates
- And more!

## 🔧 API Usage

### Web Interface
```
http://homeassistant.local:8099
```

### REST API Endpoints

**Get Current Battery Action:**
```bash
curl http://homeassistant.local:8099/api/battery/current
```

**Get Full Schedule:**
```bash
curl http://homeassistant.local:8099/api/battery/schedule
```

**Trigger Manual Optimization:**
```bash
curl -X POST http://homeassistant.local:8099/api/optimize
```

## 📊 How It Works

The optimizer uses linear programming to solve:

**Minimize:** Grid import costs - Export revenue + Battery degradation

**Subject to:**
- Energy balance (supply = demand every 30 min)
- Battery capacity limits
- Charge/discharge rate limits
- Minimum SOC requirements
- Can't charge & discharge simultaneously

**Result:** Mathematically optimal schedule that maximizes savings!

## 🎛️ Tuning

### Conservative (protect battery)
```yaml
battery_min_soc: 0.2
battery_reserve_soc: 0.3
battery_degradation_cost_per_cycle: 0.10
```

### Aggressive (maximize savings)
```yaml
battery_min_soc: 0.05
battery_reserve_soc: 0.1
battery_degradation_cost_per_cycle: 0.02
```

## ❓ Troubleshooting

### "No predictions available"
- Ensure entity_id is correct
- Check 7+ days of historical data exists
- Review add-on logs

### "Octopus rates not found"
- Verify Octopus integration installed
- Check entity names in Developer Tools → States

### "Solcast forecast failed"
- Ensure Solcast integration configured
- Check API calls remaining (10/day limit)

### "Optimization status: Infeasible"
- Try lowering `battery_reserve_soc`
- Check `max_charge_rate_kw` matches your battery

## 📞 Support

- **GitHub Issues:** Report bugs and feature requests
- **Logs:** Always check add-on logs first
- **Documentation:** See full guide in `DOCUMENTATION.md`

## 📄 License

MIT License - See LICENSE file

## 🙏 Credits

Built with:
- scikit-learn (machine learning)
- PuLP (linear programming)
- Flask (web interface)
- Home Assistant (smart home platform)

---

Happy optimizing! 🎉 Save money and the planet! 🌍
