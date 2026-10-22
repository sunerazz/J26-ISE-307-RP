import 'package:supabase_flutter/supabase_flutter.dart';

import 'config.dart';
import 'local_store.dart';
import 'models.dart';

/// Keeps the profile and past trips on the phone, and also in Supabase when it can sign in.
/// Car details stay on the phone only, because the cloud table has no columns for them.
class CloudStore {
  CloudStore({LocalStore? local}) : _local = local ?? LocalStore();

  final LocalStore _local;
  bool remote = false;

  static bool _started = false;

  Future<void> prepare() async {
    if (!supabaseConfigured) return;
    try {
      if (!_started) {
        await Supabase.initialize(url: supabaseUrl, publishableKey: supabaseAnonKey);
        _started = true;
      }
      final auth = Supabase.instance.client.auth;
      if (auth.currentSession == null) {
        await auth.signInAnonymously();
      }
      remote = auth.currentUser != null;
    } catch (_) {
      remote = false;
    }
  }

  SupabaseClient get _db => Supabase.instance.client;
  String get _userId => _db.auth.currentUser!.id;

  Future<DriverProfile> loadProfile() async {
    final local = await _local.loadProfile();
    if (!remote) return local;
    try {
      final row = await _db.from('driver_profiles').select().eq('user_id', _userId).maybeSingle();
      return row == null ? local : local.withCloud(Map<String, dynamic>.from(row));
    } catch (_) {
      return local;
    }
  }

  Future<void> saveProfile(DriverProfile profile) async {
    await _local.saveProfile(profile);
    if (!remote) return;
    await _db.from('driver_profiles').upsert({'user_id': _userId, ...profile.toCloudJson()});
  }

  Future<List<SavedTrip>> loadTrips() async {
    if (!remote) return _local.loadTrips();
    try {
      final rows = await _db
          .from('saved_trips')
          .select()
          .eq('user_id', _userId)
          .order('created_at', ascending: false)
          .limit(LocalStore.maxTrips);
      final trips = rows.map((row) => SavedTrip.fromJson(Map<String, dynamic>.from(row), placeNamed)).toList();
      // The cloud table stores place names only, so take exact coordinates from the phone when it has them.
      final local = await _local.loadTrips();
      return [
        for (final trip in trips)
          local.firstWhere(
            (saved) =>
                saved.origin.name == trip.origin.name &&
                saved.destination.name == trip.destination.name &&
                saved.when.difference(trip.when).inSeconds.abs() < 5,
            orElse: () => trip,
          ),
      ];
    } catch (_) {
      return _local.loadTrips();
    }
  }

  /// Adds one trip. Existing rows are never deleted to make room, so a failed insert loses nothing.
  Future<void> addTrip(SavedTrip trip, List<SavedTrip> all) async {
    await _local.saveTrips(all);
    if (!remote) return;
    await _db.from('saved_trips').insert({
      'user_id': _userId,
      'created_at': trip.when.toUtc().toIso8601String(),
      'origin_name': trip.origin.name,
      'destination_name': trip.destination.name,
      'station_name': trip.stationName,
      'summary': trip.summary,
    });
  }

  Future<void> clearTrips() async {
    await _local.saveTrips(const []);
    if (!remote) return;
    await _db.from('saved_trips').delete().eq('user_id', _userId);
  }
}
