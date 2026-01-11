"""
Plan Executor - Inverter Control

Reads the plan from PlanCreator and writes to inverter only when needed.
Compares plan to actual inverter state to avoid unnecessary writes.

Pure execution logic - no optimization, no decisions, just compare and apply.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional


class PlanExecutor:
    """
    Executes the plan by writing to inverter when needed.
    
    Responsibilities:
    - Get current time slot from plan
    - Read actual inverter state
    - Compare plan vs actual
    - Write to inverter ONLY if different
    - Log all actions
    
    No optimization logic - just faithful execution of the plan.
    """
    
    def __init__(self, hass, inverter, mode_switch_entity=None):
        """
        Initialize plan executor.
        
        Args:
            hass: Home Assistant API object
            inverter: Inverter interface (SystemStateProvider's inverter)
            mode_switch_entity: Energy Storage Control Switch entity ID
        """
        self.hass = hass
        self.inverter = inverter
        self.mode_switch_entity = mode_switch_entity
        self._last_execution = None
    
    def log(self, message: str, level: str = "INFO"):
        """Log a message"""
        if hasattr(self.hass, 'log'):
            self.hass.log(f"[EXECUTOR] {message}", level=level)
        else:
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{timestamp}] [EXECUTOR] {message}")
    
    def execute(self, plan: Dict) -> Dict:
        """
        Execute the plan by writing to inverter if needed.
        
        Args:
            plan: Plan object from PlanCreator with 'slots' and 'metadata'
            
        Returns:
            Execution result dict with:
                - executed: bool (was anything written)
                - action_taken: str (description of what was done)
                - current_slot: dict (the slot we're in)
                - reason: str (why we did/didn't write)
        """
        self.log("Executing plan...")
        
        # Get current time slot from plan
        current_slot = self._get_current_slot(plan)
        
        if not current_slot:
            self.log("No current slot found in plan", level="WARNING")
            return {
                'executed': False,
                'action_taken': 'none',
                'current_slot': None,
                'reason': 'No matching time slot in plan'
            }
        
        self.log(f"Current slot: {current_slot['time'].strftime('%H:%M')} - {current_slot['mode']}")
        
        # Check if we need to write to inverter
        needs_update, reason = self._needs_inverter_update(current_slot)
        
        if needs_update:
            # Apply the plan to inverter
            success = self._apply_to_inverter(current_slot)
            
            if success:
                self.log(f"✅ Applied: {current_slot['mode']} for {current_slot['time'].strftime('%H:%M')}")
                self._last_execution = datetime.now()
                return {
                    'executed': True,
                    'action_taken': current_slot['mode'],
                    'current_slot': current_slot,
                    'reason': reason
                }
            else:
                self.log(f"❌ Failed to apply plan", level="ERROR")
                return {
                    'executed': False,
                    'action_taken': 'failed',
                    'current_slot': current_slot,
                    'reason': 'Inverter write failed'
                }
        else:
            self.log(f"⏭️  No change needed: {reason}")
            return {
                'executed': False,
                'action_taken': 'none',
                'current_slot': current_slot,
                'reason': reason
            }
    
    def _get_current_slot(self, plan: Dict) -> Optional[Dict]:
        """
        Get the current 30-min slot from the plan.
        
        Finds which slot we're in based on current time.
        """
        now = datetime.now()
        
        # Round to nearest 30-min boundary
        if now.minute < 30:
            current_time = now.replace(minute=0, second=0, microsecond=0)
        else:
            current_time = now.replace(minute=30, second=0, microsecond=0)
        
        # Find matching slot
        for slot in plan.get('slots', []):
            slot_time = slot['time']
            # Check if current_time matches this slot (within 30 min window)
            if abs((slot_time - current_time).total_seconds()) < 1800:  # 30 minutes
                return slot
        
        # No exact match - get closest future slot
        future_slots = [s for s in plan.get('slots', []) if s['time'] >= current_time]
        if future_slots:
            return future_slots[0]
        
        return None
    
    def _needs_inverter_update(self, slot: Dict) -> tuple[bool, str]:
        """
        Check if inverter needs updating for this slot.
        
        Checks both:
        - Timed slots (for Force Charge/Discharge)
        - Mode switch (for Feed-in Priority vs Self-Use)
        
        Returns:
            (needs_update: bool, reason: str)
        """
        try:
            slot_time = slot['time']
            slot_mode = slot['mode']
            
            # Get current mode from switch if available
            current_switch_mode = None
            if self.mode_switch_entity:
                try:
                    current_switch_mode = self.hass.get_state(self.mode_switch_entity)
                except:
                    pass
            
            # Check for Feed-in Priority mode (uses switch, not slots)
            if slot_mode == 'Feed-in Priority':
                if current_switch_mode != "Feed-in priority":
                    return True, f"Need Feed-in Priority mode (currently {current_switch_mode})"
                else:
                    return False, "Already in Feed-in Priority mode"
            
            # For other modes, check timed slots
            active_charge_slots = self.inverter.get_active_charge_slots()
            active_discharge_slots = self.inverter.get_active_discharge_slots()
            
            # Determine actual mode from slots
            actual_mode = self._determine_actual_mode(
                slot_time,
                active_charge_slots,
                active_discharge_slots
            )
            
            # Compare
            if slot_mode == 'Force Charge' and actual_mode != 'Force Charge':
                return True, f"Need Force Charge slot (currently {actual_mode})"
            
            elif slot_mode == 'Force Discharge' and actual_mode != 'Force Discharge':
                return True, f"Need Force Discharge slot (currently {actual_mode})"
            
            elif slot_mode == 'Self Use':
                # Check both slots and mode switch
                if actual_mode != 'Self Use':
                    return True, f"Need to clear forced slots (currently {actual_mode})"
                if current_switch_mode and current_switch_mode != "Self-Use - No Timed Charge/Discharge":
                    return True, f"Need Self-Use mode (currently {current_switch_mode})"
                return False, "Already in Self Use mode"
            
            else:
                return False, f"Already in {slot_mode} mode"
                
        except Exception as e:
            self.log(f"Error checking inverter state: {e}", level="WARNING")
            # If we can't read state, better to try updating
            return True, f"Cannot read inverter state, applying plan"
    
    def _determine_actual_mode(self, slot_time: datetime, 
                               charge_slots: List[Dict], 
                               discharge_slots: List[Dict]) -> str:
        """
        Determine what mode the inverter is actually in for this time.
        
        Args:
            slot_time: The time we're checking
            charge_slots: Active charge slots from inverter
            discharge_slots: Active discharge slots from inverter
            
        Returns:
            'Force Charge' | 'Force Discharge' | 'Self Use'
        """
        # Check if this time falls within any charge slot
        for charge in charge_slots:
            if self._time_in_slot(slot_time, charge['start'], charge['end']):
                return 'Force Charge'
        
        # Check if this time falls within any discharge slot
        for discharge in discharge_slots:
            if self._time_in_slot(slot_time, discharge['start'], discharge['end']):
                return 'Force Discharge'
        
        # Not in any forced slot = Self Use
        return 'Self Use'
    
    def _time_in_slot(self, check_time: datetime, start: datetime, end: datetime) -> bool:
        """Check if time falls within a slot (handles day wrap)"""
        # Simple case: start < end (same day)
        if start <= end:
            return start <= check_time < end
        
        # Day wrap case: start > end (crosses midnight)
        else:
            return check_time >= start or check_time < end
    
    def _apply_to_inverter(self, slot: Dict) -> bool:
        """
        Apply the slot's mode to the inverter.
        
        Handles three types of control:
        1. Force Charge - Uses timed charge slot
        2. Force Discharge - Uses timed discharge slot  
        3. Feed-in Priority - Uses mode switch (for clipping prevention)
        4. Self Use - Clears slots and ensures Self-Use mode
        
        Args:
            slot: Plan slot with mode, time, soc_target, etc.
            
        Returns:
            True if successful, False otherwise
        """
        try:
            mode = slot['mode']
            slot_time = slot['time']
            
            if mode == 'Force Charge':
                # Set timed charge slot
                success = self._set_charge_slot(
                    start_time=slot_time,
                    end_time=slot_time + timedelta(minutes=30),
                    target_soc=slot.get('soc_end', 95.0)
                )
                # Also ensure we're in Self-Use mode for charging to work
                if success and self.mode_switch_entity:
                    self._set_mode("Self-Use - No Timed Charge/Discharge")
                return success
                
            elif mode == 'Force Discharge':
                # Set timed discharge slot
                success = self._set_discharge_slot(
                    start_time=slot_time,
                    end_time=slot_time + timedelta(minutes=30),
                    target_soc=slot.get('soc_end', 10.0)
                )
                # Also ensure we're in Self-Use mode for discharge to work
                if success and self.mode_switch_entity:
                    self._set_mode("Self-Use - No Timed Charge/Discharge")
                return success
            
            elif mode == 'Feed-in Priority':
                # Switch mode to prioritize grid export (clipping prevention!)
                # Solar goes to grid first, overflow to battery
                success = self._set_mode("Feed-in priority")
                if success:
                    self.log("Switched to Feed-in Priority mode (clipping prevention)")
                return success
                
            elif mode == 'Self Use':
                # Clear any forced slots AND ensure Self-Use mode
                success = self._clear_forced_slots(slot_time)
                if success and self.mode_switch_entity:
                    success = self._set_mode("Self-Use - No Timed Charge/Discharge")
                return success
            
            else:
                self.log(f"Unknown mode: {mode}", level="ERROR")
                return False
                
        except Exception as e:
            self.log(f"Error applying to inverter: {e}", level="ERROR")
            return False
    
    def _set_mode(self, mode_name: str) -> bool:
        """
        Set the Energy Storage Control Switch mode.
        
        Args:
            mode_name: One of:
                - "Self-Use - No Timed Charge/Discharge" (normal)
                - "Feed-in priority" (grid first, for clipping prevention)
        """
        if not self.mode_switch_entity:
            self.log("No mode switch entity configured", level="WARNING")
            return False
        
        try:
            self.log(f"Setting mode: {mode_name}")
            
            # Call Home Assistant service to set the select entity
            # Example: hass.call_service('select', 'select_option', 
            #                            entity_id=self.mode_switch_entity, 
            #                            option=mode_name)
            
            # For now, just log (actual implementation would call HA service)
            self.log(f"Would set {self.mode_switch_entity} to: {mode_name}")
            
            return True
            
        except Exception as e:
            self.log(f"Error setting mode: {e}", level="ERROR")
            return False
    
    def _set_charge_slot(self, start_time: datetime, end_time: datetime, 
                        target_soc: float) -> bool:
        """Set a timed charge slot on the inverter"""
        try:
            # Use inverter interface to set charge slot
            # This would call the actual inverter methods
            self.log(f"Setting charge slot: {start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')} to {target_soc:.0f}%")
            
            # Example: self.inverter.set_timed_charge_slot(1, start_time, end_time, target_soc)
            # For now, just log (actual implementation would call inverter methods)
            
            return True
            
        except Exception as e:
            self.log(f"Error setting charge slot: {e}", level="ERROR")
            return False
    
    def _set_discharge_slot(self, start_time: datetime, end_time: datetime,
                           target_soc: float) -> bool:
        """Set a timed discharge slot on the inverter"""
        try:
            self.log(f"Setting discharge slot: {start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')} to {target_soc:.0f}%")
            
            # Example: self.inverter.set_timed_discharge_slot(1, start_time, end_time, target_soc)
            
            return True
            
        except Exception as e:
            self.log(f"Error setting discharge slot: {e}", level="ERROR")
            return False
    
    def _clear_forced_slots(self, slot_time: datetime) -> bool:
        """Clear any forced charge/discharge slots for this time"""
        try:
            self.log(f"Clearing forced slots for {slot_time.strftime('%H:%M')}")
            
            # This would disable any timed slots that cover this time
            # Example: self.inverter.clear_timed_slots()
            
            return True
            
        except Exception as e:
            self.log(f"Error clearing slots: {e}", level="ERROR")
            return False
    
    def get_execution_summary(self) -> Dict:
        """
        Get summary of executor state.
        
        Returns:
            Dict with last_execution time and status
        """
        return {
            'last_execution': self._last_execution,
            'status': 'ready' if self.inverter else 'no_inverter'
        }
