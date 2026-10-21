FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY integration/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY integration /app/integration
COPY component3_energy_cost_estimation /app/component3_energy_cost_estimation
COPY component4_station_recommendation /app/component4_station_recommendation

COPY ["EV Charging Duration Prediction/src", "/app/EV Charging Duration Prediction/src"]
COPY ["EV Charging Duration Prediction/models/charging_duration_pipeline.joblib", "/app/EV Charging Duration Prediction/models/charging_duration_pipeline.joblib"]
COPY ["EV Charging Duration Prediction/models/charging_duration_pipeline_meta.joblib", "/app/EV Charging Duration Prediction/models/charging_duration_pipeline_meta.joblib"]
COPY ["EV Charging Duration Prediction/data/processed/train.csv", "/app/EV Charging Duration Prediction/data/processed/train.csv"]
COPY ["EV Charging Duration Prediction/results/test_metrics.json", "/app/EV Charging Duration Prediction/results/test_metrics.json"]

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

WORKDIR /app/integration
EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn service:app --host 0.0.0.0 --port ${PORT:-8000}"]
