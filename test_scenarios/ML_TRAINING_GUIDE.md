# ML Planner Training Guide

Complete guide to training and using the self-improving ML planner.

## 🎯 Overview

The ML planner learns optimal battery strategies from test scenarios using:
- **Random Forest** classifier (should we use Feed-in Priority?)
- **Gradient Boosting** regressor (how many hours?)
- **15 extracted features** from scenario data
- **Self-improvement loop** for continuous learning

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Required for ML planner
pip install scikit-learn numpy

# Optional for LP planner
pip install pulp
```

### 2. Generate Test Scenarios

```bash
cd test_scenarios
python generator.py --generate-all
```

**Creates 13 scenarios:**
- 5 typical (sunny summer, cloudy, winter, etc.)
- 5 edge cases (negative pricing, battery full, etc.)
- 3 stress tests (volatile pricing, max solar, tiny battery)

### 3. Train ML Planner

```bash
python train_ml_planner.py
```

**Output:**
```
[TRAIN] Generating training data from scenarios...
[TRAIN] Loaded 13 scenarios
[1/13] Processing sunny_summer_day...
  Feed-in Priority: 8.5h, Cost: £1.89
...
[ML] Training on 13 scenarios...
  Train set: 10 scenarios
  Test set: 3 scenarios
[ML] Training Feed-in Priority classifier...
  Classifier accuracy: 90.0%
[ML] Training Feed-in Priority timing regressor...
  Timing regressor R²: 0.856
[ML] Top 5 features:
  surplus_ratio: 0.245
  net_surplus: 0.198
  total_solar: 0.156
  headroom: 0.132
  peak_kw: 0.089

Evaluating on test set...
Feed-in Priority Classification:
  Accuracy: 100.0% (3/3)

Feed-in Priority Timing:
  Mean Absolute Error: 0.34 hours

✅ Training complete!
```

### 4. Test ML Planner

```bash
# Test all scenarios
python test_ml_planner.py

# Test specific scenario
python test_ml_planner.py --scenario sunny

# Compare ML vs rule-based
python test_ml_planner.py --compare
```

## 📊 How It Works

### Feature Extraction

The ML planner extracts **15 features** from each scenario:

```python
Battery Features (3):
  - soc_start: Starting state of charge (%)
  - capacity: Battery capacity (kWh)
  - headroom: Available storage space (kWh)

Solar Features (4):
  - total_solar: Total generation forecast (kWh)
  - peak_kw: Peak generation rate (kW)
  - efficiency: Solar efficiency factor (0-1)
  - net_surplus: Solar - Load (kWh)

Load Features (2):
  - total_load: Total consumption (kWh)
  - evening_peak: Peak evening load (kW)

Pricing Features (4):
  - overnight_price: Overnight avg price (p)
  - peak_price: Peak period price (p)
  - price_spread: Peak - overnight (p)
  - arbitrage_margin: Arbitrage opportunity (p)

Derived Features (2):
  - surplus_ratio: Net surplus / battery headroom
  - surplus_per_kwh: Net surplus / capacity
```

### Model Training

```
Input: Scenario features
  ↓
[Random Forest Classifier]
  ↓
Output: Use Feed-in Priority? (Yes/No)
  ↓
[Gradient Boosting Regressor]
  ↓
Output: Feed-in Priority hours (0-12h)
```

### Labels (What It Learns)

The ML model learns from the rule-based planner's decisions:
- **used_feed_in_priority**: Boolean (did it activate?)
- **feed_in_hours**: Float (how long?)
- **total_cost**: Float (what was the cost?)
- **charge_slots**: Int (how many charge slots?)
- **discharge_slots**: Int (how many discharge slots?)

## 🧪 Training Options

### Train on Specific Category

```bash
# Only typical scenarios
python train_ml_planner.py --category typical

# Only edge cases
python train_ml_planner.py --category edge_cases

# Only stress tests
python train_ml_planner.py --category stress_tests
```

### Train from Existing Results

```bash
# Run tests and save results
python runner.py  # saves results_TIMESTAMP.json

# Train from those results
python train_ml_planner.py --results results/results_20260111_120000.json
```

### Adjust Train/Test Split

```bash
# Use 30% for testing (default is 20%)
python train_ml_planner.py --test-split 0.3
```

## 📈 Model Evaluation

### Test Set Metrics

**Classification Accuracy:**
- How often does it correctly predict Feed-in Priority usage?
- Target: >90%

**Timing MAE (Mean Absolute Error):**
- Average hours difference in Feed-in Priority timing
- Target: <1 hour

**Confidence:**
- Model's certainty in predictions (0-1)
- High confidence (>0.8) means reliable prediction

### Example Test Output

```
[1/13] sunny_summer_day
   Feed-in: True, Hours: 8.5h, Confidence: 95%

[2/13] cloudy_summer_day
   Feed-in: False, Hours: 0.0h, Confidence: 88%

[3/13] winter_sunny_day
   Feed-in: False, Hours: 0.0h, Confidence: 92%

Summary:
  Scenarios tested: 13
  Feed-in Priority predicted: 4/13
  Average confidence: 89.2%
  High confidence predictions (>80%): 11
```

## 🔄 Self-Improvement Loop

```bash
# 1. Train initial model
python train_ml_planner.py

# 2. Test and collect results
python runner.py  # Baseline results

# 3. Make improvements to model
# Edit ml_planner.py to add features, tune hyperparameters, etc.

# 4. Retrain
python train_ml_planner.py

# 5. Compare
python compare.py --latest

# 6. If better, keep new model. If worse, revert.
```

## 🎓 Advanced: Hyperparameter Tuning

Edit `ml_planner.py` to adjust model parameters:

```python
# Feed-in Priority Classifier
self.feed_in_classifier = RandomForestClassifier(
    n_estimators=100,  # Increase for better accuracy (slower)
    max_depth=10,      # Increase to capture more complex patterns
    min_samples_split=2,
    min_samples_leaf=1,
    random_state=42
)

# Timing Regressor
self.timing_regressor = GradientBoostingRegressor(
    n_estimators=100,  # Increase for better predictions
    max_depth=5,       # Increase for more complex patterns
    learning_rate=0.1, # Decrease for more careful learning
    random_state=42
)
```

## 🔍 Feature Importance Analysis

After training, check which features matter most:

```
Top 5 features:
  surplus_ratio: 0.245    ← Most important!
  net_surplus: 0.198      ← Very important
  total_solar: 0.156      ← Important
  headroom: 0.132         ← Moderately important
  peak_kw: 0.089          ← Less important
```

**Interpretation:**
- **surplus_ratio** is the strongest predictor
- If net_surplus / headroom > 1.0, likely need Feed-in Priority
- Total solar and headroom are also key indicators

## 🛠️ Troubleshooting

### "No trained model found"

```bash
# Train first!
python train_ml_planner.py
```

### "No scenarios found"

```bash
# Generate scenarios first
python generator.py --generate-all
```

### Low accuracy (<80%)

**Possible causes:**
1. Not enough training data (need 10+ scenarios)
2. Features don't capture key patterns
3. Overfitting (reduce model complexity)

**Solutions:**
```bash
# Add more scenarios
# Edit generator.py to create more diverse scenarios

# Retrain with more data
python train_ml_planner.py

# Reduce model complexity
# Edit ml_planner.py: reduce n_estimators, max_depth
```

### High MAE (>2 hours)

Timing predictions are off. 

**Solutions:**
- Add more time-related features
- Tune timing regressor hyperparameters
- Collect more training examples with varied timing

## 📁 Model Files

Trained models are saved to `apps/solar_optimizer/models/`:

```
models/
└── ml_planner_models.pkl  # Trained model weights
```

**To reset:**
```bash
rm apps/solar_optimizer/models/ml_planner_models.pkl
python train_ml_planner.py  # Train from scratch
```

## 🎯 Integration with SolarBat-AI

Once trained, use ML planner in production:

```python
# In solar_optimizer.py
from apps.solar_optimizer.ml_planner import MLPlanner

# Replace PlanCreator with MLPlanner
self.plan_creator = MLPlanner()

# Use predictions in planning
prediction = self.plan_creator.predict(scenario)

if prediction['use_feed_in_priority']:
    # Apply Feed-in Priority strategy
    ...
```

## 📚 Next Steps

1. ✅ **Train on more scenarios** - Add custom scenarios to improve model
2. ✅ **Compare performance** - Run full test suite: ML vs rule-based vs LP
3. ✅ **Continuous learning** - Retrain periodically with new data
4. ✅ **Production deployment** - Integrate into main optimizer

---

**Questions? Check:**
- `ml_planner.py` - Model implementation
- `train_ml_planner.py` - Training script
- `test_ml_planner.py` - Testing script
- `test_scenarios/README.md` - Test framework docs
