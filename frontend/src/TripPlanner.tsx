import { useEffect, useMemo, useState } from 'react'
import { api, type ColomboStation, type TripRequest, type TripResponse, type TripStation } from './api'
import { fmtDetour, fmtKm, fmtKwh, fmtLkr, fmtMinutes, fmtPct, osmLink } from './format'

// Approximate area centres, for convenience only. Edit the coordinates for an exact address.
const PLACES: { name: string; latitude: number; longitude: number }[] = [
  { name: 'Colombo centre (example origin)', latitude: 6.9271, longitude: 79.8612 },
  { name: 'Colombo Fort', latitude: 6.9339, longitude: 79.85 },
  { name: 'Kollupitiya', latitude: 6.911, longitude: 79.851 },
  { name: 'Bambalapitiya', latitude: 6.889, longitude: 79.856 },
  { name: 'Wellawatte', latitude: 6.874, longitude: 79.86 },
  { name: 'Borella', latitude: 6.915, longitude: 79.878 },
  { name: 'Rajagiriya', latitude: 6.909, longitude: 79.896 },
  { name: 'Battaramulla', latitude: 6.899, longitude: 79.918 },
  { name: 'Nugegoda (example destination)', latitude: 6.8649, longitude: 79.8997 },
  { name: 'Dehiwala', latitude: 6.851, longitude: 79.865 },
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
}

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
  target_soc_percent: '',
  user_tariff_lkr_per_kwh: '',
  charging_efficiency: '',
}

function num(value: string): number {
  return Number(value)
}

function optionalNum(value: string): number | null {
  return value.trim() === '' ? null : Number(value)
}

function validate(form: FormState): string[] {
  const problems: string[] = []
  const required = (key: keyof FormState, label: string, min: number, max: number, strictMin = false) => {
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
  const optional = (key: keyof FormState, label: string, min: number, max: number, strictMin = false) => {
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

  function update(key: keyof FormState, value: string) {
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

  const hint = consumptionHint(form.consumption_kwh_per_100km)

  return (
    <div>
      <p className="banner">
        Uses the four Colombo listings in the project CSV. Live availability and queues are unknown, so
        always confirm with the operator before you go.
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

          <MapPlot
            origin={{ lat: num(form.origin_latitude), lon: num(form.origin_longitude) }}
            destination={{ lat: num(form.destination_latitude), lon: num(form.destination_longitude) }}
            stations={cards}
            recommendedId={result.recommended_station?.station_id ?? null}
          />

          {result.direct_route ? (
            <p className="muted">
              Direct road route: {fmtKm(result.direct_route.distance_km)}, about{' '}
              {fmtMinutes(result.direct_route.duration_min)} ({result.direct_route.provider}, not live traffic). ©
              OpenStreetMap contributors.
            </p>
          ) : null}

          <h2>All stations</h2>
          <div className="cards station-cards">
            {cards.map((station) => (
              <StationCard
                key={station.station_id}
                station={station}
                recommended={station.station_id === result.recommended_station?.station_id}
              />
            ))}
          </div>

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
        <dt>{plan.charging_energy_kwh !== null ? 'Charge time (listed kW)' : 'Charge to at least'}</dt>
        <dd>
          {plan.charging_energy_kwh !== null
            ? fmtMinutes(station.listed_power_duration_min)
            : plan.full_charge_insufficient
              ? 'full charge not enough'
              : fmtPct(plan.minimum_target_soc_percent)}
        </dd>
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
          <li>Connectors listed: {(station.connector_types_listed ?? []).join('; ') || 'unknown'}</li>
          <li>Listed power: {station.max_power_kw_listed !== null ? `${station.max_power_kw_listed} kW` : 'unknown'}</li>
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
            Queue / wait / congestion: not predicted
            {station.queue_prediction?.training_data
              ? ` (${station.queue_prediction.training_data} models not applied)`
              : ''}
          </li>
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
}: {
  origin: { lat: number; lon: number }
  destination: { lat: number; lon: number }
  stations: TripStation[]
  recommendedId: string | null
}) {
  const width = 640
  const height = 360
  const pad = 36
  const points = [
    { lat: origin.lat, lon: origin.lon },
    { lat: destination.lat, lon: destination.lon },
    ...stations.map((station) => ({ lat: station.latitude, lon: station.longitude })),
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
        Dots use the CSV coordinates. The dashed line joins origin, the recommended station and the
        destination; it is not the road path. Distances on this page are road routes.
      </p>
      <svg className="map" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Colombo station map">
        <rect width={width} height={height} className="map-bg" />
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
