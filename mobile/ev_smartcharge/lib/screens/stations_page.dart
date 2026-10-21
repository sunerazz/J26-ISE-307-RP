import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../app_state.dart';
import '../models.dart';

class StationsPage extends StatelessWidget {
  const StationsPage({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return Scaffold(
      appBar: AppBar(title: const Text('Stations')),
      body: RefreshIndicator(
        onRefresh: state.refreshStations,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Text(
              'These four records are the Colombo demonstration inventory from the project CSV. Availability is unknown, and this is not a complete city registry.',
            ),
            const SizedBox(height: 12),
            if (state.stationsLoading) const LinearProgressIndicator(),
            if (state.stationError != null)
              Text(state.stationError!, style: const TextStyle(color: Color(0xFF9A3412))),
            ...state.stations.map((station) => _StationTile(station: station, match: _match(state.latest, station.id))),
          ],
        ),
      ),
    );
  }

  RankedStation? _match(TripResult? result, String id) {
    if (result == null) return null;
    for (final station in result.all) {
      if (station.id == id) return station;
    }
    return null;
  }
}

class _StationTile extends StatelessWidget {
  const _StationTile({required this.station, required this.match});
  final StationListing station;
  final RankedStation? match;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        title: Text('${station.id} · ${station.name}'),
        subtitle: Text(
          '${station.address}\n'
          'Connectors: ${station.connectors.join(', ')}\n'
          'Availability: ${station.availability}. Waiting time: Unavailable. Congestion: Unavailable.\n'
          'Tariff listing (not a bill): ${station.tariffRaw ?? 'missing'} (${station.tariffStatus}).\n'
          '${match == null ? 'Search from Home to see the road distance.' : 'Road distance from the last origin: ${match!.toStation?.distanceKm.toStringAsFixed(1) ?? 'unavailable'} km.'}',
        ),
        isThreeLine: true,
        trailing: station.sourceUrl == null
            ? null
            : IconButton(
                tooltip: 'Open source listing',
                icon: const Icon(Icons.open_in_new),
                onPressed: () => launchUrl(Uri.parse(station.sourceUrl!), mode: LaunchMode.externalApplication),
              ),
      ),
    );
  }
}
