"""REST API server for the energy optimizer."""
import logging
from flask import Flask, jsonify, render_template
from flask_cors import CORS
from typing import Dict

logger = logging.getLogger(__name__)


class APIServer:
    """REST API server."""

    def __init__(self, config, coordinator):
        """Initialize API server."""
        self.config = config
        self.coordinator = coordinator
        self.app = Flask(__name__,
                        template_folder='/app/templates',
                        static_folder='/app/static')
        CORS(self.app)

        self._setup_routes()

    def _setup_routes(self):
        """Setup API routes."""

        @self.app.route('/')
        def index():
            """Web UI homepage."""
            return render_template('index.html')

        @self.app.route('/api/status')
        def status():
            """Get system status."""
            data = self.coordinator.get_latest_data()
            return jsonify({
                'status': 'ok',
                'last_update': data.get('last_update'),
                'model_trained': data.get('model_trained', False)
            })

        @self.app.route('/api/predictions')
        def predictions():
            """Get energy demand predictions."""
            data = self.coordinator.get_latest_data()
            return jsonify({
                'predictions': data.get('demand_predictions', [])
            })

        @self.app.route('/api/solar')
        def solar():
            """Get solar forecast."""
            data = self.coordinator.get_latest_data()
            return jsonify({
                'predictions': data.get('solar_predictions', []),
                'total_kwh': data.get('solar_total_kwh', 0.0)
            })

        @self.app.route('/api/battery/schedule')
        def battery_schedule():
            """Get battery optimization schedule."""
            data = self.coordinator.get_latest_data()
            optimization = data.get('optimization_result', {})
            return jsonify({
                'schedule': optimization.get('schedule', []),
                'total_cost': optimization.get('total_cost', 0.0),
                'status': optimization.get('status', 'unknown')
            })

        @self.app.route('/api/battery/current')
        def battery_current():
            """Get current battery action."""
            data = self.coordinator.get_latest_data()
            optimization = data.get('optimization_result', {})
            schedule = optimization.get('schedule', [])

            if schedule:
                current = schedule[0]
                return jsonify({
                    'action': current['action'],
                    'power_kw': current['power_kw'],
                    'soc_percent': current['soc_percent'],
                    'timestamp': current['timestamp'],
                    'import_rate_p': current['import_rate_p'],
                    'export_rate_p': current['export_rate_p']
                })

            return jsonify({
                'action': 'unknown',
                'power_kw': 0.0,
                'soc_percent': 50.0
            })

        @self.app.route('/api/optimize', methods=['POST'])
        def trigger_optimize():
            """Manually trigger optimization."""
            try:
                self.coordinator.update()
                return jsonify({'status': 'ok', 'message': 'Optimization triggered'})
            except Exception as e:
                logger.error(f"Error triggering optimization: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500

        @self.app.route('/api/train', methods=['POST'])
        def trigger_train():
            """Manually trigger model training."""
            try:
                self.coordinator.train_model()
                return jsonify({'status': 'ok', 'message': 'Training triggered'})
            except Exception as e:
                logger.error(f"Error triggering training: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500

    def run(self):
        """Run the API server."""
        port = self.config.api_port
        logger.info(f"Starting API server on port {port}")
        self.app.run(host='0.0.0.0', port=port, debug=False)
