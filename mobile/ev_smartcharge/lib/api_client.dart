import 'dart:convert';

import 'package:http/http.dart' as http;

import 'config.dart';
import 'models.dart';

class ApiException implements Exception {
  ApiException(this.message);
  final String message;
  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _base = (baseUrl ?? apiBaseUrl).replaceAll(RegExp(r'/+$'), '');

  final http.Client _client;
  final String _base;

  String get baseUrl => _base;

  Future<List<StationListing>> stations() async {
    final body = await _get('/api/v1/colombo-stations');
    final rows = (body['stations'] as List?) ?? const [];
    return rows.whereType<Map>().map((row) => StationListing.fromJson(Map<String, dynamic>.from(row))).toList();
  }

  Future<TripResult> recommend(Map<String, dynamic> payload) async {
    final body = await _post('/api/v1/recommend', payload);
    return TripResult(body);
  }

  Future<Map<String, dynamic>> _get(String path) async {
    final response = await _client.get(Uri.parse('$_base$path')).timeout(const Duration(seconds: 30));
    return _decode(response);
  }

  Future<Map<String, dynamic>> _post(String path, Map<String, dynamic> payload) async {
    final response = await _client
        .post(
          Uri.parse('$_base$path'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(payload),
        )
        .timeout(const Duration(seconds: 90));
    return _decode(response);
  }

  Map<String, dynamic> _decode(http.Response response) {
    Object? body;
    try {
      body = response.body.isEmpty ? null : jsonDecode(response.body);
    } catch (_) {
      body = response.body;
    }
    if (response.statusCode >= 400) {
      final detail = body is Map && body['detail'] != null ? body['detail'].toString() : response.body;
      throw ApiException('The server returned ${response.statusCode}. $detail');
    }
    if (body is! Map) {
      throw ApiException('The server response was not a JSON object.');
    }
    return Map<String, dynamic>.from(body);
  }
}
