FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY deploy/integration.requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY integration /app/integration
COPY component4_station_recommendation /app/component4_station_recommendation
COPY component3_energy_cost_estimation/src/__init__.py /app/component3_energy_cost_estimation/src/__init__.py
COPY component3_energy_cost_estimation/src/calculate_charging_cost.py /app/component3_energy_cost_estimation/src/calculate_charging_cost.py

WORKDIR /app/integration
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn service:app --host 0.0.0.0 --port ${PORT:-8000}"]
