"""
SolarBat-AI — AppDaemon Orchestrator

Thin orchestrator that wires together:
  - Providers (pricing, solar, load, export, system state)
  - Planners (rule-based, ML, LP)
  - Plan Executor (inverter control)
  - Dashboard (HTML visualization)

All domain logic lives in the provider/planner/executor classes.
This file is ONLY AppDaemon glue.
"""

import os
import sys
import json
from datetime import datetime, timedelta, time, timezone
from aiohttp import web

import appdaemon.plugins.hass.hassapi as hass


class SmartSolarOptimizer(hass.Hass):
    """AppDaemon app — orchestrates providers, planner, executor, and dashboard."""

    # ═══════════════ INITIALIZATION ═══════════════

    def initialize(self):
        self.log("=" * 80)
        self.log("SolarBat-AI v3.0 — Initializing...")
        self.log("=" * 80)

        # Ensure providers/planners directories are on sys.path
        app_dir = os.path.dirname(os.path.abspath(__file__))
        for d in [app_dir, os.path.join(app_dir, 'providers'), os.path.join(app_dir, 'planners')]:
            if d not in sys.path:
                sys.path.insert(0, d)

        # Config from apps.yaml
        self.config = dict(self.args)

        # State
        self.current_plan = None
        self._cached_plan_html = None
        self.plan_sensor = "sensor.solar_optimizer_plan"
        self.wastage_sensor = "sensor.solar_wastage_risk"

        # Load components
        self._init_providers()
        self._init_planner()
        self._init_executor()
        self._init_accuracy_tracker()
        self._create_sensors()

        # Web dashboard
        self.register_route(self.serve_plan_page, "/solar_plan")
        self.register_endpoint(self.save_settings_endpoint, "solar_plan_settings")
        self.log("[WEB] Dashboard registered at /app/solar_plan")

        # Scheduling
        agile_rates = self.config.get("agile_rates")
        if agile_rates:
            self.listen_state(self.on_agile_update, agile_rates)

        self.run_hourly(self.update_plan, time(0, 5, 0))
        self.run_minutely(self.execute_plan_if_time, time(0, 0, 1))
        self.run_daily(self.record_yesterday_actuals, time(1, 30, 0))
        self.run_in(self.generate_new_plan, 10)

        self.log("SolarBat-AI initialized successfully")
        self.log("=" * 80)

    # ── Component bootstrap ──

    def _init_providers(self):
        """Instantiate and setup all data providers."""
        from providers.import_pricing_provider import ImportPricingProvider
        from providers.export_pricing_provider import ExportPricingProvider
        from providers.solar_forecast_provider import SolarForecastProvider
        from load_forecaster import LoadForecaster

        self.import_pricing = ImportPricingProvider(self)
        if not self.import_pricing.setup(self.config):
            self.log("Import pricing provider setup failed", level="WARNING")

        self.export_pricing = ExportPricingProvider(self)
        if not self.export_pricing.setup(self.config):
            self.log("Export pricing provider setup failed", level="WARNING")

        self.solar_provider = SolarForecastProvider(self)
        if not self.solar_provider.setup(self.config):
            self.log("Solar forecast provider setup failed", level="WARNING")

        self.load_forecaster = LoadForecaster(self)
        if not self.load_forecaster.setup(self.config):
            self.log("Load forecaster setup failed", level="WARNING")

        # Inverter interface (Solis S6)
        try:
            from inverter_interface_solis6 import SolisInverterInterface
            self.inverter = SolisInverterInterface(self)
            if not self.inverter.setup(self.config):
                self.log("Inverter interface setup failed", level="WARNING")
        except ImportError:
            self.log("Solis inverter interface not found", level="WARNING")
            self.inverter = None

    def _init_planner(self):
        """Instantiate the selected planner."""
        planner_type = self.config.get("planner", "rule-based")

        from planners import RuleBasedPlanner, MLPlanner, LinearProgrammingPlanner

        if planner_type == "ml" and MLPlanner:
            try:
                self.planner = MLPlanner()
                self.log("Using ML planner")
                return
            except Exception as e:
                self.log(f"ML planner failed ({e}), falling back to rule-based", level="WARNING")

        if planner_type == "lp" and LinearProgrammingPlanner:
            try:
                self.planner = LinearProgrammingPlanner()
                self.log("Using LP planner")
                return
            except Exception as e:
                self.log(f"LP planner failed ({e}), falling back to rule-based", level="WARNING")

        self.planner = RuleBasedPlanner()
        self.log("Using rule-based planner")

    def _init_executor(self):
        """Instantiate the plan executor."""
        from plan_executor import PlanExecutor
        mode_switch = self.config.get("mode_switch")
        self.executor = PlanExecutor(self, self.inverter, mode_switch_entity=mode_switch)

    def _init_accuracy_tracker(self):
        """Load forecast accuracy tracker."""
        try:
            from forecast_accuracy_tracker import ForecastAccuracyTracker
            history_file = self.config.get("history_file", "/config/appdaemon/solar_optimizer_history.json")
            self.accuracy_tracker = ForecastAccuracyTracker(history_file)
            self.log(f"Accuracy tracker loaded: {self.accuracy_tracker.get_summary()}")
        except Exception as e:
            self.log(f"Accuracy tracker not available: {e}", level="WARNING")
            self.accuracy_tracker = None

    def _create_sensors(self):
        """Create HA sensors for plan display."""
        self.set_state(self.plan_sensor, state="initialized", attributes={
            "friendly_name": "Solar Optimizer 24h Plan",
            "icon": "mdi:calendar-clock",
            "plan": [], "generated_at": None,
        })
        self.set_state(self.wastage_sensor, state="0", attributes={
            "friendly_name": "Solar Wastage Risk",
            "icon": "mdi:solar-power-variant",
            "unit_of_measurement": "kWh",
        })

    # ═══════════════ PLAN GENERATION ═══════════════

    def generate_new_plan(self, kwargs=None):
        """Gather data from all providers and run the planner."""
        self.log("Generating new 24-hour plan...")

        try:
            # ── Gather data from providers ──
            price_data = self.import_pricing.get_prices_with_confidence(hours=24)
            if not price_data or not price_data.get('prices'):
                self.log("Cannot generate plan — no import pricing data", level="WARNING")
                return

            import_prices = [
                {'time': p['start'], 'price': p['price'], 'is_predicted': p.get('is_predicted', False)}
                for p in price_data['prices']
            ]

            export_prices = self.export_pricing.get_data(hours=24)
            if not export_prices:
                rate = float(self.config.get('export_rate', 15.0))
                export_prices = [{'time': p['time'], 'price': rate} for p in import_prices]

            solar_data = self.solar_provider.get_data(hours=24)
            if not solar_data:
                self.log("No solar forecast, using zeros", level="WARNING")
                solar_data = [{'time': p['time'], 'kw': 0} for p in import_prices]

            load_forecast = self.load_forecaster.predict_loads_24h()
            if not load_forecast:
                self.log("No load forecast, using defaults", level="WARNING")
                load_forecast = [{'time': p['time'], 'load_kw': 0.5, 'confidence': 'low'}
                                 for p in import_prices]

            # System state from inverter
            if self.inverter:
                inv_state = self.inverter.get_current_state()
                inv_caps = self.inverter.get_capabilities()
            else:
                inv_state = self._fallback_state()
                inv_caps = self._fallback_capabilities()

            system_state = {
                'current_state': inv_state,
                'capabilities': inv_caps,
                'active_slots': inv_state.get('active_slots', {'charge': [], 'discharge': []}),
            }

            # ── Run planner ──
            plan = self.planner.create_plan(
                import_prices=import_prices,
                export_prices=export_prices,
                solar_forecast=solar_data,
                load_forecast=load_forecast,
                system_state=system_state,
            )

            # ── Store result ──
            self.current_plan = {
                'timestamp': datetime.now(),
                'battery_soc': inv_state['battery_soc'],
                'battery_capacity': inv_caps['battery_capacity'],
                'prices': price_data['prices'],
                'plan_steps': plan.get('slots', []),
                'statistics': price_data.get('statistics', {}),
                'confidence': price_data.get('confidence', 'unknown'),
                'hours_known': price_data.get('hours_known', 0),
                'hours_predicted': price_data.get('hours_predicted', 0),
                'total_cost': self._calc_total_cost(plan.get('slots', [])),
                'metadata': plan.get('metadata', {}),
            }
            self._cached_plan_html = None

            # Update HA sensor
            mode_counts = {}
            for step in self.current_plan['plan_steps']:
                m = step.get('mode', 'Self Use')
                mode_counts[m] = mode_counts.get(m, 0) + 1

            self.set_state(self.plan_sensor, state="active", attributes={
                "friendly_name": "Solar Optimizer 24h Plan",
                "icon": "mdi:calendar-clock",
                "generated_at": datetime.now().isoformat(),
                "total_cost": f"£{self.current_plan['total_cost']:.2f}",
                "mode_counts": mode_counts,
                "confidence": self.current_plan['confidence'],
            })

            # Record predictions for accuracy tracking
            if self.accuracy_tracker:
                try:
                    self.accuracy_tracker.record_predictions(self.current_plan['plan_steps'])
                except Exception as e:
                    self.log(f"Accuracy recording error: {e}", level="WARNING")

            summary = ", ".join(f"{m}={c}h" for m, c in mode_counts.items() if c > 0)
            self.log(f"Plan generated: Cost: £{self.current_plan['total_cost']:.2f}, {summary}")

        except Exception as e:
            self.log(f"Error generating plan: {e}", level="ERROR")
            import traceback
            self.log(traceback.format_exc(), level="ERROR")

    def _fallback_state(self):
        """Get battery state directly from HA when inverter interface unavailable."""
        return {
            'battery_soc': float(self.get_state(self.config.get('battery_soc', 'sensor.battery_soc')) or 50),
            'battery_power': 0, 'pv_power': 0, 'grid_power': 0,
            'active_slots': {'charge': [], 'discharge': []},
        }

    def _fallback_capabilities(self):
        """Get capabilities from config when inverter interface unavailable."""
        return {
            'battery_capacity': float(self.config.get('battery_capacity', 10)),
            'max_charge_rate': float(self.config.get('battery_rate_max', 3000)) / 1000,
            'max_discharge_rate': float(self.config.get('battery_rate_max', 3000)) / 1000,
        }

    def _calc_total_cost(self, slots):
        if not slots:
            return 0.0
        return slots[-1].get('cumulative_cost', 0) / 100

    # ═══════════════ PLAN EXECUTION ═══════════════

    def execute_plan_if_time(self, kwargs):
        """Execute plan only at :00 and :30 (Agile slot boundaries)."""
        now = datetime.now()
        if now.minute not in [0, 30]:
            return
        if not self.current_plan:
            return
        try:
            result = self.executor.execute(
                {'slots': self.current_plan['plan_steps'],
                 'metadata': self.current_plan.get('metadata', {})}
            )
            if result and result.get('executed'):
                self.log(f"[EXEC] {result.get('action_taken', 'Mode changed')}")
        except Exception as e:
            self.log(f"Execution error: {e}", level="ERROR")

    # ═══════════════ EVENT HANDLERS ═══════════════

    def on_agile_update(self, entity, attribute, old, new, kwargs):
        self.log("Agile rates updated — regenerating plan")
        self.run_in(self.generate_new_plan, 5)

    def update_plan(self, kwargs):
        self.generate_new_plan()

    def record_yesterday_actuals(self, kwargs):
        if not self.accuracy_tracker:
            return
        try:
            self.accuracy_tracker.record_actuals_from_ha(self)
            self.log("Yesterday's actuals recorded for accuracy tracking")
        except Exception as e:
            self.log(f"Error recording actuals: {e}", level="WARNING")

    # ═══════════════ WEB DASHBOARD ═══════════════

    async def serve_plan_page(self, request, kwargs):
        """Serve HTML dashboard via register_route → /app/solar_plan."""
        try:
            if not self._cached_plan_html:
                self._cached_plan_html = self._generate_plan_html()

            html = self._cached_plan_html

            tab = request.query.get('tab', 'plan') if hasattr(request, 'query') else 'plan'
            if tab != 'plan':
                html = html.replace("switchTab('plan')", f"switchTab('{tab}')", 1)

            return web.Response(text=html, content_type='text/html', charset='utf-8')

        except Exception as e:
            self.log(f"[WEB] Error serving page: {e}", level="ERROR")
            return web.Response(
                text=f"<html><body><h1>Error</h1><p>{e}</p></body></html>",
                content_type='text/html', status=500
            )

    async def save_settings_endpoint(self, request, kwargs):
        """POST endpoint to save settings."""
        try:
            data = await request.json()
            for key, value in data.items():
                self.config[key] = value
            self._cached_plan_html = None
            return json.dumps({'status': 'ok', 'updated': len(data)}), 200
        except Exception as e:
            return json.dumps({'status': 'error', 'message': str(e)}), 500

    # ── HTML generation (same approach as test_harness) ──

    def _generate_plan_html(self):
        """Generate full HTML page using templates."""
        if not self.current_plan:
            return ("<html><body><h1>No plan generated yet</h1>"
                    "<p>Waiting for first plan cycle...</p></body></html>")

        try:
            from forecast_accuracy_tracker import (
                generate_accuracy_html_parts, build_prediction_data, generate_settings_html_parts
            )
        except ImportError:
            generate_accuracy_html_parts = None
            build_prediction_data = None
            generate_settings_html_parts = None

        plan = self.current_plan

        # Load templates
        app_dir = os.path.dirname(os.path.abspath(__file__))
        template_dir = os.path.join(app_dir, 'templates')
        try:
            with open(os.path.join(template_dir, 'plan.html'), 'r', encoding='utf-8') as f:
                html_template = f.read()
            with open(os.path.join(template_dir, 'plan.css'), 'r', encoding='utf-8') as f:
                css_content = f.read()
            with open(os.path.join(template_dir, 'plan.js'), 'r', encoding='utf-8') as f:
                js_content = f.read()
        except FileNotFoundError as e:
            return f"<html><body><h1>Template not found</h1><p>{e}</p></body></html>"

        # ── TAB 1: Plan ──
        stats = plan.get('statistics', {})
        summary_stats = f"""
            <div class="stat-box"><div class="stat-label">Current SOC</div><div class="stat-value">{plan['battery_soc']:.1f}%</div></div>
            <div class="stat-box"><div class="stat-label">Battery Size</div><div class="stat-value">{plan['battery_capacity']:.1f} kWh</div></div>
            <div class="stat-box"><div class="stat-label">Min Price</div><div class="stat-value">{stats.get('min', 0):.2f}p</div></div>
            <div class="stat-box"><div class="stat-label">Max Price</div><div class="stat-value">{stats.get('max', 0):.2f}p</div></div>
            <div class="stat-box"><div class="stat-label">Avg Price</div><div class="stat-value">{stats.get('avg', 0):.2f}p</div></div>
            <div class="stat-box"><div class="stat-label">Confidence</div><div class="stat-value">{plan.get('confidence', '?').upper()}</div></div>
            <div class="stat-box"><div class="stat-label">24h Cost</div><div class="stat-value">£{plan.get('total_cost', 0):.2f}</div></div>
        """

        mode_counts = {}
        for step in plan['plan_steps']:
            m = step.get('mode', 'Self Use')
            mode_counts[m] = mode_counts.get(m, 0) + 1

        plan_rows = ""
        for step in plan['plan_steps']:
            mode_class = f"mode-{step['mode'].lower().replace(' ', '-')}"
            pred_marker = " *" if step.get('is_predicted_price', False) else ""
            slot_cost = step.get('cost', 0)
            cost_class = "cost-positive" if slot_cost >= 0 else "cost-negative"
            cumulative = step.get('cumulative_cost', 0) / 100
            cumulative_str = f"£{cumulative:.2f}" if cumulative >= 0 else f"-£{abs(cumulative):.2f}"
            mode_display = '⚡ Feed-in Priority' if step['mode'] == 'Feed-in Priority' else step['mode']
            step_time = step.get('time', '')
            time_str = step_time.strftime('%H:%M') if hasattr(step_time, 'strftime') else str(step_time)

            plan_rows += f"""<tr class="{mode_class}">
                <td><strong>{time_str}</strong></td>
                <td><strong>{mode_display}</strong></td>
                <td>{step.get('action', '')}</td>
                <td>{step.get('soc_end', 0):.1f}%</td>
                <td>{step.get('solar_kw', 0):.2f}</td>
                <td>{step.get('import_price', 0):.2f}p{pred_marker}</td>
                <td>{step.get('export_price', 0):.2f}p</td>
                <td class="{cost_class}">{abs(slot_cost):.2f}p</td>
                <td><strong>{cumulative_str}</strong></td>
            </tr>"""

        info_summary = f"""
            <strong>Plan Summary:</strong><br>
            Known prices: {plan.get('hours_known', 0):.1f}h &nbsp;
            Predicted: {plan.get('hours_predicted', 0):.1f}h &nbsp;
            Confidence: {plan.get('confidence', '?')} &nbsp;
            Cost: £{plan.get('total_cost', 0):.2f}<br>
            <strong>Modes:</strong> {' &nbsp; '.join(f'{m}: {c}' for m, c in mode_counts.items())}
        """

        # ── TAB 2: Predictions ──
        if build_prediction_data:
            prediction_data = build_prediction_data(plan['plan_steps'])
        else:
            prediction_data = {'timeLabels': [], 'solarValues': [], 'socValues': [],
                               'loadValues': [], 'importPrices': [], 'exportPrices': []}

        prediction_info = ("<strong>Sources:</strong> Solar from Solcast, "
                           "Load from AI forecaster, Prices from Octopus Agile.")

        # ── TAB 3: Accuracy ──
        empty_accuracy = {
            'dates': [], 'solar_predicted': [], 'solar_actual': [],
            'solar_mape': [], 'load_predicted': [], 'load_actual': [],
            'load_mape': [], 'price_predicted_avg': [], 'price_actual_avg': [],
            'price_mae': [], 'summary': {}
        }
        if self.accuracy_tracker and generate_accuracy_html_parts:
            try:
                accuracy_data = self.accuracy_tracker.get_accuracy_data(days=10)
            except Exception:
                accuracy_data = empty_accuracy
            accuracy_parts = generate_accuracy_html_parts(accuracy_data)
        elif generate_accuracy_html_parts:
            accuracy_data = empty_accuracy
            accuracy_parts = generate_accuracy_html_parts(accuracy_data)
        else:
            accuracy_data = empty_accuracy
            accuracy_parts = {
                'metrics': '<div class="no-data-message"><h3>No Accuracy Data Yet</h3>'
                           '<p>Data appears after a few days of operation.</p></div>',
                'rows': '<tr><td colspan="8" style="text-align:center;color:#95a5a6;'
                        'padding:30px;">Waiting for data...</td></tr>',
                'info': 'Forecast Accuracy: Waiting for data to accumulate.'
            }

        # ── TAB 4: Settings ──
        if generate_settings_html_parts:
            settings_parts = generate_settings_html_parts(self.config)
        else:
            settings_parts = {'thresholds': '<p>Not available</p>', 'modes': '', 'sensors': '', 'info': ''}

        # ── Substitute all template placeholders ──
        html = html_template
        html = html.replace('{{timestamp}}', plan['timestamp'].strftime('%Y-%m-%d %H:%M:%S'))
        html = html.replace('{{summary_stats}}', summary_stats)
        html = html.replace('{{plan_rows}}', plan_rows)
        html = html.replace('{{info_summary}}', info_summary)
        html = html.replace('{{chart_data}}', json.dumps({}))
        html = html.replace('{{prediction_data}}', json.dumps(prediction_data))
        html = html.replace('{{prediction_info}}', prediction_info)
        html = html.replace('{{accuracy_data}}', json.dumps(accuracy_data, default=str))
        html = html.replace('{{accuracy_metrics}}', accuracy_parts.get('metrics', ''))
        html = html.replace('{{accuracy_rows}}', accuracy_parts.get('rows', ''))
        html = html.replace('{{accuracy_info}}', accuracy_parts.get('info', ''))
        html = html.replace('{{settings_thresholds}}', settings_parts.get('thresholds', ''))
        html = html.replace('{{settings_modes}}', settings_parts.get('modes', ''))
        html = html.replace('{{settings_sensors}}', settings_parts.get('sensors', ''))
        html = html.replace('{{settings_info}}', settings_parts.get('info', ''))
        html = html.replace('{{settings_data}}', json.dumps(self.config, default=str))

        # Inline CSS and JS
        html = html.replace('<link rel="stylesheet" href="plan.css">', f'<style>{css_content}</style>')
        html = html.replace('<script src="plan.js"></script>', f'<script>{js_content}</script>')

        return html