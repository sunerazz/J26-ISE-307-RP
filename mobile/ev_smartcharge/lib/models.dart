import 'services.dart';

/// A named point a trip can start or end at.
class Place {
  const Place(this.name, this.latitude, this.longitude, {this.isCurrentLocation = false});

  final String name;
  final double latitude;
  final double longitude;
  final bool isCurrentLocation;

  Map<String, dynamic> toJson() => {'name': name, 'latitude': latitude, 'longitude': longitude};

  static Place? fromJson(Object? raw) {
    if (raw is! Map || raw['latitude'] is! num || raw['longitude'] is! num) return null;
    return Place(
      raw['name']?.toString() ?? 'Saved place',
      (raw['latitude'] as num).toDouble(),
      (raw['longitude'] as num).toDouble(),
    );
  }

  @override
  bool operator ==(Object other) =>
      other is Place && other.name == name && other.latitude == latitude && other.longitude == longitude;

  @override
  int get hashCode => Object.hash(name, latitude, longitude);
}

class RouteLeg {
  RouteLeg({required this.distanceKm, required this.durationMin});

  final double distanceKm;
  final double durationMin;

  static RouteLeg? fromJson(Object? raw) {
    if (raw is! Map || raw['distance_km'] is! num || raw['duration_min'] is! num) return null;
    return RouteLeg(
      distanceKm: (raw['distance_km'] as num).toDouble(),
      durationMin: (raw['duration_min'] as num).toDouble(),
    );
  }
}

class StationListing {
  StationListing({
    required this.id,
    required this.name,
    required this.address,
    required this.area,
    required this.operator,
    required this.latitude,
    required this.longitude,
    required this.connectors,
    required this.powerKw,
    required this.tariffRaw,
    required this.sourceUrl,
    this.nearColombo,
    this.points,
    this.city = '',
  });

  final String id;
  final String name;
  final String address;
  final String area;
  final String operator;
  final double latitude;
  final double longitude;
  final List<String> connectors;
  final double? powerKw;
  final String? tariffRaw;
  final String? sourceUrl;
  final bool? nearColombo;
  final int? points;
  final String city;

  factory StationListing.fromJson(Map<String, dynamic> json) {
    return StationListing(
      id: json['station_id'] as String,
      name: json['station_name'] as String? ?? '',
      address: json['address'] as String? ?? '',
      area: json['area'] as String? ?? '',
      operator: json['operator'] as String? ?? '',
      latitude: (json['latitude'] as num).toDouble(),
      longitude: (json['longitude'] as num).toDouble(),
      connectors: ((json['connector_types_listed'] as List?) ?? const []).map((e) => e.toString()).toList(),
      powerKw: (json['max_power_kw_listed'] as num?)?.toDouble(),
      tariffRaw: json['tariff_raw'] as String?,
      sourceUrl: json['source_url'] as String?,
      nearColombo: json['in_greater_colombo'] as bool?,
      points: (json['number_of_points'] as num?)?.toInt(),
      city: json['city'] as String? ?? '',
    );
  }
}

/// One station in a recommendation response, read from the API's structured fields.
class RankedStation {
  RankedStation(this.json);
  final Map<String, dynamic> json;

  Map<String, dynamic> get _plan => Map<String, dynamic>.from((json['trip_plan'] as Map?) ?? const {});
  Map<String, dynamic> get _battery => Map<String, dynamic>.from((json['battery'] as Map?) ?? const {});

  String get id => json['station_id'] as String;
  String get name => json['station_name'] as String? ?? '';
  String get address => json['address'] as String? ?? '';
  String get area => json['area'] as String? ?? '';
  double get latitude => (json['latitude'] as num).toDouble();
  double get longitude => (json['longitude'] as num).toDouble();
  int? get rank => json['rank'] as int?;
  bool get included => json['included_in_ranking'] == true;
  bool? get connectorCompatible => json['connector_compatible'] as bool?;
  List<String> get connectors =>
      ((json['connector_types_listed'] as List?) ?? const []).map((e) => e.toString()).toList();
  /// Listed kW of the driver's plug at this station, falling back to the station maximum.
  double? get powerKw => ((json['charging_power_kw'] ?? json['max_power_kw_listed']) as num?)?.toDouble();
  String? get tariffRaw => json['tariff_raw'] as String?;
  String? get sourceUrl => json['source_url'] as String?;
  String? get exclusionReason => json['exclusion_reason'] as String?;
  RouteLeg? get toStation => RouteLeg.fromJson(json['origin_to_station']);
  RouteLeg? get onward => RouteLeg.fromJson(json['station_to_destination']);
  double? get detourKm => (json['detour_distance_km'] as num?)?.toDouble();
  double? get detourMin => (json['detour_duration_min'] as num?)?.toDouble();
  String get batteryStatus => _battery['status']?.toString() ?? 'unknown';
  double? get chargeMinutes => (json['listed_power_duration_min'] as num?)?.toDouble();
  double? get costLkr => (json['scenario_cost_lkr'] as num?)?.toDouble();

  Map<String, dynamic> get _queue => Map<String, dynamic>.from((json['queue_prediction'] as Map?) ?? const {});
  bool get hasQueueEstimate => _queue['status'] == 'area_model';

  Map<String, dynamic> get _timeline => Map<String, dynamic>.from((json['timeline'] as Map?) ?? const {});

  /// Clock time charging should finish: drive there, predicted wait, then the Component 2 session length.
  String? get chargingDoneAt => _timeline['charging_complete_time'] as String?;
  String? get destinationAt => _timeline['arrive_destination_time'] as String?;
  int? get queueVehicles => (_queue['predicted_queue_length'] as num?)?.round();
  double? get waitingMinutes => (_queue['predicted_waiting_time_min'] as num?)?.toDouble();
  String? get congestion => _queue['predicted_congestion_level'] as String?;
  String? get queueNote => _queue['reason'] as String?;
  String? get queueArea => _queue['trained_area'] as String?;
  double? get queueAreaKm => (_queue['distance_km'] as num?)?.toDouble();

  double? get arrivalPercent => (_plan['arrival_soc_percent'] as num?)?.toDouble();
  double? get minimumTargetPercent => (_plan['minimum_target_soc_percent'] as num?)?.toDouble();
  bool get fullChargeNotEnough => _plan['full_charge_insufficient'] == true;
  double? get chargeKwh => (_plan['charging_energy_kwh'] as num?)?.toDouble();
  double? get destinationPercent => (_plan['soc_at_destination_percent'] as num?)?.toDouble();
  bool? get reachesDestination => _plan['reaches_destination_with_reserve'] as bool?;

  /// Factor name -> score from 0 (worst) to 1 (best) among the stations that were compared.
  Map<String, double> get factorScores {
    final rows = (json['factor_contributions'] as List?) ?? const [];
    return {
      for (final row in rows.whereType<Map>())
        if (row['factor'] != null && row['factor_score'] is num)
          row['factor'].toString(): (row['factor_score'] as num).toDouble(),
    };
  }
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

  ChargingPlan? get plan {
    final raw = json['charging_plan'];
    return raw is Map ? ChargingPlan(Map<String, dynamic>.from(raw)) : null;
  }

  /// Plain-language comparison with simple station-choice rules.
  String? get strategySummary => (json['strategy_comparison'] as Map?)?['summary'] as String?;
  List<List<double>> get routeGeometry => _points((json['recommended_route'] as Map?)?['geometry']);

  /// Road line through every stop of a multi-stop charging plan.
  List<List<double>> get planGeometry => _points((json['plan_route'] as Map?)?['geometry']);

  /// The direct road from start to destination, used when no charger line exists.
  List<List<double>> get directGeometry => _points((json['direct_route'] as Map?)?['geometry']);

  /// The line to draw: the plan's stops when it needs several, else the best charger, else the direct road.
  List<List<double>> lineToDraw({required bool multiStop}) {
    if (multiStop && planGeometry.length >= 2) return planGeometry;
    if (routeGeometry.length >= 2) return routeGeometry;
    return directGeometry;
  }

  Map<String, dynamic> get _tripCheck => Map<String, dynamic>.from((json['trip_check'] as Map?) ?? const {});
  bool get canFinishWithoutCharging => _tripCheck['can_finish_without_charging'] == true;
  double? get destinationPercentWithoutCharging =>
      (_tripCheck['soc_at_destination_without_charging_percent'] as num?)?.toDouble();

  TripEnergy? get energy {
    final raw = json['trip_energy'];
    return raw is Map ? TripEnergy(Map<String, dynamic>.from(raw)) : null;
  }

  Map<String, dynamic> get _conditions => Map<String, dynamic>.from((json['trip_conditions'] as Map?) ?? const {});
  Weather? get weather => Weather.fromJson(_conditions['weather']);
  Map<String, dynamic> get _elevation => Map<String, dynamic>.from((_conditions['elevation'] as Map?) ?? const {});
  double? get climbMeters => (_elevation['elevation_gain_m'] as num?)?.toDouble();
  double? get descentMeters => (_elevation['elevation_loss_m'] as num?)?.toDouble();
  String? get trafficLevel => _conditions['traffic_level'] as String?;
  String? get roadType => _conditions['road_type'] as String?;
  String? get planArrivalTime => json['plan_arrival_time'] as String?;
}

/// Battery needed for the direct drive: the AI energy model next to the car's own consumption rate.
class TripEnergy {
  TripEnergy(this.json);
  final Map<String, dynamic> json;

  double? _num(String key) => (json[key] as num?)?.toDouble();
  double? get distanceKm => _num('distance_km');
  double? get durationMin => _num('duration_min');
  double? get modelKwh => _num('model_kwh');
  double? get rateKwh => _num('rate_kwh');
  double? get usedKwh => _num('used_kwh');
  double? get percentNeeded => _num('battery_percent_needed');
  double? get arrivalPercent => _num('arrival_soc_percent');
  double? get modelPer100km => _num('model_kwh_per_100km');
  double? get ratePer100km => _num('rate_kwh_per_100km');
  bool get modelApplied => json['model_applied'] == true;
  bool get usesModel => json['used_basis'] == 'Component 3 model';
  bool get canFinish => json['can_finish_without_charging'] == true;

  /// Inputs outside what the energy model was trained on, in plain words.
  List<String> get unusualInputs {
    const words = {
      'elevation_gain_m': 'hill climb',
      'elevation_loss_m': 'descent',
      'battery_capacity_kwh': 'battery size',
      'distance_km': 'trip length',
      'average_speed_kmh': 'speed',
      'vehicle_mass_kg': 'car weight',
      'ambient_temperature_c': 'temperature',
    };
    final raw = (json['out_of_training_range'] as List?) ?? const [];
    return [
      for (final item in raw.whereType<Map>())
        words[item['feature']] ?? item['feature'].toString(),
    ];
  }
}

/// The least-time charging plan from the route optimiser: zero, one or several stops.
class ChargingPlan {
  ChargingPlan(this.json);
  final Map<String, dynamic> json;

  String get status => json['status'] as String? ?? 'infeasible';
  String get explanation => json['explanation'] as String? ?? '';
  double? get arrivalPercent => (json['arrival_soc_at_destination_percent'] as num?)?.toDouble();
  double? get maxChargePercent => (json['max_charge_soc_percent'] as num?)?.toDouble();
  Map<String, dynamic> get _totals => Map<String, dynamic>.from((json['totals'] as Map?) ?? const {});
  double? get totalMinutes => (_totals['total_min'] as num?)?.toDouble();
  double? get chargingMinutes => (_totals['charging_min'] as num?)?.toDouble();
  double? get drivingMinutes => (_totals['drive_min'] as num?)?.toDouble();

  List<PlanStop> get stops {
    final raw = json['stops'];
    if (raw is! List) return const [];
    return raw.whereType<Map>().map((item) => PlanStop(Map<String, dynamic>.from(item))).toList();
  }
}

class PlanStop {
  PlanStop(this.json);
  final Map<String, dynamic> json;

  String get id => json['station_id'] as String;
  String get name => json['station_name'] as String? ?? '';
  String get area => json['area'] as String? ?? '';
  double get latitude => (json['latitude'] as num).toDouble();
  double get longitude => (json['longitude'] as num).toDouble();
  double? get arrivalPercent => (json['arrival_soc_percent'] as num?)?.toDouble();
  double? get departurePercent => (json['departure_soc_percent'] as num?)?.toDouble();
  double? get chargingMinutes => (json['charging_min'] as num?)?.toDouble();
  double? get powerKw => (json['charging_power_kw'] as num?)?.toDouble();
  double? get driveKm => (json['drive_km_from_previous'] as num?)?.toDouble();
  double? get driveMinutes => (json['drive_min_from_previous'] as num?)?.toDouble();
}

List<List<double>> _points(Object? raw) {
  if (raw is! List) return const [];
  final points = <List<double>>[];
  for (final item in raw) {
    if (item is List && item.length >= 2 && item[0] is num && item[1] is num) {
      points.add([(item[0] as num).toDouble(), (item[1] as num).toDouble()]);
    }
  }
  return points;
}

class SavedTrip {
  SavedTrip({
    required this.when,
    required this.origin,
    required this.destination,
    required this.stationName,
    required this.summary,
  });

  final DateTime when;
  final Place origin;
  final Place destination;
  final String? stationName;
  final String summary;

  Map<String, dynamic> toJson() => {
        'when': when.toIso8601String(),
        'origin': origin.toJson(),
        'destination': destination.toJson(),
        'origin_name': origin.name,
        'destination_name': destination.name,
        'station_name': stationName,
        'summary': summary,
      };

  /// Older saves (and cloud rows) only kept place names; they are matched back to the preset list.
  factory SavedTrip.fromJson(Map<String, dynamic> json, Place? Function(String name) lookup) {
    final originName = json['origin_name'] as String? ?? '';
    final destinationName = json['destination_name'] as String? ?? '';
    return SavedTrip(
      when: DateTime.tryParse(json['when'] as String? ?? json['created_at'] as String? ?? '')?.toLocal() ??
          DateTime.now(),
      origin: Place.fromJson(json['origin']) ?? lookup(originName) ?? Place(originName, 0, 0),
      destination: Place.fromJson(json['destination']) ?? lookup(destinationName) ?? Place(destinationName, 0, 0),
      stationName: json['station_name'] as String?,
      summary: json['summary'] as String? ?? '',
    );
  }

  bool get canReplan => origin.latitude != 0 && destination.latitude != 0;
}

class DriverProfile {
  DriverProfile({
    this.carName = 'Nissan Leaf (40 kWh)',
    this.batteryKwh = 39,
    this.consumption = 16,
    this.plug = 'CHAdeMO',
    this.reservePercent = 10,
    this.tariffLkr,
    this.chargingLossPercent,
  });

  String carName;
  double batteryKwh;
  double consumption;
  String plug;
  double reservePercent;
  double? tariffLkr;
  double? chargingLossPercent;

  /// The API takes efficiency (0-1); people think in "% lost while charging".
  double? get chargingEfficiency => chargingLossPercent == null ? null : 1 - chargingLossPercent! / 100;

  DriverProfile copyWith({
    String? carName,
    double? batteryKwh,
    double? consumption,
    String? plug,
    double? reservePercent,
    double? Function()? tariffLkr,
    double? Function()? chargingLossPercent,
  }) {
    return DriverProfile(
      carName: carName ?? this.carName,
      batteryKwh: batteryKwh ?? this.batteryKwh,
      consumption: consumption ?? this.consumption,
      plug: plug ?? this.plug,
      reservePercent: reservePercent ?? this.reservePercent,
      tariffLkr: tariffLkr != null ? tariffLkr() : this.tariffLkr,
      chargingLossPercent: chargingLossPercent != null ? chargingLossPercent() : this.chargingLossPercent,
    );
  }

  Map<String, dynamic> toJson() => {
        'car_name': carName,
        'battery_kwh': batteryKwh,
        'consumption_kwh_per_100km': consumption,
        'plug': plug,
        ...toCloudJson(),
      };

  /// Only the columns that exist in supabase/schema.sql.
  Map<String, dynamic> toCloudJson() => {
        'reserve_percent': reservePercent,
        'scenario_tariff_lkr': tariffLkr,
        'charging_efficiency': chargingEfficiency,
      };

  factory DriverProfile.fromJson(Map<String, dynamic> json) {
    final efficiency = (json['charging_efficiency'] as num?)?.toDouble();
    final base = DriverProfile();
    return DriverProfile(
      carName: json['car_name'] as String? ?? base.carName,
      batteryKwh: (json['battery_kwh'] as num?)?.toDouble() ?? base.batteryKwh,
      consumption: (json['consumption_kwh_per_100km'] as num?)?.toDouble() ?? base.consumption,
      plug: json['plug'] as String? ?? base.plug,
      reservePercent: (json['reserve_percent'] as num?)?.toDouble() ?? base.reservePercent,
      tariffLkr: (json['scenario_tariff_lkr'] as num?)?.toDouble(),
      chargingLossPercent: efficiency == null ? null : ((1 - efficiency) * 100).roundToDouble(),
    );
  }

  /// Applies the cloud columns on top of a locally saved profile.
  DriverProfile withCloud(Map<String, dynamic> row) {
    final cloud = DriverProfile.fromJson(row);
    return copyWith(
      reservePercent: cloud.reservePercent,
      tariffLkr: () => cloud.tariffLkr,
      chargingLossPercent: () => cloud.chargingLossPercent,
    );
  }
}
