// Display helpers. They format values the API returned and never fill in a missing one.

String fmtKm(double? km) {
  if (km == null) return '—';
  if (km < 10) return '${km.toStringAsFixed(1)} km';
  return '${km.round()} km';
}

String fmtMinutes(double? minutes) {
  if (minutes == null) return '—';
  if (minutes < 1) return '< 1 min';
  final rounded = minutes.round();
  if (rounded < 60) return '$rounded min';
  final hours = rounded ~/ 60;
  final rest = rounded % 60;
  return rest == 0 ? '$hours h' : '$hours h $rest min';
}

String fmtPercent(double? value) => value == null ? '—' : '${value.round()}%';

String fmtKwh(double? kwh) => kwh == null ? '—' : '${kwh.toStringAsFixed(1)} kWh';

String fmtLkr(double? amount) {
  if (amount == null) return '—';
  final digits = amount.round().toString();
  final grouped = digits.replaceAllMapped(RegExp(r'\B(?=(\d{3})+(?!\d))'), (_) => ',');
  return 'Rs. $grouped';
}

String fmtNumber(double value) =>
    value == value.roundToDouble() ? value.toStringAsFixed(0) : value.toStringAsFixed(1);

/// "Today, 14:05", "Yesterday, 09:30" or "12 Oct, 18:20".
String fmtWhen(DateTime when, {DateTime? now}) {
  final today = now ?? DateTime.now();
  final time = '${when.hour.toString().padLeft(2, '0')}:${when.minute.toString().padLeft(2, '0')}';
  final day = DateTime(when.year, when.month, when.day);
  final diff = DateTime(today.year, today.month, today.day).difference(day).inDays;
  if (diff == 0) return 'Today, $time';
  if (diff == 1) return 'Yesterday, $time';
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return '${when.day} ${months[when.month - 1]}, $time';
}

/// "120 DC; 70 AC" -> ["Rs. 120 per kWh (fast DC)", "Rs. 70 per kWh (AC)"].
/// Parts without a price ("verify current tariff") are dropped; the caller says prices need checking.
List<String> fmtListedPrices(String? raw) {
  if (raw == null || raw.trim().isEmpty) return const [];
  final prices = <String>[];
  for (final part in raw.split(';')) {
    final match = RegExp(r'^\s*(\d+(?:\.\d+)?)\s*(DC|AC)?', caseSensitive: false).firstMatch(part);
    if (match == null) continue;
    final kind = match.group(2)?.toUpperCase();
    final label = kind == 'DC' ? ' (fast DC)' : kind == 'AC' ? ' (AC)' : '';
    prices.add('Rs. ${match.group(1)} per kWh$label');
  }
  return prices;
}

/// Short connector names for chips.
String fmtPlug(String listed) {
  final lower = listed.toLowerCase();
  if (lower.contains('chademo')) return 'CHAdeMO';
  if (lower.contains('ccs')) return 'CCS2';
  if (lower.contains('type 2')) return 'Type 2';
  if (lower.contains('type 1') || lower.contains('j1772')) return 'Type 1';
  return listed;
}

String fmtPower(double? kw) {
  if (kw == null) return 'Power unknown';
  final speed = kw >= 20 ? 'Fast' : 'Standard';
  return '$speed · ${fmtNumber(kw)} kW';
}

/// '2026-10-22T14:35+05:30' -> '2:35 pm'. The API sends Sri Lanka local time.
String fmtClock(String? value) {
  if (value == null) return '—';
  final match = RegExp(r'T(\d{2}):(\d{2})').firstMatch(value);
  if (match == null) return value;
  final hour = int.parse(match.group(1)!);
  return '${hour % 12 == 0 ? 12 : hour % 12}:${match.group(2)} ${hour >= 12 ? 'pm' : 'am'}';
}
