# Deploying to Render

One Render web service runs everything:

- the decision API with all four components (queue/waiting/congestion, charging duration, energy and cost, station choice and route planning),
- the web dashboard, served at `/` of the same URL.

The phone app calls the same URL. It uses about 270 MB of RAM, inside the free plan's 512 MB.

## What gets built

`Dockerfile` (repository root) has two stages:

1. **Node 22** runs `npm ci` and `npm run build` in `frontend/`.
2. **Python 3.12** installs `deploy/requirements.txt`. It copies the integration service and only the model files the API loads, plus the built dashboard.

`deploy/requirements.txt` pins scikit-learn 1.7.2, XGBoost 3.4.1, pandas 2.3.3 and NumPy 2.3.5. These are the versions the saved models were trained with. Do not unpin them. A different scikit-learn can fail to load a saved pipeline, or change its predictions.

## Option A: update the existing service (j26-ise-307-rp)

The current phone build already points to `https://j26-ise-307-rp.onrender.com`, and that service already builds the root `Dockerfile`.

1. Push this folder to the Git repository the service is connected to. The repository root must contain `Dockerfile`, `.dockerignore`, `deploy/`, `frontend/`, `integration/` and the four component folders.
2. In the Render dashboard, open **j26-ise-307-rp** → **Settings** and check these values:
   - **Dockerfile Path**: `./Dockerfile`
   - **Docker Build Context Directory**: `.`
   - **Health Check Path**: `/health`
3. Under **Environment**, set these variables:
   - `OSRM_BASE_URL=https://router.project-osrm.org`
   - `CORS_ORIGINS=*`
   - `OPENAI_API_KEY`: optional. Without it, explanations use the built-in template.
4. Remove `QUEUE_API_URL`, `DURATION_API_URL` and `ENERGY_API_URL` if they exist. When they are empty, the service loads the models itself.
5. **Manual Deploy → Deploy latest commit.** The first build takes about 5–8 minutes.

## Option B: new service from the Blueprint

**New → Blueprint**, then pick the repository. Render reads `render.yaml` and creates one Docker web service in Singapore. If the name `j26-ise-307-rp` is taken, Render gives the service a different URL. In that case, build the phone app with that URL:

```powershell
flutter build apk --release --dart-define=API_BASE_URL=https://<your-service>.onrender.com
```

## Check the deployment

Replace the URL with yours:

```powershell
python deploy/smoke_test.py https://j26-ise-307-rp.onrender.com
```

The smoke test checks these:

- health and all models loaded,
- the dashboard,
- 67 stations,
- each component's own endpoint,
- a live routed trip that uses all four components.

It prints PASS or FAIL per check. On the free plan, the first request after 15 idle minutes wakes the service and can take about a minute.

## Before a demo

- Open the URL once a few minutes before you present, so the service is awake.
- Road routing uses the public OSRM server. It has no uptime guarantee and can rate-limit. A trip then fails with a clear "routing service is busy" message; wait a moment and retry.

## Run the same container locally

```powershell
docker build -t ev-decision .
docker run -p 8000:8000 ev-decision
```

Open http://localhost:8000.

## Alternative: four services

`deploy/render.four-services.yaml` and `deploy/{queue,duration,energy,integration}.Dockerfile` run each model as its own service. On the free plan each one sleeps separately, so a cold trip request can wait for several start-ups in a row. Prefer the single service.
