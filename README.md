# 🦇 SolarBat-AI

Intelligent solar battery optimizer for Home Assistant. Automatically manages your battery charging and discharging to minimise electricity costs using Octopus Agile pricing, Solcast solar forecasts, and learned consumption patterns.

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## What It Does

SolarBat-AI generates an optimal 24-hour battery plan every 30 minutes, deciding when to:

- **Charge** from the grid during cheap Agile periods (overnight lows)
- **Discharge** to the grid during expensive peaks (earning money)
- **Self Use** for normal solar + battery operation
- **Feed-in Priority** to prevent solar clipping on high-generation days

It learns your household consumption patterns over time, tracks Solcast forecast accuracy, and adapts its decisions accordingly.

## Web Dashboard

Accessible at `http://<your-HA-IP>:5050/api/appdaemon/solar_plan` with four tabs:

| Tab | What it shows |
|-----|---------------|
| **📋 Plan** | Current 24h optimisation plan with mode decisions and costs |
| **🔮 Predictions** | Solar, battery SOC, load, and pricing forecasts for next 24hrs |
| **📊 Accuracy** | 10-day prediction vs actual comparison with error metrics |
| **⚙️ Settings** | All configurable thresholds, inverter modes, and sensor mappings |

## Requirements

- **Home Assistant** with **AppDaemon 4.x** (install via Add-on Store)
- **Solcast** integration for solar forecasting
- **Octopus Energy** integration for Agile pricing
- **Solax ModBus** or compatible inverter integration (Solis, Solax, etc.)

## Installation

### Via Add-on (Recommended)

The simplest way to install SolarBat-AI is as a standalone Home Assistant add-on. No separate AppDaemon add-on is required.

1. Go to **Settings → Add-ons → Add-on Store**
2. Click **⋮** (top right) → **Repositories**
3. Add: `https://github.com/YOUR_USERNAME/solarbat-ai-addon`
4. Click **Close**, refresh the page
5. Find **SolarBat-AI**, click **Install**
6. Click **Start** — the addon creates a template `apps.yaml`
7. Click **Stop**, then edit `apps.yaml` in `/addon_configs/xxx_solarbat-ai/`
8. Update sensor entity IDs to match your system (see Configuration below)
9. Remove the `Template: True` line
10. Click **Start** again

The web dashboard is accessible via the **Open Web UI** button once running.

### Manual Installation (Advanced)

If you prefer to run AppDaemon separately or develop locally:

```bash
cd /addon_configs/a0d7b954_appdaemon/apps
git clone https://github.com/YOUR_USERNAME/SolarBat-AI.git solar_optimizer
```

Then copy `apps.yaml.example` to your AppDaemon `apps.yaml` and configure.

## Configuration

Create or edit `/config/appdaemon/apps/apps.yaml`:

```yaml
solar_optimizer:
  module: solar_optimizer
  class: SmartSolarOptimizer
  
  # ── REQUIRED: Your entity IDs ──
  battery_soc: sensor.solax_battery_soc
  battery_capacity: sensor.solax_battery_capacity
  inverter_mode: select.solax_charger_use_mode
  
  # Inverter mode names (must match exactly, case-sensitive)
  mode_self_use: "Self Use"
  mode_grid_first: "Grid First"
  mode_force_charge: "Force Charge"
  mode_force_discharge: "Force Discharge"   # Leave empty if not supported
  
  # Inverter capability sensors
  max_charge_rate: sensor.solax_battery_charge_max_current
  max_discharge_rate: sensor.solax_battery_discharge_max_current
  battery_voltage: sensor.solax_battery_voltage
  inverter_max_power: sensor.solax_inverter_power
  grid_export_limit: sensor.solax_export_control_user_limit
  
  # Real-time power sensors
  pv_power: sensor.solax_pv_power
  battery_power: sensor.solax_battery_power
  load_power: sensor.solax_house_load
  grid_power: sensor.solax_measured_power
  
  # Solar forecasting (Solcast)
  solcast_remaining: sensor.solcast_pv_forecast_forecast_remaining_today
  solcast_tomorrow: sensor.solcast_pv_forecast_forecast_tomorrow
  solcast_forecast_today: sensor.solcast_pv_forecast_forecast_today
  
  # Octopus Agile pricing (replace xxxxx with your MPAN)
  agile_current: sensor.octopus_energy_electricity_xxxxx_current_rate
  agile_rates: event.octopus_energy_electricity_xxxxx_current_day_rates
  
  # ── OPTIONAL ──
  has_export: false
  # export_rate_sensor: sensor.octopus_energy_electricity_export_current_rate
  
  enable_preemptive_discharge: true
  min_wastage_threshold: 1.0          # kWh - min solar waste to trigger discharge
  min_benefit_threshold: 0.50         # £ - min benefit to justify discharge
  preemptive_discharge_min_soc: 50    # % - don't discharge below this
  preemptive_discharge_max_price: 20  # p/kWh - don't discharge if grid is expensive
  min_change_interval: 3600           # seconds between mode changes
```

**Finding your entity IDs:** Go to Developer Tools → States and search for "solax", "solis", "octopus", or "solcast".

## How It Works

The optimizer runs on a 30-minute cycle aligned to Agile pricing slots:

1. **Data Collection** — Fetches current battery state, solar forecast, Agile prices, and learned load patterns
2. **Plan Generation** — Creates an optimal 24h schedule considering price arbitrage, solar clipping prevention, and battery health
3. **Execution** — Sets the inverter mode for the current slot
4. **Learning** — Records actual consumption, solar generation, and price data to improve future predictions

### Inverter Modes

| Mode | When | Why |
|------|------|-----|
| Self Use | Default | Normal solar + battery operation |
| Force Charge | Cheap overnight periods | Fill battery at ~5p/kWh |
| Force Discharge | Peak price periods | Export at ~35-45p/kWh |
| Feed-in Priority | High solar mornings | Route solar to grid first, preventing clipping |

### Clipping Prevention

On high-solar days, the optimizer detects when generation will exceed battery + consumption capacity. It switches to Feed-in Priority mode early, routing solar to the grid before the battery fills up — preventing energy waste.

## HA Dashboard Cards

Example Lovelace cards are in `dashboards/`. Add them to your dashboard for at-a-glance status.

## Monitoring

The optimizer creates these HA sensors:

- `sensor.solar_optimizer_plan` — Current plan with next action
- `sensor.solar_wastage_risk` — Predicted solar clipping risk
- `sensor.solar_optimizer_capabilities` — Detected inverter capabilities

Check AppDaemon logs for detailed plan output: Settings → Add-ons → AppDaemon → Log.

## Troubleshooting

**No plan generated?** Check that all required sensors exist and return valid values in Developer Tools → States.

**Mode changes too frequent?** Increase `min_change_interval` (default 3600 seconds).

**Inverter not responding?** Verify your mode names match exactly — go to Developer Tools → States, find your inverter mode entity, and check the available options list.

**Pre-emptive discharge not triggering?** Ensure `enable_preemptive_discharge: true` and that solar forecast exceeds battery capacity + expected consumption.

## Project Structure

```
SolarBat-AI/
├── apps/solar_optimizer/          # Core AppDaemon app (HACS installs this)
│   ├── solar_optimizer.py         # Main orchestrator
│   ├── forecast_accuracy_tracker.py
│   ├── load_forecaster.py
│   ├── plan_executor.py
│   ├── planners/                  # Rule-based, LP, and ML planners
│   ├── providers/                 # Data providers (pricing, solar, load, etc.)
│   └── templates/                 # Web dashboard HTML/CSS/JS
├── dashboards/                    # HA Lovelace card examples
├── tests/                         # Test harness, scenarios, and dev tools
├── docs/                          # Additional documentation
├── hacs.json                      # HACS manifest
└── README.md
```

## Contributing

Pull requests welcome. The `tests/` directory contains a full test harness that connects to your HA instance for local development — see `tests/README.md` for details.

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgments

Built with Solcast, Octopus Energy API, and the Home Assistant + AppDaemon ecosystem.
