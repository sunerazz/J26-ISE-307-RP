import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../app_state.dart';

class RoutesPage extends StatelessWidget {
  const RoutesPage({super.key});

  @override
  Widget build(BuildContext context) {
    final trips = context.watch<AppState>().trips;
    return Scaffold(
      appBar: AppBar(title: const Text('My routes')),
      body: trips.isEmpty
          ? const Center(child: Text('Searches you run on this phone are saved here.'))
          : ListView.separated(
              padding: const EdgeInsets.all(16),
              itemCount: trips.length,
              separatorBuilder: (context, index) => const SizedBox(height: 8),
              itemBuilder: (context, index) {
                final trip = trips[index];
                return Card(
                  child: ListTile(
                    title: Text('${trip.originName} → ${trip.destinationName}'),
                    subtitle: Text(
                      '${trip.stationId == null ? 'No station recommended' : '${trip.stationId} · ${trip.stationName ?? ''}'}\n${trip.summary}',
                    ),
                    isThreeLine: true,
                  ),
                );
              },
            ),
    );
  }
}
