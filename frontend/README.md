# EV charging decision support

The dashboard has two tabs.

- **Colombo trip** calls the integration API. It ranks the four CSV stations with road routes. It does not show synthetic queue numbers as if they belonged to those stations.
- **Synthetic station check** keeps the earlier station checker. Those forecasts use the saved Component 1 models and are labelled synthetic.

## Run

Terminal 1, from `integration`:

```powershell
python -m uvicorn service:app --reload --port 8000
```

Terminal 2, from `frontend`:

```powershell
npm install
npm run dev
```

Open http://127.0.0.1:5173. Vite proxies `/api` and `/health` to port 8000.

Optional explanation model, set before starting the API:

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:OPENAI_MODEL="gpt-4o-mini"
```

Without a key, explanations use the template. `OSRM_BASE_URL` can point at your own OSRM server. The default is the public demo.
