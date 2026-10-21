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

COPY component3_energy_cost_estimation/src /app/src
COPY component3_energy_cost_estimation/api /app/api
COPY component3_energy_cost_estimation/models/energy_consumption_pipeline.joblib /app/models/energy_consumption_pipeline.joblib
COPY component3_energy_cost_estimation/models/energy_consumption_pipeline_meta.joblib /app/models/energy_consumption_pipeline_meta.joblib
COPY component3_energy_cost_estimation/results/test_metrics.json /app/results/test_metrics.json

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
