class RouteLeg {
  RouteLeg({
    required this.distanceKm,
    required this.durationMin,
    required this.provider,
    required this.geometry,
  });

  final double distanceKm;
  final double durationMin;
  final String provider;
  final List<List<double>> geometry;

  static RouteLeg? fromJson(Object? raw) {
    if (raw is! Map) return null;
    return RouteLeg(
      distanceKm: (raw['distance_km'] as num).toDouble(),
      durationMin: (raw['duration_min'] as num).toDouble(),
      provider: raw['provider']?.toString() ?? '',
      geometry: _points(raw['geometry']),
    );
  }
}

class StationListing {
  StationListing({
    required this.id,
    required this.name,
    required this.address,
    required this.area,
    required this.latitude,
    required this.longitude,
    required this.connectors,
    required this.powerKw,
    required this.tariffRaw,
    required this.tariffStatus,
    required this.availability,
    required this.sourceUrl,
    required this.sourceNote,
  });

  final String id;
  final String name;
  final String address;
  final String area;
  final double latitude;
  final double longitude;
  final List<String> connectors;
  final double? powerKw;
  final String? tariffRaw;
  final String tariffStatus;
  final String availability;
  final String? sourceUrl;
  final String? sourceNote;

  factory StationListing.fromJson(Map<String, dynamic> json) {
    return StationListing(
      id: json['station_id'] as String,
      name: json['station_name'] as String? ?? '',
      address: json['address'] as String? ?? '',
      area: json['area'] as String? ?? '',
      latitude: (json['latitude'] as num).toDouble(),
      longitude: (json['longitude'] as num).toDouble(),
      connectors: ((json['connector_types_listed'] as List?) ?? const []).map((e) => e.toString()).toList(),
      powerKw: (json['max_power_kw_listed'] as num?)?.toDouble(),
      tariffRaw: json['tariff_raw'] as String?,
      tariffStatus: json['tariff_status'] as String? ?? 'missing',
      availability: json['availability_status'] as String? ?? 'unknown',
      sourceUrl: json['source_url'] as String?,
      sourceNote: json['source_note'] as String?,
    );
  }
}

class RankedStation {
  RankedStation(this.json);
  final Map<String, dynamic> json;

  String get id => json['station_id'] as String;
  String get name => json['station_name'] as String? ?? '';
  String get address => json['address'] as String? ?? '';
  String get area => json['area'] as String? ?? '';
  double get latitude => (json['latitude'] as num).toDouble();
  double get longitude => (json['longitude'] as num).toDouble();
  int? get rank => json['rank'] as int?;
  bool get included => json['included_in_ranking'] == true;
  String? get exclusion => json['exclusion_reason'] as String?;
  String get availability => json['availability_status'] as String? ?? 'unknown';
  List<String> get connectors =>
      ((json['connector_types_listed'] as List?) ?? const []).map((e) => e.toString()).toList();
  double? get powerKw => (json['max_power_kw_listed'] as num?)?.toDouble();
  String? get tariffRaw => json['tariff_raw'] as String?;
  String get tariffStatus => json['tariff_status'] as String? ?? 'missing';
  RouteLeg? get toStation => RouteLeg.fromJson(json['origin_to_station']);
  RouteLeg? get onward => RouteLeg.fromJson(json['station_to_destination']);
  double? get detourKm => (json['detour_distance_km'] as num?)?.toDouble();
  double? get detourMin => (json['detour_duration_min'] as num?)?.toDouble();
  String get batteryStatus => (json['battery'] as Map?)?['status']?.toString() ?? 'unknown';
  double? get energyToReachKwh => ((json['battery'] as Map?)?['estimated_energy_kwh'] as num?)?.toDouble();
  double? get chargeMinutes => (json['listed_power_duration_min'] as num?)?.toDouble();
  double? get scenarioCostLkr => (json['scenario_cost_lkr'] as num?)?.toDouble();
  String? get plainSummary => json['plain_summary'] as String?;
  String? get sourceUrl => json['source_url'] as String?;
  String? get sourceNote => json['source_note'] as String?;
  String get queueStatus => (json['queue_prediction'] as Map?)?['status']?.toString() ?? 'unavailable';
  String? get queueReason => (json['queue_prediction'] as Map?)?['reason'] as String?;
}

class TripResult {
  TripResult(this.json);
  final Map<String, dynamic> json;

  RankedStation? get recommended {
    final raw = json['recommended_station'];
    if (raw is! Map) return null;
    return RankedStation(Map<String, dynamic>.from(raw));
  }

  List<RankedStation> get alternatives {
    final raw = json['alternatives'];
    if (raw is! List) return const [];
    return raw.whereType<Map>().map((item) => RankedStation(Map<String, dynamic>.from(item))).toList();
  }

  List<RankedStation> get all {
    final lead = recommended;
    return [?lead, ...alternatives];
  }

  RouteLeg? get direct => RouteLeg.fromJson(json['direct_route']);
  List<List<double>> get recommendedGeometry => _points((json['recommended_route'] as Map?)?['geometry']);
  String? get recommendedRouteNote => (json['recommended_route'] as Map?)?['note'] as String?;
  List<String> get warnings => ((json['warnings'] as List?) ?? const []).map((e) => e.toString()).toList();
  List<String> get quickAnswer => ((json['quick_answer'] as List?) ?? const []).map((e) => e.toString()).toList();
  String? get explanation => (json['explanation'] as Map?)?['text'] as String?;
  bool get liveAvailability => json['live_availability'] == true;
  Map<String, dynamic>? get energyAndCost {
    final raw = json['energy_and_cost'];
    if (raw is! Map) return null;
    return Map<String, dynamic>.from(raw);
  }

  bool get energyModelApplied => energyAndCost?['energy_model_applied'] == true;
  String? get tripEnergyMethod => energyAndCost?['trip_energy_method'] as String?;
  String? get energyModelReason => energyAndCost?['energy_model_reason'] as String?;
}

List<List<double>> _points(Object? raw) {
  if (raw is! List) return const [];
  final points = <List<double>>[];
  for (final item in raw) {
    if (item is List && item.length >= 2) {
      points.add([(item[0] as num).toDouble(), (item[1] as num).toDouble()]);
    }
  }
  return points;
}

class SavedTrip {
  SavedTrip({
    required this.when,
    required this.originName,
    required this.destinationName,
    required this.stationId,
    required this.stationName,
    required this.summary,
  });

  final String when;
  final String originName;
  final String destinationName;
  final String? stationId;
  final String? stationName;
  final String summary;

  Map<String, dynamic> toJson() => {
        'when': when,
        'origin_name': originName,
        'destination_name': destinationName,
        'station_id': stationId,
        'station_name': stationName,
        'summary': summary,
      };

  factory SavedTrip.fromJson(Map<String, dynamic> json) {
    return SavedTrip(
      when: json['when'] as String? ?? '',
      originName: json['origin_name'] as String? ?? '',
      destinationName: json['destination_name'] as String? ?? '',
      stationId: json['station_id'] as String?,
      stationName: json['station_name'] as String?,
      summary: json['summary'] as String? ?? '',
    );
  }
}

class DriverProfile {
  DriverProfile({
    this.reservePercent = 10,
    this.scenarioTariffLkr,
    this.chargingEfficiency,
  });

  double reservePercent;
  double? scenarioTariffLkr;
  double? chargingEfficiency;

  Map<String, dynamic> toJson() => {
        'reserve_percent': reservePercent,
        'scenario_tariff_lkr': scenarioTariffLkr,
        'charging_efficiency': chargingEfficiency,
      };

  factory DriverProfile.fromJson(Map<String, dynamic> json) {
    return DriverProfile(
      reservePercent: (json['reserve_percent'] as num?)?.toDouble() ?? 10,
      scenarioTariffLkr: (json['scenario_tariff_lkr'] as num?)?.toDouble(),
      chargingEfficiency: (json['charging_efficiency'] as num?)?.toDouble(),
    );
  }
}
