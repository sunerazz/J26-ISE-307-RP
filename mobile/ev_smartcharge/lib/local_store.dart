import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'config.dart';
import 'models.dart';

class LocalStore {
  static const _profileKey = 'driver_profile';
  static const _tripsKey = 'saved_trips';
  static const maxTrips = 20;

  Future<DriverProfile> loadProfile() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_profileKey);
    if (raw == null) return DriverProfile();
    try {
      return DriverProfile.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    } catch (_) {
      return DriverProfile();
    }
  }

  Future<void> saveProfile(DriverProfile profile) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_profileKey, jsonEncode(profile.toJson()));
  }

  Future<List<SavedTrip>> loadTrips() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_tripsKey);
    if (raw == null) return [];
    try {
      final rows = jsonDecode(raw) as List;
      return rows
          .whereType<Map>()
          .map((row) => SavedTrip.fromJson(Map<String, dynamic>.from(row), placeNamed))
          .toList();
    } catch (_) {
      return [];
    }
  }

  Future<void> saveTrips(List<SavedTrip> trips) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tripsKey, jsonEncode(trips.take(maxTrips).map((trip) => trip.toJson()).toList()));
  }
}
