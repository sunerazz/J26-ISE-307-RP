import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models.dart';

/// Weather right now at a point, from Open-Meteo (free, no key).
class Weather {
  const Weather({required this.temperatureC, required this.text, required this.code, required this.isDay, this.humidity});

  final double temperatureC;
  final String text;
  final int code;
  final bool isDay;
  final int? humidity;

  static Weather? fromJson(Object? raw) {
    if (raw is! Map || raw['temperature_c'] is! num) return null;
    return Weather(
      temperatureC: (raw['temperature_c'] as num).toDouble(),
      text: raw['weather_text']?.toString() ?? '',
      code: (raw['weather_code'] as num?)?.toInt() ?? -1,
      isDay: raw['is_day'] != false,
      humidity: (raw['humidity_percent'] as num?)?.toInt(),
    );
  }
}

const _weatherText = {
  0: 'Clear sky',
  1: 'Mainly clear',
  2: 'Partly cloudy',
  3: 'Overcast',
  45: 'Fog',
  48: 'Fog',
  51: 'Light drizzle',
  53: 'Drizzle',
  55: 'Heavy drizzle',
  61: 'Light rain',
  63: 'Rain',
  65: 'Heavy rain',
  80: 'Rain showers',
  81: 'Rain showers',
  82: 'Heavy showers',
  95: 'Thunderstorm',
  96: 'Thunderstorm',
  99: 'Thunderstorm',
};

class PlaceServices {
  PlaceServices({http.Client? client}) : _client = client ?? http.Client();
  final http.Client _client;

  static const _headers = {'User-Agent': 'ev-smartcharge/1.0 (research app)'};

  Future<Weather?> weather(double latitude, double longitude) async {
    final uri = Uri.https('api.open-meteo.com', '/v1/forecast', {
      'latitude': latitude.toStringAsFixed(4),
      'longitude': longitude.toStringAsFixed(4),
      'current': 'temperature_2m,relative_humidity_2m,weather_code,is_day',
      'timezone': 'Asia/Colombo',
    });
    try {
      final response = await _client.get(uri, headers: _headers).timeout(const Duration(seconds: 8));
      if (response.statusCode != 200) return null;
      final current = (jsonDecode(response.body) as Map)['current'] as Map?;
      if (current == null || current['temperature_2m'] is! num) return null;
      final code = (current['weather_code'] as num?)?.toInt() ?? -1;
      return Weather(
        temperatureC: (current['temperature_2m'] as num).toDouble(),
        text: _weatherText[code] ?? 'Weather',
        code: code,
        isDay: current['is_day'] != 0,
        humidity: (current['relative_humidity_2m'] as num?)?.toInt(),
      );
    } catch (_) {
      return null;
    }
  }

  /// Places in Sri Lanka matching [query], nearest to [near] first. Photon geocoder (OpenStreetMap data).
  Future<List<Place>> search(String query, {double? nearLatitude, double? nearLongitude}) async {
    if (query.trim().length < 2) return const [];
    final uri = Uri.https('photon.komoot.io', '/api/', {
      'q': query.trim(),
      'limit': '8',
      'bbox': '79.4,5.8,82.0,9.9',
      if (nearLatitude != null) 'lat': nearLatitude.toStringAsFixed(4),
      if (nearLongitude != null) 'lon': nearLongitude.toStringAsFixed(4),
    });
    try {
      final response = await _client.get(uri, headers: _headers).timeout(const Duration(seconds: 8));
      if (response.statusCode != 200) return const [];
      final features = ((jsonDecode(utf8.decode(response.bodyBytes)) as Map)['features'] as List?) ?? const [];
      final places = <Place>[];
      final seen = <String>{};
      for (final feature in features.whereType<Map>()) {
        final props = (feature['properties'] as Map?) ?? const {};
        final coords = ((feature['geometry'] as Map?)?['coordinates'] as List?) ?? const [];
        if (coords.length < 2 || props['countrycode'] != 'LK') continue;
        final name = props['name']?.toString() ?? '';
        if (name.isEmpty) continue;
        final area = [props['city'], props['county'], props['state']]
            .whereType<String>()
            .where((part) => part != name)
            .take(2)
            .join(', ');
        final label = area.isEmpty ? name : '$name, $area';
        if (!seen.add(label)) continue;
        places.add(Place(label, (coords[1] as num).toDouble(), (coords[0] as num).toDouble()));
      }
      return places;
    } catch (_) {
      return const [];
    }
  }
}
