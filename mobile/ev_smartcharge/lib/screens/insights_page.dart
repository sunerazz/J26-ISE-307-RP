import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../app_state.dart';

class InsightsPage extends StatelessWidget {
  const InsightsPage({super.key});

  @override
  Widget build(BuildContext context) {
    final base = context.watch<AppState>().apiBaseUrl;
    return Scaffold(
      appBar: AppBar(title: const Text('Insights')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('API: $base', style: const TextStyle(color: Color(0xFF6B7280))),
          const SizedBox(height: 12),
          const _Note(
            title: 'Queue, waiting time, congestion',
            body:
                'These three models forecast 30 minutes ahead for synthetic stations ST01–ST06. The Colombo listings ST001–ST004 do not have the observed queue and lag features those models need, so this app does not show a waiting time or congestion class for them.',
          ),
          const _Note(
            title: 'Charging duration',
            body:
                'The saved duration model was trained on a separate session table whose locations are US cities. It does not take a target SOC. When a target SOC is set, the charge-time tile uses listed kilowatts divided into the energy required. That is a calculation, not that model.',
          ),
          const _Note(
            title: 'Energy and cost',
            body:
                'The energy model was trained on 5,000 synthetic trips. It predicts kWh from the road leg plus elevation, temperature, air conditioning, traffic, road type, and vehicle mass. Ending state of charge is not an input, because that column is the same energy written another way. If you leave those trip conditions empty, the app keeps using the kWh per 100 km you entered. A rupee figure appears only when Profile has a scenario tariff, and that figure is not an official station price.',
          ),
          const _Note(
            title: 'Routes',
            body:
                'Road distance, time, and the map line come from OSRM using OpenStreetMap. They are not live traffic. A missing road shape is left missing.',
          ),
        ],
      ),
    );
  }
}

class _Note extends StatelessWidget {
  const _Note({required this.title, required this.body});
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
            const SizedBox(height: 6),
            Text(body),
          ],
        ),
      ),
    );
  }
}
