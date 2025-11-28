# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2024-11-16

### Added
- Initial release
- ML-based energy demand prediction using Gradient Boosting
- Solar generation forecasting via Solcast integration
- Octopus Energy tariff integration for dynamic pricing
- Battery optimization using linear programming (PuLP)
- Home Assistant sensor creation and updates
- REST API endpoints for external access
- Web interface dashboard
- Automatic update cycle (configurable interval)
- Support for 48-hour optimization window
- Example automations for battery control
- Comprehensive documentation

### Features
- Predicts energy demand for next 48 hours (96 x 30-min slots)
- Optimizes battery charge/discharge to minimize costs
- Accounts for battery degradation in optimization
- Supports dynamic import/export tariffs
- Configurable battery parameters (capacity, efficiency, limits)
- Web UI for monitoring at http://homeassistant.local:8099
- Full REST API for integration

### Supported Integrations
- Octopus Energy (import/export rates)
- Solcast PV Forecast (solar generation)
- Any battery system with SOC sensor

### Requirements
- Home Assistant
- Python 3.11+
- Octopus Energy integration (optional but recommended)
- Solcast integration (optional but recommended)
- Battery with SOC sensor

## Future Enhancements (Roadmap)

- [ ] Support for Forecast.Solar as alternative to Solcast
- [ ] Multi-battery support
- [ ] EV charging optimization integration
- [ ] Weather-aware predictions
- [ ] Historical performance tracking
- [ ] Alternative optimization algorithms
- [ ] Support for additional tariff providers
- [ ] Advanced ML models (LSTM, Prophet)
- [ ] Grafana dashboard templates
