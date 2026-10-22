import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../app_state.dart';
import '../config.dart';
import '../format.dart';
import '../models.dart';
import '../services.dart';
import '../shell.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/route_map.dart';
import '../widgets/station_sheet.dart';

/// Short reason a station was not suggested, from the API's structured fields.
String whyNot(RankedStation station, String plugLabel) {
  if (station.connectorCompatible == false) return 'No $plugLabel plug';
  if (station.batteryStatus == 'infeasible') return 'Too far for your battery';
  final reason = station.exclusionReason?.toLowerCase() ?? '';
  if (reason.contains('detour')) return 'Too far off your route';
  if (reason.contains('road route')) return 'No road route found';
  if (reason.contains('unavailable') || reason.contains('operational')) return 'Listed as not working';
  if (station.batteryStatus == 'unknown') return 'Couldn’t check the distance';
  return 'Not suitable for this trip';
}

/// Plain reasons the top station was chosen. Only claims backed by the result are made.
List<String> whyThis(TripResult result, RankedStation station, String plugLabel) {
  final compared = result.all.where((item) => item.included).length;
  final scores = station.factorScores;
  return [
    if (compared == 1) 'It’s the only charger that suits your car and battery for this trip',
    if (station.connectorCompatible == true) 'It has a $plugLabel plug for your car',
    if (station.arrivalPercent != null)
      'You’ll get there with about ${fmtPercent(station.arrivalPercent)} battery left',
    if (compared > 1 && (scores['detour_time'] == 1 || scores['detour_distance'] == 1))
      'It adds the least extra driving of the chargers that fit',
    if (compared > 1 && scores['listed_power_duration'] == 1) 'It charges fastest of the options',
    if (compared > 1 && scores['scenario_cost'] == 1) 'It’s the cheapest charge of the options',
  ];
}

class ResultsPage extends StatelessWidget {
  const ResultsPage({super.key, required this.result});
  final TripResult result;

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final plugLabel = plugFor(state.profile.plug).label;
    final best = result.recommended;
    final plan = result.plan;
    final multiStop = plan != null && plan.status == 'planned' && plan.stops.length > 1;
    final planIds = {for (final stop in plan?.stops ?? const <PlanStop>[]) stop.id};
    // Only stations that passed the checks are listed; the rest are counted.
    final others = result.alternatives.where((station) => station.included).toList();
    final skipped = result.alternatives.length - others.length;
    final mapped = [
      for (final station in result.all)
        if (station.id == best?.id || (station.included && (station.rank ?? 99) <= 4) || planIds.contains(station.id)) station,
    ];
    return Scaffold(
      appBar: AppBar(title: Text(best == null ? 'No charger found' : 'Your best charger')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
        children: [
          RouteMap(
            height: 280,
            line: result.lineToDraw(multiStop: multiStop).map((pair) => LatLng(pair[0], pair[1])).toList(),
            pins: [
              MapPin(
                point: LatLng(state.origin.latitude, state.origin.longitude),
                label: 'Start',
                color: AppColors.brand,
                icon: Icons.trip_origin_rounded,
              ),
              MapPin(
                point: LatLng(state.destination.latitude, state.destination.longitude),
                label: 'Destination',
                color: AppColors.gold,
                icon: Icons.flag_rounded,
              ),
              for (final station in mapped)
                MapPin(
                  point: LatLng(station.latitude, station.longitude),
                  label: planIds.contains(station.id) && multiStop
                      ? 'Stop: ${_short(station.name)}'
                      : station.id == best?.id
                          ? 'Best: ${_short(station.name)}'
                          : _short(station.name),
                  color: planIds.contains(station.id) && multiStop
                      ? AppColors.cyan
                      : station.id == best?.id
                          ? AppColors.brand
                          : AppColors.muted,
                  icon: Icons.ev_station_rounded,
                  emphasis: station.id == best?.id,
                ),
            ],
          ),
          const SizedBox(height: 14),
          _TripOverview(result: result, state: state),
          const SizedBox(height: 12),
          if (result.canFinishWithoutCharging) ...[
            Notice(
              tone: Tone.good,
              title: 'You can make it without charging',
              text: 'You’d reach ${state.destination.name} with about '
                  '${fmtPercent(result.energy?.arrivalPercent ?? result.destinationPercentWithoutCharging)} battery. '
                  'Charging on the way is optional.',
            ),
            const SizedBox(height: 12),
          ],
          if (multiStop) ...[
            _PlanCard(plan: plan, destination: state.destination.name),
            const SizedBox(height: 12),
          ],
          if (best == null && !multiStop)
            _NoMatch(result: result, plugLabel: plugLabel)
          else if (best == null)
            const SizedBox.shrink()
          else ...[
            _BestCard(result: result, station: best, plugLabel: plugLabel),
            ..._tripWarnings(best, state),
            const SectionTitle('Why this charger'),
            Panel(
              child: Column(
                children: [
                  for (final reason in whyThis(result, best, plugLabel))
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 5),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(Icons.check_circle_rounded, color: AppColors.brand, size: 20),
                          const SizedBox(width: 10),
                          Expanded(child: Text(reason, style: const TextStyle(height: 1.35))),
                        ],
                      ),
                    ),
                ],
              ),
            ),
          ],
          if (others.isNotEmpty) ...[
            SectionTitle(best == null ? 'Chargers we checked' : 'Other chargers'),
            for (final station in others.take(8))
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _OptionTile(station: station, plugLabel: plugLabel),
              ),
          ],
          if (skipped > 0)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Text(
                '$skipped other chargers were left out: wrong plug, too far for your battery, or not listed as working.',
                style: const TextStyle(color: AppColors.muted, fontSize: 13),
              ),
            ),
          const SizedBox(height: 8),
          const Notice(
            tone: Tone.neutral,
            icon: Icons.info_outline_rounded,
            text: 'Charger availability isn’t shown live. Distances use real roads but not live traffic. '
                'Battery figures are estimates — keep a safety margin.',
          ),
        ],
      ),
    );
  }

  List<Widget> _tripWarnings(RankedStation station, AppState state) {
    final reserve = state.profile.reservePercent.round();
    if (station.fullChargeNotEnough) {
      return [
        const SizedBox(height: 12),
        Notice(
          tone: Tone.bad,
          title: 'A full charge may not be enough',
          text: 'Even at 100% you may not reach ${state.destination.name} with your $reserve% reserve. '
              'Plan a second charging stop.',
        ),
      ];
    }
    if (station.reachesDestination == false) {
      return [
        const SizedBox(height: 12),
        Notice(
          tone: Tone.warn,
          title: 'Charge a little more',
          text: 'Charging to ${state.chargeTo}% leaves about ${fmtPercent(station.destinationPercent)} when you arrive — '
              'below your $reserve% safety reserve. Charge to at least ${fmtPercent(station.minimumTargetPercent)}.',
        ),
      ];
    }
    return const [];
  }
}

/// Several stops: shown before the single best charger, because one stop is not enough.
class _PlanCard extends StatelessWidget {
  const _PlanCard({required this.plan, required this.destination});
  final ChargingPlan plan;
  final String destination;

  @override
  Widget build(BuildContext context) {
    final stops = plan.stops;
    return Panel(
      highlight: AppColors.cyan,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Tag('${stops.length} charging stops', tone: Tone.info, icon: Icons.route_rounded),
          const SizedBox(height: 10),
          Text(
            'One stop isn’t enough when charging to ${fmtPercent(plan.maxChargePercent)}. This plan takes about '
            '${fmtMinutes(plan.totalMinutes)} in total.',
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, height: 1.3),
          ),
          const SizedBox(height: 12),
          for (final stop in stops)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  CircleAvatar(
                    radius: 14,
                    backgroundColor: AppColors.cyan,
                    child: Text(
                      '${stops.indexOf(stop) + 1}',
                      style: const TextStyle(color: AppColors.background, fontSize: 13, fontWeight: FontWeight.w800),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(stop.name, style: const TextStyle(fontWeight: FontWeight.w700)),
                        Text(
                          '${stop.area} · after ${fmtKm(stop.driveKm)} · '
                          '${fmtPercent(stop.arrivalPercent)} → ${fmtPercent(stop.departurePercent)} · '
                          '${fmtMinutes(stop.chargingMinutes)} charging',
                          style: const TextStyle(color: AppColors.muted, fontSize: 13),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          Text(
            'Reach $destination with about ${fmtPercent(plan.arrivalPercent)}. '
            'Charging minutes are the Component 2 duration model, from battery size, charger power, and the charge levels.',
            style: const TextStyle(color: AppColors.muted, fontSize: 12.5),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: () {
              final state = context.read<AppState>();
              openDirections(
                origin: state.origin.isCurrentLocation ? null : LatLng(state.origin.latitude, state.origin.longitude),
                destination: LatLng(stops.first.latitude, stops.first.longitude),
              );
            },
            icon: const Icon(Icons.navigation_rounded),
            label: const Text('Navigate to the first stop'),
          ),
        ],
      ),
    );
  }
}

String _short(String name) {
  final cleaned = name.replaceAll(RegExp(r'^ChargeNET\s*-\s*', caseSensitive: false), '');
  return cleaned.length <= 18 ? cleaned : '${cleaned.substring(0, 17)}…';
}

String _traffic(String? level) => switch (level) {
      'high' => 'Heavy traffic',
      'low' => 'Light traffic',
      'medium' => 'Moderate traffic',
      _ => 'Traffic unknown',
    };

String _road(String? type) => switch (type) {
      'highway' => 'Highway',
      'urban' => 'City roads',
      'mixed' => 'Mixed roads',
      _ => 'Roads unknown',
    };

/// Distance, time, battery needed, energy use and the conditions they were estimated for.
class _TripOverview extends StatelessWidget {
  const _TripOverview({required this.result, required this.state});
  final TripResult result;
  final AppState state;

  @override
  Widget build(BuildContext context) {
    final energy = result.energy;
    final direct = result.direct;
    final weather = result.weather ?? state.weather;
    final km = energy?.distanceKm ?? direct?.distanceKm;
    final minutes = energy?.durationMin ?? direct?.durationMin;
    // Older servers do not send trip_energy; then use road distance × the car's consumption rate.
    final profile = state.profile;
    final rateKwh = km == null ? null : km * profile.consumption / 100;
    final needed = energy?.percentNeeded ?? (rateKwh == null ? null : rateKwh / profile.batteryKwh * 100);
    final usedKwh = energy?.usedKwh ?? rateKwh;
    final arrival = energy?.arrivalPercent ??
        result.destinationPercentWithoutCharging ??
        (needed == null ? null : state.batteryNow - needed);
    final arrivalColor = arrival == null
        ? AppColors.muted
        : arrival < state.profile.reservePercent
            ? AppColors.bad
            : arrival < 25
                ? AppColors.warn
                : AppColors.brand;
    final perKm = energy?.usesModel == true ? energy?.modelPer100km : (energy?.ratePer100km ?? profile.consumption);
    final unusual = energy?.unusualInputs ?? const <String>[];
    return Panel(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text('Your trip', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  '${fmtKm(km)} · ${fmtMinutes(minutes)}',
                  textAlign: TextAlign.right,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w800, color: AppColors.muted),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          MetricGrid(
            children: [
              MetricTile(
                icon: Icons.battery_charging_full_rounded,
                value: needed == null ? '—' : '${needed.round()}%',
                label: 'battery needed',
                caption: usedKwh == null ? null : '${fmtKwh(usedKwh)} for the drive',
                color: AppColors.cyan,
              ),
              MetricTile(
                icon: Icons.battery_5_bar_rounded,
                value: arrival != null && arrival < 0 ? 'Not enough' : fmtPercent(arrival),
                label: 'when you arrive',
                caption: arrival != null && arrival < 0
                    ? 'short by ${(-arrival).round()}% — charge on the way'
                    : 'without charging',
                color: arrivalColor,
              ),
              MetricTile(
                icon: Icons.speed_rounded,
                value: perKm == null ? '—' : perKm.toStringAsFixed(1),
                label: 'kWh per 100 km',
                caption: energy?.usesModel == true ? 'AI estimate for this route' : 'your car’s usual rate',
                color: AppColors.brand,
              ),
              MetricTile(
                icon: weather == null ? Icons.thermostat_rounded : _weatherIcon(weather),
                value: weather == null ? '—' : '${weather.temperatureC.round()}°C',
                label: weather?.text ?? 'weather unavailable',
                caption: weather?.humidity == null ? 'at your start' : '${weather!.humidity}% humidity at start',
                color: AppColors.gold,
              ),
            ],
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              if (result.climbMeters != null) Tag('↑ ${result.climbMeters!.round()} m climb', icon: Icons.terrain_rounded),
              if (result.descentMeters != null) Tag('↓ ${result.descentMeters!.round()} m descent'),
              if (result.trafficLevel != null) Tag(_traffic(result.trafficLevel), icon: Icons.traffic_rounded),
              if (result.roadType != null) Tag(_road(result.roadType), icon: Icons.add_road_rounded),
            ],
          ),
          if (energy != null) ...[
            const SizedBox(height: 12),
            _EnergyCompare(energy: energy),
          ],
          if (unusual.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: Text(
                'This trip’s ${unusual.join(', ')} ${unusual.length == 1 ? 'is' : 'are'} beyond what the AI energy model '
                'learned from, so we plan with whichever estimate is higher.',
                style: const TextStyle(color: AppColors.muted, fontSize: 12, height: 1.35),
              ),
            ),
        ],
      ),
    );
  }
}

IconData _weatherIcon(Weather weather) {
  final code = weather.code;
  if (code >= 95) return Icons.thunderstorm_rounded;
  if (code >= 51) return Icons.water_drop_rounded;
  if (code == 45 || code == 48) return Icons.foggy;
  if (code >= 2) return Icons.cloud_rounded;
  return weather.isDay ? Icons.wb_sunny_rounded : Icons.nightlight_round;
}

/// The AI energy model next to the car's own rate, as two bars. The larger one is used for safety.
class _EnergyCompare extends StatelessWidget {
  const _EnergyCompare({required this.energy});
  final TripEnergy energy;

  @override
  Widget build(BuildContext context) {
    final model = energy.modelKwh;
    final rate = energy.rateKwh;
    final top = [model ?? 0, rate ?? 0].reduce((a, b) => a > b ? a : b);
    Widget bar(String label, double? value, Color color, bool used) {
      final share = value == null || top <= 0 ? 0.0 : value / top;
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          children: [
            SizedBox(
              width: 112,
              child: Text(label, style: TextStyle(fontSize: 12.5, color: used ? AppColors.ink : AppColors.muted, fontWeight: FontWeight.w700)),
            ),
            Expanded(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: LinearProgressIndicator(
                  value: share,
                  minHeight: 8,
                  backgroundColor: AppColors.background,
                  color: used ? color : color.withValues(alpha: 0.45),
                ),
              ),
            ),
            const SizedBox(width: 10),
            SizedBox(
              width: 64,
              child: Text(
                value == null ? 'not run' : fmtKwh(value),
                textAlign: TextAlign.right,
                style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w800, color: used ? AppColors.ink : AppColors.muted),
              ),
            ),
          ],
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
      decoration: BoxDecoration(color: AppColors.surfaceHigh, borderRadius: BorderRadius.circular(14)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          bar('AI energy model', model, AppColors.cyan, energy.usesModel),
          bar('Your car’s rate', rate, AppColors.brand, !energy.usesModel),
          const SizedBox(height: 2),
          Text(
            model == null
                ? 'Live weather or road height was unavailable, so this uses your car’s usual rate.'
                : 'We plan with the higher of the two, so the battery check is never too optimistic.',
            style: const TextStyle(fontSize: 11.5, color: AppColors.muted),
          ),
        ],
      ),
    );
  }
}

class _BestCard extends StatelessWidget {
  const _BestCard({required this.result, required this.station, required this.plugLabel});
  final TripResult result;
  final RankedStation station;
  final String plugLabel;

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    final hasCost = state.profile.tariffLkr != null;
    final congestion = station.congestion;
    final congestionColor = switch (congestion) {
      'Low' => AppColors.good,
      'Medium' => AppColors.warn,
      'High' => AppColors.bad,
      _ => AppColors.muted,
    };
    return Panel(
      highlight: AppColors.brand,
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            alignment: WrapAlignment.spaceBetween,
            spacing: 8,
            runSpacing: 6,
            children: [
              const Tag('Best match', tone: Tone.good, icon: Icons.star_rounded),
              Tag(fmtPower(station.powerKw), tone: Tone.info, icon: Icons.bolt_rounded),
            ],
          ),
          const SizedBox(height: 12),
          Text(station.name, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800, letterSpacing: -0.4)),
          const SizedBox(height: 2),
          Text(
            [
              station.area.isEmpty ? station.address : station.area,
              (station.detourKm ?? 0) <= 0.05 ? 'on your route' : '+${fmtMinutes(station.detourMin)} detour',
            ].join(' · '),
            style: const TextStyle(color: AppColors.muted),
          ),
          if (station.chargingDoneAt != null) ...[
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(16),
                gradient: LinearGradient(colors: [AppColors.brand.withValues(alpha: 0.16), AppColors.cyan.withValues(alpha: 0.08)]),
                border: Border.all(color: AppColors.brand.withValues(alpha: 0.35)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.schedule_rounded, color: AppColors.brand),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Charging done by ${fmtClock(station.chargingDoneAt)}',
                          style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15.5),
                        ),
                        if (station.destinationAt != null)
                          Text(
                            'At your destination by ${fmtClock(station.destinationAt)}',
                            style: const TextStyle(color: AppColors.muted, fontSize: 12.5),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 12),
          MetricGrid(
            children: [
              MetricTile(
                icon: Icons.groups_rounded,
                value: station.hasQueueEstimate ? '${station.queueVehicles} cars' : '—',
                label: 'queue in 30 min',
                color: AppColors.cyan,
              ),
              MetricTile(
                icon: Icons.hourglass_bottom_rounded,
                value: station.hasQueueEstimate ? fmtMinutes(station.waitingMinutes) : '—',
                label: 'expected wait',
                color: AppColors.gold,
              ),
              MetricTile(
                icon: Icons.traffic_rounded,
                value: station.hasQueueEstimate ? (congestion ?? '—') : '—',
                label: 'how busy',
                color: congestionColor,
              ),
              _chargeTile(state),
              MetricTile(
                icon: Icons.battery_3_bar_rounded,
                value: fmtPercent(station.arrivalPercent),
                label: 'battery on arrival',
                color: AppColors.brand,
              ),
              MetricTile(
                icon: Icons.payments_outlined,
                value: hasCost ? fmtLkr(station.costLkr) : 'Add price',
                label: 'charging cost',
                color: AppColors.gold,
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            station.hasQueueEstimate
                ? 'Queue and wait are a 30-minute forecast for ${station.queueArea ?? 'the nearest town'}'
                    '${station.queueAreaKm != null ? ' (${station.queueAreaKm!.toStringAsFixed(1)} km away)' : ''}'
                    ' from a simulation-trained model — not a live count at this charger.'
                : 'No queue forecast: this charger is far from the towns the queue model covers.',
            style: const TextStyle(fontSize: 12, color: AppColors.muted, height: 1.35),
          ),
          if (station.chargeMinutes != null && (station.chargeKwh ?? 0) > 0)
            const Padding(
              padding: EdgeInsets.only(top: 4),
              child: Text(
                'Charging time is the Component 2 duration model, from your battery, this charger’s power, and the charge levels.',
                style: TextStyle(fontSize: 12, color: AppColors.muted),
              ),
            ),
          if (!hasCost)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: TextButton(
                style: TextButton.styleFrom(padding: EdgeInsets.zero),
                onPressed: () {
                  HomeShell.of(context).goTo(HomeShell.settingsTab);
                  Navigator.of(context).pop();
                },
                child: const Text('Add your electricity price to see the cost'),
              ),
            ),
          const SizedBox(height: 12),
          DecoratedBox(
            decoration: BoxDecoration(gradient: AppColors.accentGradient, borderRadius: BorderRadius.circular(18)),
            child: FilledButton.icon(
              style: FilledButton.styleFrom(backgroundColor: Colors.transparent, shadowColor: Colors.transparent),
              onPressed: () => openDirections(
                origin: state.origin.isCurrentLocation ? null : LatLng(state.origin.latitude, state.origin.longitude),
                via: LatLng(station.latitude, station.longitude),
                destination: LatLng(state.destination.latitude, state.destination.longitude),
              ),
              icon: const Icon(Icons.navigation_rounded),
              label: const Text('Start navigation'),
            ),
          ),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: () => showStationSheet(context, StationInfo.fromRanked(station)),
            icon: const Icon(Icons.info_outline_rounded),
            label: const Text('Charger details and price'),
          ),
        ],
      ),
    );
  }

  Widget _chargeTile(AppState state) {
    final kwh = station.chargeKwh;
    if (station.fullChargeNotEnough) {
      return const MetricTile(icon: Icons.ev_station_rounded, value: '100%', label: 'may not be enough', color: AppColors.bad);
    }
    if (kwh == null) {
      return MetricTile(
        icon: Icons.ev_station_rounded,
        value: fmtPercent(station.minimumTargetPercent),
        label: 'charge to at least',
      );
    }
    if (kwh <= 0) {
      return MetricTile(icon: Icons.ev_station_rounded, value: 'Not needed', label: 'already at ${state.chargeTo}%');
    }
    return MetricTile(
      icon: Icons.ev_station_rounded,
      value: fmtMinutes(station.chargeMinutes),
      label: 'duration model',
      caption: '+${fmtKwh(kwh)}',
    );
  }
}

class _OptionTile extends StatelessWidget {
  const _OptionTile({required this.station, required this.plugLabel});
  final RankedStation station;
  final String plugLabel;

  @override
  Widget build(BuildContext context) {
    final details = station.included
        ? [
            (station.detourKm ?? 0) <= 0.05 ? 'On your route' : '+${fmtMinutes(station.detourMin)} drive',
            if (station.arrivalPercent != null) 'arrive with ${fmtPercent(station.arrivalPercent)}',
            if (station.chargeMinutes != null && (station.chargeKwh ?? 0) > 0) '${fmtMinutes(station.chargeMinutes)} charging',
            if (station.hasQueueEstimate) 'wait ${fmtMinutes(station.waitingMinutes)} · ${station.congestion ?? 'congestion unknown'}',
          ].join(' · ')
        : null;
    return Panel(
      onTap: () => showStationSheet(context, StationInfo.fromRanked(station)),
      padding: const EdgeInsets.fromLTRB(16, 14, 12, 14),
      child: Row(
        children: [
          CircleAvatar(
            backgroundColor: station.included ? AppColors.brandSoft : AppColors.neutralSoft,
            child: Icon(
              Icons.ev_station_rounded,
              color: station.included ? AppColors.brand : AppColors.muted,
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(station.name, style: const TextStyle(fontWeight: FontWeight.w700)),
                const SizedBox(height: 4),
                if (details != null)
                  Text(details, style: const TextStyle(color: AppColors.muted, fontSize: 13))
                else
                  Tag(whyNot(station, plugLabel), tone: Tone.warn),
              ],
            ),
          ),
          const Icon(Icons.chevron_right_rounded, color: AppColors.muted),
        ],
      ),
    );
  }
}

class _NoMatch extends StatelessWidget {
  const _NoMatch({required this.result, required this.plugLabel});
  final TripResult result;
  final String plugLabel;

  @override
  Widget build(BuildContext context) {
    final reasons = result.all.map((station) => whyNot(station, plugLabel)).toSet();
    final tips = <String>[
      if (reasons.contains('No $plugLabel plug'))
        'None of these chargers list a $plugLabel plug. If your car takes another plug, change it in Settings.',
      if (reasons.contains('Too far for your battery'))
        'Your battery may be too low to reach a charger safely. Lowering the safety reserve in Settings shows more options — only if you’re comfortable with it.',
      if (reasons.contains('No road route found') || reasons.contains('Couldn’t check the distance'))
        'We couldn’t get road routes for some chargers. Try again in a moment.',
    ];
    return Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.search_off_rounded, color: AppColors.warn, size: 28),
              SizedBox(width: 10),
              Expanded(
                child: Text(
                  'No charger suits this trip',
                  style: TextStyle(fontSize: 19, fontWeight: FontWeight.w800),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          for (final tip in tips.isEmpty ? ['Try a different start point, battery level or plug type.'] : tips)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('•  ', style: TextStyle(fontWeight: FontWeight.w800)),
                  Expanded(child: Text(tip, style: const TextStyle(height: 1.4))),
                ],
              ),
            ),
          const SizedBox(height: 4),
          OutlinedButton.icon(
            onPressed: () {
              HomeShell.of(context).goTo(HomeShell.settingsTab);
              Navigator.of(context).pop();
            },
            icon: const Icon(Icons.tune_rounded),
            label: const Text('Open settings'),
          ),
        ],
      ),
    );
  }
}
