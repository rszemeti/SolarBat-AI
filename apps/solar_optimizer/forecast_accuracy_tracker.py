#!/usr/bin/env python3
"""
SolarBat-AI Dashboard Data Helpers

Provides:
- ForecastAccuracyTracker: stores daily predictions vs actuals
- generate_accuracy_html_parts(): HTML for the Accuracy tab
- generate_prediction_data(): JSON for the Predictions tab charts
- generate_settings_html_parts(): HTML for the Settings tab
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional


# ═══════════════════════════════════════════════════════════════
# FORECAST ACCURACY TRACKER
# ═══════════════════════════════════════════════════════════════

class ForecastAccuracyTracker:
    """Tracks prediction vs actual values for forecast accuracy analysis."""
    
    def __init__(self, cache_dir: str = None):
        if cache_dir is None:
            cache_dir = os.path.join(os.path.expanduser('~'), '.solarbat-ai')
        os.makedirs(cache_dir, exist_ok=True)
        self.filepath = os.path.join(cache_dir, 'forecast_accuracy.json')
        self.data = self._load()
    
    def _load(self) -> Dict:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {'days': {}}
    
    def _save(self):
        try:
            with open(self.filepath, 'w') as f:
                json.dump(self.data, f, indent=2)
        except IOError as e:
            print(f"[ACCURACY] Warning: Could not save: {e}")
    
    def _ensure_day(self, date_str: str):
        if date_str not in self.data['days']:
            self.data['days'][date_str] = {'predicted': {}, 'actual': {}}
    
    def record_predictions(self, date_str: str, solar_total_kwh: float,
                          load_total_kwh: float, avg_import_price: float):
        self._ensure_day(date_str)
        self.data['days'][date_str]['predicted'] = {
            'solar_kwh': round(solar_total_kwh, 2),
            'load_kwh': round(load_total_kwh, 2),
            'avg_import_price': round(avg_import_price, 2),
            'recorded_at': datetime.now().isoformat()
        }
        self._save()
    
    def record_actuals(self, date_str: str, solar_total_kwh: float,
                      load_total_kwh: float, avg_import_price: float):
        self._ensure_day(date_str)
        self.data['days'][date_str]['actual'] = {
            'solar_kwh': round(solar_total_kwh, 2),
            'load_kwh': round(load_total_kwh, 2),
            'avg_import_price': round(avg_import_price, 2),
            'recorded_at': datetime.now().isoformat()
        }
        self._save()
    
    def get_accuracy_data(self, days: int = 10) -> Dict:
        """Get accuracy data for the last N days with both predicted and actual."""
        result = {
            'dates': [], 'solar_predicted': [], 'solar_actual': [], 'solar_mape': [],
            'load_predicted': [], 'load_actual': [], 'load_mape': [],
            'price_predicted_avg': [], 'price_actual_avg': [], 'price_mae': [],
            'summary': {}
        }
        
        complete = []
        for date_str, day in self.data.get('days', {}).items():
            if day.get('predicted') and day.get('actual'):
                complete.append((date_str, day))
        
        complete.sort(key=lambda x: x[0], reverse=True)
        complete = complete[:days]
        complete.reverse()
        
        if not complete:
            return result
        
        for date_str, day in complete:
            pred, act = day['predicted'], day['actual']
            result['dates'].append(date_str)
            
            sp, sa = pred.get('solar_kwh', 0), act.get('solar_kwh', 0)
            result['solar_predicted'].append(sp)
            result['solar_actual'].append(sa)
            result['solar_mape'].append(_mape(sp, sa))
            
            lp, la = pred.get('load_kwh', 0), act.get('load_kwh', 0)
            result['load_predicted'].append(lp)
            result['load_actual'].append(la)
            result['load_mape'].append(_mape(lp, la))
            
            pp, pa = pred.get('avg_import_price', 0), act.get('avg_import_price', 0)
            result['price_predicted_avg'].append(pp)
            result['price_actual_avg'].append(pa)
            result['price_mae'].append(round(abs(pp - pa), 2))
        
        n = len(complete)
        result['summary'] = {
            'days_tracked': n,
            'solar_avg_mape': round(sum(result['solar_mape']) / n, 1),
            'load_avg_mape': round(sum(result['load_mape']) / n, 1),
            'price_avg_mae': round(sum(result['price_mae']) / n, 2),
            'solar_rating': _rate(sum(result['solar_mape']) / n, 15, 30),
            'load_rating': _rate(sum(result['load_mape']) / n, 10, 25),
            'price_rating': _rate(sum(result['price_mae']) / n, 3, 8),
        }
        
        return result
    
    def prune_old_data(self, max_days: int = 60):
        cutoff = (datetime.now() - timedelta(days=max_days)).strftime('%Y-%m-%d')
        self.data['days'] = {k: v for k, v in self.data['days'].items() if k >= cutoff}
        self._save()
    
    def get_stats(self) -> Dict:
        days = self.data.get('days', {})
        complete = sum(1 for d in days.values() if d.get('predicted') and d.get('actual'))
        return {'total_days': len(days), 'complete': complete}


def _mape(predicted: float, actual: float) -> float:
    if actual == 0:
        return 0.0 if predicted == 0 else 100.0
    return round(abs(predicted - actual) / abs(actual) * 100, 1)

def _rate(val, good_thresh, ok_thresh):
    if val <= good_thresh: return 'good'
    if val <= ok_thresh: return 'ok'
    return 'poor'


# ═══════════════════════════════════════════════════════════════
# ACCURACY TAB HTML
# ═══════════════════════════════════════════════════════════════

def generate_accuracy_html_parts(accuracy_data: Dict) -> Dict:
    """Generate HTML snippets for {{accuracy_metrics}}, {{accuracy_rows}}, {{accuracy_info}}."""
    summary = accuracy_data.get('summary', {})
    dates = accuracy_data.get('dates', [])
    
    if not dates:
        return {
            'metrics': """
                <div class="no-data-message">
                    <h3>No Accuracy Data Yet</h3>
                    <p>Data appears here once the system has recorded both predictions and actuals
                    for at least one complete day. Check back after a few days of operation.</p>
                </div>""",
            'rows': '<tr><td colspan="8" style="text-align:center;color:#95a5a6;padding:30px;">Waiting for data...</td></tr>',
            'info': '<strong>Forecast Accuracy:</strong> Waiting for prediction+actual pairs to accumulate.'
        }
    
    def rc(rating):
        return rating if rating in ('good', 'ok', 'poor') else ''
    
    def label(rating):
        return 'Excellent' if rating == 'good' else 'Needs work' if rating == 'poor' else 'Acceptable'
    
    metrics = f"""
        <div class="accuracy-stat {rc(summary.get('solar_rating',''))}">
            <div class="stat-label">Solar MAPE</div>
            <div class="stat-value">{summary.get('solar_avg_mape',0):.1f}%</div>
            <div class="stat-detail">{label(summary.get('solar_rating',''))} — target &lt;15%</div>
        </div>
        <div class="accuracy-stat {rc(summary.get('load_rating',''))}">
            <div class="stat-label">Load MAPE</div>
            <div class="stat-value">{summary.get('load_avg_mape',0):.1f}%</div>
            <div class="stat-detail">{label(summary.get('load_rating',''))} — target &lt;10%</div>
        </div>
        <div class="accuracy-stat {rc(summary.get('price_rating',''))}">
            <div class="stat-label">Price MAE</div>
            <div class="stat-value">{summary.get('price_avg_mae',0):.1f}p</div>
            <div class="stat-detail">{label(summary.get('price_rating',''))} — target &lt;3p</div>
        </div>
        <div class="accuracy-stat">
            <div class="stat-label">Days Tracked</div>
            <div class="stat-value">{summary.get('days_tracked',0)}</div>
            <div class="stat-detail">Complete pairs</div>
        </div>"""
    
    rows = ""
    for i, d in enumerate(dates):
        sp, sa, sm = accuracy_data['solar_predicted'][i], accuracy_data['solar_actual'][i], accuracy_data['solar_mape'][i]
        lp, la, lm = accuracy_data['load_predicted'][i], accuracy_data['load_actual'][i], accuracy_data['load_mape'][i]
        pm = accuracy_data['price_mae'][i]
        
        ec = lambda v, g, o: 'error-good' if v <= g else ('error-ok' if v <= o else 'error-poor')
        
        rows += f"""<tr>
            <td>{d}</td><td>{sp:.1f}</td><td>{sa:.1f}</td><td class="{ec(sm,15,30)}">{sm:.1f}%</td>
            <td>{lp:.1f}</td><td>{la:.1f}</td><td class="{ec(lm,10,25)}">{lm:.1f}%</td>
            <td class="{ec(pm,3,8)}">{pm:.1f}p</td>
        </tr>"""
    
    info = f"""
        <strong>Accuracy Summary ({summary.get('days_tracked',0)} days):</strong><br>
        <strong>Solar:</strong> {summary.get('solar_avg_mape',0):.1f}% MAPE &nbsp;
        <strong>Load:</strong> {summary.get('load_avg_mape',0):.1f}% MAPE &nbsp;
        <strong>Price:</strong> {summary.get('price_avg_mae',0):.1f}p MAE<br>
        <em>MAPE = Mean Absolute Percentage Error. MAE = Mean Absolute Error.</em>"""
    
    return {'metrics': metrics, 'rows': rows, 'info': info}


# ═══════════════════════════════════════════════════════════════
# PREDICTION DATA (TAB 2)
# ═══════════════════════════════════════════════════════════════

def build_prediction_data(plan_steps: list) -> Dict:
    """
    Extract prediction chart data from plan steps.
    Returns dict with timeLabels, solarValues, socValues, loadValues, importPrices, exportPrices.
    """
    data = {
        'timeLabels': [],
        'solarValues': [],
        'socValues': [],
        'loadValues': [],
        'importPrices': [],
        'exportPrices': []
    }
    
    for step in plan_steps:
        t = step.get('time', '')
        data['timeLabels'].append(t.strftime('%H:%M') if hasattr(t, 'strftime') else str(t))
        data['solarValues'].append(step.get('solar_kw', step.get('expected_solar', 0)))
        data['socValues'].append(step.get('soc_end', step.get('expected_soc', 0)))
        data['loadValues'].append(step.get('load_kw', step.get('expected_consumption', 0)))
        data['importPrices'].append(step.get('import_price', step.get('price', 0)))
        data['exportPrices'].append(step.get('export_price', 0))
    
    return data


# ═══════════════════════════════════════════════════════════════
# SETTINGS TAB HTML (TAB 4)
# ═══════════════════════════════════════════════════════════════

def generate_settings_html_parts(config: Dict) -> Dict:
    """
    Generate HTML for {{settings_thresholds}}, {{settings_modes}}, {{settings_sensors}}, {{settings_info}}.
    
    config should be the self.args dict from the AppDaemon app.
    """
    
    def text_input(key, label, value, hint='', mono=False):
        cls = 'setting-input' + (' mono' if mono else '')
        return f"""<div class="setting-item">
            <label class="setting-label">{label}</label>
            <input type="text" class="setting-input" data-key="{key}" value="{_esc(value)}" />
            {'<span class="setting-hint">' + hint + '</span>' if hint else ''}
        </div>"""
    
    def num_input(key, label, value, unit='', hint=''):
        return f"""<div class="setting-item">
            <label class="setting-label">{label}{(' (' + unit + ')') if unit else ''}</label>
            <input type="number" step="any" class="setting-input" data-key="{key}" value="{value}" />
            {'<span class="setting-hint">' + hint + '</span>' if hint else ''}
        </div>"""
    
    def toggle_input(key, label, checked):
        chk = 'checked' if checked else ''
        return f"""<div class="setting-item">
            <div class="setting-toggle">
                <label class="toggle-switch">
                    <input type="checkbox" data-key="{key}" {chk} />
                    <span class="toggle-slider"></span>
                </label>
                <span class="toggle-label">{label}</span>
            </div>
        </div>"""
    
    # Thresholds
    thresholds = ''
    thresholds += num_input('min_wastage_threshold', 'Min Wastage Threshold', config.get('min_wastage_threshold', 1.0), 'kWh', 'Minimum solar waste to trigger pre-emptive discharge')
    thresholds += num_input('min_benefit_threshold', 'Min Benefit Threshold', config.get('min_benefit_threshold', 0.50), '£', 'Minimum financial benefit to justify discharge')
    thresholds += num_input('preemptive_discharge_min_soc', 'Discharge Min SOC', config.get('preemptive_discharge_min_soc', 50), '%', 'Never discharge below this level')
    thresholds += num_input('preemptive_discharge_max_price', 'Discharge Max Price', config.get('preemptive_discharge_max_price', 20), 'p/kWh', 'Don\'t discharge if grid is more expensive')
    thresholds += num_input('min_change_interval', 'Min Mode Change Interval', config.get('min_change_interval', 3600), 'seconds', 'Prevents inverter mode spam')
    thresholds += toggle_input('enable_preemptive_discharge', 'Enable Pre-emptive Discharge', config.get('enable_preemptive_discharge', True))
    thresholds += toggle_input('has_export', 'Has Export Tariff', config.get('has_export', False))
    
    # Inverter modes
    modes = ''
    modes += text_input('mode_self_use', 'Self Use Mode', config.get('mode_self_use', 'Self Use'), 'Exact inverter mode name')
    modes += text_input('mode_grid_first', 'Grid First Mode', config.get('mode_grid_first', 'Grid First'))
    modes += text_input('mode_force_charge', 'Force Charge Mode', config.get('mode_force_charge', 'Force Charge'))
    modes += text_input('mode_force_discharge', 'Force Discharge Mode', config.get('mode_force_discharge', ''), 'Leave empty if not supported')
    
    # Sensor entity mappings
    sensor_defs = [
        ('battery_soc', 'Battery SOC', 'sensor.solax_battery_soc'),
        ('battery_capacity', 'Battery Capacity', 'sensor.solax_battery_capacity'),
        ('inverter_mode', 'Inverter Mode Select', 'select.solax_charger_use_mode'),
        ('max_charge_rate', 'Max Charge Rate', 'sensor.solax_battery_charge_max_current'),
        ('max_discharge_rate', 'Max Discharge Rate', 'sensor.solax_battery_discharge_max_current'),
        ('inverter_max_power', 'Inverter Max Power', 'sensor.solax_inverter_power'),
        ('battery_voltage', 'Battery Voltage', 'sensor.solax_battery_voltage'),
        ('grid_export_limit', 'Grid Export Limit', 'sensor.solax_export_control_user_limit'),
        ('pv_power', 'PV Power', 'sensor.solax_pv_power'),
        ('battery_power', 'Battery Power', 'sensor.solax_battery_power'),
        ('load_power', 'House Load', 'sensor.solax_house_load'),
        ('grid_power', 'Grid Power', 'sensor.solax_measured_power'),
        ('solcast_remaining', 'Solcast Remaining Today', 'sensor.solcast_pv_forecast_forecast_remaining_today'),
        ('solcast_tomorrow', 'Solcast Tomorrow', 'sensor.solcast_pv_forecast_forecast_tomorrow'),
        ('solcast_forecast_today', 'Solcast Forecast Today', 'sensor.solcast_pv_forecast_forecast_today'),
        ('agile_current', 'Agile Current Rate', 'sensor.octopus_energy_electricity_current_rate'),
        ('agile_rates', 'Agile Rates Event', 'event.octopus_energy_electricity_current_day_rates'),
        ('export_rate_sensor', 'Export Rate Sensor', ''),
    ]
    
    sensors = ''
    for key, label, default in sensor_defs:
        sensors += text_input(key, label, config.get(key, default))
    
    info = """
        <strong>About Settings:</strong><br>
        Changes are sent to the AppDaemon backend and saved to the config file.
        They take effect on the next plan generation cycle (typically every 30 minutes or on Agile rate update).<br><br>
        <strong>Sensor mappings</strong> must be valid Home Assistant entity IDs. Check Developer Tools → States to find yours.<br>
        <strong>Inverter modes</strong> must match exactly (case-sensitive) — check your inverter's select entity options.
    """
    
    return {
        'thresholds': thresholds,
        'modes': modes,
        'sensors': sensors,
        'info': info
    }


def build_settings_data(config: Dict) -> Dict:
    """Build a JSON-serialisable dict of current settings for the JS side."""
    return {k: v for k, v in config.items() if isinstance(v, (str, int, float, bool, type(None)))}


def _esc(val):
    """HTML-escape a value for attribute insertion."""
    return str(val).replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
