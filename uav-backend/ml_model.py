import os
import random

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

# Trained model is persisted here so process restarts (Render sleep/wake, dev
# reloads) load it instead of retraining from scratch. Only trained when the
# file is missing (fresh clone / new instance).
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anomaly_model.joblib")

# ==============================================================================
# TRAINING ENVELOPE (For Phase 7 Confidence Heatmap)
# Altitude Range: 0 to 20,000 ft
# Throttle Range: 40.0 to 100.0 %
# The ML model is trained ONLY on healthy residuals within this envelope.
# If live telemetry falls outside this range, model confidence is degraded
# and should be flagged as "Extrapolated".
# ==============================================================================


class AnomalyDetector:
    def __init__(self):
        self.model = self._load_or_train()

    def _load_or_train(self):
        """Load the persisted model if present; otherwise train and save it."""
        if os.path.exists(MODEL_PATH):
            try:
                return joblib.load(MODEL_PATH)
            except Exception:
                # Stale model (e.g. sklearn version changed) - fall through and retrain.
                pass
        model = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)
        model.fit(self.generate_synthetic_healthy_data())
        try:
            joblib.dump(model, MODEL_PATH)
        except OSError:
            # Read-only filesystem (some hosts) - just use the in-memory model.
            pass
        return model

    def generate_synthetic_healthy_data(self, num_samples=500):
        """
        Generates healthy residuals within the training envelope.
        Seeded, so a retrain reproduces the exact same model as the persisted one.
        """
        rng = random.Random(42)
        return np.array([
            [rng.uniform(-20, 20), rng.uniform(-10, 10), rng.uniform(-5, 5)]
            for _ in range(num_samples)
        ])

    def evaluate(self, residuals: dict):
        """
        Takes live residuals and returns anomaly score (0-1) and reason.
        """
        # Convert dictionary to numpy array in the same feature order: [rpm, egt, cht]
        X_live = np.array([[residuals["rpm"], residuals["egt"], residuals["cht"]]])

        # IsolationForest decision_function: >0 is normal, <0 is anomaly
        raw_score = self.model.decision_function(X_live)[0]

        # Convert raw_score (typically -0.5 to 0.5) to a 0-1 scale.
        # Let's map so that raw_score < 0 gives an anomaly_score > 0.5.
        anomaly_score = max(0.0, min(1.0, 0.5 - raw_score * 2))

        reason = "Nominal"
        if anomaly_score > 0.5:
            # Determine which residual is most out of bounds
            abs_res = {
                "RPM": abs(residuals["rpm"]),
                "EGT": abs(residuals["egt"]),
                "CHT": abs(residuals["cht"])
            }
            # Find the max deviation relative to typical noise
            normalized_dev = {
                "RPM variance": abs_res["RPM"] / 20.0,
                "EGT shift": abs_res["EGT"] / 10.0,
                "CHT drift": abs_res["CHT"] / 5.0
            }
            worst_feature = max(normalized_dev, key=normalized_dev.get)
            reason = f"Anomaly detected driven by {worst_feature}"

        return float(anomaly_score), reason

    def check_confidence(self, altitude: float, throttle: float) -> str:
        """
        Checks if the current operating conditions fall within the training envelope.
        """
        if 0.0 <= altitude <= 20000.0 and 40.0 <= throttle <= 100.0:
            return "HIGH CONFIDENCE (In Envelope)"
        return "EXTRAPOLATED (Out of Envelope)"


# Instantiate the singleton so the model is ready (loaded, not retrained) on startup
detector = AnomalyDetector()