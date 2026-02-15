# Architecture

## Overview

SolarBat-AI uses a provider-based architecture where data sources are decoupled from planning logic. This makes it easy to swap pricing providers, add new inverter interfaces, or test with mock data.

```
┌─────────────────────────────────────────────────┐
│              solar_optimizer.py                   │
│           (Main Orchestrator / Hass.Hass)         │
│                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Import   │  │ Solar    │  │ Load     │       │
│  │ Pricing  │  │ Forecast │  │ Forecast │       │
│  │ Provider │  │ Provider │  │ Provider │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
│       └──────────────┼──────────────┘             │
│                      ▼                            │
│              ┌──────────────┐                     │
│              │   Planner    │                     │
│              │ (Rule/LP/ML) │                     │
│              └──────┬───────┘                     │
│                     ▼                             │
│              ┌──────────────┐                     │
│              │Plan Executor │                     │
│              └──────┬───────┘                     │
│                     ▼                             │
│              ┌──────────────┐                     │
│              │  Inverter    │                     │
│              │  Interface   │                     │
│              └──────────────┘                     │
└─────────────────────────────────────────────────┘
```

## Data Providers (`providers/`)

Each provider handles one data source with caching and error handling:

| Provider | Source | Output |
|----------|--------|--------|
| `ImportPricingProvider` | Octopus Agile API | 48 half-hour price slots |
| `ExportPricingProvider` | Agile Export or fixed rate | Export prices per slot |
| `SolarForecastProvider` | Solcast integration | Hourly kW generation forecast |
| `LoadForecastProvider` | Historical consumption patterns | Expected kW per hour |
| `SystemStateProvider` | HA sensors | Battery SOC, PV power, grid power |
| `TimeSeriesPredictor` | Historical data | Weighted predictions using yesterday-first strategy |

## Planners (`planners/`)

Three planning strategies available:

- **RuleBasedPlanner** — Fast heuristic decisions based on price thresholds. Recommended for most users.
- **LPPlanner** — Linear programming optimisation for maximum profit. Best results but requires `scipy`.
- **MLPlanner** — Machine learning approach. Experimental, needs training data.

## Inverter Interface

The inverter abstraction layer allows supporting different hardware:

- `inverter_interface_solis6.py` — Solis/Solax via solax_modbus (current)
- `inverter_interface_base.py` — Base class for adding new inverters

## Web Dashboard

The optimizer registers an AppDaemon HTTP endpoint serving a self-contained HTML dashboard with inlined CSS/JS. Templates live in `apps/solar_optimizer/templates/` and are rendered server-side with simple `{{placeholder}}` substitution.

## Forecast Accuracy Tracking

`forecast_accuracy_tracker.py` stores daily prediction vs actual values in a JSON file. Each plan generation records predictions; a daily 01:30 job records yesterday's actuals from the hourly consumption history.
