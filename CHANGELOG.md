# Changelog

All notable changes to SolarBat-AI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-01-11

### Added
- **Pre-emptive discharge optimization** - Automatically drains battery before solar overflow to prevent wastage
- **30-minute Agile pricing support** - Fully aware of half-hourly price slots
- **Dynamic inverter capability detection** - Auto-reads charge/discharge rates, export limits
- **Wastage risk sensor** - Real-time alert when solar will be wasted
- **Round-trip efficiency modeling** - Accounts for battery charge/discharge losses
- **Enhanced price analysis** - Compares against historical median prices
- **Export tariff support** - Handles Agile Export and similar tariffs
- **Comprehensive logging** - Detailed decision explanations
- **Dashboard examples** - Ready-to-use Lovelace cards
- **Complete documentation** - Installation, configuration, troubleshooting guides

### Changed
- **Complete code rewrite** - Clean, maintainable architecture
- **Hourly planning with 30-min price awareness** - Better than Predbat's complex approach
- **Improved wastage calculation** - Accounts for export limits and efficiency
- **Better battery simulation** - Uses actual inverter limits

### Fixed
- **Excessive inverter writes** - Configurable rate limiting prevents spam
- **Mode switching thrashing** - Intelligent hysteresis
- **Inaccurate planning** - Uses real inverter capabilities vs assumptions

### Breaking Changes
- Configuration structure changed (see Migration Guide)
- Requires additional sensor entities for capability detection
- History file format updated (auto-migrates on first run)

## [1.0.0] - 2025-XX-XX

### Initial Release
- Basic optimization for Octopus Agile
- Simple mode switching
- Basic solar forecast integration

---

## Upgrade Notes

### From v1.x to v2.0

**Before upgrading:**

1. Backup your configuration:
   ```bash
   cp /config/appdaemon/apps/solar_optimizer.yaml /config/solar_optimizer.yaml.v1.backup
   ```

2. Backup history (will be auto-migrated but good to have):
   ```bash
   cp /config/appdaemon/solar_optimizer_history.json /config/solar_optimizer_history.json.v1.backup
   ```

**After upgrading:**

1. Update configuration with new required sensors (see Configuration Guide)
2. Add inverter capability sensors
3. Configure pre-emptive discharge settings (optional)
4. Test for 24 hours with conservative settings

**Key differences:**

- Now requires capability sensors (max_charge_rate, max_discharge_rate, etc.)
- Pre-emptive discharge is NEW - start with `enable_preemptive_discharge: false`
- min_change_interval now more important - start at 7200 (2 hours)

---

## Roadmap

### v2.1 (Q2 2026)
- [ ] Octopus Flux tariff support
- [ ] Battery degradation modeling
- [ ] Cost tracking dashboard
- [ ] Mobile notifications
- [ ] Improved consumption prediction

### v2.2 (Q3 2026)
- [ ] Multiple battery support
- [ ] EV charging integration
- [ ] Weather-aware optimization
- [ ] Machine learning predictions
- [ ] Custom automation triggers

### v3.0 (Q4 2026)
- [ ] Complete UI panel
- [ ] Built-in Home Assistant integration (no AppDaemon needed)
- [ ] Multi-inverter support
- [ ] Advanced grid services (demand response, etc.)
