# Installation Guide

## Quick Start

### Step 1: Install Prerequisites

Ensure you have these Home Assistant integrations installed:

1. **Octopus Energy**
   ```
   Settings → Devices & Services → Add Integration → "Octopus Energy"
   ```
   - Enter your Octopus account credentials
   - Note the entity IDs created (you'll need these for config)

2. **Solcast PV Forecast** (via HACS)
   ```
   HACS → Integrations → Search "Solcast" → Install
   ```
   - Create account at https://solcast.com
   - Add your solar array details
   - Get your API key
   - Configure integration with API key

### Step 2: Add This Repository

1. Go to **Settings → Add-ons → Add-on Store**
2. Click the **⋮** menu (top right) → **Repositories**
3. Add repository URL: `https://github.com/yourusername/ha-energy-predictor`
4. Click **Add**

### Step 3: Install the Add-on

1. Refresh the Add-on Store
2. Find **"Energy Demand Predictor & Battery Optimizer"**
3. Click on it
4. Click **Install**
5. Wait 5-10 minutes for build to complete

### Step 4: Configure

1. Go to the **Configuration** tab
2. Find your entity IDs:
   ```
   Developer Tools → States → Search for:
   - Your energy consumption sensor (e.g., "house_load")
   - Octopus rate events (e.g., "octopus_energy")
   - Battery SOC (e.g., "battery_soc")
   - Solcast forecast (e.g., "solcast")
   ```

3. Update configuration:
   ```yaml
   entity_id: sensor.YOUR_ENERGY_SENSOR
   octopus_import_rate_entity: event.octopus_energy_electricity_XXX_current_day_rates
   octopus_export_rate_entity: event.octopus_energy_electricity_XXX_export_current_day_rates
   battery_soc_entity: sensor.YOUR_BATTERY_SOC
   battery_capacity_kwh: YOUR_BATTERY_CAPACITY
   max_charge_rate_kw: YOUR_MAX_CHARGE_RATE
   max_discharge_rate_kw: YOUR_MAX_DISCHARGE_RATE
   ```

4. Click **Save**

### Step 5: Start the Add-on

1. Go to the **Info** tab
2. Enable **Start on boot** (recommended)
3. Enable **Watchdog** (recommended)
4. Click **Start**

### Step 6: Check Logs

1. Go to the **Log** tab
2. Look for:
   ```
   ✅ Training energy demand model...
   ✅ Model training complete!
   ✅ Starting optimization update cycle
   ✅ Optimization complete!
   ```

3. If you see errors, check:
   - Entity IDs are correct
   - Sufficient historical data exists (7+ days)
   - Integrations are working

### Step 7: Verify Sensors

Go to **Developer Tools → States** and search for:
- `sensor.energy_demand_predictor`
- `sensor.solar_predictor`
- `sensor.battery_optimizer`
- `sensor.energy_cost_predictor`

All should have state values and attributes.

### Step 8: Access Web UI

Open browser and go to:
```
http://homeassistant.local:8099
```

You should see the dashboard with current battery action and costs.

### Step 9: Create Automations

1. Copy automation templates from `automations_examples.yaml`
2. Adjust entity IDs to match your battery system
3. Add to your `automations.yaml` or via UI
4. Test each automation individually

### Step 10: Monitor and Tune

1. Check the add-on logs regularly for first few days
2. Monitor battery behavior
3. Adjust configuration parameters as needed:
   - `battery_reserve_soc` - Higher = more conservative
   - `battery_degradation_cost_per_cycle` - Higher = less cycling
   - `auto_update_interval` - More frequent = more responsive

## Troubleshooting

### "No historical data"
- Wait 7 days for sufficient history
- Check entity_id is correct
- Verify sensor has been recording data

### "Octopus rates not found"
- Verify Octopus integration installed
- Check entity names exactly match
- Ensure rates are published (check in Developer Tools)

### "Solcast forecast empty"
- Check Solcast integration is configured
- Verify API key is valid
- Check API call limit (10/day on free tier)

### "Optimization failed"
- Review constraints (may be too strict)
- Check battery parameters are realistic
- Look at logs for specific error

### "Battery not responding to commands"
- Verify automation entity IDs are correct
- Check battery control entities exist and work
- Test manual control first
- Some systems need specific modes/values

## Advanced Configuration

### Conservative Settings
Protect battery lifespan:
```yaml
battery_min_soc: 0.2
battery_reserve_soc: 0.3
battery_degradation_cost_per_cycle: 0.10
solar_forecast_mode: estimate10
```

### Aggressive Settings
Maximize cost savings:
```yaml
battery_min_soc: 0.05
battery_reserve_soc: 0.1
battery_degradation_cost_per_cycle: 0.02
solar_forecast_mode: estimate90
```

### High-Frequency Updates
For Agile tariff (rates change every 30 min):
```yaml
auto_update_interval: 1800  # 30 minutes
```

## Getting Help

1. Check add-on logs first
2. Review this documentation
3. Search existing GitHub issues
4. Create new issue with:
   - Your configuration (redact sensitive info)
   - Relevant log excerpts
   - What you expected vs what happened

## Next Steps

- Set up Lovelace dashboard cards (see README)
- Configure notifications for rate changes
- Optimize your specific use case
- Share your results with the community!

Happy optimizing! 🎉
