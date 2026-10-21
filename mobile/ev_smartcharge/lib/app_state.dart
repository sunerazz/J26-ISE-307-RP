import 'package:flutter/foundation.dart';

import 'api_client.dart';
import 'local_store.dart';
import 'models.dart';

class AppState extends ChangeNotifier {
  AppState({ApiClient? api, LocalStore? store})
      : _api = api ?? ApiClient(),
        _store = store ?? LocalStore();

  final ApiClient _api;
  final LocalStore _store;

  DriverProfile profile = DriverProfile();
  List<SavedTrip> trips = [];
  List<StationListing> stations = [];
  TripResult? latest;
  String? stationError;
  bool stationsLoading = false;

  String get apiBaseUrl => _api.baseUrl;

  Future<void> load() async {
    profile = await _store.loadProfile();
    trips = await _store.loadTrips();
    notifyListeners();
    await refreshStations();
  }

  Future<void> refreshStations() async {
    stationsLoading = true;
    stationError = null;
    notifyListeners();
    try {
      stations = await _api.stations();
    } catch (error) {
      stationError = error.toString();
    } finally {
      stationsLoading = false;
      notifyListeners();
    }
  }

  Future<TripResult> recommend(Map<String, dynamic> payload) async {
    final result = await _api.recommend(payload);
    latest = result;
    notifyListeners();
    return result;
  }

  Future<void> remember(SavedTrip trip) async {
    trips = [trip, ...trips].take(20).toList();
    await _store.saveTrips(trips);
    notifyListeners();
  }

  Future<void> updateProfile(DriverProfile next) async {
    profile = next;
    await _store.saveProfile(next);
    notifyListeners();
  }
}
