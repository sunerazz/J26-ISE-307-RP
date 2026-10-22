import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

import 'api_client.dart';
import 'cloud_store.dart';
import 'config.dart';
import 'format.dart';
import 'local_store.dart';
import 'models.dart';

class AppState extends ChangeNotifier {
  AppState({ApiClient? api, CloudStore? store})
      : _api = api ?? ApiClient(),
        _store = store ?? CloudStore();

  final ApiClient _api;
  final CloudStore _store;

  bool ready = false;

  /// Selected bottom tab. Kept here so pushed screens can switch tabs too.
  int tab = 0;

  void goToTab(int index) {
    tab = index;
    notifyListeners();
  }
  bool get syncedToCloud => _store.remote;

  DriverProfile profile = DriverProfile();
  List<SavedTrip> trips = [];

  List<StationListing> stations = [];
  String? stationError;
  bool stationsLoading = false;

  // The trip being planned. Kept here so it survives switching tabs.
  Place origin = places.first;
  Place destination = placeNamed('Nugegoda')!;
  double batteryNow = 40;

  /// null means "just enough to finish the trip".
  int? chargeTo = 80;

  bool searching = false;
  bool locating = false;
  TripResult? latest;

  Future<void> load() async {
    await _store.prepare();
    profile = await _store.loadProfile();
    trips = await _store.loadTrips();
    ready = true;
    notifyListeners();
    // Also wakes the server up before the first search.
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

  void setOrigin(Place place) {
    origin = place;
    notifyListeners();
  }

  void setDestination(Place place) {
    destination = place;
    notifyListeners();
  }

  void swapPlaces() {
    final previous = origin;
    origin = destination;
    destination = previous;
    notifyListeners();
  }

  void setBatteryNow(double value) {
    batteryNow = value;
    notifyListeners();
  }

  void setChargeTo(int? value) {
    chargeTo = value;
    notifyListeners();
  }

  /// Returns a message to show when the location cannot be used, or null on success.
  Future<String?> useCurrentLocation() async {
    locating = true;
    notifyListeners();
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        return 'Location is turned off on this phone. Turn it on, or pick an area from the list.';
      }
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) {
        return 'Location permission was not given. You can pick an area from the list instead.';
      }
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.high, timeLimit: Duration(seconds: 15)),
      );
      origin = Place('My location', position.latitude, position.longitude, isCurrentLocation: true);
      return null;
    } catch (_) {
      return 'Could not find your location. Try again outdoors, or pick an area from the list.';
    } finally {
      locating = false;
      notifyListeners();
    }
  }

  /// Checks the plan before calling the server. Returns a message, or null if it can be searched.
  String? validatePlan() {
    if (origin == destination) return 'Start and destination are the same place. Pick a different destination.';
    if (batteryNow <= profile.reservePercent) {
      return 'Your battery (${batteryNow.round()}%) is at or below your safety reserve '
          '(${profile.reservePercent.round()}%). Lower the reserve in Settings, or charge first.';
    }
    final target = chargeTo;
    if (target != null && target <= profile.reservePercent) {
      return 'Charge-to level must be above your ${profile.reservePercent.round()}% safety reserve.';
    }
    return null;
  }

  Future<TripResult> search() async {
    searching = true;
    notifyListeners();
    try {
      final result = await _api.recommend({
        'origin_latitude': origin.latitude,
        'origin_longitude': origin.longitude,
        'destination_latitude': destination.latitude,
        'destination_longitude': destination.longitude,
        'current_soc_percent': batteryNow.round(),
        'usable_battery_capacity_kwh': profile.batteryKwh,
        'consumption_kwh_per_100km': profile.consumption,
        'minimum_reserve_percent': profile.reservePercent,
        'required_connector': profile.plug,
        'target_soc_percent': chargeTo,
        'user_tariff_lkr_per_kwh': profile.tariffLkr,
        'charging_efficiency': profile.chargingEfficiency,
        'include_explanation': false,
      });
      latest = result;
      await _remember(result);
      return result;
    } finally {
      searching = false;
      notifyListeners();
    }
  }

  Future<void> _remember(TripResult result) async {
    final station = result.recommended;
    final summary = station == null
        ? 'No charger matched your car and battery'
        : [
            if (station.detourMin != null) '+${fmtMinutes(station.detourMin)} drive',
            if (station.arrivalPercent != null) 'arrive with ${fmtPercent(station.arrivalPercent)}',
          ].join(' · ');
    final trip = SavedTrip(
      when: DateTime.now(),
      origin: origin,
      destination: destination,
      stationName: station?.name,
      summary: summary,
    );
    trips = [trip, ...trips].take(LocalStore.maxTrips).toList();
    try {
      await _store.addTrip(trip, trips);
    } catch (_) {
      // History is a convenience; a failed cloud save must not hide the result.
    }
  }

  void replan(SavedTrip trip) {
    origin = trip.origin;
    destination = trip.destination;
    tab = 0;
    notifyListeners();
  }

  Future<void> clearHistory() async {
    trips = [];
    notifyListeners();
    await _store.clearTrips();
  }

  Future<void> updateProfile(DriverProfile next) async {
    profile = next;
    notifyListeners();
    await _store.saveProfile(next);
  }
}
