# Pricing System

## How Agile Prices Work

Octopus Agile publishes half-hourly electricity prices, typically available from 4pm for the following day. Prices can range from negative (you're paid to use electricity) to 35p+ during peak periods.

SolarBat-AI exploits this by:
- **Charging** during the cheapest slots (typically 01:00-05:00, around 5-10p/kWh)
- **Discharging/exporting** during expensive peaks (typically 16:00-19:00, 30-45p/kWh)
- **Self-using** solar during the day to avoid imports

## Price Thresholds

The optimizer dynamically calculates thresholds based on the day's price distribution:

- **Charge threshold** — Bottom 20% of prices → Force Charge
- **Discharge threshold** — Top 30% of prices → Force Discharge (if profitable)
- **Profit margin** — Export price must exceed import price by enough to cover round-trip losses (~15%)

## Predicted vs Known Prices

When Agile rates haven't been published yet (before 4pm for next day), the optimizer uses the `TimeSeriesPredictor` to estimate future prices based on historical patterns. These predicted slots are marked with `*` in the plan table.

Confidence levels:
- **HIGH** — All prices from Agile API
- **MEDIUM** — Mix of known and predicted
- **LOW** — Mostly predicted prices

## Export Tariff

If `has_export: true` is set, the optimizer factors in export revenue when deciding whether to discharge. Without an export tariff, discharge decisions are based purely on avoiding expensive import periods.
