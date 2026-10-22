import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../app_state.dart';
import '../format.dart';
import '../models.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/route_map.dart';
import '../widgets/station_sheet.dart';

class StationsPage extends StatefulWidget {
  const StationsPage({super.key});

  @override
  State<StationsPage> createState() => _StationsPageState();
}

class _StationsPageState extends State<StationsPage> {
  bool _nearColombo = true;

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final near = state.stations.where((station) => station.nearColombo != false).toList();
    final stations = _nearColombo ? near : state.stations;
    final plug = state.profile.plug.toLowerCase();
    return Scaffold(
      appBar: AppBar(title: const Text('Chargers')),
      body: RefreshIndicator(
        onRefresh: state.refreshStations,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
          children: [
            if (stations.isEmpty && state.stationsLoading)
              const Padding(
                padding: EdgeInsets.only(top: 120),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (stations.isEmpty && state.stationError != null)
              EmptyState(
                icon: Icons.cloud_off_rounded,
                title: 'Couldn’t load chargers',
                message: state.stationError!,
                action: FilledButton(
                  style: FilledButton.styleFrom(minimumSize: const Size(160, 48)),
                  onPressed: state.refreshStations,
                  child: const Text('Try again'),
                ),
              )
            else ...[
              SegmentedButton<bool>(
                segments: [
                  ButtonSegment(value: true, label: Text('Near Colombo (${near.length})')),
                  ButtonSegment(value: false, label: Text('All Sri Lanka (${state.stations.length})')),
                ],
                selected: {_nearColombo},
                onSelectionChanged: (value) => setState(() => _nearColombo = value.first),
              ),
              const SizedBox(height: 12),
              if (stations.isNotEmpty)
                RouteMap(
                  height: 220,
                  pins: [
                    for (final station in stations)
                      MapPin(
                        point: LatLng(station.latitude, station.longitude),
                        label: (station.area.isEmpty ? station.city : station.area).split('/').first.trim(),
                        color: AppColors.brand,
                        icon: Icons.ev_station_rounded,
                      ),
                  ],
                ),
              const SizedBox(height: 16),
              for (final station in stations)
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: _StationCard(
                    station: station,
                    fitsCar: station.connectors.any((item) => item.toLowerCase().contains(plug)),
                  ),
                ),
              const SizedBox(height: 4),
              const Text(
                'Charger details come from public listings and may change. Check availability before you go.',
                style: TextStyle(color: AppColors.muted, fontSize: 12.5),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _StationCard extends StatelessWidget {
  const _StationCard({required this.station, required this.fitsCar});
  final StationListing station;
  final bool fitsCar;

  @override
  Widget build(BuildContext context) {
    final prices = fmtListedPrices(station.tariffRaw);
    return Panel(
      onTap: () => showStationSheet(context, StationInfo.fromListing(station)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const CircleAvatar(
                backgroundColor: AppColors.brandSoft,
                child: Icon(Icons.ev_station_rounded, color: AppColors.brand),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(station.name, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
                    const SizedBox(height: 2),
                    Text(station.area, style: const TextStyle(color: AppColors.muted)),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right_rounded, color: AppColors.muted),
            ],
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              fitsCar
                  ? const Tag('Fits your car', tone: Tone.good, icon: Icons.check_rounded)
                  : const Tag('Not your plug', tone: Tone.warn, icon: Icons.block_rounded),
              Tag(fmtPower(station.powerKw), tone: Tone.info, icon: Icons.bolt_rounded),
              for (final plug in station.connectors) Tag(fmtPlug(plug)),
              if (station.points != null && station.points! > 1) Tag('${station.points} points'),
            ],
          ),
          if (prices.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              'Listed price: ${prices.map((price) => price.replaceAll(' per kWh', '/kWh')).join(' · ')}',
              style: const TextStyle(color: AppColors.muted, fontSize: 13),
            ),
          ],
        ],
      ),
    );
  }
}
