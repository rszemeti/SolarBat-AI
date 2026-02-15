# SolarBat-AI Test Framework

Comprehensive test framework for validating optimization strategies across diverse scenarios.

## 🎯 Purpose

- **Regression Testing**: Ensure changes don't break existing scenarios
- **Performance Benchmarking**: Compare versions quantitatively  
- **Edge Case Coverage**: Test extreme conditions
- **Algorithm Validation**: Verify expected behaviors

## 📁 Structure

```
test_scenarios/
├── generator.py         # Generate test scenarios
├── runner.py           # Execute all tests
├── compare.py          # Compare results
├── scenarios/          # JSON test scenarios
│   ├── typical/        # Normal operating conditions
│   ├── edge_cases/     # Boundary conditions
│   └── stress_tests/   # Extreme scenarios
└── results/            # Test run outputs
    └── results_*.json  # Timestamped results
```

## 🚀 Quick Start

### 1. Generate Test Scenarios

```bash
cd test_scenarios
python generator.py --generate-all
```

**Generates:**
- 5 typical scenarios (sunny summer, cloudy, winter, etc.)
- 5 edge cases (negative pricing, battery full, zero solar, etc.)
- 3 stress tests (volatile pricing, max solar, tiny battery)

### 2. Run All Tests

```bash
python runner.py
```

**Output:**
```
[1/13] typical/sunny_summer_day
  17kWp array, perfect sunny summer day, typical load
  ⚡ Feed-in Priority: 8.5h
  💰 Cost: £1.89
  🔋 SOC: 70% → 85%
  ⏱️  Runtime: 0.023s
  ✅ PASS

...

TEST SUMMARY
============
Total Scenarios: 13
Passed: 12 (92.3%)
Failed: 1 (7.7%)
Total Cost: £24.67
Average Cost: £1.90/scenario
```

### 3. Compare Versions

```bash
# Make a code change
# Run tests again
python runner.py

# Compare latest two runs
python compare.py --latest
```

**Output:**
```
METRIC COMPARISON
=================
Total Cost:
  Run 1: £24.67
  Run 2: £22.45
  Change: 📉 -£2.22 (-9.0%) ✅

IMPROVEMENTS (8):
  sunny_summer_day: £1.89 → £1.65 (saved £0.24)
  ...
```

## 📊 Scenarios

### Typical Scenarios

| Scenario | Description | Tests |
|----------|-------------|-------|
| `sunny_summer_day` | 17kWp, 80% efficiency, high solar | Feed-in Priority strategy |
| `cloudy_summer_day` | 17kWp, 35% efficiency, low solar | No clipping, self-use |
| `winter_sunny_day` | 17kWp, 60% efficiency, short day | Evening peak discharge |
| `spring_moderate_day` | 17kWp, 70% efficiency, balanced | Self-use + arbitrage |
| `autumn_partial_cloud` | 17kWp, 65% efficiency, variable | Smart self-use |

### Edge Cases

| Scenario | Description | Tests |
|----------|-------------|-------|
| `negative_pricing_overnight` | Import at -5p (get paid!) | Aggressive charging |
| `battery_full_at_dawn` | 95% SOC, 68kWh solar coming | Critical: Feed-in Priority |
| `zero_solar_day` | Complete solar failure | Pure arbitrage |
| `low_battery_emergency` | 15% SOC, expensive ahead | Emergency charging |
| `extreme_arbitrage` | 8p overnight, 45p peak | Maximize profit |

### Stress Tests

| Scenario | Description | Tests |
|----------|-------------|-------|
| `volatile_pricing` | Prices 5-50p, rapid swings | Handle volatility |
| `maximum_solar_generation` | 95% efficiency, 90% SOC | Extreme clipping risk |
| `tiny_battery` | 3kWh battery (vs 10kWh) | Work with limits |

## 📋 JSON Format

```json
{
  "name": "sunny_summer_day",
  "description": "17kWp array, perfect sunny summer day",
  "date": "2026-07-15",
  "battery": {
    "soc_start": 70.0,
    "capacity_kwh": 10.0,
    "max_charge_kw": 3.0,
    "max_discharge_kw": 3.0
  },
  "solar_profile": {
    "type": "parametric_bell_curve",
    "peak_kw": 17.0,
    "sunrise_hour": 5.0,
    "sunset_hour": 21.0,
    "efficiency": 0.8,
    "total_kwh": 68.5
  },
  "load_profile": {
    "type": "parametric_daily",
    "base_kw": 0.3,
    "morning_peak_kw": 1.5,
    "evening_peak_kw": 2.5,
    "total_kwh": 12.4
  },
  "pricing": {
    "type": "agile_typical",
    "overnight_avg_p": 12.0,
    "day_avg_p": 18.0,
    "peak_avg_p": 28.0,
    "export_fixed_p": 15.0
  },
  "expected_outcomes": {
    "feed_in_priority_hours": ">6",
    "total_cost_max": 2.50,
    "clipping_kwh": 0.0
  }
}
```

## 🎯 Validation

Tests automatically validate:

✅ **Feed-in Priority Usage**: Activated when expected  
✅ **Cost Targets**: Within expected ranges  
✅ **Clipping Prevention**: Zero clipping on high solar days  
✅ **Arbitrage Profit**: Earn money on negative pricing  
✅ **Mode Counts**: Correct charge/discharge slot usage

## 🔧 Advanced Usage

### Run Specific Category

```bash
python runner.py --category typical
python runner.py --category edge_cases
python runner.py --category stress_tests
```

### Generate Custom Scenarios

```bash
python generator.py --generate-typical
python generator.py --generate-edge-cases
```

### Add Your Own Scenario

Create `scenarios/custom/my_scenario.json`:

```json
{
  "name": "my_custom_test",
  "description": "My special test case",
  ...
}
```

Then run:
```bash
python runner.py
```

## 📈 CI/CD Integration

Add to GitHub Actions:

```yaml
- name: Run Test Suite
  run: |
    cd test_scenarios
    python generator.py --generate-all
    python runner.py
    
- name: Check for Regressions
  run: |
    cd test_scenarios
    python compare.py --latest
```

## 🎓 Example Workflow

**1. Develop New Feature**
```bash
# Make code changes to plan_creator.py
```

**2. Run Full Test Suite**
```bash
cd test_scenarios
python runner.py
```

**3. Analyze Results**
```
✅ 12/13 PASS (92.3%)
❌ FAIL: battery_full_at_dawn
   - Expected >8h Feed-in Priority, got 2h
```

**4. Fix Bug & Re-test**
```bash
# Fix the issue
python runner.py
```

**5. Compare Performance**
```bash
python compare.py --latest

VERDICT
=======
🏆 CLEAR WIN - Run 2 is better on all metrics!
```

## 💡 Best Practices

- ✅ **Run tests before commits** - Catch regressions early
- ✅ **Add tests for bugs** - Prevent recurrence  
- ✅ **Compare versions** - Track improvements
- ✅ **Review failures** - Understand why tests fail
- ✅ **Keep scenarios diverse** - Cover edge cases

## 📊 Interpreting Results

### Good Signs ✅
- Pass rate >90%
- Lower total cost vs previous
- Zero clipping on high solar days
- Feed-in Priority used appropriately

### Red Flags ❌
- Falling pass rate
- Increasing costs
- Clipping on sunny days
- Feed-in Priority never used

## 🛠️ Troubleshooting

**Tests failing after changes?**
1. Check which scenarios failed
2. Review expected vs actual behavior
3. Validate logic changes
4. Update expectations if behavior is correct

**Results look wrong?**
1. Check input data generation
2. Verify profile expansion logic
3. Test single scenario in isolation
4. Add debug logging

## 📚 Related Files

- `../test_with_mock_data.py` - Single scenario testing
- `../test_data.py` - Data generation helpers
- `../apps/solar_optimizer/plan_creator.py` - Optimization engine

---

**Built with ❤️ for SolarBat-AI v2.3**
