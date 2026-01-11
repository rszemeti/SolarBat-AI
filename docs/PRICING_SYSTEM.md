# Pricing System Documentation

## Overview

The pricing system uses an abstraction layer to provide electricity prices for planning, handling both known prices (from integrations) and predicted prices (when data is unavailable).

## Architecture

```
┌─────────────────────────────────────┐
│       pricing_provider_base.py      │
│       (Abstract Interface)          │
│                                     │
│  • get_prices_for_planning()       │
│  • predict_price()                  │
│  • record_price()                   │
└──────────────┬──────────────────────┘
               │
               │ implements
               ▼
┌─────────────────────────────────────┐
│  pricing_provider_octopus_agile.py  │
│  (Octopus Agile Implementation)     │
│                                     │
│  • Handles 30-min Agile slots      │
│  • Manages 4pm price updates        │
│  • Predicts missing prices          │
└─────────────────────────────────────┘
```

## The Problem

**Octopus Agile publishes prices around 4pm each day for the next day.**

When planning at 10am:
- ✅ Current day prices: Available (00:00-23:30)
- ❌ Next day prices: Not available yet (00:00-23:30)
- ❌ Total gap: ~14 hours missing

**Without prediction:** Can only plan ~14 hours ahead  
**With prediction:** Can plan full 24 hours ahead

## Solution: Hybrid Known + Predicted Prices

The pricing provider:

1. **Gets known prices** from Octopus integration
2. **Fills gaps** with predicted prices
3. **Records actual prices** to improve predictions
4. **Marks which prices are predicted** for confidence tracking

## Prediction Methods

Predictions use multiple fallback strategies:

### 1. Yesterday Same Time (Best)
- Most recent similar data
- **Confidence:** Medium
- **Example:** Tuesday 18:00 → Monday 18:00

### 2. Last Week Same Time
- Same day of week
- **Confidence:** Low  
- **Example:** Tuesday 18:00 → Last Tuesday 18:00

### 3. Historical Hour Average
- Average of all recorded prices for this hour
- **Confidence:** Medium
- **Example:** Average of all 18:00 prices in history

### 4. Overall Average (Fallback)
- Average of all prices or 24.5p/kWh default
- **Confidence:** Low
- **Example:** When no history available

## Usage in Planner

```python
# Initialize pricing provider
pricing = OctopusAgilePricingProvider(hass)
pricing.setup({
    'current_rate_sensor': 'sensor.octopus_energy_electricity_xxxxx_current_rate',
    'rates_event': 'event.octopus_energy_electricity_xxxxx_current_day_rates'
})

# Get 24 hours of prices (known + predicted)
price_data = pricing.get_prices_with_confidence(hours=24)

print(f"Known: {price_data['hours_known']:.1f}h")
print(f"Predicted: {price_data['hours_predicted']:.1f}h")
print(f"Confidence: {price_data['confidence']}")

# Use prices for planning
for price in price_data['prices']:
    hour = price['start'].hour
    price_value = price['price']
    is_predicted = price['is_predicted']
    
    if is_predicted:
        print(f"{hour:02d}:00 = {price_value:.2f}p (predicted: {price['prediction_method']})")
    else:
        print(f"{hour:02d}:00 = {price_value:.2f}p (known)")
```

## Example Output

**10am on Tuesday (before 4pm update):**

```
Octopus Agile: 14.0 hours of prices available until 23:30 11/01
Known: 14.0h
Predicted: 10.0h
Confidence: medium

Prices:
10:00 = 15.23p (known)
11:00 = 14.87p (known)
...
23:00 = 18.45p (known)
00:00 = 17.20p (predicted: yesterday_same_time)  ← Tomorrow predicted
01:00 = 16.85p (predicted: yesterday_same_time)
...
09:00 = 15.10p (predicted: yesterday_same_time)
```

**5pm on Tuesday (after 4pm update):**

```
Octopus Agile: 32.0 hours of prices available until 23:30 12/01
Known: 24.0h
Predicted: 0.0h
Confidence: high

All prices are known - no predictions needed!
```

## Confidence Levels

| Predicted Hours | Confidence | Planning Reliability |
|----------------|------------|---------------------|
| 0 hours | **High** | Excellent - all known |
| 1-6 hours | **Medium** | Good - mostly known |
| 6+ hours | **Low** | Acceptable - many predictions |

## Price Statistics

The provider calculates statistics for decision-making:

```python
stats = price_data['statistics']
print(f"Min: {stats['min']:.2f}p")
print(f"Max: {stats['max']:.2f}p")
print(f"Avg: {stats['avg']:.2f}p")
print(f"Median: {stats['median']:.2f}p")
```

## Historical Learning

The system learns from actual prices:

1. **Record every price** as it becomes active
2. **Keep 30 days** of history
3. **Use for predictions** when needed
4. **Improve over time** as more data collected

## Benefits

### 1. Always Can Plan 24 Hours
- Even at 10am (before 4pm update)
- Uses predictions to fill gaps
- Planner never starved of data

### 2. Transparent Predictions
- Clearly marked which prices are predicted
- Includes prediction method
- Confidence levels provided

### 3. Adapts to Your Pattern
- Learns your actual price patterns
- Yesterday same time = your local pattern
- Improves predictions over time

### 4. Handles Update Timing
- Knows prices update around 4pm
- Can detect when update is expected
- Can identify gaps in data

## Edge Cases Handled

### Case 1: First Run (No History)
**Solution:** Uses sensible default (24.5p/kWh average)

### Case 2: Price Update Delay
**Solution:** Continues with predictions until new prices arrive

### Case 3: Integration Offline
**Solution:** Uses all predictions with low confidence warning

### Case 4: Partial Data
**Solution:** Mixes known + predicted seamlessly

## Future Enhancements

### Machine Learning Predictions
Could upgrade prediction to use:
- Time series forecasting (ARIMA, Prophet)
- Weather correlation (wind/solar affects Agile)
- Historical pattern recognition
- Multi-day patterns

### Multiple Tariffs
Could add providers for:
- Octopus Flux (static 3-rate)
- Octopus Go (cheap overnight)
- Economy 7 (fixed cheap overnight)
- Fixed rate tariffs

## Configuration

```yaml
# In apps.yaml
pricing:
  provider: octopus_agile  # or 'octopus_flux', 'economy7', etc.
  
  # Octopus Agile specific
  current_rate_sensor: sensor.octopus_energy_electricity_xxxxx_current_rate
  rates_event: event.octopus_energy_electricity_xxxxx_current_day_rates
  export_rate_sensor: sensor.octopus_energy_electricity_export_current_rate  # optional
```

## Testing Predictions

To test the prediction system:

```python
# Simulate being at 10am (14 hours known, 10 predicted)
prices = pricing.get_prices_for_planning(hours=24)

# Check predictions
for price in prices:
    if price['is_predicted']:
        print(f"Predicted {price['start']}: {price['price']:.2f}p via {price['prediction_method']}")

# Check against actual when available
# Record what predictions were vs what actual was
```

## Summary

The pricing system provides:
- ✅ **Complete 24h coverage** - Always enough data to plan
- ✅ **Transparent** - Know what's predicted vs known
- ✅ **Smart prediction** - Uses best available method
- ✅ **Self-improving** - Learns from actual prices
- ✅ **Extensible** - Easy to add other tariffs
- ✅ **Handles Agile 4pm update** - Seamlessly fills gaps

The planner can now **always generate a 24-hour plan**, regardless of when Octopus publishes tomorrow's prices!
