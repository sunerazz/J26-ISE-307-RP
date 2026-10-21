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
    charging_energy_kwh: number | null
    grid_energy_kwh: number | null
    summary: string
    scenario_cost: { estimated_total: number; currency: string; energy_basis: string } | null
  }
  models: Record<string, { loaded?: boolean; model_name?: string | null; test_metrics?: unknown; reason?: string }>
  limitations: string[]
  explanation?: { text: string; llm_used: boolean; provider: string }
  live_availability: boolean
  live_queue_prediction: boolean
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
}

export const api = {
  health: () =>
    request<{ status: string; routing_ready: boolean; energy_model_loaded: boolean }>('/health'),
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
