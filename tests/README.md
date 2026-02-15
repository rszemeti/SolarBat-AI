# Testing

## Test Harness (`test_harness.py`)

The main development tool. Connects to your HA instance via the API and runs the optimizer locally in VS Code or terminal.

### Setup

```bash
cd tests/
pip install -r requirements-dev.txt
```

Create a `.env` file:

```
HA_URL=http://your-homeassistant:8123
HA_TOKEN=your_long_lived_access_token
```

### Running

```bash
python test_harness.py
```

This will connect to HA, fetch real sensor data, generate a plan, and open it in your browser.

## Other Test Files

| File | Purpose |
|------|---------|
| `test_data.py` | Mock data generators for offline testing |
| `test_with_mock_data.py` | Run optimizer with synthetic data (no HA needed) |
| `test_new_strategies.py` | Test specific charging/discharging strategies |
| `visualize_strategies.py` | Generate comparison charts across strategies |
| `update_test_expectations.sh` | Refresh test scenario expected outputs |

## Scenario Tests (`scenarios/`)

Pre-built test scenarios covering typical days, edge cases, and stress tests:

```bash
cd scenarios/
python runner.py                    # Run all scenarios
python compare_planners.py          # Compare rule-based vs LP vs ML
python train_ml_planner.py          # Train ML planner on historical data
```

See `scenarios/README.md` for scenario descriptions and the ML training guide.
