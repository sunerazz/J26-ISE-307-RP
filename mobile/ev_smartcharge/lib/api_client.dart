import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'config.dart';
import 'models.dart';

/// An error with a message that can be shown to a driver as it is.
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

  Future<List<StationListing>> stations() async {
    final body = await _send(() => _client.get(Uri.parse('$_base/api/v1/colombo-stations')));
    final rows = (body['stations'] as List?) ?? const [];
    return rows.whereType<Map>().map((row) => StationListing.fromJson(Map<String, dynamic>.from(row))).toList();
  }

  Future<TripResult> recommend(Map<String, dynamic> payload) async {
    final body = await _send(
      () => _client.post(
        Uri.parse('$_base/api/v1/recommend'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(payload),
      ),
    );
    return TripResult(body);
  }

  Future<Map<String, dynamic>> _send(Future<http.Response> Function() call) async {
    final http.Response response;
    try {
      // The free server sleeps when idle; the first request can take close to a minute.
      response = await call().timeout(const Duration(seconds: 90));
    } on TimeoutException {
      throw ApiException('The server is taking too long to answer. It may be waking up — please try again in a minute.');
    } on SocketException {
      throw ApiException('No internet connection. Check your connection and try again.');
    } on http.ClientException {
      throw ApiException('Could not reach the server. Check your connection and try again.');
    }
    Object? body;
    try {
      body = response.body.isEmpty ? null : jsonDecode(response.body);
    } catch (_) {
      body = null;
    }
    final code = response.statusCode;
    if (code == 422) {
      throw ApiException('Some trip details look wrong. Check your battery and car settings and try again.');
    }
    if (code == 503) {
      throw ApiException('The road-routing service is busy right now. Please try again in a moment.');
    }
    if (code >= 500) {
      throw ApiException('Something went wrong on the server. Please try again shortly.');
    }
    if (code >= 400) {
      throw ApiException('The request could not be completed (error $code).');
    }
    if (body is! Map) {
      throw ApiException('The server sent an unexpected answer. Please try again.');
    }
    return Map<String, dynamic>.from(body);
  }
}
