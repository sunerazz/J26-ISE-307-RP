import 'dart:convert';
import 'dart:io';

import 'package:ev_smartcharge/api_client.dart';
import 'package:ev_smartcharge/app_state.dart';
import 'package:ev_smartcharge/cloud_store.dart';
import 'package:ev_smartcharge/format.dart';
import 'package:ev_smartcharge/main.dart';
import 'package:ev_smartcharge/models.dart';
import 'package:ev_smartcharge/screens/results_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

/// Keeps everything in memory; no Supabase or shared preferences.
class MemoryStore extends CloudStore {
  DriverProfile profile = DriverProfile();
  List<SavedTrip> saved = [];

  @override
  Future<void> prepare() async {}
  @override
  Future<DriverProfile> loadProfile() async => profile;
  @override
  Future<void> saveProfile(DriverProfile next) async => profile = next;
  @override
  Future<List<SavedTrip>> loadTrips() async => saved;
  @override
  Future<void> addTrip(SavedTrip trip, List<SavedTrip> all) async => saved = all;
  @override
  Future<void> clearTrips() async => saved = [];
}

String fixture(String name) => File('test/fixtures/$name').readAsStringSync();

ApiClient fakeApi({int recommendStatus = 200, List<Map<String, dynamic>>? sentBodies}) {
  return ApiClient(
    baseUrl: 'https://example.test',
    client: MockClient((request) async {
      if (request.url.path.endsWith('/colombo-stations')) {
        return http.Response(fixture('stations_response.json'), 200);
      }
      sentBodies?.add(jsonDecode(request.body) as Map<String, dynamic>);
      if (recommendStatus != 200) return http.Response('{"detail":"down"}', recommendStatus);
      return http.Response.bytes(utf8.encode(fixture('recommend_response.json')), 200);
    }),
  );
}

void main() {
  group('format', () {
    test('missing values show a dash, never zero', () {
      expect(fmtKm(null), '—');
      expect(fmtMinutes(null), '—');
      expect(fmtLkr(null), '—');
    });

    test('readable numbers', () {
      expect(fmtKm(3.24), '3.2 km');
      expect(fmtMinutes(51.4), '51 min');
      expect(fmtMinutes(95), '1 h 35 min');
      expect(fmtLkr(2399.4), 'Rs. 2,399');
      expect(fmtPower(30), 'Fast · 30 kW');
      expect(fmtPower(6.6), 'Standard · 6.6 kW');
    });

    test('listed prices are explained, unpriced notes are dropped', () {
      expect(fmtListedPrices('120 DC; 70 AC'), ['Rs. 120 per kWh (fast DC)', 'Rs. 70 per kWh (AC)']);
      expect(fmtListedPrices('80 listed; verify current tariff'), ['Rs. 80 per kWh']);
      expect(fmtListedPrices(null), isEmpty);
    });

    test('history dates read naturally', () {
      final now = DateTime(2026, 10, 21, 18);
      expect(fmtWhen(DateTime(2026, 10, 21, 9, 5), now: now), 'Today, 09:05');
      expect(fmtWhen(DateTime(2026, 10, 20, 22, 30), now: now), 'Yesterday, 22:30');
      expect(fmtWhen(DateTime(2026, 10, 3, 7, 0), now: now), '3 Oct, 07:00');
    });
  });

  group('server response', () {
    final result = TripResult(jsonDecode(fixture('recommend_response.json')) as Map<String, dynamic>);

    test('reads the recommended station and trip plan', () {
      final best = result.recommended!;
      expect(best.name, 'Vortex Energy / ChargeNET');
      expect(best.arrivalPercent, closeTo(37.8, 0.01));
      expect(best.chargeKwh, closeTo(25.34, 0.01));
      expect(best.reachesDestination, isTrue);
      expect(result.canFinishWithoutCharging, isTrue);
      expect(result.routeGeometry.length, greaterThan(2));
    });

    test('explains skipped chargers in plain words', () {
      final skipped = result.alternatives.firstWhere((station) => !station.included);
      expect(whyNot(skipped, 'CHAdeMO'), 'No CHAdeMO plug');
    });

    test('reasons only claim what the result supports', () {
      final reasons = whyThis(result, result.recommended!, 'CHAdeMO');
      expect(reasons, contains('It has a CHAdeMO plug for your car'));
      expect(reasons.any((reason) => reason.contains('38%')), isTrue);
      expect(reasons, isNot(contains('It’s the only charger that suits your car and battery for this trip')));
    });
  });

  group('profile', () {
    test('charging losses map to efficiency and back', () {
      final profile = DriverProfile(chargingLossPercent: 10);
      expect(profile.chargingEfficiency, closeTo(0.9, 1e-9));
      expect(DriverProfile.fromJson(profile.toJson()).chargingLossPercent, 10);
    });

    test('cloud copy only has columns that exist in the table', () {
      expect(DriverProfile().toCloudJson().keys, {'reserve_percent', 'scenario_tariff_lkr', 'charging_efficiency'});
    });
  });

  group('app', () {
    Future<AppState> pumpApp(WidgetTester tester, {ApiClient? api}) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 2.6;
      addTearDown(tester.view.reset);
      final state = AppState(api: api ?? fakeApi(), store: MemoryStore());
      await tester.runAsync(state.load);
      await tester.pumpWidget(SmartChargeApp(state: state));
      await tester.pump();
      return state;
    }

    testWidgets('no technical words on the main screens', (tester) async {
      await pumpApp(tester);
      const banned = ['CSV', 'SOC', 'synthetic', 'Supabase', 'scenario', 'API', 'ST00', 'listing'];
      for (final tab in ['Plan', 'Chargers', 'History', 'Settings']) {
        await tester.tap(find.text(tab).last);
        await tester.pump();
        final texts = tester
            .widgetList<Text>(find.byType(Text))
            .map((text) => text.data ?? text.textSpan?.toPlainText() ?? '')
            .join(' ');
        for (final word in banned) {
          expect(texts.contains(word), isFalse, reason: '"$word" is visible on the $tab tab');
        }
      }
    });

    testWidgets('swap updates both places', (tester) async {
      final state = await pumpApp(tester);
      expect(state.origin.name, 'Colombo 01');
      await tester.tap(find.byTooltip('Swap start and destination'));
      await tester.pump();
      expect(state.origin.name, 'Nugegoda');
      expect(find.text('Nugegoda'), findsOneWidget);
      expect(find.text('Colombo 01'), findsOneWidget);
    });

    testWidgets('search sends the saved car and shows the result', (tester) async {
      final sent = <Map<String, dynamic>>[];
      final state = await pumpApp(tester, api: fakeApi(sentBodies: sent));
      await tester.runAsync(state.search);
      expect(sent.single['required_connector'], 'CHAdeMO');
      expect(sent.single['usable_battery_capacity_kwh'], 39);
      expect(sent.single['target_soc_percent'], 80);
      expect(state.trips, hasLength(1));

      await tester.pumpWidget(MaterialApp(home: ResultsPage(result: state.latest!)).wrapWith(state));
      await tester.pump();
      expect(find.text('Your best charger'), findsOneWidget);
      expect(find.text('Vortex Energy / ChargeNET'), findsOneWidget);
      expect(find.text('You can make it without charging'), findsOneWidget);
      expect(find.text('Start navigation'), findsOneWidget);
    });

    testWidgets('server failure shows a friendly message', (tester) async {
      await pumpApp(tester, api: fakeApi(recommendStatus: 503));
      await tester.scrollUntilVisible(find.text('Find best charger'), 200);
      await tester.runAsync(() async {
        await tester.tap(find.text('Find best charger'));
        await Future<void>.delayed(const Duration(milliseconds: 50));
      });
      await tester.pump();
      expect(find.text('Couldn’t find chargers'), findsOneWidget);
      expect(find.textContaining('routing service is busy'), findsOneWidget);
    });

    testWidgets('battery below the reserve is caught before searching', (tester) async {
      final state = await pumpApp(tester);
      state.setBatteryNow(5);
      await tester.pump();
      await tester.scrollUntilVisible(find.text('Find best charger'), 200);
      await tester.tap(find.text('Find best charger'));
      await tester.pump();
      expect(find.textContaining('at or below your safety reserve'), findsOneWidget);
    });
  });
}

extension on Widget {
  Widget wrapWith(AppState state) => ChangeNotifierProvider<AppState>.value(value: state, child: this);
}
