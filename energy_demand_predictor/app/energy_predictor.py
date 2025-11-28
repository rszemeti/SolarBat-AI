"""Energy demand prediction using machine learning."""
import numpy as np
import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
import joblib
import os

logger = logging.getLogger(__name__)


class EnergyDemandPredictor:
    """ML-based energy demand predictor."""

    def __init__(self, config, ha_client):
        """Initialize predictor."""
        self.config = config
        self.ha_client = ha_client
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        self.model_path = '/data/energy_model.pkl'
        self.scaler_path = '/data/energy_scaler.pkl'

        # Try to load existing model
        self._load_model()

    def _load_model(self):
        """Load trained model from disk."""
        if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
            try:
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)
                self.is_trained = True
                logger.info("Loaded existing energy prediction model")
            except Exception as e:
                logger.error(f"Error loading model: {e}")

    def _save_model(self):
        """Save trained model to disk."""
        try:
            joblib.dump(self.model, self.model_path)
            joblib.dump(self.scaler, self.scaler_path)
            logger.info("Saved energy prediction model")
        except Exception as e:
            logger.error(f"Error saving model: {e}")

    def _extract_features(self, timestamp: datetime) -> np.ndarray:
        """Extract features from timestamp."""
        features = [
            timestamp.hour,
            timestamp.minute,
            timestamp.weekday(),
            timestamp.day,
            timestamp.month,
            int(timestamp.weekday() >= 5),  # Is weekend
            np.sin(2 * np.pi * timestamp.hour / 24),  # Hour cyclical
            np.cos(2 * np.pi * timestamp.hour / 24),
            np.sin(2 * np.pi * timestamp.weekday() / 7),  # Day cyclical
            np.cos(2 * np.pi * timestamp.weekday() / 7),
            np.sin(2 * np.pi * timestamp.month / 12),  # Month cyclical
            np.cos(2 * np.pi * timestamp.month / 12),
        ]
        return np.array(features)

    def _prepare_training_data(self, history: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare training data from historical records."""
        X = []
        y = []

        for record in history:
            try:
                timestamp = datetime.fromisoformat(record['last_updated'].replace('Z', '+00:00'))
                state = float(record['state'])

                if state < 0 or state > 50:  # Sanity check
                    continue

                features = self._extract_features(timestamp)
                X.append(features)
                y.append(state)
            except (ValueError, KeyError):
                continue

        return np.array(X), np.array(y)

    def train(self) -> bool:
        """Train the prediction model."""
        logger.info("Starting model training...")

        # Get historical data
        history = self.ha_client.get_history(
            self.config.entity_id,
            days=self.config.max_training_days
        )

        if len(history) < 100:
            logger.error(f"Insufficient training data: {len(history)} records")
            return False

        # Prepare data
        X, y = self._prepare_training_data(history)

        if len(X) < 100:
            logger.error(f"Insufficient valid training samples: {len(X)}")
            return False

        logger.info(f"Training with {len(X)} samples")

        # Scale features
        X_scaled = self.scaler.fit_transform(X)

        # Train model
        self.model = GradientBoostingRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=42
        )

        self.model.fit(X_scaled, y)
        self.is_trained = True

        # Save model
        self._save_model()

        logger.info("Model training complete!")
        return True

    def predict(self, slots: int = 96) -> List[Dict]:
        """
        Predict energy demand for next N slots (30-min intervals).

        Args:
            slots: Number of 30-minute slots to predict

        Returns:
            List of predictions with timestamps
        """
        if not self.is_trained:
            logger.warning("Model not trained, training now...")
            if not self.train():
                return []

        predictions = []
        now = datetime.now()

        # Round to next 30-minute interval
        minutes = (now.minute // 30 + 1) * 30
        if minutes == 60:
            start_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            start_time = now.replace(minute=minutes, second=0, microsecond=0)

        for i in range(slots):
            timestamp = start_time + timedelta(minutes=30 * i)
            features = self._extract_features(timestamp)
            features_scaled = self.scaler.transform([features])

            prediction = self.model.predict(features_scaled)[0]
            prediction = max(0, prediction)  # No negative predictions

            predictions.append({
                'timestamp': timestamp.isoformat(),
                'predicted_kw': round(prediction, 3),
                'slot': i
            })

        return predictions

    def get_next_prediction(self) -> float:
        """Get prediction for next 30-minute slot."""
        predictions = self.predict(slots=1)
        if predictions:
            return predictions[0]['predicted_kw']
        return 0.0
