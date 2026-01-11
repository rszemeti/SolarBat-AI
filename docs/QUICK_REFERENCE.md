# Quick Reference

Fast answers to common questions.

## Installation

```bash
cd /config/appdaemon/apps
git clone https://github.com/rszemeti/SolarBat-AI.git solar_optimizer
cp solar_optimizer/apps/solar_optimizer/apps.yaml.example solar_optimizer.yaml
nano solar_optimizer.yaml  # Edit with your entity IDs
# Restart AppDaemon
```

## Key Sensors

| Sensor | Description |
|--------|-------------|
| `sensor.solar_optimizer_plan` | 24-hour optimization plan |
| `sensor.solar_wastage_risk` | Solar wastage risk (kWh) |
| `sensor.solar_optimizer_capabilities` | Detected inverter limits |

## Modes Explained

| Mode | When Used | Purpose |
|------|-----------|---------|
| **Self Use** | Default, expensive periods | Use solar + battery, avoid grid |
| **Grid First** | Cheap periods, good solar coming | Use grid, save battery |
| **Force Charge** | Negative/very cheap prices | Charge battery from grid |

## Key Configuration Options

```yaml
# Pre-emptive discharge
enable_preemptive_discharge: true    # Enable wastage prevention
min_wastage_threshold: 1.0           # Min kWh to trigger (lower = more aggressive)
min_benefit_threshold: 0.50          # Min £ benefit (lower = more aggressive)
preemptive_discharge_min_soc: 50     # Don't discharge below this %

# Behavior
min_change_interval: 3600            # Min seconds between changes
```

## Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| No plan generated | Check logs, verify all sensors exist |
| Too many mode changes | Increase `min_change_interval` to 7200 |
| Wastage not detecting | Lower `min_wastage_threshold` to 0.5 |
| Pre-discharge too aggressive | Increase `min_benefit_threshold` to 1.0 |
| Mode changes ignored | Check inverter mode entity ID and options |

## Useful Commands

```bash
# View logs
tail -f /config/appdaemon/appdaemon.log | grep "Solar"

# Check sensor status
ha states sensor.solar_optimizer_plan

# Restart AppDaemon
ha addons restart a0d7b954_appdaemon

# Check plan attributes
ha states sensor.solar_optimizer_plan --attributes
```

## Default Values (if sensors unavailable)

- Battery capacity: 10.0 kWh
- Max charge rate: 2.0 kW
- Max discharge rate: 3.0 kW
- Battery voltage: 51.2 V
- Export limit: 3.68 kW

## Understanding Wastage Alerts

**Alert Level: Low** (< 1 kWh)
- Minor wastage, may not trigger discharge
- Monitor but no action needed

**Alert Level: Medium** (1-3 kWh)
- Moderate wastage risk
- Pre-discharge likely if enabled and beneficial

**Alert Level: High** (> 3 kWh)
- Significant wastage
- Pre-discharge highly recommended
- Check battery is not already at min SOC

## Decision Logic Priority

1. **Pre-emptive discharge** (morning, if wastage detected)
2. **Force charge** (negative or <3p pricing)
3. **Grid first** (cheap grid, good solar coming)
4. **Self use** (expensive periods, poor solar)

## Files and Locations

```
/config/appdaemon/apps/solar_optimizer/     # Application files
/config/appdaemon/apps/solar_optimizer.yaml # Your configuration
/config/appdaemon/solar_optimizer_history.json # Historical data
/config/appdaemon/appdaemon.log             # Logs
```

## Important Links

- [GitHub Repository](https://github.com/rszemeti/SolarBat-AI)
- [Full Documentation](docs/)
- [Configuration Guide](docs/configuration.md)
- [Installation Guide](docs/installation.md)

## Support

1. Check logs first
2. Review configuration
3. Search GitHub issues
4. Open new issue with logs + config

## Version

**Current:** 2.0.0  
**Released:** January 2026  
**License:** MIT
