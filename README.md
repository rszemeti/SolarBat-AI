# Home Assistant Solar Integration

Complete AI-powered energy management system for Home Assistant with solar power and battery optimization.

## 📂 Repository Contents

### `/energy_demand_predictor/`

Complete Home Assistant add-on for energy demand prediction and battery optimization.

**Features:**
- 🤖 ML-based energy demand prediction (48 hours ahead)
- ☀️ Solar generation forecasting (Solcast integration)
- 💰 Dynamic tariff optimization (Octopus Energy)
- 🔋 Battery charge/discharge optimization
- 📊 Web dashboard and REST API
- 🏠 Automatic Home Assistant sensor creation

**Installation:**

See [`energy_demand_predictor/README.md`](energy_demand_predictor/README.md) and [`energy_demand_predictor/INSTALL.md`](energy_demand_predictor/INSTALL.md) for full documentation.

Quick start:
1. Install Octopus Energy and Solcast integrations in Home Assistant
2. Add this repository to Home Assistant add-ons
3. Install and configure the add-on
4. Add automation templates
5. Start saving money! 💵

## 🎯 What This Does

This system uses artificial intelligence and mathematical optimization to:

1. **Predict** your energy usage for the next 48 hours
2. **Forecast** solar generation based on weather
3. **Fetch** dynamic electricity prices (import & export)
4. **Optimize** when to charge/discharge your battery
5. **Minimize** your electricity costs automatically

**Expected savings: £8-15 per day** compared to unoptimized battery usage!

## 🚀 Quick Start

```bash
# 1. Add to Home Assistant
Settings → Add-ons → Add-on Store → ⋮ → Repositories
Add: https://github.com/yourusername/ha-energy-predictor

# 2. Install prerequisites
- Octopus Energy integration
- Solcast PV Forecast integration
- Battery system with SOC sensor

# 3. Install and configure add-on
# 4. Add automations to control battery
# 5. Monitor via web UI: http://homeassistant.local:8099
```

## 📊 How It Works

```
┌─────────────────┐
│  Historical     │
│  Energy Data    │──┐
└─────────────────┘  │
                     │    ┌──────────────┐
┌─────────────────┐  │    │              │
│  Solcast Solar  │──┼───→│  ML Model &  │
│  Forecast       │  │    │  Optimizer   │
└─────────────────┘  │    │              │
                     │    └──────┬───────┘
┌─────────────────┐  │           │
│  Octopus Energy │──┘           │
│  Tariff Rates   │              │
└─────────────────┘              ▼
                        ┌─────────────────┐
                        │  Optimal        │
                        │  Battery        │
                        │  Schedule       │
                        └─────────────────┘
```

## 🏗️ Architecture

- **Python Backend:** ML prediction, optimization, HA integration
- **Machine Learning:** scikit-learn Gradient Boosting
- **Optimization:** PuLP linear programming solver
- **Web Interface:** Flask REST API + HTML/JS dashboard
- **Home Assistant:** Automatic sensor creation and updates

## 📱 Created Sensors

After installation, these sensors appear in Home Assistant:

- `sensor.energy_demand_predictor` - Energy demand forecast
- `sensor.solar_predictor` - Solar generation forecast
- `sensor.battery_optimizer` - Current battery action
- `sensor.energy_cost_predictor` - 48h cost forecast

Each sensor includes detailed attributes with full schedules and predictions.

## 🤖 Example Automations

Control your battery based on AI recommendations:

```yaml
automation:
  - alias: "Battery Optimizer - Execute Actions"
    trigger:
      - platform: time_pattern
        minutes: "/30"
    action:
      - choose:
          - conditions: "{{ states('sensor.battery_optimizer') == 'charge' }}"
            sequence:
              - service: number.set_value
                target:
                  entity_id: number.battery_charge_current
                data:
                  value: "{{ state_attr('sensor.battery_optimizer', 'target_power_kw') }}"
```

See [`energy_demand_predictor/automations_examples.yaml`](energy_demand_predictor/automations_examples.yaml) for complete templates.

## 🔧 Configuration

```yaml
# Energy consumption
entity_id: sensor.house_load
prediction_slots: 96  # 48 hours
max_training_days: 30

# Octopus Energy
enable_octopus_integration: true
octopus_import_rate_entity: event.octopus_energy_electricity_xxx_current_day_rates
octopus_export_rate_entity: event.octopus_energy_electricity_xxx_export_current_day_rates

# Solar (Solcast)
solar_forecast_provider: solcast
solcast_forecast_entity: sensor.solcast_pv_forecast_forecast_today

# Battery
battery_capacity_kwh: 9.5
battery_min_soc: 0.1
battery_reserve_soc: 0.2
max_charge_rate_kw: 3.6
max_discharge_rate_kw: 3.6

# Grid
allow_grid_export: true
max_export_rate_kw: 5.0
```

## 📚 Documentation

- **README:** [`energy_demand_predictor/README.md`](energy_demand_predictor/README.md)
- **Installation:** [`energy_demand_predictor/INSTALL.md`](energy_demand_predictor/INSTALL.md)
- **Automations:** [`energy_demand_predictor/automations_examples.yaml`](energy_demand_predictor/automations_examples.yaml)
- **Changelog:** [`energy_demand_predictor/CHANGELOG.md`](energy_demand_predictor/CHANGELOG.md)

## 🌟 Features

### Energy Prediction
- Machine learning model learns your usage patterns
- Considers time of day, day of week, seasonality
- Retrains automatically with new data
- 48-hour forecast in 30-minute intervals

### Solar Forecasting
- Integrates with Solcast for accurate forecasts
- Supports multiple forecast modes (conservative/optimistic)
- Accounts for weather and panel specifications

### Battery Optimization
- Linear programming solver finds optimal schedule
- Minimizes: `import_cost - export_revenue + degradation`
- Respects battery limits and constraints
- Updates every 30-60 minutes

### Tariff Integration
- Dynamic pricing from Octopus Energy
- Supports Agile, Go, and other variable tariffs
- Import and export rates
- Automatically adapts to price changes

## 🎛️ Tuning

**Conservative** (protect battery):
- Higher reserve SOC
- Higher degradation cost
- Wider safety margins

**Aggressive** (maximize savings):
- Lower reserve SOC
- Lower degradation cost
- More frequent cycling

## 💡 Use Cases

- **Time-of-use tariffs:** Buy low, sell high
- **Agile pricing:** Real-time rate optimization
- **Solar self-consumption:** Maximize use of own generation
- **EV charging:** Charge car during cheap periods
- **Load shifting:** Run appliances at optimal times

## 🐛 Troubleshooting

Common issues and solutions in [`INSTALL.md`](energy_demand_predictor/INSTALL.md)

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

MIT License - see [`LICENSE`](energy_demand_predictor/LICENSE)

## 🙏 Acknowledgments

- Home Assistant community
- Octopus Energy for great API
- Solcast for solar forecasting
- scikit-learn and PuLP teams

## 📞 Support

- **Issues:** GitHub Issues
- **Discussions:** GitHub Discussions
- **Documentation:** See `/energy_demand_predictor/` folder

---

**Save money and the planet! 🌍⚡💰**
