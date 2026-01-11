# Windows Testing Setup Guide

Quick guide to test SolarBat-AI on Windows before deploying to Home Assistant.

## Prerequisites

- ✅ Windows 10/11
- ✅ Python 3.9+ installed
- ✅ VS Code installed
- ✅ Home Assistant running on your network

## Step-by-Step Setup

### 1. Install Python (if needed)

1. Download from https://www.python.org/downloads/
2. **Important:** Check "Add Python to PATH" during installation
3. Verify in Command Prompt:
   ```cmd
   python --version
   ```

### 2. Extract the ZIP

1. Right-click `SolarBat-AI-v2.1-WIP.zip`
2. Choose "Extract All..."
3. Extract to a folder like `C:\Dev\SolarBat-AI`

### 3. Open in VS Code

1. Open VS Code
2. File → Open Folder
3. Select the extracted `SolarBat-AI-v2` folder

### 4. Install Dependencies

Open VS Code Terminal (Ctrl + ` or Terminal menu):

```cmd
pip install requests python-dotenv
```

That's it! Just these two packages needed.

### 5. Get Your Home Assistant Token

1. Open Home Assistant in browser
2. Click your profile picture (bottom left)
3. Scroll down to **"Long-Lived Access Tokens"**
4. Click **"Create Token"**
5. Name it "SolarBat-AI Testing"
6. **Copy the token** (you won't see it again!)

### 6. Create .env File

In VS Code:

1. Create new file: `.env` (in root folder)
2. Add these two lines:
   ```
   HA_URL=http://192.168.1.100:8123
   HA_TOKEN=your_token_here_really_long_string
   ```

**Finding your HA URL:**
- Usually: `http://homeassistant.local:8123`
- Or IP: `http://192.168.1.XXX:8123`
- Same URL you use in browser

### 7. Run First Test

In VS Code terminal:

```cmd
python test_harness.py
```

**Expected output:**
```
============================================================
  SolarBat-AI Test Harness - Windows Edition
============================================================

🔌 Connecting to http://192.168.1.100:8123...
✅ Connected to Home Assistant!

Test 1: Connection Test
============================================================
✅ Connection test passed!

Test 2: Reading Entities
============================================================
📖 Trying to read some entities...
  ✅ sensor.solis_battery_soc = 67.0
  ✅ sensor.solis_battery_capacity = 10.0
  ❌ sensor.solis_pv_power not found

💡 TIP: Go to HA Developer Tools → States and search for:
   - 'solis' or 'battery' for battery entities
   - 'octopus' for pricing entities
```

## Troubleshooting

### "python is not recognized"

**Solution:** Python not in PATH
1. Reinstall Python, check "Add to PATH"
2. Or add manually: System → Environment Variables

### "Cannot connect to http://..."

**Solutions:**
1. Try IP address instead of hostname:
   ```
   HA_URL=http://192.168.1.100:8123
   ```
2. Check HA is running (can you access in browser?)
3. Disable Windows Firewall temporarily to test

### "Authentication failed"

**Solutions:**
1. Check token is correct (copy/paste carefully)
2. No extra spaces before/after token
3. Generate a new token if needed

### "ModuleNotFoundError: No module named 'requests'"

**Solution:** Install dependencies again:
```cmd
pip install requests python-dotenv
```

### Can't find .env file in VS Code

**Solution:** File Explorer might hide it
1. In VS Code Explorer, files starting with `.` are shown
2. Or create in Command Prompt:
   ```cmd
   notepad .env
   ```

## Finding Your Entity IDs

### Method 1: Developer Tools (Best)

1. In Home Assistant, go to **Developer Tools** → **States**
2. Search for entity types:

**For battery:**
- Search: `solis` or `battery`
- Look for: `sensor.solis_battery_soc`

**For pricing:**
- Search: `octopus`
- Look for: `sensor.octopus_energy_electricity_xxxxx_current_rate`

**For slots:**
- Search: `timed_charge`
- Look for: `number.solis_inverter_timed_charge_start_hours`

### Method 2: Integration Page

1. Settings → Devices & Services
2. Click on "Solax ModBus"
3. Click on your inverter device
4. See all entities listed

## What the Tests Do

**Test 1: Connection**
- Checks it can connect to HA
- Verifies your token works

**Test 2: Reading Entities**
- Tries to read common sensor names
- Shows which entities exist

**Test 3: Pricing**
- Asks for your Octopus entity
- Reads current electricity price

**Test 4: Inverter**
- Asks for your slot entity
- Reads current slot settings

## Next Steps

Once basic tests pass:

1. **Find all your entity IDs** using Developer Tools
2. **Update .env** with correct entity names
3. **Run full test** (once we build the complete version)
4. **Deploy to AppDaemon** when confident

## Quick Reference

**VS Code Terminal Commands:**

```cmd
# Install deps
pip install requests python-dotenv

# Run test
python test_harness.py

# Check Python version
python --version

# List installed packages
pip list
```

**Common Entity Name Patterns:**

```
Battery:
  sensor.solis_battery_soc
  sensor.solax_battery_soc
  
Pricing:
  sensor.octopus_energy_electricity_[MPAN]_current_rate
  event.octopus_energy_electricity_[MPAN]_current_day_rates
  
Solar:
  sensor.solcast_pv_forecast_forecast_remaining_today
  
Slots:
  number.solis_inverter_timed_charge_start_hours
  number.solis_inverter_timed_discharge_soc
```

## Tips

💡 **Use Tab completion** - Type partial entity name and VS Code will suggest

💡 **Keep HA open** - Have Developer Tools → States open in browser while testing

💡 **Test during the day** - When you can see solar generation

💡 **Don't worry about failures** - First run is just finding your entity names

## Ready to Test!

Once you've:
- ✅ Created .env with your URL and token
- ✅ Installed dependencies
- ✅ Run `python test_harness.py` successfully

You're ready to configure your actual entity IDs and do full testing!
