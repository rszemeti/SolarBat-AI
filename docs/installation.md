# Installation Guide

Step-by-step guide to installing SolarBat-AI v2.0

## Prerequisites

Before installing, ensure you have:

1. ✅ Home Assistant running (2024.1 or later recommended)
2. ✅ AppDaemon 4.x installed
3. ✅ Solax ModBus integration installed and working
4. ✅ Octopus Energy integration installed
5. ✅ Solcast Solar integration installed
6. ✅ SSH access or Terminal add-on

## Step-by-Step Installation

### Step 1: Install AppDaemon

If not already installed:

1. Go to **Settings** → **Add-ons** → **Add-on Store**
2. Search for "AppDaemon"
3. Click **Install**
4. After installation, click **Start**
5. Enable "Start on boot" and "Watchdog"

### Step 2: Clone Repository

**Option A: Via SSH/Terminal**

```bash
cd /config/appdaemon/apps
git clone https://github.com/rszemeti/SolarBat-AI.git solar_optimizer
```

**Option B: Manual Download**

1. Download ZIP from GitHub
2. Extract to `/config/appdaemon/apps/solar_optimizer/`

### Step 3: Create Configuration File

```bash
cd /config/appdaemon/apps
cp solar_optimizer/apps/solar_optimizer/apps.yaml.example solar_optimizer.yaml
```

### Step 4: Edit Configuration

Edit `/config/appdaemon/apps/solar_optimizer.yaml`:

```bash
nano solar_optimizer.yaml
```

**Minimum required changes:**

1. Replace `xxxxx` in Agile entity IDs with your MPAN
2. Verify all sensor entity IDs match your system
3. Set your battery capacity if sensor doesn't exist

Example:
```yaml
solar_optimizer:
  module: solar_optimizer
  class: SmartSolarOptimizer
  
  battery_soc: sensor.solax_battery_soc
  battery_capacity: sensor.solax_battery_capacity
  inverter_mode: select.solax_charger_use_mode
  
  # ... rest of config ...
  
  # IMPORTANT: Replace with YOUR MPAN
  agile_current: sensor.octopus_energy_electricity_1234567890_current_rate
  agile_rates: event.octopus_energy_electricity_1234567890_current_day_rates
```

### Step 5: Restart AppDaemon

**Via UI:**
1. Go to **Settings** → **Add-ons** → **AppDaemon**
2. Click **Restart**

**Via SSH:**
```bash
ha addons restart a0d7b954_appdaemon
```

### Step 6: Verify Installation

Check AppDaemon logs:

```bash
tail -f /config/appdaemon/appdaemon.log
```

Look for:
```
INFO solar_optimizer: ================================================================================
INFO solar_optimizer: Solar Battery Optimizer v2.0 - Initializing...
INFO solar_optimizer: ================================================================================
INFO solar_optimizer: Smart Solar Optimizer initialized successfully
INFO solar_optimizer: Pre-emptive discharge: ENABLED
INFO solar_optimizer: Generating new 24-hour plan...
```

### Step 7: Add Dashboard

1. Go to your Home Assistant dashboard
2. Click **Edit Dashboard** → **Add Card** → **Manual**
3. Paste contents from `/dashboards/optimizer_dashboard.yaml`
4. Click **Save**

**Note:** If using the ApexCharts card, install it from HACS first:
- HACS → Frontend → Search "ApexCharts" → Install

## Verification Checklist

After installation, verify:

- [ ] AppDaemon logs show successful initialization
- [ ] Sensors created: `sensor.solar_optimizer_plan`, `sensor.solar_wastage_risk`, `sensor.solar_optimizer_capabilities`
- [ ] Dashboard displays plan (may take a few minutes for first plan)
- [ ] Inverter mode changes (watch for next hour boundary)

## Troubleshooting Installation

### AppDaemon won't start

**Check logs:**
```bash
docker logs addon_a0d7b954_appdaemon
```

**Common issues:**
- Syntax error in configuration
- Wrong indentation in YAML
- Invalid entity IDs

### "ModuleNotFoundError"

AppDaemon can't find the module. Check:
```bash
ls /config/appdaemon/apps/solar_optimizer/
```

Should contain:
- `solar_optimizer.py`
- `apps.yaml.example`

### "No module named 'solar_optimizer'"

Configuration file is in wrong location. Should be:
```
/config/appdaemon/apps/solar_optimizer.yaml
```

NOT:
```
/config/appdaemon/apps/solar_optimizer/solar_optimizer.yaml
```

### Sensors not appearing

1. Wait 5 minutes after restart
2. Check Developer Tools → States for `sensor.solar_optimizer_plan`
3. Check AppDaemon logs for errors

### No plan generated

Check logs for specific error:

**"Cannot generate plan - missing data"**
- Verify all sensor entities exist
- Check Octopus integration is working
- Verify Solcast has recent forecast

**"Invalid battery SOC"**
- Check battery_soc sensor has valid value
- Verify sensor entity ID is correct

## Post-Installation

### Recommended First Steps

1. **Monitor for 24 hours** - Let it generate plans, but watch carefully
2. **Check mode changes** - Verify inverter responds correctly
3. **Review wastage sensor** - See if it detects wastage risk accurately
4. **Adjust settings** - Fine-tune based on observations

### Initial Configuration Suggestions

Start conservatively:

```yaml
enable_preemptive_discharge: false  # Disable until you trust it
min_change_interval: 7200  # 2 hours between changes
```

After 1 week of successful operation, enable pre-emptive discharge:

```yaml
enable_preemptive_discharge: true
min_wastage_threshold: 2.0  # Conservative threshold
min_benefit_threshold: 1.00  # Require £1 benefit
min_change_interval: 3600  # 1 hour (can reduce after confidence builds)
```

## Updating

### Git Method

```bash
cd /config/appdaemon/apps/solar_optimizer
git pull origin main
```

### Manual Method

1. Download new version from GitHub
2. Backup your configuration:
   ```bash
   cp /config/appdaemon/apps/solar_optimizer.yaml /config/solar_optimizer.yaml.backup
   ```
3. Replace files in `/config/appdaemon/apps/solar_optimizer/`
4. Restore your configuration
5. Restart AppDaemon

## Uninstalling

If you need to remove SolarBat-AI:

1. Remove configuration:
   ```bash
   rm /config/appdaemon/apps/solar_optimizer.yaml
   ```

2. Remove app directory:
   ```bash
   rm -rf /config/appdaemon/apps/solar_optimizer
   ```

3. Restart AppDaemon

4. Remove dashboard cards

5. (Optional) Remove history:
   ```bash
   rm /config/appdaemon/solar_optimizer_history.json
   ```

## Getting Help

If you encounter issues:

1. Check the [Configuration Guide](configuration.md)
2. Search [GitHub Issues](https://github.com/rszemeti/SolarBat-AI/issues)
3. Post logs and configuration (remove sensitive data!)
4. Join Home Assistant Discord - #appdaemon channel

## Next Steps

- [Configuration Guide](configuration.md) - Detailed configuration options
- [User Guide](user_guide.md) - How to use the optimizer
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
