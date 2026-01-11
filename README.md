# SolarBat-AI v2.3

Intelligent battery management for solar + storage systems with Octopus Agile pricing.

**Built for the Home Assistant community to optimize solar battery systems and maximize savings with time-of-use electricity tariffs.**

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Version](https://img.shields.io/badge/version-2.3.0-green.svg)
![HA](https://img.shields.io/badge/Home%20Assistant-AppDaemon-blue.svg)

---

## 🌟 Features

### Core Optimization
- ✅ **24-Hour AI Planning** - ML-powered load forecasting with confidence scoring
- ✅ **Smart Clipping Prevention** - Uses mode switch to prioritize grid export (no battery cycling!)
- ✅ **Arbitrage Trading** - Buy cheap, sell expensive automatically
- ✅ **Zero Solar Waste** - Intelligent mode switching prevents clipping losses

### Architecture (v2.3)
- ✅ **Provider-Based Design** - Clean separation: data sources → optimization → execution
- ✅ **Fully Testable** - Each component isolated and independently testable
- ✅ **Swappable Components** - Easy to add new tariffs, inverters, or forecasting methods
- ✅ **Health Monitoring** - Every data source reports status and confidence

### Intelligence
- ✅ **AI Load Forecasting** - Multi-method prediction (yesterday, last week, trends, averages)
- ✅ **Price Prediction** - Handles 4pm Agile price gap with historical learning
- ✅ **Cost Tracking** - Per-slot and cumulative cost/revenue tracking
- ✅ **Confidence Scoring** - Know when data is reliable vs uncertain

### Control
- ✅ **Three-Way Control System:**
  - **Timed Charge Slots** - Cheap import (Agile pricing)
  - **Timed Discharge Slots** - Profitable export 
  - **Mode Switch** - Solar routing (battery-first vs grid-first)
- ✅ **Minimal Writes** - Only updates inverter when plan differs from actual
- ✅ **Smart Execution** - Compares plan to reality before writing

---

## 📋 What's New in v2.3

### Major Architecture Refactor
**Clean Provider/Consumer Pattern:**
```
Data Providers → Plan Creator → Plan Executor → Inverter
```

### New Components
- **5 Independent Data Providers:**
  - ImportPricingProvider (Octopus Agile with prediction)
  - ExportPricingProvider (Fixed or dynamic export rates)
  - SolarForecastProvider (Solcast integration)
  - LoadForecastProvider (AI consumption prediction)
  - SystemStateProvider (Current inverter/battery state)

- **PlanCreator** - Pure optimization engine (no HA dependencies)
- **PlanExecutor** - Smart inverter control (writes only when needed)

### Breakthrough: Mode Switch Integration
**Clipping Prevention Without Battery Cycling:**

**OLD (v2.2):** Discharge battery to make room → wasteful cycling
**NEW (v2.3):** Switch to "Feed-in Priority" mode → solar goes to grid first!

When battery is full and high solar is coming:
- Switches inverter mode to prioritize grid export
- Solar flows: Grid (5kW) → Battery (overflow)
- **Zero clipping, minimal battery wear!**

### Benefits
- ✅ **Testable** - Mock any provider, test optimization in isolation
- ✅ **Maintainable** - Change one component without touching others
- ✅ **Extensible** - Add new tariffs or inverters easily
- ✅ **Observable** - Health status for every data source

---

## 🔧 Requirements

### Home Assistant Integrations

1. **AppDaemon 4.x** - Install via Add-on store
2. **Solax ModBus Integration** - For Solis/Solax inverter control
   - Provides battery, inverter, and power sensors
   - Required for timed charge/discharge slot control
   - **NEW:** Energy Storage Control Mode Switch support
3. **Octopus Energy Integration** (Official HACS integration)
   - Provides Agile pricing data
4. **Solcast Solar Integration** (HACS)
   - Provides solar forecast

### Supported Hardware

**Inverters:** 
- ✅ **Solis S6 Hybrid** (via solax_modbus) - Fully tested
- ✅ **Solis S6 with Mode Switch** - NEW in v2.3!
- ✅ Other Solis models with timed slot support (via solax_modbus)
- ⚠️ Solax inverters (should work but untested)
- 🔄 Other brands - Need custom interface implementation

**Mode Switch Support:**
The v2.3 architecture uses the inverter's **Energy Storage Control Mode Switch** for intelligent solar routing:
- `Self-Use - No Timed Charge/Discharge` → Solar to battery first
- `Feed-in priority` → Solar to grid first (clipping prevention!)

**Tariffs:**
- ✅ Octopus Agile (Import) - Required
- ✅ Octopus Agile Export - Optional (or fixed export rate)

---

## 📦 Installation

### Method 1: Direct Clone (Recommended)

1. SSH into your Home Assistant or use the Terminal add-on:

```bash
cd /config/appdaemon/apps
git clone https://github.com/rszemeti/SolarBat-AI.git solar_optimizer
cd solar_optimizer
```

2. Copy the example configuration:

```bash
cp apps/solar_optimizer/apps.yaml.example ../../solar_optimizer.yaml
```

3. Edit the configuration with your entity IDs:

```bash
nano ../../solar_optimizer.yaml
```

4. Restart AppDaemon:
   - Settings → Add-ons → AppDaemon → Restart

### Method 2: Manual Download

1. Download this repository as ZIP
2. Extract to `/config/appdaemon/apps/solar_optimizer/`
3. Copy `apps.yaml.example` to `/config/appdaemon/apps/solar_optimizer.yaml`
4. Edit with your entity IDs
5. Restart AppDaemon

---

## ⚙️ Configuration

### Quick Start Configuration

Edit `/config/appdaemon/apps/solar_optimizer.yaml`:

```yaml
solar_optimizer:
  module: solar_optimizer
  class: SmartSolarOptimizer
  
  # REQUIRED: Update these with YOUR entity IDs
  battery_soc: sensor.solax_battery_soc
  battery_capacity: sensor.solax_battery_capacity
  inverter_mode: select.solax_charger_use_mode
  
  # Inverter capability sensors (auto-detected)
  max_charge_rate: sensor.solax_battery_charge_max_current
  max_discharge_rate: sensor.solax_battery_discharge_max_current
  battery_voltage: sensor.solax_battery_voltage
  
  # Solar forecasting
  solcast_remaining: sensor.solcast_pv_forecast_forecast_remaining_today
  solcast_tomorrow: sensor.solcast_pv_forecast_forecast_tomorrow
  
  # Agile pricing - REPLACE xxxxx with YOUR MPAN
  agile_current: sensor.octopus_energy_electricity_xxxxx_current_rate
  agile_rates: event.octopus_energy_electricity_xxxxx_current_day_rates
```

See [Configuration Guide](docs/configuration.md) for complete options.

---

## 📊 Dashboard

Example Lovelace cards are provided in `/dashboards/`.

### Quick Dashboard Setup

Add these cards to your dashboard:

**1. Next Action Card** - Shows what the optimizer will do next

```yaml
# See dashboards/cards/next_action.yaml
```

**2. Wastage Alert Card** - Warns when solar will be wasted

```yaml
# See dashboards/cards/wastage_alert.yaml
```

**3. 24-Hour Plan Chart** - Visual timeline of the optimization plan

```yaml
# Requires: custom:apexcharts-card
# See dashboards/optimizer_dashboard.yaml for complete example
```

---

## 🏗️ Architecture (v2.3)

### Clean Separation of Concerns

```
┌──────────────────────────────────────────┐
│        DATA PROVIDERS (5)                │
│  ────────────────────────────────────    │
│  Import Pricing  (Octopus Agile + AI)    │
│  Export Pricing  (Fixed or dynamic)      │
│  Solar Forecast  (Solcast)               │
│  Load Forecast   (AI multi-method)       │
│  System State    (Inverter readings)     │
└──────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│         PLAN CREATOR                     │
│  Pure optimization logic                 │
│  No HA dependencies                      │
│  Fully testable                          │
└──────────────────────────────────────────┘
              ↓
         Plan Object
         (48 x 30-min slots)
              ↓
┌──────────────────────────────────────────┐
│        PLAN EXECUTOR                     │
│  Compares plan vs actual                 │
│  Writes only when different              │
│  Minimal inverter updates                │
└──────────────────────────────────────────┘
```

### Benefits
- **Testable:** Mock any provider to test optimization in isolation
- **Maintainable:** Change pricing logic without touching inverter control
- **Extensible:** Add new tariffs by creating a new provider
- **Observable:** Health status for each data source

---

## 🎯 How It Works

### Three-Way Control System

v2.3 uses a sophisticated three-way control strategy:

#### 1. Timed Charge Slots
```
When: Cheap import prices (arbitrage opportunities)
Control: number.solis_inverter_timed_charge_*
Effect: Grid charges battery to target SOC
Example: 02:00-02:30 charge to 90% at 13.27p/kWh
```

#### 2. Timed Discharge Slots
```
When: High export prices OR profitable arbitrage
Control: number.solis_inverter_timed_discharge_*
Effect: Battery discharges to grid at max rate
Example: 16:00-16:30 discharge to 20% at 25p/kWh
```

#### 3. Mode Switch (NEW in v2.3!)
```
Entity: select.solis_inverter_energy_storage_control_switch

Self-Use Mode:
  Solar → Battery first → Overflow to grid
  Use: Normal operation, battery has capacity
  
Feed-in Priority Mode:
  Solar → Grid first → Overflow to battery
  Use: Clipping prevention when battery full!
```

### Decision Priority

The optimizer makes decisions in this priority order:

1. **Clipping Prevention (Mode Switch)** - Battery full + high solar coming? Switch to Feed-in Priority to route solar to grid first
2. **Arbitrage Trading** - Buy cheap (13p), sell expensive (25p) = profit!
3. **Deficit Prevention** - Charge if battery low and expensive prices ahead
4. **Wastage Prevention** - Don't charge before big solar day
5. **Self Use (Default)** - Normal operation, battery-first solar routing

### Clipping Prevention: The Breakthrough

**The Problem:**
```
Battery: 95% full (0.5kWh space remaining)
Solar:   9kW arriving in 2 hours
Export:  5kW DNO limit
Result:  4kW clipped! ❌
```

**OLD Solution (v2.2):**
```
1. Force Discharge: 95% → 50%
2. Solar arrives: charges 50% → 95%
Result: ✓ No clipping, but battery cycled unnecessarily
```

**NEW Solution (v2.3 - Mode Switch):**
```
1. Switch to "Feed-in Priority" mode
2. Solar arrives (9kW):
   - 5kW → Grid (DNO limit)
   - 4kW → Battery (fills 95% → 99%)
3. Switch back to "Self-Use" when full
Result: ✓ No clipping, minimal battery wear! 🎉
```

### Inverter Modes (v2.3)

| Control Type | Purpose | When Used |
|--------------|---------|-----------|
| **Timed Charge Slot** | Buy cheap import | Negative/low Agile prices (<15p) |
| **Timed Discharge Slot** | Sell high export | Profitable arbitrage (export > import + 1p) |
| **Feed-in Priority Mode** | Route solar to grid first | Clipping prevention (battery full + high solar) |
| **Self Use Mode** | Battery-first solar routing | Default operation |

### AI Load Forecasting

Multi-method ensemble prediction:

```
┌────────────────────────────────────┐
│  Yesterday same time    (weight 3) │
│  Last week same time    (weight 2) │  → Weighted
│  30-day hour average    (weight 1) │     Average
│  Recent trend analysis  (weight 1.5)│
└────────────────────────────────────┘
         ↓
   Confidence Score
   (high/medium/low/very_low)
```

### Cost Optimization Logic

**Example Decision Tree:**
```
Battery 45%, Solar 2kW, Load 1kW
Import 13.27p, Export 15.00p

1. Check arbitrage: 15.00p > 13.27p + 1.0p ✓
   → Force Charge (buy cheap, sell expensive later!)
   
2. Solar surplus: 2kW - 1kW = 1kW
   → Charge from solar simultaneously
   
3. Net result: Battery charges, cost = 13.27p for grid import
   → Later export at 15.00p = 1.73p profit per kWh!
```
```

### Learning and Adaptation

The system learns from your actual usage:

- **Consumption patterns** - Tracks hourly usage by weekday/weekend
- **Solar accuracy** - Compares Solcast forecasts to actual generation
- **Wastage events** - Records when battery was full but solar was available
- **Price patterns** - Understands typical Agile pricing for your region

---

## 🔍 Monitoring

### AppDaemon Logs

Check logs for optimizer activity:

```bash
tail -f /config/appdaemon/appdaemon.log | grep "Solar"
```

### Sensors Created

The optimizer creates these sensors in Home Assistant:

- `sensor.solar_optimizer_plan` - The 24-hour plan with all details
- `sensor.solar_wastage_risk` - Current solar wastage risk (kWh)
- `sensor.solar_optimizer_capabilities` - Detected inverter capabilities

### Understanding the Plan

Each hourly step shows:
- **Mode**: Force Charge / Grid First / Self Use
- **Reason**: Why this decision was made
- **Battery SOC**: Expected battery level
- **Cost**: Estimated grid import cost
- **Prices**: Both 30-min Agile slots

---

## 🐛 Troubleshooting

### No Plan Generated

**Check AppDaemon logs:**
```bash
tail -f /config/appdaemon/appdaemon.log
```

**Common issues:**
- Missing sensor entities (check entity IDs in config)
- Octopus integration not providing Agile rates
- Solcast not configured or API limit reached

**Solution:**
```bash
# Verify all sensors exist
ha states sensor.solax_battery_soc
ha states sensor.octopus_energy_electricity_xxxxx_current_rate
```

### Mode Changes Too Frequently

The optimizer has built-in rate limiting but you can adjust:

```yaml
min_change_interval: 7200  # Increase to 2 hours
```

### Pre-emptive Discharge Not Triggering

**Check settings:**
```yaml
enable_preemptive_discharge: true
min_wastage_threshold: 1.0  # Lower to 0.5 to trigger sooner
min_benefit_threshold: 0.25  # Lower to require less financial benefit
```

**Check wastage sensor:**
- Look at `sensor.solar_wastage_risk`
- If it's 0, there's no wastage risk detected

### Inverter Not Responding to Mode Changes

**Verify:**
1. The `inverter_mode` entity ID is correct
2. The select options match your inverter exactly (case-sensitive)
3. The solax_modbus integration is working

**Test manually:**
```yaml
# Try changing mode manually via Developer Tools → Services
service: select.select_option
target:
  entity_id: select.solax_charger_use_mode
data:
  option: "Self Use"
```

---

## 🤝 Contributing

Contributions welcome! 

### How to Contribute

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Test thoroughly
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Areas for Contribution

- Support for other inverter brands
- Support for other tariffs (Octopus Flux, etc.)
- Improved solar forecasting (integration with other services)
- Machine learning for consumption prediction
- Home Assistant UI panel
- Documentation improvements

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- Built for the Home Assistant community
- Inspired by Predbat (but with less complexity and inverter writes!)
- Thanks to all contributors and testers
- Special thanks to the Solax ModBus integration developers
- Thanks to Octopus Energy for their innovative Agile tariff

---

## 📞 Support

### Getting Help

1. **Check the docs** - [docs/](docs/) folder has detailed guides
2. **Search issues** - Your question may already be answered
3. **Open an issue** - Include logs and configuration (remove sensitive data!)
4. **Discussions** - For general questions and sharing experiences

### Useful Links

- [Home Assistant Community Forum](https://community.home-assistant.io/)
- [Octopus Energy Integration](https://github.com/BottlecapDave/HomeAssistant-OctopusEnergy)
- [Solcast Integration](https://github.com/BJReplay/ha-solcast-solar)
- [Solax ModBus Integration](https://github.com/wills106/homeassistant-solax-modbus)

---

## 📈 Roadmap

### v2.1 (Planned)
- [ ] Support for Octopus Flux tariff
- [ ] Better handling of battery degradation
- [ ] Cost tracking and savings reporting
- [ ] Mobile notifications for key events

### v2.2 (Future)
- [ ] Support for multiple batteries
- [ ] Integration with electric vehicle charging
- [ ] Weather-aware optimization
- [ ] Machine learning consumption predictions

---

## ⚠️ Disclaimer

This software is provided as-is. Always monitor your system's behavior initially and ensure it's working as expected. The authors are not responsible for any issues with your inverter, battery, or electricity costs.

**Best practices:**
- Start with conservative settings
- Monitor for the first few days
- Keep `min_change_interval` at least 1 hour initially
- Don't discharge below 20% SOC until you're confident it's working

---

**Version:** 2.0.0  
**Last Updated:** January 2026  
**Maintained by:** Community contributors
