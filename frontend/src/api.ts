const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''

const FIELD_LABELS: Record<string, string> = {
  origin_latitude: 'Origin latitude',
  origin_longitude: 'Origin longitude',
  destination_latitude: 'Destination latitude',
  destination_longitude: 'Destination longitude',
  current_soc_percent: 'Current battery %',
  usable_battery_capacity_kwh: 'Usable battery size',
  consumption_kwh_per_100km: 'Consumption',
  minimum_reserve_percent: 'Reserve %',
  target_soc_percent: 'Charge to %',
  user_tariff_lkr_per_kwh: 'Tariff',
  charging_efficiency: 'Charging efficiency',
}

function readableError(status: number, body: unknown, text: string): string {
  const detail = typeof body === 'object' && body && 'detail' in body ? (body as { detail: unknown }).detail : text
  if (Array.isArray(detail)) {
    const lines = detail.map((item: { loc?: unknown[]; msg?: string }) => {
      const field = String(item.loc?.[item.loc.length - 1] ?? 'input')
      return `${FIELD_LABELS[field] ?? field}: ${item.msg ?? 'invalid value'}`
    })
    return `Please check these inputs:\n${lines.join('\n')}`
  }
  if (status === 503) {
    return `A service the dashboard depends on is unavailable right now. ${String(detail)}`
  }
  if (status >= 500) {
    return `The server could not finish this request (error ${status}). ${String(detail)}`
  }
  return typeof detail === 'string' ? detail : JSON.stringify(detail, null, 2)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  const text = await res.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = { detail: text }
  }
  if (!res.ok) {
    throw new Error(readableError(res.status, body, text))
  }
  return body as T
}

export type StationInfo = {
  station_id: string
  station_name?: string
  location_type: string
  n_snapshots: number
  first_timestamp: string
  last_timestamp: string
}

export type Observation = {
  timestamp: string
  queue_length: number | null
  waiting_time_min: number | null
  congestion_level: string | null
  available_chargers: number | null
  total_chargers: number | null
}

export type StationNowResponse = {
  station_id: string
  location_type: string
  requested_local_time: string
  matched_snapshot_timestamp: string
  forecast_horizon_minutes: number
  match_rule: string
  data_note: string
  predictions: {
    queue: {
      predicted_queue_length: number
      plain_english: string
      unit: string
      model_name?: string
    }
    waiting_time: {
      predicted_waiting_time_min: number
      plain_english: string
      unit: string
      model_name?: string
    }
    congestion: {
      predicted_congestion_level: string
      plain_english: string
      class_probabilities?: Record<string, number> | null
      model_name?: string
    }
  }
  human_summary: string
  llm_used: boolean
  explanation_provider: string | null
  training_data?: string
  observed_now?: Observation | null
  recorded_outcome_30min?: Observation | null
  typical_error?: {
    queue_mae_vehicles: number | null
    waiting_time_mae_min: number | null
    congestion_accuracy: number | null
    source: string
  } | null
}

export type ColomboStation = {
  station_id: string
  station_name: string
  address: string
  latitude: number
  longitude: number
  connector_types_listed: string[]
  availability_status: string
  source_url?: string
  source_note?: string
  tariff_raw?: string | null
  tariff_status?: string
  waiting_time_min?: number | null
  queue_length_current?: number | null
}

export type TripStation = {
  station_id: string
  station_name: string
  address: string
  latitude: number
  longitude: number
  rank: number | null
  score: number | null
  included_in_ranking: boolean
  exclusion_reason: string | null
  connector_types_listed: string[]
  connector_compatible: boolean | null
  max_power_kw_listed: number | null
  tariff_raw: string | null
  tariff_status: string
  availability_status: string
  confirmed_operational: boolean
  operational_listing: string | null
  source_url: string | null
  source_note: string | null
  detour_distance_km: number | null
  detour_duration_min: number | null
  origin_to_station: { distance_km: number; duration_min: number; provider: string } | null
  station_to_destination: { distance_km: number; duration_min: number; provider: string } | null
  battery: { status: string; estimated_energy_kwh: number | null; energy_above_reserve_kwh: number | null }
  listed_power_duration_min: number | null
  listed_power_duration_note: string
  scenario_cost_lkr: number | null
  queue_prediction: {
    status: string
    predicted_queue_length: number | null
    predicted_waiting_time_min: number | null
    predicted_congestion_level: string | null
    reason: string
    training_data: string
    trained_area?: string | null
    trained_station_id?: string | null
    distance_km?: number | null
  }
  timeline?: {
    available: boolean
    departure_time?: string
    arrive_at_station_time?: string
    predicted_wait_min?: number | null
    start_charging_time?: string
    charging_min?: number | null
    charging_complete_time?: string | null
    arrive_destination_time?: string | null
    missing?: string[]
    basis?: string
  }
  ranking_explanation: string
  plain_summary: string
  trip_plan: {
    arrival_soc_percent: number | null
    onward_energy_kwh: number | null
    minimum_target_soc_percent: number | null
    full_charge_insufficient: boolean | null
    charging_energy_kwh: number | null
    soc_at_destination_percent: number | null
    reaches_destination_with_reserve: boolean | null
  }
  factor_contributions?: { factor: string; value: number; factor_score: number; weight: number }[]
  area?: string
  city?: string | null
  number_of_points?: number | null
  connector_details?: { connector: string; quantity: number | null; power_kw: number | null; supply: string | null }[]
  usage_type?: string | null
  access_note?: string | null
  opening_hours_listed?: string | null
  phone?: string | null
  charging_power_kw?: number | null
  tariff_for_connector_lkr_per_kwh?: number | null
  tariff_basis?: string | null
  pareto_optimal?: boolean | null
}

export type PlanStop = {
  stop: number
  station_id: string
  station_name: string
  area: string
  latitude: number
  longitude: number
  arrival_soc_percent: number
  departure_soc_percent: number
  energy_added_kwh: number
  charging_power_kw: number
  charging_min: number
  overhead_min: number
  listed_tariff_lkr_per_kwh: number | null
  listed_cost_lkr: number | null
  drive_km_from_previous: number
  drive_min_from_previous: number
}

export type ChargingPlan = {
  status: 'no_charge_needed' | 'planned' | 'infeasible'
  objective: string
  algorithm: string
  assumptions: string[]
  explanation: string
  stops: PlanStop[]
  final_leg: { distance_km: number; duration_min: number } | null
  arrival_soc_at_destination_percent: number | null
  candidates_considered: number
  labels_explored: number
  max_charge_soc_percent: number
  totals: {
    drive_km: number
    drive_min: number
    charging_min: number
    overhead_min: number
    total_min: number
    energy_added_kwh: number
    listed_cost_lkr: number | null
    listed_cost_complete: boolean
    stops: number
  } | null
}

export type StrategyRow = {
  strategy: string
  label: string
  station_ids: string[]
  feasible: boolean
  reason: string | null
  stops?: number
  total_trip_min?: number
  charging_min?: number
  detour_km?: number | null
  listed_cost_lkr?: number | null
}

export type RoutingSummary = {
  provider: string
  stations_in_inventory: number
  stations_routed: number
  table_requests: number
  route_requests: number
  total_requests: number
  per_station_requests_equivalent: number
  note: string
}

export type ResearchSummary = {
  data_completeness: {
    retrieved_on: string
    source: string
    license: string
    stations_in_inventory: number
    original_station_count: number
    operational_listings: number
    in_greater_colombo: number
    with_dc_fast_charging: number
    fields: {
      field: string
      label: string
      original_csv_filled: number
      original_csv_total: number
      same_four_stations_now_filled: number
      inventory_filled: number
      inventory_total: number
    }[]
    corrections_to_original_rows: { station_id: string; field: string; original: string; rebuilt: string; why: string }[]
    still_unknown: string
  } | null
  routing_evaluation: {
    scenarios: number
    places: number
    vehicles: Record<string, { usable_kwh: number; kwh_per_100km: number }>
    start_soc_percent: number[]
    reserve_percent: number
    trips_without_charging: number
    trips_needing_charging: number
    strategies: Record<
      string,
      {
        label: string
        trips_scored: number
        trips_completed: number
        success_rate: number
        mean_total_trip_min: number | null
        mean_minutes_slower_than_optimised: number | null
        mean_detour_km: number | null
      }
    >
    optimised_plan: {
      completed: number
      infeasible_with_listed_stations: number
      rescued_trips: number
      stops_distribution: Record<string, number>
      mean_minutes_saved_vs_best_single_stop: number | null
    }
    routing_requests: { mean_matrix_method: number; mean_per_station_method: number; note: string }
    matrix_source: string
    matrix_retrieved_on: string
  } | null
  how_to_reproduce: string[]
}

export type TripResponse = {
  recommended_station: TripStation | null
  alternatives: TripStation[]
  direct_route: { distance_km: number; duration_min: number; provider: string } | null
  warnings: string[]
  quick_answer: string[]
  trip_check: {
    status: string
    direct_energy_kwh: number | null
    soc_at_destination_without_charging_percent: number | null
    can_finish_without_charging: boolean | null
    note: string
  }
  ranking_summary: string
  charging_duration: {
    status: string
    predicted_charging_duration_min: number | null
    reason: string
    model_name?: string
    metrics?: { mae_min?: number; r2?: number } | null
    used_in_ranking: boolean
  }
  energy_and_cost: {
    energy_model_loaded: boolean
    energy_model_applied?: boolean
    energy_model_reason?: string | null
    trip_energy_method?: string
    charging_energy_kwh: number | null
    grid_energy_kwh: number | null
    summary: string
    scenario_cost: { estimated_total: number; currency: string; energy_basis: string } | null
  }
  models: Record<
    string,
    {
      loaded?: boolean
      model_name?: string | null
      test_metrics?: Record<string, number | null> | null
      reason?: string
      applied_to_listed_stations?: boolean
      applied_to_this_trip?: boolean
    }
  >
  departure_time?: string
  plan_arrival_time?: string | null
  limitations: string[]
  explanation?: { text: string; llm_used: boolean; provider: string }
  live_availability: boolean
  live_queue_prediction: boolean
  charging_plan?: ChargingPlan | null
  strategy_comparison?: { rows: StrategyRow[]; summary: string; note: string } | null
  routing_summary?: RoutingSummary | null
}

export type TripRequest = {
  origin_latitude: number
  origin_longitude: number
  destination_latitude: number
  destination_longitude: number
  current_soc_percent: number
  usable_battery_capacity_kwh: number
  consumption_kwh_per_100km: number
  minimum_reserve_percent: number
  required_connector?: string | null
  target_soc_percent?: number | null
  user_tariff_lkr_per_kwh?: number | null
  charging_efficiency?: number | null
  duration_features?: Record<string, string | number> | null
  max_charge_soc_percent?: number
  energy_conditions?: EnergyConditions | null
}

export type EnergyConditions = {
  elevation_gain_m: number
  elevation_loss_m: number
  ambient_temperature_c: number
  ac_on: boolean
  traffic_level: string
  road_type: string
  vehicle_mass_kg: number
}

export type DurationPrediction = {
  predicted_charging_duration_min: number
  raw_prediction_min: number
  model_name: string | null
  selected_model: string | null
  test_metrics: { mae_min?: number; rmse_min?: number; r2?: number; n?: number } | null
  charging_start_time: string | null
  expected_completion_time: string | null
  note: string
}

export type EnergyPrediction = {
  predicted_energy_kwh: number
  model_name?: string | null
  [key: string]: unknown
}

export type CostEstimate = {
  estimated_total: number
  currency: string
  formula: string
  assumptions: string[]
  battery_energy_kwh: number
  grid_energy_kwh: number | null
}

export type EnergySchema = {
  feature_columns: string[]
  condition_features: string[]
  categories: Record<string, string[]>
  selected_model: string | null
  test_metrics: { mae_kwh?: number; rmse_kwh?: number; r2?: number; n?: number } | null
  note: string
}

export const api = {
  health: () =>
    request<{ status: string; routing_ready: boolean; energy_model_loaded: boolean }>('/health'),
  component4Research: () => request<ResearchSummary>('/api/v1/component4/research'),
  predictDuration: (features: Record<string, string | number>, chargingStartTime: string | null) =>
    request<DurationPrediction>('/api/v1/duration/predict', {
      method: 'POST',
      body: JSON.stringify({ features, charging_start_time: chargingStartTime }),
    }),
  energySchema: () => request<EnergySchema>('/api/v1/energy-schema'),
  predictEnergy: (record: Record<string, string | number>) =>
    request<EnergyPrediction>('/api/v1/energy/predict', { method: 'POST', body: JSON.stringify(record) }),
  energyCost: (body: { energy_kwh: number; tariff_lkr_per_kwh: number; charging_efficiency?: number | null }) =>
    request<CostEstimate>('/api/v1/energy/cost', { method: 'POST', body: JSON.stringify(body) }),
  colomboStations: () => request<{ count: number; stations: ColomboStation[]; source: string }>('/api/v1/colombo-stations'),
  recommend: (body: TripRequest) =>
    request<TripResponse>('/api/v1/recommend', { method: 'POST', body: JSON.stringify(body) }),
  explain: (result: TripResponse, question: string) =>
    request<{ text: string; llm_used: boolean; provider: string }>('/api/v1/explain', {
      method: 'POST',
      body: JSON.stringify({ result, question }),
    }),
  durationSchema: () =>
    request<{
      feature_columns: string[]
      numeric_features: string[]
      categories: Record<string, string[]>
      note: string
    }>('/api/v1/duration-schema'),
  syntheticHealth: () => request<{ all_models_loaded: boolean }>('/api/v1/synthetic/health'),
  syntheticStations: () => request<{ stations: StationInfo[] }>('/api/v1/synthetic/stations'),
  predictStationNow: (body: {
    station_id: string
    use_current_time?: boolean
    include_llm?: boolean
  }) =>
    request<StationNowResponse>('/api/v1/synthetic/predict/station-now', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}
