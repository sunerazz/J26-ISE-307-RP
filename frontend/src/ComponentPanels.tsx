import { useEffect, useState } from 'react'
import { api, type CostEstimate, type DurationPrediction, type EnergyPrediction, type EnergySchema } from './api'
import { fixLabel, fmtClock, fmtKwh, fmtLkr, fmtMinutes } from './format'

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

function localNow(): string {
  const now = new Date()
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset())
  return now.toISOString().slice(0, 16)
}

// Example inputs, shown and editable. Keys are matched by prefix because the
// spreadsheet's temperature column name carries a broken degree sign.
const DURATION_EXAMPLE: [string, string][] = [
  ['Battery Capacity', '40'],
  ['Charging Rate', '24'],
  ['State of Charge', '30'],
  ['Distance Driven', '120'],
  ['Vehicle Age', '3'],
  ['Temperature', '30'],
  ['Vehicle Model', 'Nissan Leaf'],
  ['Time of Day', 'Afternoon'],
  ['Charger Type', 'DC Fast Charger'],
  ['User Type', 'Commuter'],
]

type DurationSchema = {
  feature_columns: string[]
  numeric_features: string[]
  categories: Record<string, string[]>
  note: string
}

/** Component 2: charging-duration prediction and expected completion time. */
export function DurationPanel() {
  const [schema, setSchema] = useState<DurationSchema | null>(null)
  const [values, setValues] = useState<Record<string, string>>({})
  const [start, setStart] = useState(localNow())
  const [result, setResult] = useState<DurationPrediction | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api
      .durationSchema()
      .then((loaded) => {
        setSchema(loaded)
        const initial: Record<string, string> = {}
        for (const column of loaded.feature_columns) {
          const example = DURATION_EXAMPLE.find(([prefix]) => column.startsWith(prefix))
          if (example) initial[column] = example[1]
          else if (column === 'Day of Week') initial[column] = DAYS[new Date().getDay()]
          else if (loaded.categories[column]) initial[column] = loaded.categories[column][0]
        }
        setValues(initial)
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  async function predict() {
    if (!schema) return
    setBusy(true)
    setError(null)
    try {
      const features: Record<string, string | number> = {}
      for (const column of schema.feature_columns) {
        const raw = values[column] ?? ''
        features[column] = schema.numeric_features.includes(column) ? Number(raw) : raw
      }
      setResult(await api.predictDuration(features, start || null))
    } catch (e) {
      setResult(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <p className="banner">
        Component 2 · AI-based charging-duration prediction and expected completion time. The model was trained on
        charging sessions from five US cities, so pick one of them as the location. It is not applied to each Colombo
        charger; the trip planner shows a completion time from road time, predicted wait and listed charger power.
      </p>
      <section className="panel controls">
        <h2 className="step">Session details</h2>
        {schema ? (
          <div className="form-grid">
            {schema.feature_columns.map((column) => (
              <label key={column}>
                {fixLabel(column)}
                {schema.categories[column] ? (
                  <select
                    value={values[column] ?? ''}
                    onChange={(e) => setValues((current) => ({ ...current, [column]: e.target.value }))}
                  >
                    {schema.categories[column].map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    inputMode="decimal"
                    value={values[column] ?? ''}
                    onChange={(e) => setValues((current) => ({ ...current, [column]: e.target.value }))}
                  />
                )}
              </label>
            ))}
            <label>
              Charging starts at
              <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} />
            </label>
          </div>
        ) : (
          <p className="muted">Loading the model's input list…</p>
        )}
        <button type="button" disabled={busy || !schema} onClick={() => void predict()}>
          {busy ? 'Predicting…' : 'Predict charging duration'}
        </button>
        <p className="muted small">
          In this dataset, “Time of Day” and “Day of Week” do not match the session start timestamps, so they are chosen
          here like any other input rather than read from the clock.
        </p>
      </section>
      {error ? <pre className="error">{error}</pre> : null}
      {result ? (
        <section className="panel summary answer">
          <h2>Predicted charging duration</h2>
          <div className="research-grid">
            <div>
              <strong>{fmtMinutes(result.predicted_charging_duration_min)}</strong>
              <span>predicted session length</span>
            </div>
            <div>
              <strong>{fmtClock(result.expected_completion_time)}</strong>
              <span>expected completion (start {fmtClock(result.charging_start_time)})</span>
            </div>
            <div>
              <strong>± {fmtMinutes(result.test_metrics?.mae_min)}</strong>
              <span>average error on held-out test sessions</span>
            </div>
          </div>
          <p className="small">
            Model: {result.selected_model} · test MAE {result.test_metrics?.mae_min?.toFixed(1)} min, RMSE{' '}
            {result.test_metrics?.rmse_min?.toFixed(1)} min, R² {result.test_metrics?.r2?.toFixed(3)} on{' '}
            {result.test_metrics?.n} sessions.
          </p>
          <p className="muted small">{result.note}</p>
        </section>
      ) : null}
    </div>
  )
}

const ENERGY_EXAMPLE: Record<string, string> = {
  distance_km: '115',
  average_speed_kmh: '52',
  trip_duration_min: '132',
  battery_capacity_kwh: '40',
  soc_start_pct: '80',
  elevation_gain_m: '500',
  elevation_loss_m: '20',
  ambient_temperature_c: '30',
  ac_on: '1',
  vehicle_mass_kg: '1700',
  traffic_level: 'medium',
  road_type: 'mixed',
}

const ENERGY_LABELS: Record<string, string> = {
  distance_km: 'Distance (km)',
  average_speed_kmh: 'Average speed (km/h)',
  trip_duration_min: 'Trip duration (min)',
  battery_capacity_kwh: 'Battery capacity (kWh)',
  soc_start_pct: 'Battery at start (%)',
  elevation_gain_m: 'Climb (m)',
  elevation_loss_m: 'Descent (m)',
  ambient_temperature_c: 'Outside temperature (°C)',
  ac_on: 'Air conditioning (1 = on, 0 = off)',
  vehicle_mass_kg: 'Vehicle mass (kg)',
  traffic_level: 'Traffic',
  road_type: 'Road type',
}

/** Component 3: trip energy prediction and charging cost. */
export function EnergyPanel() {
  const [schema, setSchema] = useState<EnergySchema | null>(null)
  const [values, setValues] = useState<Record<string, string>>(ENERGY_EXAMPLE)
  const [prediction, setPrediction] = useState<EnergyPrediction | null>(null)
  const [tariff, setTariff] = useState('')
  const [efficiency, setEfficiency] = useState('0.9')
  const [cost, setCost] = useState<CostEstimate | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api
      .energySchema()
      .then(setSchema)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  async function predict() {
    if (!schema) return
    setBusy(true)
    setError(null)
    setCost(null)
    try {
      const record: Record<string, string | number> = {}
      for (const column of schema.feature_columns) {
        const raw = values[column] ?? ''
        record[column] = schema.categories[column] ? raw : Number(raw)
      }
      setPrediction(await api.predictEnergy(record))
    } catch (e) {
      setPrediction(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function price() {
    if (!prediction) return
    setError(null)
    try {
      setCost(
        await api.energyCost({
          energy_kwh: prediction.predicted_energy_kwh,
          tariff_lkr_per_kwh: Number(tariff),
          charging_efficiency: efficiency.trim() ? Number(efficiency) : null,
        }),
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const capacity = Number(values.battery_capacity_kwh)
  const socUsed = prediction && capacity > 0 ? (prediction.predicted_energy_kwh / capacity) * 100 : null

  return (
    <div>
      <p className="banner">
        Component 3 · AI-based battery consumption prediction and charging cost estimation. The energy model was trained
        on synthetic trips. The cost uses the tariff you type; no official tariff is assumed.
      </p>
      <section className="panel controls">
        <h2 className="step">1 · Trip</h2>
        {schema ? (
          <div className="form-grid">
            {schema.feature_columns.map((column) => (
              <label key={column}>
                {ENERGY_LABELS[column] ?? column}
                {schema.categories[column] ? (
                  <select
                    value={values[column] ?? ''}
                    onChange={(e) => setValues((current) => ({ ...current, [column]: e.target.value }))}
                  >
                    {schema.categories[column].map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    inputMode="decimal"
                    value={values[column] ?? ''}
                    onChange={(e) => setValues((current) => ({ ...current, [column]: e.target.value }))}
                  />
                )}
              </label>
            ))}
          </div>
        ) : (
          <p className="muted">Loading the model's input list…</p>
        )}
        <button type="button" disabled={busy || !schema} onClick={() => void predict()}>
          {busy ? 'Predicting…' : 'Predict battery consumption'}
        </button>
        <p className="muted small">Example values: Colombo → Kandy, about 115 km with a 500 m climb.</p>
      </section>
      {error ? <pre className="error">{error}</pre> : null}
      {prediction ? (
        <section className="panel summary answer">
          <h2>Predicted battery consumption</h2>
          <div className="research-grid">
            <div>
              <strong>{fmtKwh(prediction.predicted_energy_kwh)}</strong>
              <span>energy for this trip</span>
            </div>
            <div>
              <strong>{socUsed !== null ? `${Math.round(socUsed)}%` : '—'}</strong>
              <span>of a {values.battery_capacity_kwh} kWh battery</span>
            </div>
            <div>
              <strong>± {fmtKwh(schema?.test_metrics?.mae_kwh)}</strong>
              <span>average error on held-out test trips</span>
            </div>
          </div>
          <p className="small">
            Model: {schema?.selected_model} · test MAE {schema?.test_metrics?.mae_kwh?.toFixed(2)} kWh, RMSE{' '}
            {schema?.test_metrics?.rmse_kwh?.toFixed(2)} kWh, R² {schema?.test_metrics?.r2?.toFixed(3)} on{' '}
            {schema?.test_metrics?.n} trips.
          </p>

          <h2 className="step">2 · Charging cost to put this energy back</h2>
          <div className="form-grid">
            <label>
              Tariff (LKR per kWh)
              <input
                inputMode="decimal"
                value={tariff}
                placeholder="e.g. 120 for a chargeNET DC listing"
                onChange={(e) => setTariff(e.target.value)}
              />
            </label>
            <label>
              Charging efficiency (0–1)
              <input inputMode="decimal" value={efficiency} onChange={(e) => setEfficiency(e.target.value)} />
            </label>
          </div>
          <button type="button" disabled={!tariff.trim()} onClick={() => void price()}>
            Estimate cost
          </button>
          {cost ? (
            <div className="research-grid">
              <div>
                <strong>{fmtLkr(cost.estimated_total)}</strong>
                <span>
                  {cost.grid_energy_kwh !== null
                    ? `${fmtKwh(cost.grid_energy_kwh)} drawn from the charger`
                    : `${fmtKwh(cost.battery_energy_kwh)} into the battery`}
                </span>
              </div>
            </div>
          ) : null}
          {cost ? (
            <p className="muted small">
              {cost.formula}. {cost.assumptions.join(' ')}
            </p>
          ) : null}
        </section>
      ) : null}
    </div>
  )
}
