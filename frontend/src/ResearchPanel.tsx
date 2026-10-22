import { useEffect, useState } from 'react'
import { api, type ResearchSummary } from './api'

const ORDER = ['nearest_station', 'minimum_detour', 'weighted_ranking', 'optimised_plan']

/** Component 4 evidence for the research panel. Every number is read from the saved evaluation files. */
export default function ResearchPanel() {
  const [data, setData] = useState<ResearchSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .component4Research()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  if (error) return <pre className="error">{error}</pre>
  if (!data) return <p className="muted center">Loading Component 4 results…</p>

  const inventory = data.data_completeness
  const evaluation = data.routing_evaluation

  return (
    <div className="results">
      {inventory ? (
        <section className="panel">
          <h2>1 · Station data: from 4 listings to {inventory.stations_in_inventory}</h2>
          <p className="muted small">
            {inventory.source}, retrieved {inventory.retrieved_on}. {inventory.license}.
          </p>
          <div className="research-grid">
            <div>
              <strong>{inventory.stations_in_inventory}</strong>
              <span>stations (was {inventory.original_station_count})</span>
            </div>
            <div>
              <strong>{inventory.in_greater_colombo}</strong>
              <span>within 20 km of Colombo Fort</span>
            </div>
            <div>
              <strong>{inventory.with_dc_fast_charging}</strong>
              <span>with DC fast charging</span>
            </div>
            <div>
              <strong>{inventory.operational_listings}</strong>
              <span>listed as operational</span>
            </div>
          </div>
          <div className="table-scroll">
            <table className="factors">
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Original CSV</th>
                  <th>Same 4 stations, rebuilt</th>
                  <th>Full inventory</th>
                </tr>
              </thead>
              <tbody>
                {inventory.fields.map((item) => (
                  <tr key={item.field}>
                    <td>{item.label}</td>
                    <td>
                      {item.original_csv_filled}/{item.original_csv_total}
                    </td>
                    <td>
                      {item.same_four_stations_now_filled}/{item.original_csv_total}
                    </td>
                    <td>
                      {item.inventory_filled}/{item.inventory_total}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small">{inventory.still_unknown}</p>
          {inventory.corrections_to_original_rows.length ? (
            <details>
              <summary>Corrections to the original four rows ({inventory.corrections_to_original_rows.length})</summary>
              <ul className="small">
                {inventory.corrections_to_original_rows.map((item) => (
                  <li key={`${item.station_id}-${item.field}`}>
                    {item.station_id} {item.field}: {item.original} → {item.rebuilt}. {item.why}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </section>
      ) : (
        <p className="muted">The data completeness report has not been generated. Run python -m src.build_inventory.</p>
      )}

      {evaluation ? (
        <>
          <section className="panel">
            <h2>2 · Route optimisation: success on trips that need charging</h2>
            <p className="muted small">
              {evaluation.scenarios.toLocaleString()} scenarios: every ordered pair of {evaluation.places} towns ×{' '}
              {Object.keys(evaluation.vehicles).length} Nissan Leaf variants × start charge{' '}
              {evaluation.start_soc_percent.join('/')}%, reserve {evaluation.reserve_percent}%.{' '}
              {evaluation.trips_needing_charging.toLocaleString()} of them need charging and are scored. Road legs:{' '}
              {evaluation.matrix_source}, retrieved {evaluation.matrix_retrieved_on}.
            </p>
            {ORDER.map((key) => {
              const item = evaluation.strategies[key]
              if (!item) return null
              const pct = item.success_rate * 100
              return (
                <div className="bar-row" key={key}>
                  <span>{item.label}</span>
                  <div className="bar-track" role="img" aria-label={`${item.label}: ${pct.toFixed(1)}% of trips completed`}>
                    <div className={`bar-fill ${key === 'optimised_plan' ? 'best' : ''}`} style={{ width: `${pct}%` }} />
                  </div>
                  <strong>{pct.toFixed(1)}%</strong>
                </div>
              )
            })}
            <div className="table-scroll">
              <table className="factors">
                <thead>
                  <tr>
                    <th>Strategy</th>
                    <th>Trips completed</th>
                    <th>Mean min slower than optimised (same trips)</th>
                    <th>Mean extra distance</th>
                  </tr>
                </thead>
                <tbody>
                  {ORDER.map((key) => {
                    const item = evaluation.strategies[key]
                    return item ? (
                      <tr key={key} className={key === 'optimised_plan' ? 'highlight' : ''}>
                        <td>{item.label}</td>
                        <td>
                          {item.trips_completed}/{item.trips_scored}
                        </td>
                        <td>{item.mean_minutes_slower_than_optimised ?? '—'}</td>
                        <td>{item.mean_detour_km != null ? `${item.mean_detour_km} km` : '—'}</td>
                      </tr>
                    ) : null
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <h2>3 · What the multi-stop planner adds</h2>
            <div className="research-grid">
              <div>
                <strong>{evaluation.optimised_plan.rescued_trips}</strong>
                <span>trips only the planner completes (no single stop works)</span>
              </div>
              <div>
                <strong>{evaluation.optimised_plan.mean_minutes_saved_vs_best_single_stop ?? '—'} min</strong>
                <span>mean saving vs the best single-stop rule, where one exists</span>
              </div>
              <div>
                <strong>{evaluation.optimised_plan.infeasible_with_listed_stations}</strong>
                <span>trips no plan can complete with the listed stations</span>
              </div>
            </div>
            <p className="small">
              Stops per completed trip:{' '}
              {Object.entries(evaluation.optimised_plan.stops_distribution)
                .map(([stops, count]) => `${stops} stop${stops === '1' ? '' : 's'}: ${count}`)
                .join(' · ')}
            </p>
          </section>

          <section className="panel">
            <h2>4 · Routing cost per trip</h2>
            <div className="research-grid">
              <div>
                <strong>{evaluation.routing_requests.mean_per_station_method}</strong>
                <span>routing requests before (two per station)</span>
              </div>
              <div>
                <strong>{evaluation.routing_requests.mean_matrix_method}</strong>
                <span>routing requests now (one road matrix)</span>
              </div>
            </div>
            <p className="muted small">{evaluation.routing_requests.note}</p>
          </section>
        </>
      ) : (
        <p className="muted">The routing evaluation has not been generated. Run python -m src.evaluate_routing.</p>
      )}

      <p className="muted small">
        Reproduce from component4_station_recommendation: {data.how_to_reproduce.join(' then ')}. Figures and per-scenario
        rows are in its results folder.
      </p>
    </div>
  )
}
