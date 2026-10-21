import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'models.dart';

class LocalStore {
  static const _profileKey = 'driver_profile';
  static const _routesKey = 'saved_trips';

  Future<DriverProfile> loadProfile() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_profileKey);
    if (raw == null) return DriverProfile();
    return DriverProfile.fromJson(jsonDecode(raw) as Map<String, dynamic>);
  }

  Future<void> saveProfile(DriverProfile profile) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_profileKey, jsonEncode(profile.toJson()));
  }

  Future<List<SavedTrip>> loadTrips() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_routesKey);
    if (raw == null) return [];
    final rows = jsonDecode(raw) as List;
    return rows.whereType<Map>().map((row) => SavedTrip.fromJson(Map<String, dynamic>.from(row))).toList();
  }

  Future<void> saveTrips(List<SavedTrip> trips) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_routesKey, jsonEncode(trips.map((trip) => trip.toJson()).toList()));
  }
}
