FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    pydantic \
    pandas \
    numpy \
    scikit-learn \
    xgboost \
    joblib

COPY EV-Queue-Prediction/src /app/src
COPY EV-Queue-Prediction/api /app/api
COPY EV-Queue-Prediction/models/best_model.joblib /app/models/best_model.joblib
COPY EV-Queue-Prediction/models/best_model_meta.joblib /app/models/best_model_meta.joblib
COPY EV-Queue-Prediction/models/waiting_time_best_model.joblib /app/models/waiting_time_best_model.joblib
COPY EV-Queue-Prediction/models/waiting_time_best_model_meta.joblib /app/models/waiting_time_best_model_meta.joblib
COPY EV-Queue-Prediction/models/congestion_best_model.joblib /app/models/congestion_best_model.joblib
COPY EV-Queue-Prediction/models/congestion_best_model_meta.joblib /app/models/congestion_best_model_meta.joblib
COPY EV-Queue-Prediction/data/processed/waiting_time/modelling_table.csv /app/data/processed/waiting_time/modelling_table.csv
COPY EV-Queue-Prediction/reports/test_metrics.json /app/reports/test_metrics.json
COPY EV-Queue-Prediction/reports/waiting_time_test_metrics.json /app/reports/waiting_time_test_metrics.json
COPY EV-Queue-Prediction/reports/congestion_test_metrics.json /app/reports/congestion_test_metrics.json

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
