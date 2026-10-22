import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../app_state.dart';
import '../config.dart';
import '../format.dart';
import '../models.dart';
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
        if (station.id == best?.id || (station.included && (station.rank ?? 99) <= 5) || planIds.contains(station.id)) station,
    ];
    return Scaffold(
      appBar: AppBar(title: Text(best == null ? 'No charger found' : 'Your best charger')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
        children: [
          RouteMap(
            height: 260,
            line: result.routeGeometry.map((pair) => LatLng(pair[0], pair[1])).toList(),
            pins: [
              MapPin(
                point: LatLng(state.origin.latitude, state.origin.longitude),
                label: 'Start',
                color: AppColors.good,
              ),
              MapPin(
                point: LatLng(state.destination.latitude, state.destination.longitude),
                label: state.destination.name,
                color: AppColors.bad,
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
                      ? AppColors.info
                      : station.id == best?.id
                      ? AppColors.brand
                      : station.included
                          ? const Color(0xFF475569)
                          : const Color(0xFF94A3B8),
                  icon: Icons.ev_station_rounded,
                  emphasis: station.id == best?.id,
                ),
            ],
          ),
          const SizedBox(height: 14),
          if (result.canFinishWithoutCharging) ...[
            Notice(
              tone: Tone.good,
              title: 'You can make it without charging',
              text: 'You’d reach ${state.destination.name} with about '
                  '${fmtPercent(result.destinationPercentWithoutCharging)} battery. Charging on the way is optional.',
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
                          const Icon(Icons.check_rounded, color: AppColors.good, size: 20),
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
      highlight: AppColors.info,
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
                    backgroundColor: AppColors.info,
                    child: Text(
                      '${stops.indexOf(stop) + 1}',
                      style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w800),
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
            'Charging times assume full listed power.',
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

class _BestCard extends StatelessWidget {
  const _BestCard({required this.result, required this.station, required this.plugLabel});
  final TripResult result;
  final RankedStation station;
  final String plugLabel;

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    final hasCost = state.profile.tariffLkr != null;
    return Panel(
      highlight: AppColors.brand,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Tag('Best match', tone: Tone.good, icon: Icons.star_rounded),
          const SizedBox(height: 10),
          Text(station.name, style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w800)),
          const SizedBox(height: 2),
          Text(station.area.isEmpty ? station.address : station.area, style: const TextStyle(color: AppColors.muted)),
          const SizedBox(height: 10),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              Tag(fmtPower(station.powerKw), tone: Tone.info, icon: Icons.bolt_rounded),
              Tag('$plugLabel plug', tone: Tone.good, icon: Icons.power_rounded),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Stat(
                icon: Icons.alt_route_rounded,
                value: (station.detourKm ?? 0) <= 0.05 ? 'On route' : '+${fmtMinutes(station.detourMin)}',
                label: (station.detourKm ?? 0) <= 0.05 ? 'no detour' : 'extra drive (${fmtKm(station.detourKm)})',
              ),
              const SizedBox(width: 8),
              Stat(
                icon: Icons.battery_3_bar_rounded,
                value: fmtPercent(station.arrivalPercent),
                label: 'battery when you arrive',
              ),
              const SizedBox(width: 8),
              _chargeStat(state),
              if (hasCost) ...[
                const SizedBox(width: 8),
                Stat(icon: Icons.payments_outlined, value: fmtLkr(station.costLkr), label: 'estimated cost'),
              ],
            ],
          ),
          if (station.chargeMinutes != null && (station.chargeKwh ?? 0) > 0)
            const Padding(
              padding: EdgeInsets.only(top: 8),
              child: Text(
                'Charging time assumes the charger runs at full power. It’s often a bit slower.',
                style: TextStyle(fontSize: 12, color: AppColors.muted),
              ),
            ),
          const SizedBox(height: 8),
          Row(
            children: [
              Stat(
                icon: Icons.groups_rounded,
                value: station.hasQueueEstimate ? '${station.queueVehicles}' : '—',
                label: 'queue in 30 min',
              ),
              const SizedBox(width: 8),
              Stat(
                icon: Icons.hourglass_bottom_rounded,
                value: station.hasQueueEstimate ? fmtMinutes(station.waitingMinutes) : '—',
                label: 'est. waiting',
              ),
              const SizedBox(width: 8),
              Stat(
                icon: Icons.traffic_rounded,
                value: station.hasQueueEstimate ? (station.congestion ?? '—') : '—',
                label: 'congestion',
              ),
            ],
          ),
          if (station.queueNote != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(station.queueNote!, style: const TextStyle(fontSize: 12, color: AppColors.muted)),
            ),
          if (station.chargingDoneAt != null)
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: Row(
                children: [
                  const Icon(Icons.schedule_rounded, size: 18, color: AppColors.brand),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      'Charging done by ${fmtClock(station.chargingDoneAt)}'
                      '${station.destinationAt != null ? ' · at destination ${fmtClock(station.destinationAt)}' : ''}',
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                  ),
                ],
              ),
            ),
          if (!hasCost)
            Padding(
              padding: const EdgeInsets.only(top: 4),
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
          FilledButton.icon(
            onPressed: () => openDirections(
              origin: state.origin.isCurrentLocation ? null : LatLng(state.origin.latitude, state.origin.longitude),
              via: LatLng(station.latitude, station.longitude),
              destination: LatLng(state.destination.latitude, state.destination.longitude),
            ),
            icon: const Icon(Icons.navigation_rounded),
            label: const Text('Start navigation'),
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

  Widget _chargeStat(AppState state) {
    final kwh = station.chargeKwh;
    if (station.fullChargeNotEnough) {
      return const Stat(icon: Icons.ev_station_rounded, value: '100%', label: 'may not be enough');
    }
    if (kwh == null) {
      return Stat(
        icon: Icons.ev_station_rounded,
        value: fmtPercent(station.minimumTargetPercent),
        label: 'charge to at least',
      );
    }
    if (kwh <= 0) {
      return Stat(icon: Icons.ev_station_rounded, value: 'Not needed', label: 'already at ${state.chargeTo}%');
    }
    return Stat(
      icon: Icons.ev_station_rounded,
      value: fmtMinutes(station.chargeMinutes),
      label: 'to charge to ${state.chargeTo}%',
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
            backgroundColor: station.included ? AppColors.brandSoft : const Color(0xFFF0F2F1),
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
