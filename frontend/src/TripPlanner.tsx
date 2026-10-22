import { useEffect, useMemo, useState } from 'react'
import { api, type ChargingPlan, type ColomboStation, type TripRequest, type TripResponse, type TripStation } from './api'
import { fmtClock, fmtDetour, fmtKm, fmtKwh, fmtLkr, fmtMinutes, fmtPct, osmLink } from './format'

// Approximate area centres, for convenience only. Edit the coordinates for an exact address.
// Coordinates are the Component 4 charger pins (the mean when an area has several).
// Nugegoda, Rajagiriya, Malabe and Panadura are the queue-model towns; they have no charger pin.
const PLACES: { name: string; latitude: number; longitude: number }[] = [
  { name: 'Colombo 01', latitude: 6.93374, longitude: 79.84411 },
  { name: 'Nugegoda', latitude: 6.8649, longitude: 79.8997 },
  { name: 'Rajagiriya', latitude: 6.909, longitude: 79.896 },
  { name: 'Malabe', latitude: 6.9063, longitude: 79.9696 },
  { name: 'Panadura', latitude: 6.7132, longitude: 79.9026 },
  { name: 'Colombo 02', latitude: 6.9175, longitude: 79.8558 },
  { name: 'Colombo 07', latitude: 6.91145, longitude: 79.86512 },
  { name: 'Colombo 3', latitude: 6.91657, longitude: 79.84932 },
  { name: 'Colombo 6', latitude: 6.87094, longitude: 79.86528 },
  { name: 'Colombo 9', latitude: 6.93363, longitude: 79.87916 },
  { name: 'Maradana / Colombo 10', latitude: 6.92936, longitude: 79.86104 },
  { name: 'Battaramulla', latitude: 6.90845, longitude: 79.93925 },
  { name: 'Pannipitiya', latitude: 6.84284, longitude: 79.95336 },
  { name: 'Dehiwala', latitude: 6.84256, longitude: 79.88459 },
  { name: 'Dehiwala-Mount Lavinia', latitude: 6.86217, longitude: 79.86513 },
  { name: 'Moratuwa', latitude: 6.79517, longitude: 79.88741 },
  { name: 'Wattala', latitude: 6.98869, longitude: 79.89691 },
  { name: 'Homagama', latitude: 6.82584, longitude: 80.03807 },
  { name: 'Negombo', latitude: 7.18682, longitude: 79.85954 },
  { name: 'Gampaha', latitude: 7.00639, longitude: 79.95439 },
  { name: 'Kalutara', latitude: 6.62528, longitude: 79.9422 },
  { name: 'Galle', latitude: 6.06932, longitude: 80.23406 },
  { name: 'Matara', latitude: 5.96849, longitude: 80.53129 },
  { name: 'Kandy', latitude: 7.2985, longitude: 80.64356 },
  { name: 'Peradeniya', latitude: 7.26841, longitude: 80.58078 },
  { name: 'Nuwara Eliya', latitude: 6.9658, longitude: 80.77193 },
  { name: 'Dambulla', latitude: 7.82372, longitude: 80.65469 },
  { name: 'Anuradhapura', latitude: 8.32699, longitude: 80.39574 },
  { name: 'Trincomalee', latitude: 8.62308, longitude: 81.2115 },
  { name: 'Batticaloa', latitude: 7.72006, longitude: 81.71013 },
]

// Typical values to start from. Real usable capacity and consumption vary by car, speed and weather.
const CARS: { name: string; capacity: string; consumption: string; connector: string }[] = [
  { name: 'Nissan Leaf 40 kWh', capacity: '39', consumption: '16', connector: 'CHAdeMO' },
  { name: 'Nissan Leaf e+ 62 kWh', capacity: '59', consumption: '17', connector: 'CHAdeMO' },
  { name: 'BYD Atto 3 (60 kWh)', capacity: '60', consumption: '17', connector: 'CCS2' },
]

type FormState = {
  origin_latitude: string
  origin_longitude: string
  destination_latitude: string
  destination_longitude: string
  current_soc_percent: string
  usable_battery_capacity_kwh: string
  consumption_kwh_per_100km: string
  minimum_reserve_percent: string
  required_connector: string
  target_soc_percent: string
  user_tariff_lkr_per_kwh: string
  charging_efficiency: string
  use_energy_model: boolean
  elevation_gain_m: string
  elevation_loss_m: string
  ambient_temperature_c: string
  ac_on: string
  traffic_level: string
  road_type: string
  vehicle_mass_kg: string
}

type TextField = Exclude<keyof FormState, 'use_energy_model'>

const INITIAL: FormState = {
  origin_latitude: '6.9271',
  origin_longitude: '79.8612',
  destination_latitude: '6.8649',
  destination_longitude: '79.8997',
  current_soc_percent: '80',
  usable_battery_capacity_kwh: '40',
  consumption_kwh_per_100km: '15',
  minimum_reserve_percent: '10',
  required_connector: 'CHAdeMO',
  target_soc_percent: '80',
  user_tariff_lkr_per_kwh: '',
  charging_efficiency: '',
  // Example trip conditions for the energy model, shown and editable in step 4.
  use_energy_model: true,
  elevation_gain_m: '10',
  elevation_loss_m: '10',
  ambient_temperature_c: '30',
  ac_on: 'yes',
  traffic_level: 'medium',
  road_type: 'urban',
  vehicle_mass_kg: '1700',
}

function num(value: string): number {
  return Number(value)
}

function optionalNum(value: string): number | null {
  return value.trim() === '' ? null : Number(value)
}

function validate(form: FormState): string[] {
  const problems: string[] = []
  const required = (key: TextField, label: string, min: number, max: number, strictMin = false) => {
    const raw = form[key].trim()
    const value = Number(raw)
    if (raw === '' || !Number.isFinite(value)) {
      problems.push(`${label} must be a number.`)
    } else if ((strictMin ? value <= min : value < min) || value > max) {
      problems.push(`${label} must be ${strictMin ? 'above' : 'at least'} ${min} and at most ${max}.`)
    }
  }
  required('origin_latitude', 'Origin latitude', -90, 90)
  required('origin_longitude', 'Origin longitude', -180, 180)
  required('destination_latitude', 'Destination latitude', -90, 90)
  required('destination_longitude', 'Destination longitude', -180, 180)
  required('current_soc_percent', 'Current battery %', 0, 100)
  required('usable_battery_capacity_kwh', 'Usable battery size', 0, 300, true)
  required('consumption_kwh_per_100km', 'Consumption', 0, 100, true)
  required('minimum_reserve_percent', 'Reserve %', 0, 100)
  const optional = (key: TextField, label: string, min: number, max: number, strictMin = false) => {
    if (form[key].trim() === '') return
    const value = Number(form[key])
    if (!Number.isFinite(value) || (strictMin ? value <= min : value < min) || value > max) {
      problems.push(`${label} must be a number between ${min} and ${max}, or left blank.`)
    }
  }
  optional('target_soc_percent', 'Charge to %', 0, 100)
  optional('user_tariff_lkr_per_kwh', 'Tariff', 0, 100000)
  optional('charging_efficiency', 'Charging efficiency (e.g. 0.9 for 90%)', 0, 1, true)
  if (
    form.target_soc_percent.trim() !== '' &&
    Number(form.target_soc_percent) <= Number(form.minimum_reserve_percent)
  ) {
    problems.push('Charge to % should be above your reserve %.')
  }
  return problems
}

function consumptionHint(value: string): string | null {
  const v = Number(value)
  if (!Number.isFinite(v) || value.trim() === '') return null
  if (v < 10 || v > 30) return 'Most cars use 12–25 kWh/100 km. Check this value.'
  return null
}

export default function TripPlanner() {
  const [form, setForm] = useState<FormState>(INITIAL)
  const [stations, setStations] = useState<ColomboStation[]>([])
  const [apiOk, setApiOk] = useState<boolean | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [problems, setProblems] = useState<string[]>([])
  const [result, setResult] = useState<TripResponse | null>(null)
  const [durationSchema, setDurationSchema] = useState<{
    feature_columns: string[]
    numeric_features: string[]
    categories: Record<string, string[]>
    note: string
  } | null>(null)
  const [durationValues, setDurationValues] = useState<Record<string, string>>({})
  const [question, setQuestion] = useState('Why this station?')
  const [followUp, setFollowUp] = useState<string | null>(null)
  const [locating, setLocating] = useState(false)

  useEffect(() => {
    void (async () => {
      try {
        const health = await api.health()
        setApiOk(health.routing_ready)
        const listed = await api.colomboStations()
        setStations(listed.stations)
        try {
          const schema = await api.durationSchema()
          setDurationSchema(schema)
        } catch {
          setDurationSchema(null)
        }
      } catch {
        setApiOk(false)
      }
    })()
  }, [])

  function update(key: TextField, value: string) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  function pickPlace(which: 'origin' | 'destination', index: string) {
    const place = PLACES[Number(index)]
    if (!place) return
    setForm((current) => ({
      ...current,
      [`${which}_latitude`]: String(place.latitude),
      [`${which}_longitude`]: String(place.longitude),
    }))
  }

  function pickCar(index: string) {
    const car = CARS[Number(index)]
    if (!car) return
    setForm((current) => ({
      ...current,
      usable_battery_capacity_kwh: car.capacity,
      consumption_kwh_per_100km: car.consumption,
      required_connector: car.connector,
    }))
  }

  function useMyLocation() {
    if (!navigator.geolocation) {
      setError('This browser cannot share your location. Pick an area or type coordinates.')
      return
    }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocating(false)
        setForm((current) => ({
          ...current,
          origin_latitude: position.coords.latitude.toFixed(5),
          origin_longitude: position.coords.longitude.toFixed(5),
        }))
      },
      () => {
        setLocating(false)
        setError('Location permission was refused or unavailable. Pick an area or type coordinates.')
      },
      { timeout: 10000 },
    )
  }

  async function submit() {
    setError(null)
    setFollowUp(null)
    const found = validate(form)
    setProblems(found)
    if (found.length) return
    const durationFeatures: Record<string, string | number> = {}
    if (durationSchema) {
      const filled = durationSchema.feature_columns.filter((column) => (durationValues[column] ?? '').trim() !== '')
      if (filled.length === durationSchema.feature_columns.length) {
        for (const column of durationSchema.feature_columns) {
          const raw = durationValues[column]
          durationFeatures[column] = durationSchema.numeric_features.includes(column) ? Number(raw) : raw
        }
      } else if (filled.length > 0) {
        setProblems(['Fill every field of the optional duration model, or clear them all. Partial values are not guessed.'])
        return
      }
    }
    const conditions = form.use_energy_model
      ? {
          elevation_gain_m: num(form.elevation_gain_m),
          elevation_loss_m: num(form.elevation_loss_m),
          ambient_temperature_c: num(form.ambient_temperature_c),
          ac_on: form.ac_on === 'yes',
          traffic_level: form.traffic_level,
          road_type: form.road_type,
          vehicle_mass_kg: num(form.vehicle_mass_kg),
        }
      : null
    if (conditions && Object.values(conditions).some((value) => typeof value === 'number' && !Number.isFinite(value))) {
      setProblems(['Trip conditions must be numbers, or untick "Predict drive energy with the Component 3 model".'])
      return
    }
    const body: TripRequest = {
      origin_latitude: num(form.origin_latitude),
      origin_longitude: num(form.origin_longitude),
      destination_latitude: num(form.destination_latitude),
      destination_longitude: num(form.destination_longitude),
      current_soc_percent: num(form.current_soc_percent),
      usable_battery_capacity_kwh: num(form.usable_battery_capacity_kwh),
      consumption_kwh_per_100km: num(form.consumption_kwh_per_100km),
      minimum_reserve_percent: num(form.minimum_reserve_percent),
      required_connector: form.required_connector || null,
      target_soc_percent: optionalNum(form.target_soc_percent),
      user_tariff_lkr_per_kwh: optionalNum(form.user_tariff_lkr_per_kwh),
      charging_efficiency: optionalNum(form.charging_efficiency),
      duration_features: Object.keys(durationFeatures).length ? durationFeatures : null,
      energy_conditions: conditions,
    }
    setBusy(true)
    try {
      setResult(await api.recommend(body))
    } catch (e) {
      setResult(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function ask() {
    if (!result || !question.trim()) return
    setBusy(true)
    setError(null)
    try {
      const answer = await api.explain(result, question.trim())
      setFollowUp(answer.text)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const cards = useMemo(() => {
    if (!result) return []
    return [result.recommended_station, ...(result.alternatives ?? [])].filter(
      (item): item is TripStation => item !== null,
    )
  }, [result])

  const ranked = cards.filter((station) => station.included_in_ranking)
  const excluded = cards.filter((station) => !station.included_in_ranking)
  const hint = consumptionHint(form.consumption_kwh_per_100km)

  return (
    <div>
      <p className="banner">
        Uses {stations.length || 'the'} Open Charge Map listings for Sri Lanka. Live availability and queues are
        unknown, so always confirm with the operator before you go.
      </p>
      <p className={`api-pill ${apiOk ? 'ok' : apiOk === false ? 'down' : ''}`}>
        {apiOk === null ? 'Checking API…' : apiOk ? 'Recommendation API ready' : 'API offline — start integration on :8000'}
      </p>

      <section className="panel controls">
        <h2 className="step">1 · Your trip</h2>
        <div className="form-grid">
          <label>
            Start from
            <select defaultValue="" onChange={(e) => pickPlace('origin', e.target.value)}>
              <option value="">Pick an area (or type coordinates below)</option>
              {PLACES.map((place, index) => (
                <option key={place.name} value={index}>
                  {place.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Going to
            <select defaultValue="" onChange={(e) => pickPlace('destination', e.target.value)}>
              <option value="">Pick an area (or type coordinates below)</option>
              {PLACES.map((place, index) => (
                <option key={place.name} value={index}>
                  {place.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Origin latitude
            <input inputMode="decimal" value={form.origin_latitude} onChange={(e) => update('origin_latitude', e.target.value)} />
          </label>
          <label>
            Origin longitude
            <input inputMode="decimal" value={form.origin_longitude} onChange={(e) => update('origin_longitude', e.target.value)} />
          </label>
          <label>
            Destination latitude
            <input
              inputMode="decimal"
              value={form.destination_latitude}
              onChange={(e) => update('destination_latitude', e.target.value)}
            />
          </label>
          <label>
            Destination longitude
            <input
              inputMode="decimal"
              value={form.destination_longitude}
              onChange={(e) => update('destination_longitude', e.target.value)}
            />
          </label>
        </div>
        <p className="muted small">
          <button type="button" className="secondary" disabled={locating} onClick={useMyLocation}>
            {locating ? 'Finding you…' : 'Use my location as the start'}
          </button>{' '}
          Area names are approximate centres. Trip coordinates are sent to the routing service (OSRM) to get
          road distances.
        </p>

        <h2 className="step">2 · Your car</h2>
        <div className="form-grid">
          <label>
            Car preset
            <select defaultValue="" onChange={(e) => pickCar(e.target.value)}>
              <option value="">Custom (type values below)</option>
              {CARS.map((car, index) => (
                <option key={car.name} value={index}>
                  {car.name} — typical values
                </option>
              ))}
            </select>
          </label>
          <label>
            Plug type
            <select value={form.required_connector} onChange={(e) => update('required_connector', e.target.value)}>
              <option value="">Any listed connector</option>
              <option value="CHAdeMO">CHAdeMO</option>
              <option value="CCS2">CCS2 (Combo)</option>
              <option value="Type 1 (J1772)">Type 1 (J1772)</option>
              <option value="Type 2 socket">Type 2 socket</option>
            </select>
          </label>
          <label>
            Current battery %
            <input inputMode="decimal" value={form.current_soc_percent} onChange={(e) => update('current_soc_percent', e.target.value)} />
          </label>
          <label>
            Keep at least (reserve) %
            <input
              inputMode="decimal"
              value={form.minimum_reserve_percent}
              onChange={(e) => update('minimum_reserve_percent', e.target.value)}
            />
          </label>
          <label>
            Usable battery size (kWh)
            <input
              inputMode="decimal"
              value={form.usable_battery_capacity_kwh}
              onChange={(e) => update('usable_battery_capacity_kwh', e.target.value)}
            />
          </label>
          <label>
            Consumption (kWh per 100 km)
            <input
              inputMode="decimal"
              value={form.consumption_kwh_per_100km}
              onChange={(e) => update('consumption_kwh_per_100km', e.target.value)}
            />
            {hint ? <span className="hint">{hint}</span> : null}
          </label>
        </div>

        <h2 className="step">3 · Charging (optional)</h2>
        <div className="form-grid">
          <label>
            Charge to %
            <input
              inputMode="decimal"
              value={form.target_soc_percent}
              placeholder="Blank = just tell me the minimum"
              onChange={(e) => update('target_soc_percent', e.target.value)}
            />
          </label>
          <label>
            Tariff you expect (LKR per kWh)
            <input
              inputMode="decimal"
              value={form.user_tariff_lkr_per_kwh}
              placeholder="Your own figure, not an official price"
              onChange={(e) => update('user_tariff_lkr_per_kwh', e.target.value)}
            />
          </label>
          <label>
            Charging efficiency (0–1)
            <input
              inputMode="decimal"
              value={form.charging_efficiency}
              placeholder="e.g. 0.9 adds 10% for charging losses"
              onChange={(e) => update('charging_efficiency', e.target.value)}
            />
          </label>
        </div>

        <h2 className="step">4 · Trip conditions (Component 3 energy model)</h2>
        <label className="check">
          <input
            type="checkbox"
            checked={form.use_energy_model}
            onChange={(e) => setForm((current) => ({ ...current, use_energy_model: e.target.checked }))}
          />
          Predict drive energy with the Component 3 model (otherwise: road km × your consumption figure)
        </label>
        {form.use_energy_model ? (
          <div className="form-grid">
            <label>
              Climb on the way (m)
              <input inputMode="decimal" value={form.elevation_gain_m} onChange={(e) => update('elevation_gain_m', e.target.value)} />
              <span className="hint">Colombo is flat; Colombo → Kandy climbs about 500 m.</span>
            </label>
            <label>
              Descent on the way (m)
              <input inputMode="decimal" value={form.elevation_loss_m} onChange={(e) => update('elevation_loss_m', e.target.value)} />
            </label>
            <label>
              Outside temperature (°C)
              <input inputMode="decimal" value={form.ambient_temperature_c} onChange={(e) => update('ambient_temperature_c', e.target.value)} />
            </label>
            <label>
              Air conditioning
              <select value={form.ac_on} onChange={(e) => update('ac_on', e.target.value)}>
                <option value="yes">On</option>
                <option value="no">Off</option>
              </select>
            </label>
            <label>
              Traffic
              <select value={form.traffic_level} onChange={(e) => update('traffic_level', e.target.value)}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </label>
            <label>
              Road type
              <select value={form.road_type} onChange={(e) => update('road_type', e.target.value)}>
                <option value="urban">Urban</option>
                <option value="mixed">Mixed</option>
                <option value="highway">Highway</option>
              </select>
            </label>
            <label>
              Vehicle mass with passengers (kg)
              <input inputMode="decimal" value={form.vehicle_mass_kg} onChange={(e) => update('vehicle_mass_kg', e.target.value)} />
            </label>
          </div>
        ) : null}

        {problems.length ? (
          <div className="problems" role="alert">
            <strong>Please fix these first:</strong>
            <ul>
              {problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <button type="button" disabled={busy || !apiOk} onClick={() => void submit()}>
          {busy ? 'Calculating road routes… (can take ~10 s)' : 'Find my best station'}
        </button>
        <p className="muted small">Inventory: {stations.length ? `${stations.length} listed stations` : 'not loaded'}.</p>

        {durationSchema ? (
          <details className="duration-box">
            <summary>Advanced: separate session-duration model (US data)</summary>
            <p className="muted small">{durationSchema.note}</p>
            <div className="form-grid">
              {durationSchema.feature_columns.map((column) => (
                <label key={column}>
                  {column}
                  {durationSchema.categories[column] ? (
                    <select
                      value={durationValues[column] ?? ''}
                      onChange={(e) =>
                        setDurationValues((current) => ({ ...current, [column]: e.target.value }))
                      }
                    >
                      <option value="">Not provided</option>
                      {durationSchema.categories[column].map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      value={durationValues[column] ?? ''}
                      onChange={(e) =>
                        setDurationValues((current) => ({ ...current, [column]: e.target.value }))
                      }
                    />
                  )}
                </label>
              ))}
            </div>
          </details>
        ) : null}
      </section>

      {error ? <pre className="error">{error}</pre> : null}

      {result ? (
        <div className="results">
          <section className={`panel summary answer ${result.recommended_station ? '' : 'none'}`}>
            <h2>{result.recommended_station ? 'Your answer' : 'No station fits these inputs'}</h2>
            {result.recommended_station ? (
              <p className="answer-station">
                {result.recommended_station.station_id} · {result.recommended_station.station_name}
              </p>
            ) : null}
            {result.recommended_station ? <KeyStats station={result.recommended_station} /> : null}
            <ul className="quick">
              {(result.quick_answer ?? []).map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
            <details>
              <summary>Full explanation</summary>
              <p className="summary-text">{result.explanation?.text}</p>
              <p className="muted small">
                Explanation: {result.explanation?.provider}
                {result.explanation?.llm_used ? ' (language model, checked against the result)' : ' (template)'}
              </p>
            </details>
          </section>

          {(result.warnings ?? []).length ? (
            <section className="panel">
              <h2>Things to know</h2>
              <ul>
                {(result.warnings ?? []).map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <ModelOutputs result={result} />

          {result.charging_plan ? <ChargingPlanPanel plan={result.charging_plan} /> : null}

          {result.strategy_comparison ? (
            <section className="panel">
              <h2>Route optimisation compared with simple rules</h2>
              <p>{result.strategy_comparison.summary}</p>
              <div className="table-scroll">
                <table className="factors">
                  <thead>
                    <tr>
                      <th>Strategy</th>
                      <th>Stations</th>
                      <th>Finishes trip?</th>
                      <th>Total time</th>
                      <th>Charging</th>
                      <th>Extra distance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.strategy_comparison.rows.map((row) => (
                      <tr key={row.strategy} className={row.strategy === 'optimised_plan' ? 'highlight' : ''}>
                        <td>{row.label}</td>
                        <td>{row.station_ids.join(' → ') || '—'}</td>
                        <td>{row.feasible ? 'Yes' : <span title={row.reason ?? ''}>No</span>}</td>
                        <td>{row.feasible ? fmtMinutes(row.total_trip_min) : '—'}</td>
                        <td>{row.feasible ? fmtMinutes(row.charging_min) : '—'}</td>
                        <td>{row.feasible ? fmtKm(row.detour_km) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="muted small">{result.strategy_comparison.note}</p>
              {result.routing_summary ? (
                <p className="muted small">
                  Routing cost: {result.routing_summary.total_requests} requests to {result.routing_summary.provider} for{' '}
                  {result.routing_summary.stations_routed} candidate stations (one request per leg would need{' '}
                  {result.routing_summary.per_station_requests_equivalent}). {result.routing_summary.note}
                </p>
              ) : null}
            </section>
          ) : null}

          <MapPlot
            origin={{ lat: num(form.origin_latitude), lon: num(form.origin_longitude) }}
            destination={{ lat: num(form.destination_latitude), lon: num(form.destination_longitude) }}
            stations={ranked.slice(0, 8)}
            recommendedId={result.recommended_station?.station_id ?? null}
            plan={result.charging_plan ?? null}
          />

          {result.direct_route ? (
            <p className="muted">
              Direct road route: {fmtKm(result.direct_route.distance_km)}, about{' '}
              {fmtMinutes(result.direct_route.duration_min)} ({result.direct_route.provider}, not live traffic). ©
              OpenStreetMap contributors.
            </p>
          ) : null}

          <h2>Ranked stations ({ranked.length})</h2>
          <div className="cards station-cards">
            {ranked.slice(0, 6).map((station) => (
              <StationCard
                key={station.station_id}
                station={station}
                recommended={station.station_id === result.recommended_station?.station_id}
              />
            ))}
          </div>
          {ranked.length > 6 ? (
            <details className="panel details">
              <summary>Show the other {ranked.length - 6} ranked stations</summary>
              <div className="cards station-cards">
                {ranked.slice(6).map((station) => (
                  <StationCard key={station.station_id} station={station} recommended={false} />
                ))}
              </div>
            </details>
          ) : null}
          {excluded.length ? (
            <details className="panel details">
              <summary>Stations not ranked for this trip ({excluded.length})</summary>
              <div className="table-scroll">
                <table className="factors">
                  <thead>
                    <tr>
                      <th>Station</th>
                      <th>Area</th>
                      <th>Why not</th>
                    </tr>
                  </thead>
                  <tbody>
                    {excluded.map((station) => (
                      <tr key={station.station_id}>
                        <td>
                          {station.station_id} · {station.station_name}
                        </td>
                        <td>{station.area || station.city || ''}</td>
                        <td>{station.exclusion_reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          ) : null}

          <details className="panel details">
            <summary>How this was calculated (energy, duration, models)</summary>
            <p>{result.energy_and_cost?.summary}</p>
            <p>
              Charging energy: {fmtKwh(result.energy_and_cost?.charging_energy_kwh)}. Grid energy:{' '}
              {fmtKwh(result.energy_and_cost?.grid_energy_kwh)}. Energy model loaded:{' '}
              {result.energy_and_cost?.energy_model_loaded ? 'yes' : 'no'}.
            </p>
            {result.trip_check?.note ? <p>{result.trip_check.note}</p> : null}
            <p>
              Component 2 duration: {result.charging_duration?.status ?? 'unavailable'}.{' '}
              {result.charging_duration?.predicted_charging_duration_min != null
                ? `${fmtMinutes(result.charging_duration.predicted_charging_duration_min)}. `
                : ''}
              {result.charging_duration?.reason}
            </p>
            <p className="muted small">{result.ranking_summary}</p>
            <ul>
              {(result.limitations ?? []).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </details>

          <section className="panel">
            <h2>Ask about this result</h2>
            <label>
              Question
              <input value={question} onChange={(e) => setQuestion(e.target.value)} />
            </label>
            <button type="button" disabled={busy} onClick={() => void ask()}>
              {busy ? 'Working…' : 'Ask'}
            </button>
            {followUp ? <p className="summary-text">{followUp}</p> : null}
          </section>
        </div>
      ) : (
        <p className="muted center">Fill in your trip and car, then press “Find my best station”.</p>
      )}
    </div>
  )
}

function KeyStats({ station }: { station: TripStation }) {
  const plan = station.trip_plan
  return (
    <dl className="stats">
      <div>
        <dt>Detour</dt>
        <dd>{fmtDetour(station.detour_distance_km, station.detour_duration_min)}</dd>
      </div>
      <div>
        <dt>Arrive with</dt>
        <dd>{fmtPct(plan.arrival_soc_percent)}</dd>
      </div>
      <div>
        <dt>{plan.charging_energy_kwh !== null ? 'Charge time (duration model)' : 'Charge to at least'}</dt>
        <dd>
          {plan.charging_energy_kwh !== null
            ? fmtMinutes(station.listed_power_duration_min)
            : plan.full_charge_insufficient
              ? 'full charge not enough'
              : fmtPct(plan.minimum_target_soc_percent)}
        </dd>
      </div>
      <div>
        <dt>Predicted wait (C1)</dt>
        <dd>
          {station.queue_prediction?.predicted_waiting_time_min != null
            ? fmtMinutes(station.queue_prediction.predicted_waiting_time_min)
            : 'no forecast'}
        </dd>
      </div>
      <div>
        <dt>Charging done</dt>
        <dd>{station.timeline?.charging_complete_time ? fmtClock(station.timeline.charging_complete_time) : 'set charge to %'}</dd>
      </div>
      <div>
        <dt>Scenario cost</dt>
        <dd>{fmtLkr(station.scenario_cost_lkr)}</dd>
      </div>
    </dl>
  )
}

function Badge({ ok, label }: { ok: boolean | null; label: string }) {
  const tone = ok === true ? 'good' : ok === false ? 'bad' : 'unknown'
  const mark = ok === true ? '✓' : ok === false ? '✗' : '?'
  return (
    <span className={`badge ${tone}`}>
      {mark} {label}
    </span>
  )
}

function StationCard({ station, recommended }: { station: TripStation; recommended: boolean }) {
  const battery = station.battery.status
  return (
    <article className={`card ${recommended ? 'recommended' : ''} ${station.included_in_ranking ? '' : 'excluded'}`}>
      <h3>
        {station.rank ? `#${station.rank} ` : 'Not ranked · '}
        {station.station_id} · {station.station_name}
        {recommended ? <span className="badge good pill">Recommended</span> : null}
      </h3>
      <p className="muted small">{station.address}</p>
      <div className="badges">
        <Badge
          ok={battery === 'feasible' ? true : battery === 'infeasible' ? false : null}
          label={battery === 'feasible' ? 'Reachable' : battery === 'infeasible' ? 'Not reachable' : 'Reach unknown'}
        />
        <Badge
          ok={station.connector_compatible}
          label={
            station.connector_compatible === null
              ? `Plugs: ${(station.connector_types_listed ?? []).join(', ') || 'unknown'}`
              : station.connector_compatible
                ? 'Your plug is listed'
                : 'Your plug is not listed'
          }
        />
        <Badge ok={null} label="Availability unknown" />
        {station.pareto_optimal ? <span className="badge good">Best trade-off: time vs listed cost</span> : null}
      </div>
      {station.included_in_ranking ? <KeyStats station={station} /> : null}
      <p>{station.plain_summary}</p>
      <p className="links small">
        <a href={osmLink(station.latitude, station.longitude)} target="_blank" rel="noreferrer">
          Open in map
        </a>
        {station.source_url ? (
          <>
            {' · '}
            <a href={station.source_url} target="_blank" rel="noreferrer">
              Source listing
            </a>
          </>
        ) : null}
      </p>
      <details>
        <summary>Technical details</summary>
        <ul>
          <li>
            Connectors listed:{' '}
            {station.connector_details?.length
              ? station.connector_details
                  .map(
                    (item) =>
                      `${item.connector}${item.quantity ? ` ×${item.quantity}` : ''}${item.power_kw !== null ? ` ${item.power_kw} kW` : ''}${item.supply ? ` ${item.supply}` : ''}`,
                  )
                  .join('; ')
              : (station.connector_types_listed ?? []).join('; ') || 'unknown'}
          </li>
          <li>
            Power for your plug: {station.charging_power_kw != null ? `${station.charging_power_kw} kW` : 'unknown'} (station
            maximum {station.max_power_kw_listed !== null ? `${station.max_power_kw_listed} kW` : 'unknown'})
          </li>
          <li>
            Listed rate for your plug:{' '}
            {station.tariff_for_connector_lkr_per_kwh != null
              ? `LKR ${station.tariff_for_connector_lkr_per_kwh}/kWh (${station.tariff_basis})`
              : 'not listed'}
          </li>
          {station.number_of_points != null ? <li>Charging points: {station.number_of_points}</li> : null}
          {station.opening_hours_listed ? <li>Listed hours: {station.opening_hours_listed}</li> : null}
          {station.access_note ? <li>Access: {station.access_note}</li> : null}
          {station.phone ? <li>Phone: {station.phone}</li> : null}
          <li>
            Road to station:{' '}
            {station.origin_to_station
              ? `${station.origin_to_station.distance_km.toFixed(2)} km, ${station.origin_to_station.duration_min.toFixed(1)} min`
              : 'unavailable'}
          </li>
          <li>
            Station to destination:{' '}
            {station.station_to_destination
              ? `${station.station_to_destination.distance_km.toFixed(2)} km, ${station.station_to_destination.duration_min.toFixed(1)} min`
              : 'unavailable'}
          </li>
          <li>
            Battery: {battery}
            {station.battery.estimated_energy_kwh !== null
              ? ` · ${station.battery.estimated_energy_kwh.toFixed(2)} kWh to reach it, ${station.battery.energy_above_reserve_kwh?.toFixed(2)} kWh above reserve`
              : ''}
          </li>
          <li>
            Battery at destination after charging:{' '}
            {fmtPct(station.trip_plan.soc_at_destination_percent)}
          </li>
          <li>
            Queue in 30 min:{' '}
            {station.queue_prediction?.predicted_queue_length != null
              ? `${station.queue_prediction.predicted_queue_length} vehicles`
              : 'not estimated'}
          </li>
          <li>
            Waiting time:{' '}
            {station.queue_prediction?.predicted_waiting_time_min != null
              ? fmtMinutes(station.queue_prediction.predicted_waiting_time_min)
              : 'not estimated'}
          </li>
          <li>
            Congestion: {station.queue_prediction?.predicted_congestion_level ?? 'not estimated'}
          </li>
          {station.queue_prediction?.reason ? <li className="muted">{station.queue_prediction.reason}</li> : null}
          <li>{station.listed_power_duration_note}</li>
          <li>Tariff listing: {station.tariff_raw ?? 'missing'} ({station.tariff_status}) — not used as a price</li>
          <li>Listing status: {station.operational_listing ?? 'unknown'}. Confirmed operational: no.</li>
        </ul>
        {station.exclusion_reason ? <p>{station.exclusion_reason}</p> : null}
        {station.factor_contributions?.length ? (
          <table className="factors">
            <thead>
              <tr>
                <th>Factor</th>
                <th>Value</th>
                <th>Score (1 = best)</th>
                <th>Weight</th>
              </tr>
            </thead>
            <tbody>
              {station.factor_contributions.map((item) => (
                <tr key={item.factor}>
                  <td>{item.factor.replace(/_/g, ' ')}</td>
                  <td>{Number(item.value).toFixed(2)}</td>
                  <td>{item.factor_score.toFixed(2)}</td>
                  <td>{Math.round(item.weight * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
        <p className="muted small">{station.ranking_explanation}</p>
        {station.source_note ? <p className="muted small">{station.source_note}</p> : null}
      </details>
    </article>
  )
}

function MapPlot({
  origin,
  destination,
  stations,
  recommendedId,
  plan,
}: {
  origin: { lat: number; lon: number }
  destination: { lat: number; lon: number }
  stations: TripStation[]
  recommendedId: string | null
  plan: ChargingPlan | null
}) {
  const stops = plan?.stops ?? []
  const width = 640
  const height = 360
  const pad = 36
  const points = [
    { lat: origin.lat, lon: origin.lon },
    { lat: destination.lat, lon: destination.lon },
    ...stations.map((station) => ({ lat: station.latitude, lon: station.longitude })),
    ...stops.map((stop) => ({ lat: stop.latitude, lon: stop.longitude })),
  ]
  const lats = points.map((point) => point.lat)
  const lons = points.map((point) => point.lon)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const minLon = Math.min(...lons)
  const maxLon = Math.max(...lons)
  const latSpan = Math.max(maxLat - minLat, 0.01)
  const lonSpan = Math.max(maxLon - minLon, 0.01)
  const x = (lon: number) => pad + ((lon - minLon) / lonSpan) * (width - pad * 2)
  const y = (lat: number) => pad + ((maxLat - lat) / latSpan) * (height - pad * 2)
  const recommended = stations.find((station) => station.station_id === recommendedId)

  return (
    <section className="panel">
      <h2>Map</h2>
      <p className="muted small">
        Shows the top-ranked stations and the stops of the charging plan. Lines join the points in order;
        they are not the road path. Distances on this page are road routes.
      </p>
      <svg className="map" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Colombo station map">
        <rect width={width} height={height} className="map-bg" />
        {stops.length > 1 ? (
          <polyline
            className="map-plan"
            points={[origin, ...stops.map((stop) => ({ lat: stop.latitude, lon: stop.longitude })), destination]
              .map((point) => `${x(point.lon)},${y(point.lat)}`)
              .join(' ')}
          />
        ) : null}
        {stops.map((stop) => (
          <g key={`stop-${stop.station_id}`}>
            <circle cx={x(stop.longitude)} cy={y(stop.latitude)} r="9" className="map-stop" />
            <text x={x(stop.longitude) + 11} y={y(stop.latitude) + 14}>
              Stop {stop.stop}: {stop.station_id}
            </text>
          </g>
        ))}
        {recommended?.origin_to_station ? (
          <polyline
            className="map-route"
            points={`${x(origin.lon)},${y(origin.lat)} ${x(recommended.longitude)},${y(recommended.latitude)} ${x(destination.lon)},${y(destination.lat)}`}
          />
        ) : null}
        <circle cx={x(origin.lon)} cy={y(origin.lat)} r="6" className="map-origin" />
        <text x={x(origin.lon) + 8} y={y(origin.lat)}>Start</text>
        <circle cx={x(destination.lon)} cy={y(destination.lat)} r="6" className="map-dest" />
        <text x={x(destination.lon) + 8} y={y(destination.lat)}>Destination</text>
        {stations.map((station) => (
          <g key={station.station_id}>
            <circle
              cx={x(station.longitude)}
              cy={y(station.latitude)}
              r={station.station_id === recommendedId ? 8 : 5}
              className={
                station.station_id === recommendedId
                  ? 'map-best'
                  : station.included_in_ranking
                    ? 'map-station'
                    : 'map-excluded'
              }
            />
            <text x={x(station.longitude) + 8} y={y(station.latitude) - 8}>
              {station.station_id}
            </text>
          </g>
        ))}
      </svg>
    </section>
  )
}

function ChargingPlanPanel({ plan }: { plan: ChargingPlan }) {
  const totals = plan.totals
  return (
    <section className={`panel plan ${plan.status}`}>
      <h2>
        Charging plan{' '}
        {plan.status === 'planned' && totals
          ? `· ${totals.stops} stop${totals.stops > 1 ? 's' : ''}`
          : plan.status === 'no_charge_needed'
            ? '· no stop needed'
            : '· not possible'}
      </h2>
      <p>{plan.explanation}</p>
      {plan.stops.length ? (
        <ol className="timeline">
          {plan.stops.map((stop) => (
            <li key={stop.station_id}>
              <p className="muted small">
                Drive {fmtKm(stop.drive_km_from_previous)} · {fmtMinutes(stop.drive_min_from_previous)}
              </p>
              <p>
                <strong>
                  Stop {stop.stop}: {stop.station_id} · {stop.station_name}
                </strong>{' '}
                <span className="muted">({stop.area})</span>
              </p>
              <p>
                Arrive {fmtPct(stop.arrival_soc_percent)} → leave {fmtPct(stop.departure_soc_percent)} · add{' '}
                {fmtKwh(stop.energy_added_kwh)} at {stop.charging_power_kw} kW ≈ {fmtMinutes(stop.charging_min)} ·{' '}
                {stop.listed_cost_lkr !== null ? `${fmtLkr(stop.listed_cost_lkr)} at the listed rate` : 'rate not listed'}
              </p>
            </li>
          ))}
          {plan.final_leg ? (
            <li>
              <p className="muted small">
                Drive {fmtKm(plan.final_leg.distance_km)} · {fmtMinutes(plan.final_leg.duration_min)}
              </p>
              <p>
                <strong>Destination</strong> · arrive with about {fmtPct(plan.arrival_soc_at_destination_percent)}
              </p>
            </li>
          ) : null}
        </ol>
      ) : null}
      {totals && totals.stops ? (
        <dl className="stats">
          <div>
            <dt>Total trip</dt>
            <dd>{fmtMinutes(totals.total_min)}</dd>
          </div>
          <div>
            <dt>Driving</dt>
            <dd>{fmtMinutes(totals.drive_min)}</dd>
          </div>
          <div>
            <dt>Charging (duration model)</dt>
            <dd>{fmtMinutes(totals.charging_min)}</dd>
          </div>
          <div>
            <dt>Listed-rate cost</dt>
            <dd>{totals.listed_cost_complete ? fmtLkr(totals.listed_cost_lkr) : 'a stop has no listed rate'}</dd>
          </div>
        </dl>
      ) : null}
      <details>
        <summary>How the plan is found</summary>
        <p className="small">{plan.algorithm}</p>
        <p className="muted small">
          {plan.candidates_considered} candidate stations, {plan.labels_explored} search states explored. Charging capped at{' '}
          {plan.max_charge_soc_percent}%.
        </p>
        <ul className="small">
          {plan.assumptions.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </details>
    </section>
  )
}

function metric(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined || !Number.isFinite(value) ? '—' : value.toFixed(digits)
}

/** One row per research component: what it predicted for this trip, and how good it is on held-out data. */
function ModelOutputs({ result }: { result: TripResponse }) {
  const best = result.recommended_station
  const queue = best?.queue_prediction
  const timeline = best?.timeline
  const energy = result.energy_and_cost
  const models = result.models ?? {}
  const plan = result.charging_plan
  const queueMetrics = models.queue?.test_metrics
  const waitMetrics = models.waiting_time?.test_metrics
  const congestionMetrics = models.congestion?.test_metrics
  const durationMetrics = models.duration?.test_metrics
  const energyMetrics = models.energy?.test_metrics
  return (
    <section className="panel">
      <h2>What each component says about this trip</h2>
      <div className="table-scroll">
        <table className="factors components">
          <thead>
            <tr>
              <th>Component</th>
              <th>Result for this trip</th>
              <th>Model and held-out test quality</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>1 · Queue, waiting time, congestion</td>
              <td>
                {queue?.status === 'area_model' ? (
                  <>
                    At {best?.station_id}: about <strong>{queue.predicted_queue_length}</strong> vehicles queued,{' '}
                    <strong>{fmtMinutes(queue.predicted_waiting_time_min)}</strong> wait, congestion{' '}
                    <strong>{queue.predicted_congestion_level}</strong> in 30 min.
                    <br />
                    <span className="muted small">
                      Synthetic forecast for {queue.trained_area} ({queue.distance_km} km away), not a count at this charger.
                    </span>
                  </>
                ) : (
                  <span className="muted">{queue?.reason ?? 'No station was recommended.'}</span>
                )}
              </td>
              <td className="small">
                {models.queue?.model_name ?? '—'} · queue MAE {metric(queueMetrics?.mae)} vehicles, R² {metric(queueMetrics?.r2)}
                <br />
                wait MAE {metric(waitMetrics?.mae_min, 1)} min, R² {metric(waitMetrics?.r2)}
                <br />
                congestion macro-F1 {metric(congestionMetrics?.macro_f1)} (majority-class baseline{' '}
                {metric(congestionMetrics?.baseline_most_frequent_macro_f1)})
              </td>
            </tr>
            <tr>
              <td>2 · Charging duration and completion time</td>
              <td>
                {timeline?.available && timeline.charging_complete_time ? (
                  <>
                    Arrive {fmtClock(timeline.arrive_at_station_time)}
                    {timeline.predicted_wait_min != null ? `, wait ${fmtMinutes(timeline.predicted_wait_min)}` : ''}, charge{' '}
                    {fmtMinutes(timeline.charging_min)} → <strong>done by {fmtClock(timeline.charging_complete_time)}</strong>
                    {timeline.arrive_destination_time ? `, at destination ${fmtClock(timeline.arrive_destination_time)}` : ''}.
                    <br />
                    <span className="muted small">{timeline.basis}</span>
                  </>
                ) : (
                  <span className="muted">Enter “Charge to %” to get a completion time.</span>
                )}
                {result.charging_duration?.status === 'predicted' ? (
                  <>
                    <br />
                    Component 2 model: {fmtMinutes(result.charging_duration.predicted_charging_duration_min)} (separate US-data estimate).
                  </>
                ) : null}
              </td>
              <td className="small">
                {models.duration?.model_name ?? '—'} · MAE {metric(durationMetrics?.mae_min, 1)} min, R²{' '}
                {metric(durationMetrics?.r2)}. Trained on US sessions, so it runs in the “Charging duration” tab, not per
                Colombo charger.
              </td>
            </tr>
            <tr>
              <td>3 · Battery consumption and cost</td>
              <td>
                {energy?.energy_model_applied ? (
                  <>
                    Direct drive uses <strong>{fmtKwh(result.trip_check?.direct_energy_kwh)}</strong> (model), arriving with{' '}
                    {fmtPct(result.trip_check?.soc_at_destination_without_charging_percent)}.{' '}
                  </>
                ) : (
                  <span className="muted">Energy model not used for this search: {energy?.energy_model_reason} </span>
                )}
                {energy?.charging_energy_kwh != null ? <>Charging adds {fmtKwh(energy.charging_energy_kwh)}. </> : null}
                {energy?.scenario_cost ? (
                  <>
                    Cost <strong>{fmtLkr(energy.scenario_cost.estimated_total)}</strong> at your tariff.
                  </>
                ) : (
                  <span className="muted">Add your tariff to see the cost.</span>
                )}
              </td>
              <td className="small">
                {models.energy?.model_name ?? '—'} · MAE {metric(energyMetrics?.mae_kwh)} kWh, R² {metric(energyMetrics?.r2)}{' '}
                (synthetic trips)
              </td>
            </tr>
            <tr>
              <td>4 · Station choice and route</td>
              <td>
                {plan?.explanation ?? 'No plan.'}
                {result.plan_arrival_time && plan?.status === 'planned' ? (
                  <> Arrive about {fmtClock(result.plan_arrival_time)}.</>
                ) : null}
              </td>
              <td className="small">
                Road-routed ranking and multi-stop planner; evaluation in the “Component 4 research” tab.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="muted small">Departure time used: {fmtClock(result.departure_time)} (Sri Lanka time).</p>
    </section>
  )
}
