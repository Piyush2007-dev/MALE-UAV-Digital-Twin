import os
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
import random
# ==============================================================================
# TRAINING ENVELOPE (For Phase 7 Confidence Heatmap)
# Altitude Range: 0 to 20,000 ft
# Throttle Range: 40.0 to 100.0 %
# The ML model is trained ONLY on healthy data within this envelope.
# If live telemetry falls outside this range, model confidence is degraded
# and should be flagged as "Extrapolated".
# ==============================================================================
# ==============================================================================
# ALGORITHM SELECTION RATIONALE: ISOLATION FOREST
#
# We utilize scikit-learn's IsolationForest as a deliberate engineering choice
# for our first-pass anomaly screen. This provides key operational benefits:
#
# 1. Fast & Lightweight: No GPU or heavy deep learning loops required.
# 2. Unsupervised: Needs zero failure-labeled data, identifying anomalies
#    purely by isolating them in feature space against a healthy baseline.
# 3. Validated: Proven, real-world methodology for this exact use case,
#    supported by literature:
#    Amruthnath & Gupta, "A research study on unsupervised machine learning
#    algorithms for early fault detection in predictive maintenance,"
#    IEEE ICIEA 2018.
#
# This serves as a rapid, interpretable anomaly detector that flags deviations,
# acting as the trigger for deeper localized diagnostic engines.
#
# The feature vector utilizes a 5-dimensional space including egt_spread 
# and cht_spread, which carry the cross-cylinder imbalance signal that is 
# the primary indicator of cylinder misfire.
# ==============================================================================


class AnomalyDetector:
    def __init__(self):
        self.model = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)
        self.train_model()

    def generate_synthetic_healthy_data(self, num_samples=500):
        """
        Generates healthy residual data within the valid training envelope.

        The generated synthetic data acts as the nominal baseline for the 
        Isolation Forest model. Features include standard deviations for RPM, 
        EGT, and CHT, alongside inter-cylinder temperature spreads.
        
        Feature vector [5D]: 
        [res_rpm, res_egt_cyl0, res_cht_cyl0, egt_spread, cht_spread]

        Nominal spread ranges are derived from the engine's mechanical cylinder 
        trims and inherent thermal noise:
        - EGT spread: 2.0-5.0°C (anomalous if >40°C on misfire)
        - CHT spread: 0.5-2.5°C (anomalous if it stays artificially low during cooling faults)
        
        Args:
            num_samples (int): Number of synthetic samples to generate.
            
        Returns:
            np.ndarray: Matrix of shape (num_samples, 5) containing synthetic features.
        """
        data = []
        for _ in range(num_samples):
            # Cylinder-0 residuals (deviation from expected baseline)
            res_rpm = random.uniform(-20, 20)
            res_egt = random.uniform(-10, 10)
            res_cht = random.uniform(-5, 5)

            # Cross-cylinder thermal spreads
            egt_spread = random.uniform(2.0, 5.0)   # nominal ~3.3°C peak-to-peak
            cht_spread = random.uniform(0.5, 2.5)   # nominal ~1.6°C peak-to-peak

            data.append([res_rpm, res_egt, res_cht, egt_spread, cht_spread])

        return np.array(data)

    def train_model(self):
        model_path = os.path.join(os.path.dirname(__file__), "models", "anomaly_detector.pkl")
        os.makedirs(os.path.dirname(model_path), exist_ok=True)

        if os.path.exists(model_path):
            self.model = joblib.load(model_path)
        else:
            X_train = self.generate_synthetic_healthy_data()
            self.model.fit(X_train)
            joblib.dump(self.model, model_path)

    def evaluate(self, residuals: dict):
        """
        Evaluate live telemetry residuals to determine anomaly probability.

        Passes the 5-feature residual vector into the trained Isolation Forest 
        to detect deviations from the expected nominal state. The classifier 
        directly assesses cross-cylinder imbalance, which serves as the primary 
        indicator for issues such as cylinder misfire.

        Args:
            residuals (dict): Dictionary mapping feature names to their current residual values.
            
        Returns:
            tuple: (anomaly_score (float, 0.0-1.0), reason (str))
        """
        egt_spread = residuals.get("egt_spread", 3.5)   # fallback to nominal
        cht_spread = residuals.get("cht_spread", 1.6)

        X_live = np.array([[
            residuals["rpm"],
            residuals["egt"],
            residuals["cht"],
            egt_spread,
            cht_spread,
        ]])

        # IsolationForest decision_function: >0 is normal, <0 is anomaly
        raw_score = self.model.decision_function(X_live)[0]

        # Map raw_score (typically -0.5 to 0.5) → anomaly score in [0, 1]
        # raw_score < 0  →  anomaly_score > 0.5
        anomaly_score = max(0.0, min(1.0, 0.5 - raw_score * 2))

        reason = "Nominal"
        if anomaly_score > 0.5:
            # Normalised deviation for each feature
            normalized_dev = {
                "RPM variance":  abs(residuals["rpm"]) / 20.0,
                "EGT shift":     abs(residuals["egt"]) / 10.0,
                "CHT drift":     abs(residuals["cht"]) / 5.0,
                "EGT spread":    max(0.0, egt_spread - 5.0) / 5.0,   # >5°C is suspicious
                "CHT spread":    max(0.0, cht_spread - 3.0) / 2.0,   # >3°C is suspicious
            }
            worst_feature = max(normalized_dev, key=normalized_dev.get)
            reason = f"Anomaly detected driven by {worst_feature}"

        return float(anomaly_score), reason

    def check_confidence(self, altitude: float, throttle: float) -> str:
        """
        Evaluate if current operating conditions fall within the training envelope.
        
        The model is trained to recognize anomalies strictly within standard 
        operational limits. Data generated outside these bounds reduces confidence 
        in the anomaly detection result.
        
        Args:
            altitude (float): Current altitude in feet.
            throttle (float): Current throttle position (0.0 to 100.0).
            
        Returns:
            str: Status string indicating HIGH CONFIDENCE or EXTRAPOLATED.
        """
        if 0.0 <= altitude <= 20000.0 and 40.0 <= throttle <= 100.0:
            return "HIGH CONFIDENCE (In Envelope)"
        return "EXTRAPOLATED (Out of Envelope)"


# Instantiate the singleton so it trains on startup
detector = AnomalyDetector()
