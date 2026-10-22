import { useEffect, useState } from 'react'
import { api, type StationInfo, type StationNowResponse } from './api'
import { fmtMinutes } from './format'

function congestionTone(level: string): string {
  const v = level.toLowerCase()
  if (v === 'low') return 'good'
  if (v === 'medium') return 'warn'
  return 'bad'
}

export default function StationCheck() {
  const [stations, setStations] = useState<StationInfo[]>([])
  const [stationId, setStationId] = useState('ST01')
  const [useLlm, setUseLlm] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [apiOk, setApiOk] = useState<boolean | null>(null)
  const [result, setResult] = useState<StationNowResponse | null>(null)

  useEffect(() => {
    void (async () => {
      try {
        const h = await api.syntheticHealth()
        setApiOk(h.all_models_loaded)
        const s = await api.syntheticStations()
        setStations(s.stations)
        if (s.stations.length) setStationId(s.stations[0].station_id)
      } catch {
        setApiOk(false)
      }
    })()
  }, [])

  async function checkNow() {
    setBusy(true)
    setError(null)
    try {
      const data = await api.predictStationNow({
        station_id: stationId,
        use_current_time: true,
        include_llm: useLlm,
      })
      setResult(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const selected = stations.find((s) => s.station_id === stationId)
  const now = result?.observed_now
  const typical = result?.typical_error
  const probabilities = result?.predictions.congestion.class_probabilities ?? null
  const waitMae = typical?.waiting_time_mae_min
  const waitRange =
    result && waitMae !== null && waitMae !== undefined
      ? waitMae < 1
        ? 'within about a minute'
        : `${fmtMinutes(Math.max(0, result.predictions.waiting_time.predicted_waiting_time_min - waitMae))} – ${fmtMinutes(
            result.predictions.waiting_time.predicted_waiting_time_min + waitMae,
          )} (forecast ± average test error at this station)`
      : null

  return (
    <div>
      <p className="banner">
        Component 1 · AI-based queue length, waiting time and congestion prediction, 30 minutes ahead. The models were
        trained on simulated 15-minute snapshots for five Colombo-area towns. The trip planner uses the nearest
        town's forecast for chargers within 15 km. These are not live readings at a charger.
      </p>
      <p className={`api-pill ${apiOk ? 'ok' : apiOk === false ? 'down' : ''}`}>
        {apiOk === null
          ? 'Checking models…'
          : apiOk
            ? 'Synthetic models loaded'
            : 'Models offline — start the integration API on port 8000'}
      </p>

      <section className="panel controls">
        <label>
          Synthetic station
          <select value={stationId} onChange={(e) => setStationId(e.target.value)}>
            {stations.map((s) => (
              <option key={s.station_id} value={s.station_id}>
                {s.station_id} · {s.station_name ?? s.location_type} ({s.location_type})
              </option>
            ))}
          </select>
        </label>
        {selected ? (
          <p className="muted small">
            {selected.location_type} station · snapshots {selected.first_timestamp} →{' '}
            {selected.last_timestamp}
          </p>
        ) : null}

        <label className="check">
          <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} />
          Human-readable explanation (uses OpenAI if <code>OPENAI_API_KEY</code> is set; otherwise a
          clear template)
        </label>

        <button type="button" disabled={busy || !apiOk} onClick={() => void checkNow()}>
          {busy ? 'Checking station…' : 'Check now'}
        </button>
      </section>

      {error ? <pre className="error">{error}</pre> : null}

      {result ? (
        <div className="results">
          <section className="panel summary">
            <h2>Easy summary</h2>
            <p className="summary-text">{result.human_summary}</p>
            <p className="muted small">
              Explanation source: {result.explanation_provider}
              {result.llm_used ? ' (LLM)' : ' (template)'} · forecast horizon{' '}
              {result.forecast_horizon_minutes} min · synthetic snapshot
            </p>
          </section>

          <div className="cards">
            <article className="card">
              <h3>Queue in 30 min</h3>
              <p className="metric">{result.predictions.queue.predicted_queue_length}</p>
              <p className="metric-unit">
                vehicles
                {now?.queue_length !== null && now?.queue_length !== undefined ? ` · now ${now.queue_length}` : ''}
              </p>
              <p>{result.predictions.queue.plain_english}</p>
              {typical?.queue_mae_vehicles !== null && typical?.queue_mae_vehicles !== undefined ? (
                <p className="muted small">Typical error here: ±{typical.queue_mae_vehicles.toFixed(1)} vehicles</p>
              ) : null}
            </article>
            <article className="card">
              <h3>Waiting time in 30 min</h3>
              <p className="metric">{fmtMinutes(result.predictions.waiting_time.predicted_waiting_time_min)}</p>
              <p className="metric-unit">
                {now?.waiting_time_min !== null && now?.waiting_time_min !== undefined
                  ? `now ${fmtMinutes(now.waiting_time_min)}`
                  : 'synthetic model'}
              </p>
              <p>{result.predictions.waiting_time.plain_english}</p>
              {waitRange ? <p className="muted small">Likely range: {waitRange}</p> : null}
            </article>
            <article
              className={`card tone-${congestionTone(result.predictions.congestion.predicted_congestion_level)}`}
            >
              <h3>Congestion in 30 min</h3>
              <p className="metric level">{result.predictions.congestion.predicted_congestion_level}</p>
              <p className="metric-unit">{now?.congestion_level ? `now ${now.congestion_level}` : 'Low / Medium / High'}</p>
              <p>{result.predictions.congestion.plain_english}</p>
              {probabilities ? (
                <div className="probs" aria-label="Model confidence per level">
                  {['Low', 'Medium', 'High'].map((level) =>
                    probabilities[level] !== undefined ? (
                      <div key={level} className="prob-row">
                        <span>{level}</span>
                        <span className="prob-bar">
                          <span className={`prob-fill tone-${congestionTone(level)}`} style={{ width: `${probabilities[level] * 100}%` }} />
                        </span>
                        <span>{Math.round(probabilities[level] * 100)}%</span>
                      </div>
                    ) : null,
                  )}
                </div>
              ) : null}
            </article>
          </div>

          {result.recorded_outcome_30min ? (
            <section className="panel">
              <h2>How close was it?</h2>
              <p className="muted small">
                This snapshot is from synthetic history, so the record also shows what happened 30 minutes later
                ({result.recorded_outcome_30min.timestamp}). It is shown for comparison only and was not a model input.
              </p>
              <table className="factors">
                <thead>
                  <tr>
                    <th></th>
                    <th>Forecast</th>
                    <th>Recorded</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Queue</td>
                    <td>{result.predictions.queue.predicted_queue_length}</td>
                    <td>{result.recorded_outcome_30min.queue_length ?? 'unknown'}</td>
                  </tr>
                  <tr>
                    <td>Wait</td>
                    <td>{fmtMinutes(result.predictions.waiting_time.predicted_waiting_time_min)}</td>
                    <td>{fmtMinutes(result.recorded_outcome_30min.waiting_time_min)}</td>
                  </tr>
                  <tr>
                    <td>Congestion</td>
                    <td>{result.predictions.congestion.predicted_congestion_level}</td>
                    <td>{result.recorded_outcome_30min.congestion_level ?? 'unknown'}</td>
                  </tr>
                </tbody>
              </table>
            </section>
          ) : null}

          <section className="panel details">
            <h2>Time matching</h2>
            <ul>
              <li>
                Your check time: <strong>{result.requested_local_time}</strong>
              </li>
              <li>
                Snapshot used: <strong>{result.matched_snapshot_timestamp}</strong>
              </li>
              <li>
                Match rule: <strong>{result.match_rule}</strong>
              </li>
              <li>
                Model: <strong>{result.predictions.queue.model_name ?? 'saved artifact'}</strong>
              </li>
            </ul>
            <p className="muted small">{result.data_note}</p>
          </section>
        </div>
      ) : (
        <p className="muted center">Select a synthetic station and press Check now.</p>
      )}
    </div>
  )
}
