String fmtKm(double? km) {
  if (km == null) return 'Unavailable';
  return '${km.toStringAsFixed(1)} km';
}

String fmtMinutes(double? minutes) {
  if (minutes == null) return 'Unavailable';
  if (minutes < 1) return '< 1 min';
  return '${minutes.round()} min';
}

String fmtKwh(double? kwh) {
  if (kwh == null) return 'Unavailable';
  return '${kwh.toStringAsFixed(1)} kWh';
}

String fmtLkr(double? amount) {
  if (amount == null) return 'Unavailable';
  return 'Rs. ${amount.toStringAsFixed(0)}';
}
