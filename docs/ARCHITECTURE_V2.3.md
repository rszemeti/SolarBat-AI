# SolarBat-AI v2.3 Architecture

## Overview

v2.3 introduces a clean **Provider/Consumer** architecture with clear separation of concerns.

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                    DATA PROVIDERS                             │
│  (Independent, testable, swappable components)               │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ImportPricingProvider                                       │
│    └─ Future import electricity prices (Octopus Agile)      │
│                                                               │
│  ExportPricingProvider                                       │
│    └─ Future export electricity prices (Agile Export/Fixed)  │
│                                                               │
│  SolarForecastProvider                                       │
│    └─ PV generation forecast (Solcast)                      │
│                                                               │
│  LoadForecastProvider                                        │
│    └─ House consumption forecast (AI-based)                 │
│                                                               │
│  SystemStateProvider                                         │
│    └─ Current battery/inverter state (Solis)               │
│                                                               │
└──────────────────────────────────────────────────────────────┘
                            ↓
                   All providers implement
                      DataProvider ABC
                            ↓
┌──────────────────────────────────────────────────────────────┐
│                     PLAN CREATOR                              │
│                                                               │
│  Consumes data from all providers                           │
│  Runs optimization algorithm                                │
│  Produces JSON plan with actions for each 30-min slot       │
│                                                               │
│  Output: Plan object with:                                  │
│    - Timestamp                                              │
│    - List of 48 time slots (24 hours)                      │
│    - Each slot: mode, SOC target, action, cost             │
│    - Metadata: confidence, data sources used               │
└──────────────────────────────────────────────────────────────┘
                            ↓
                      Plan Object
                  (Pure data, no logic)
                            ↓
┌──────────────────────────────────────────────────────────────┐
│                    PLAN EXECUTOR                              │
│                                                               │
│  Reads current plan                                         │
│  Compares to current system state                           │
│  Determines what inverter changes are needed                │
│  Writes to inverter ONLY if different from current         │
│  Logs all actions taken                                     │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

## Provider Interface

All providers implement `DataProvider` ABC:

```python
class DataProvider(ABC):
    def setup(self, config: Dict) -> bool:
        """Setup with configuration"""
        
    def get_data(self, **kwargs) -> Any:
        """Get provider's data"""
        
    def get_health(self) -> Dict:
        """Health check - status, confidence, last update"""
        
    def clear_cache(self):
        """Clear any cached data"""
```

## Provider Details

### 1. ImportPricingProvider
- **Purpose**: Future import electricity prices
- **Source**: Octopus Agile API via HA integration
- **Returns**: List of {time, price, is_predicted} dicts
- **Features**:
  - Auto-discovers Octopus entities
  - Predicts prices for 4pm gap
  - Reports confidence level

### 2. ExportPricingProvider
- **Purpose**: Future export electricity prices
- **Source**: Octopus Agile Export / Fixed rate
- **Returns**: List of {time, price} dicts
- **Features**:
  - Supports dynamic (Agile Export) or fixed rates
  - Can be constant if on fixed export tariff

### 3. SolarForecastProvider
- **Purpose**: PV generation forecast
- **Source**: Solcast via HA integration
- **Returns**: List of {time, kw} dicts
- **Features**:
  - Parses Solcast detailedForecast
  - Supports solar_scaling for testing
  - Validates forecast quality

### 4. LoadForecastProvider
- **Purpose**: House consumption forecast
- **Source**: HA history + AI prediction
- **Returns**: List of {time, kw, confidence} dicts
- **Features**:
  - Multi-method prediction (yesterday, last week, average, trend)
  - Confidence weighting
  - Learns from your patterns

### 5. SystemStateProvider
- **Purpose**: Current battery/inverter state
- **Source**: Solis inverter via solax_modbus
- **Returns**: Dict with SOC, power, limits, capabilities
- **Features**:
  - Real-time state reading
  - Capability detection
  - Time slot management

## Plan Creator

**Input**: Data from all 5 providers
**Output**: Optimized plan

```python
{
    'timestamp': datetime,
    'slots': [
        {
            'time': datetime,
            'mode': 'Force Charge|Force Discharge|Self Use',
            'action': 'Human readable description',
            'soc_target': 75.0,
            'import_price': 15.23,
            'export_price': 15.00,
            'solar_kw': 2.5,
            'load_kw': 1.2,
            'cost': -5.23,  # Negative = revenue
            'cumulative_cost': 12.45
        },
        # ... 47 more slots
    ],
    'metadata': {
        'total_cost': 12.45,
        'data_sources': {
            'import_pricing': 'healthy',
            'export_pricing': 'healthy',
            'solar': 'healthy',
            'load': 'degraded',  # Low confidence
            'state': 'healthy'
        },
        'confidence': 'high'
    }
}
```

## Plan Executor

**Input**: Plan object from creator
**Output**: Inverter state changes

**Logic**:
1. Get current time slot from plan
2. Read current inverter state
3. Compare plan.mode vs actual mode
4. Compare plan.soc_target vs actual target
5. If different → write to inverter
6. If same → skip (no unnecessary writes)
7. Log all decisions

**Example**:
```
Plan says: Force Charge to 80% at 02:00
Current:   Self Use mode, no charge target
Action:    Write charge slot 02:00-02:30, SOC 80%
Log:       "Applied Force Charge mode for 02:00-02:30 (plan step 9)"
```

## Benefits

### 1. Testability
```python
# Test plan creator with mock providers
mock_pricing = MockImportPricing(prices=[...])
mock_solar = MockSolarProvider(forecast=[...])
plan = PlanCreator([mock_pricing, mock_solar, ...])
```

### 2. Swappable Implementations
```python
# Switch from Octopus to Tracker
from providers.octopus_tracker_provider import TrackerPricingProvider
pricing = TrackerPricingProvider(hass)  # Same interface!
```

### 3. Independent Development
- Can work on LoadForecastProvider without touching anything else
- Each provider has its own tests
- Providers can be used by other apps

### 4. Monitoring & Health
```python
for provider in [import_pricing, export_pricing, solar, load, state]:
    health = provider.get_health()
    if health['status'] != 'healthy':
        log_warning(f"{provider.name}: {health['message']}")
```

### 5. Caching
Each provider manages its own cache:
- ImportPricing: Cache for 30 min (prices don't change)
- Solar: Cache for 1 hour (Solcast updates hourly)
- Load: No cache (always predict fresh)
- State: No cache (real-time data)

## Migration from v2.2

**What's changing**:
- `pricing_provider_octopus_agile.py` → `providers/import_pricing_provider.py`
- `cost_optimizer.py` → `plan_creator.py`
- New: `providers/export_pricing_provider.py`
- New: `providers/solar_forecast_provider.py`
- New: `providers/load_forecast_provider.py`
- New: `providers/system_state_provider.py`
- New: `plan_executor.py`

**What's preserved**:
- All existing logic (just reorganized)
- Test harness still works
- Web visualization still works
- AI load prediction kept
- Arbitrage logic kept
- Clipping prevention kept

## File Structure

```
apps/solar_optimizer/
├── providers/
│   ├── __init__.py
│   ├── base_provider.py              # ABC for all providers
│   ├── import_pricing_provider.py    # Octopus Agile import
│   ├── export_pricing_provider.py    # Export pricing
│   ├── solar_forecast_provider.py    # Solcast
│   ├── load_forecast_provider.py     # AI consumption
│   └── system_state_provider.py      # Inverter state
├── plan_creator.py                    # Optimization engine
├── plan_executor.py                   # Writes to inverter
└── solar_optimizer.py                 # Main app (orchestrator)
```

## Implementation Notes

- All providers are **stateless** (except cache)
- Plan creator is **pure function** (providers → plan)
- Plan executor is **idempotent** (same plan = same outcome)
- Everything is **independently testable**
- Clean **dependency injection** throughout
