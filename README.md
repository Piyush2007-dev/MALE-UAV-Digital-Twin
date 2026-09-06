# MALE UAV Digital Twin

A comprehensive digital twin simulation and telemetry dashboard for a Medium-Altitude Long-Endurance (MALE) Unmanned Aerial Vehicle (UAV) engine. 

The system couples a high-fidelity Python-based thermodynamic physics engine with a real-time Next.js visualization dashboard, providing predictive maintenance and anomaly detection capabilities through Machine Learning (Isolation Forest).

## System Architecture

The architecture is divided into two primary layers:

### 1. Physics & Machine Learning Backend (FastAPI)
Located in `uav-backend/`, this Python engine serves as the true "twin". It is built with a highly-modular, domain-driven architecture:
* **`api/` & `schemas/`**: Fast and thin routing layer handling HTTP endpoints (`/api/telemetry`, `/api/reset`).
* **`physics/`**: The thermodynamic engine core. Simulates a turbocharged 4-stroke Otto cycle engine using the International Standard Atmosphere (ISA) to model altitude lapse rates, turbo boost compensation, and thermal equilibrium (EGT/CHT).
* **`ml/`**: Machine Learning pipeline. Implements an unsupervised Scikit-Learn `IsolationForest` to rapidly screen for anomalies (cross-cylinder imbalances, cooling faults), paired with deterministic classification rules.
* **`health/`**: Predictive Maintenance layer. Tracks cumulative operational damage utilizing exponential decay functions to estimate Remaining Useful Life (RUL) and generate an AHP-weighted composite Health Index (HI).
* **`decision/`**: Automated decision routing that assigns mission reliability tiers (CONTINUE, DERATE, DIVERT, RTB) based on real-time health data.
* **`state.py`**: Manages and persists the cross-cycle engine state across HTTP polling calls.

### 2. Frontend Visualization Dashboard (Next.js)
Located in `src/`, the React dashboard acts as the Ground Control Station (GCS):
* **Real-Time Telemetry:** Renders live, high-density engine metrics (RPM, MAP, Fuel Flow, Oil Pressure).
* **Fault Injection Interface:** Allows the operator to simulate various in-flight component failures (e.g., Cylinder Misfire, Thermal Degradation, Bearing Micro-Spalling).
* **Diagnostic Visualization:** Provides auto-zooming real-time EGT and CHT thermal plots, alongside Fast Fourier Transform (FFT) vibration order tracking and Kurtosis indexing.

## Getting Started

### Prerequisites
- Node.js 18+ (for frontend)
- Python 3.10+ (for backend)

### Starting the Backend
```bash
cd uav-backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
*Note: The ML model automatically generates and caches its weights in `uav-backend/models/` upon initial startup.*

### Starting the Frontend
```bash
# In the root directory
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to access the dashboard.
