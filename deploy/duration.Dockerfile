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

COPY ["EV Charging Duration Prediction/src", "/app/src"]
COPY ["EV Charging Duration Prediction/api", "/app/api"]
COPY ["EV Charging Duration Prediction/models/charging_duration_pipeline.joblib", "/app/models/charging_duration_pipeline.joblib"]
COPY ["EV Charging Duration Prediction/models/charging_duration_pipeline_meta.joblib", "/app/models/charging_duration_pipeline_meta.joblib"]
COPY ["EV Charging Duration Prediction/data/processed/train.csv", "/app/data/processed/train.csv"]
COPY ["EV Charging Duration Prediction/results/test_metrics.json", "/app/results/test_metrics.json"]

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
