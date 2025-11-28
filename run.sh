#!/usr/bin/env bashs

set -e

CONFIG_PATH=/data/options.json

echo "Starting Energy Demand Predictor & Battery Optimizer..."

# Export config path for Python app
export CONFIG_PATH

# Run the application
cd /app
exec python3 -u app/main.py
