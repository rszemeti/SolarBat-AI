# SolarBat-AI v2.0

Intelligent battery management for solar + storage systems with Octopus Agile pricing.

**Built for the Home Assistant community to optimize solar battery systems and maximize savings with time-of-use electricity tariffs.**

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Version](https://img.shields.io/badge/version-2.0.0-green.svg)
![HA](https://img.shields.io/badge/Home%20Assistant-AppDaemon-blue.svg)

---

## 🌟 Features

- ✅ **24-Hour Optimization Planning** - Full day lookahead with hourly strategy
- ✅ **Pre-emptive Discharge** - Automatically drains battery before solar overflow to prevent wastage
- ✅ **Octopus Agile Aware** - Optimizes for 30-minute pricing slots
- ✅ **Auto Capability Detection** - Reads inverter limits (charge/discharge rates, export limits)
- ✅ **Historical Learning** - Adapts to your actual consumption patterns and solar forecast accuracy
- ✅ **Zero Inverter Spam** - Configurable minimum interval between mode changes
- ✅ **Export Tariff Support** - Handles Agile Export or similar tariffs
- ✅ **Transparency** - Clear logging and dashboard showing all decisions and reasoning

---

## 📋 What's New in v2.0

### Major Improvements
- **30-minute Agile pricing support** - Fully aware of half-hourly price variations
- **Dynamic inverter capability detection** - Auto-reads charge/discharge limits from inverter
- **Pre-emptive discharge optimization** - Prevents solar wastage by strategically draining battery
- **Enhanced wastage detection** - Calculates expected solar overflow accounting for export limits
- **Round-trip efficiency modeling** - Accounts for charge/discharge losses in cost calculations
- **Improved price analysis** - Compares current prices against historical medians

### Breaking Changes from v1.x
- Configuration structure updated (see Migration Guide)
- Requires additional sensor entities for capability detection
- History file format changed (will auto-upgrade on first run)

---

## 🔧 Requirements

### Home Assistant Integrations

1. **AppDaemon 4.x** - Install via Add-on store
2. **Solax ModBus Integration** - For Solis/Solax inverter control
   - Provides battery, inverter, and power sensors
   - Required for timed charge/discharge slot control
3. **Octopus Energy Integration** (Official HACS integration)
   - Provides Agile pricing data
4. **Solcast Solar Integration** (HACS)
   - Provides solar forecast

### Supported Hardware

**Inverters:** 
- ✅ **Solis S6 Hybrid** (via solax_modbus) - Fully tested
- ✅ Other Solis models with timed slot support (via solax_modbus)
- ⚠️ Solax inverters (should work but untested)
- 🔄 Other brands - Need custom interface implementation

**Note:** The system uses an abstraction layer, so other inverter brands can be supported by implementing a custom interface class.

**Tariffs:**
- ✅ Octopus Agile (Import) - Required
- ✅ Octopus Agile Export - Optional

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

## 🎯 How It Works

### Decision Priority

The optimizer makes decisions in this priority order:

1. **Pre-emptive Discharge** - If solar will be wasted, discharge battery (Force Discharge if available, else Self Use with consumption drain)
2. **Force Charge** - Charge from grid during negative or very cheap pricing (<3p/kWh)
3. **Grid First** - Use grid power during cheap periods, save battery for expensive times
4. **Self Use** - Standard battery operation - use solar and battery to avoid grid import

### Inverter Modes

| Mode | Description | When Used |
|------|-------------|-----------|
| **Force Discharge** | Actively discharge battery to grid at max rate | Pre-emptive discharge when wastage detected (if inverter supports it) |
| **Force Charge** | Charge battery from grid at max rate | Negative pricing, very cheap electricity |
| **Grid First** | Use grid power, don't discharge battery | Cheap periods with good solar forecast |
| **Self Use** | Use solar + battery, minimize grid import | Default mode, expensive periods |

**Note:** Not all inverters support Force Discharge mode. If unavailable, pre-emptive discharge uses Self Use mode and relies on household consumption to drain the battery (slower but still effective).

### Pre-emptive Discharge Logic

The most innovative feature - prevents solar wastage:

```
Morning (6am):
  - Battery: 85%
  - Forecast: 25kWh solar today
  - Expected consumption: 15kWh
  - Battery space: 1.5kWh
  
  Problem: 25kWh solar > 1.5kWh space + 15kWh consumption
  Solution: Discharge 5kWh between 6-9am
  Result: Battery ready to absorb solar, nothing wasted
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
