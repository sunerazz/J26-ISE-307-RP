// Display helpers. They only format numbers the API returned; they never fill in a missing value.

export function fmtMinutes(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined || !Number.isFinite(minutes)) return 'unknown'
  if (minutes < 1) return 'under 1 min'
  const rounded = Math.round(minutes)
  if (rounded < 60) return `${rounded} min`
  const hours = Math.floor(rounded / 60)
  const rest = rounded % 60
  return rest ? `${hours} h ${rest} min` : `${hours} h`
}

export function fmtKm(km: number | null | undefined): string {
  if (km === null || km === undefined || !Number.isFinite(km)) return 'unknown'
  return `${km < 10 ? km.toFixed(1) : Math.round(km)} km`
}

export function fmtDetour(km: number | null | undefined, minutes: number | null | undefined): string {
  if (km === null || km === undefined) return 'unknown'
  if (km <= 0.05) return 'on your route'
  const extra = minutes !== null && minutes !== undefined && minutes > 0.5 ? ` · +${fmtMinutes(minutes)}` : ''
  return `+${fmtKm(km)}${extra}`
}

export function fmtPct(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'unknown'
  return `${Math.round(value)}%`
}

export function fmtKwh(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'unknown'
  return `${value.toFixed(1)} kWh`
}

export function fmtLkr(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'not calculated'
  return `LKR ${Math.round(value).toLocaleString('en-LK')}`
}

export function osmLink(latitude: number, longitude: number): string {
  return `https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=17/${latitude}/${longitude}`
}

/** '2026-10-22T14:35+05:30' -> '2:35 pm'. The API sends Sri Lanka local time. */
export function fmtClock(value: string | null | undefined): string {
  if (!value) return 'unknown'
  const match = /T(\d{2}):(\d{2})/.exec(value)
  if (!match) return value
  const hour = Number(match[1])
  const suffix = hour >= 12 ? 'pm' : 'am'
  return `${hour % 12 || 12}:${match[2]} ${suffix}`
}

/** Feature names from the Component 2 spreadsheet carry a broken degree sign ('Â°C'). Display only. */
export function fixLabel(label: string): string {
  return label.replace('Â°', '°')
}
