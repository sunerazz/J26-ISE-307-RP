# One container: the decision API (all four components) plus the web dashboard.
# Used by Render (render.yaml) and Railway (railway.toml).

# --- Stage 1: build the React dashboard --------------------------------------
FROM node:22-slim AS dashboard
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Empty API base: the dashboard calls the API on the same origin.
ENV VITE_API_BASE_URL=""
RUN npm run build

# --- Stage 2: Python API -------------------------------------------------------
FROM python:3.12-slim

WORKDIR /app

# libgomp1 is needed by xgboost.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY deploy/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY integration /app/integration

# Component 4: station inventory, routing, planner and saved evaluation results.
COPY component4_station_recommendation/src /app/component4_station_recommendation/src
COPY component4_station_recommendation/api /app/component4_station_recommendation/api
COPY component4_station_recommendation/data/raw/sri_lanka_ev_stations.csv /app/component4_station_recommendation/data/raw/sri_lanka_ev_stations.csv
COPY component4_station_recommendation/data/raw/colombo_ev_stations.csv /app/component4_station_recommendation/data/raw/colombo_ev_stations.csv
COPY component4_station_recommendation/results/data_completeness_report.json /app/component4_station_recommendation/results/data_completeness_report.json
COPY component4_station_recommendation/results/routing_evaluation_summary.json /app/component4_station_recommendation/results/routing_evaluation_summary.json

# Component 3: energy model and cost function.
COPY component3_energy_cost_estimation/src /app/component3_energy_cost_estimation/src
COPY component3_energy_cost_estimation/models/energy_consumption_pipeline.joblib /app/component3_energy_cost_estimation/models/energy_consumption_pipeline.joblib
COPY component3_energy_cost_estimation/models/energy_consumption_pipeline_meta.joblib /app/component3_energy_cost_estimation/models/energy_consumption_pipeline_meta.joblib
COPY component3_energy_cost_estimation/results/test_metrics.json /app/component3_energy_cost_estimation/results/test_metrics.json
# Training inputs, read only for their min/max so out-of-range requests can be flagged.
COPY component3_energy_cost_estimation/data/processed/train.csv /app/component3_energy_cost_estimation/data/processed/train.csv

# Component 2: charging-duration model.
COPY ["EV Charging Duration Prediction/src", "/app/EV Charging Duration Prediction/src"]
COPY ["EV Charging Duration Prediction/models/charging_duration_pipeline.joblib", "/app/EV Charging Duration Prediction/models/charging_duration_pipeline.joblib"]
COPY ["EV Charging Duration Prediction/models/charging_duration_pipeline_meta.joblib", "/app/EV Charging Duration Prediction/models/charging_duration_pipeline_meta.joblib"]
COPY ["EV Charging Duration Prediction/data/processed/train.csv", "/app/EV Charging Duration Prediction/data/processed/train.csv"]
COPY ["EV Charging Duration Prediction/results/test_metrics.json", "/app/EV Charging Duration Prediction/results/test_metrics.json"]

# Component 1: queue, waiting-time and congestion models.
COPY EV-Queue-Prediction/src /app/EV-Queue-Prediction/src
COPY EV-Queue-Prediction/api /app/EV-Queue-Prediction/api
COPY EV-Queue-Prediction/models/best_model.joblib /app/EV-Queue-Prediction/models/best_model.joblib
COPY EV-Queue-Prediction/models/best_model_meta.joblib /app/EV-Queue-Prediction/models/best_model_meta.joblib
COPY EV-Queue-Prediction/models/waiting_time_best_model.joblib /app/EV-Queue-Prediction/models/waiting_time_best_model.joblib
COPY EV-Queue-Prediction/models/waiting_time_best_model_meta.joblib /app/EV-Queue-Prediction/models/waiting_time_best_model_meta.joblib
COPY EV-Queue-Prediction/models/congestion_best_model.joblib /app/EV-Queue-Prediction/models/congestion_best_model.joblib
COPY EV-Queue-Prediction/models/congestion_best_model_meta.joblib /app/EV-Queue-Prediction/models/congestion_best_model_meta.joblib
COPY EV-Queue-Prediction/data/processed/waiting_time/modelling_table.csv /app/EV-Queue-Prediction/data/processed/waiting_time/modelling_table.csv
COPY EV-Queue-Prediction/reports/test_metrics.json /app/EV-Queue-Prediction/reports/test_metrics.json
COPY EV-Queue-Prediction/reports/waiting_time_test_metrics.json /app/EV-Queue-Prediction/reports/waiting_time_test_metrics.json
COPY EV-Queue-Prediction/reports/congestion_test_metrics.json /app/EV-Queue-Prediction/reports/congestion_test_metrics.json

# The built dashboard, served by the API at /.
COPY --from=dashboard /build/dist /app/frontend_dist
ENV FRONTEND_DIST=/app/frontend_dist \
    PYTHONUNBUFFERED=1

WORKDIR /app/integration
EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn service:app --host 0.0.0.0 --port ${PORT:-8000}"]
