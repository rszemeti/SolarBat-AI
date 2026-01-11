# SolarBat-AI v2.1 - New Architecture with Inverter Abstraction

## Overview

The system has been redesigned with proper separation of concerns using an **inverter interface abstraction layer**. This makes the code:
- **Maintainable** - Changes to inverter control don't affect planning logic
- **Extensible** - Easy to add support for different inverter brands
- **Testable** - Can test planning without touching hardware
- **Reusable** - Others can write interfaces for their inverters

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    solar_optimizer.py                       │
│                    (Strategic Planner)                      │
│                                                             │
│  • Analyzes solar forecasts, prices, consumption           │
│  • Generates 24-hour optimization plan                     │
│  • Decides WHAT needs to happen and WHEN                   │
│  • Output: Plan with hourly steps                          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ Plan
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 inverter_controller.py                      │
│                 (Execution Coordinator)                     │
│                                                             │
│  • Reads current hour from plan                            │
│  • Translates plan step to InverterCommand                 │
│  • Compares with current inverter state                    │
│  • Calls interface if change needed                        │
│  • Handles rate limiting and safety checks                 │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ InverterCommand
                           ▼
┌─────────────────────────────────────────────────────────────┐
│             inverter_interface_base.py                      │
│             (Abstract Interface)                            │
│                                                             │
│  Defines contract for all inverter implementations:        │
│  • force_charge(start, end, target_soc)                    │
│  • force_discharge(start, end, target_soc)                 │
│  • clear_all_slots()                                        │
│  • get_capabilities()                                       │
│  • get_current_state()                                      │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ implements
                           ▼
┌─────────────────────────────────────────────────────────────┐
│          inverter_interface_solis6.py                        │
│          (Solis/Solax Implementation)                       │
│                                                             │
│  Solis-specific implementation (via solax_modbus):         │
│  • Manages timed charge/discharge slots                    │
│  • Sets start/end hours and minutes                        │
│  • Sets target SOC and current (Amps)                      │
│  • Reads actual inverter state                             │
│  • Uses slot 1 for all dynamic control                     │
│                                                             │
│  Tested with: Solis S6 Hybrid via solax_modbus            │
└─────────────────────────────────────────────────────────────┘
```

## File Structure

```
apps/solar_optimizer/
├── solar_optimizer.py              # Main planner (mostly unchanged)
├── inverter_controller.py          # NEW: Execution coordinator
├── inverter_interface_base.py      # NEW: Abstract base class
├── inverter_interface_solis6.py     # NEW: Solax implementation
└── apps.yaml.example               # Updated config
```

## How It Works

### 1. Planning Phase (solar_optimizer.py)

The planner generates a 24-hour plan with hourly steps:

```python
plan_step = {
    'timestamp': '2026-01-11T06:00:00',
    'hour': 6,
    'action': 'force_discharge',  # What to do
    'reason': 'Pre-emptive discharge: 5kWh solar wastage detected',
    'target_soc': 40,  # Discharge to 40%
    'duration': 2  # For 2 hours
}
```

### 2. Execution Phase (inverter_controller.py)

Every 30 minutes, the controller:

1. Reads current hour's plan step
2. Translates to InverterCommand:
   ```python
   command = InverterCommand(
       action='force_discharge',
       start_time=time(6, 0),   # 06:00
       end_time=time(8, 0),     # 08:00
       target_soc=40
   )
   ```
3. Checks if inverter already has this command set
4. If different, calls interface to update inverter

### 3. Interface Layer (inverter_interface_*.py)

The interface translates high-level commands to hardware-specific calls:

```python
# High-level command
interface.force_discharge(
    start_time=time(6, 0),
    end_time=time(8, 0),
    target_soc=40
)

# Becomes (for Solis via solax_modbus):
set_value('number.solis_inverter_timed_discharge_start_hours', 6)
set_value('number.solis_inverter_timed_discharge_start_minutes', 0)
set_value('number.solis_inverter_timed_discharge_end_hours', 8)
set_value('number.solis_inverter_timed_discharge_end_minutes', 0)
set_value('number.solis_inverter_timed_discharge_soc', 40)
set_value('number.solis_inverter_timed_discharge_current', MAX_AMPS)
```

## Benefits of This Architecture

### For You
- **Cleaner code** - Each component has one responsibility
- **Easier debugging** - Can test each layer independently
- **Better logging** - Can see exactly what each layer is doing
- **Safer** - Interface validates commands before sending

### For Others
- **Other inverter brands** - Just write a new interface class:
  - `inverter_interface_givener

gy.py`
  - `inverter_interface_solaredge.py`
  - etc.
- **Same planner** - Planning logic works for all inverters
- **Easy adoption** - "I have a GivEnergy, where's the interface?" → "Here!"

## Example: Adding GivEnergy Support

Someone with GivEnergy just needs to:

1. Copy `inverter_interface_base.py` (no changes)
2. Create `inverter_interface_givenergy.py`:
   ```python
   class GivEnergyInverterInterface(InverterInterface):
       def force_charge(self, start_time, end_time, target_soc, current_amps):
           # GivEnergy uses different entity structure
           self.set_value('select.givenergy_mode', 'Eco')
           self.set_value('number.givenergy_charge_start', start_time.hour)
           # etc.
   ```
3. Update config to use GivEnergy interface
4. Done! All planning logic works unchanged

## Configuration Changes

### Old Way (Mode-Based)
```yaml
inverter_mode: select.solax_charger_use_mode
mode_self_use: "Self Use"
mode_grid_first: "Grid First"
mode_force_charge: "Force Charge"
```

### New Way (Interface-Based)
```yaml
# Specify which interface to use
inverter_interface: solax  # or 'givenergy', 'solaredge', etc.

# Solax-specific entities (timed slots)
charge_slot1_start_hour: number.solis8_inverter_timed_charge_start_hours
charge_slot1_start_minute: number.solis8_inverter_timed_charge_start_minutes
charge_slot1_end_hour: number.solis8_inverter_timed_charge_end_hours
charge_slot1_end_minute: number.solis8_inverter_timed_charge_end_minutes
charge_slot1_soc: number.solis8_inverter_timed_charge_soc
charge_slot1_current: number.solis8_inverter_timed_charge_current

discharge_slot1_start_hour: number.solis8_inverter_timed_discharge_start_hours
discharge_slot1_start_minute: number.solis8_inverter_timed_discharge_start_minutes
discharge_slot1_end_hour: number.solis8_inverter_timed_discharge_end_hours
discharge_slot1_end_minute: number.solis8_inverter_timed_discharge_end_minutes
discharge_slot1_soc: number.solis8_inverter_timed_discharge_soc
discharge_slot1_current: number.solis8_inverter_timed_discharge_current
```

## Safety Features

The interface layer provides safety:

1. **Validation** - Checks time windows and SOC values before sending
2. **State comparison** - Only updates if actually different
3. **Error handling** - Graceful degradation if commands fail
4. **Rate limiting** - Prevents spamming inverter
5. **Logging** - Detailed logs of all commands

## Next Steps

The full implementation includes:

1. ✅ **inverter_interface_base.py** - Abstract base (complete)
2. ✅ **inverter_interface_solis6.py** - Solax implementation (complete)
3. 🔄 **inverter_controller.py** - Execution coordinator (in progress)
4. 🔄 **solar_optimizer.py** - Updated to use controller (in progress)
5. 📝 **apps.yaml.example** - New configuration template (needs update)
6. 📝 **Documentation** - Usage guide (needs update)

## Migration from v2.0

If you have v2.0 installed:

1. **Backup your config**
2. **Extract v2.1 package**
3. **Update config** with new slot entity IDs
4. **Restart AppDaemon**
5. **Monitor logs** - Interface will log all commands

The planner logic is mostly unchanged - it just outputs to the interface now instead of direct mode switching.

## Questions?

This is a significant architectural improvement. The code is:
- More professional
- More maintainable
- More extensible
- Easier to debug

But it does require more configuration upfront (specifying all the slot entities).

Worth it? Absolutely! Especially for a system that will run 24/7 controlling your expensive battery.
