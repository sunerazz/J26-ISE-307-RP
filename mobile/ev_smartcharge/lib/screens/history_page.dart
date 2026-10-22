import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../app_state.dart';
import '../format.dart';
import '../models.dart';
import '../shell.dart';
import '../theme.dart';
import '../widgets/common.dart';

class HistoryPage extends StatelessWidget {
  const HistoryPage({super.key});

  Future<void> _confirmClear(BuildContext context) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Clear history?'),
        content: const Text('All your past trips will be removed.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Cancel')),
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Clear', style: TextStyle(color: AppColors.bad)),
          ),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    try {
      await context.read<AppState>().clearHistory();
    } catch (_) {
      if (context.mounted) showMessage(context, 'History was cleared on this phone but not in your account. Try again later.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final trips = state.trips;
    return Scaffold(
      appBar: AppBar(
        title: const Text('History'),
        actions: [
          if (trips.isNotEmpty)
            TextButton(onPressed: () => _confirmClear(context), child: const Text('Clear')),
        ],
      ),
      body: trips.isEmpty
          ? EmptyState(
              icon: Icons.route_rounded,
              title: 'No trips yet',
              message: 'Trips you plan will show up here, so you can repeat them with one tap.',
              action: FilledButton(
                style: FilledButton.styleFrom(minimumSize: const Size(180, 48)),
                onPressed: () => HomeShell.of(context).goTo(HomeShell.planTab),
                child: const Text('Plan a trip'),
              ),
            )
          : ListView.separated(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
              itemCount: trips.length,
              separatorBuilder: (context, index) => const SizedBox(height: 10),
              itemBuilder: (context, index) => _TripTile(trip: trips[index]),
            ),
    );
  }
}

class _TripTile extends StatelessWidget {
  const _TripTile({required this.trip});
  final SavedTrip trip;

  @override
  Widget build(BuildContext context) {
    return Panel(
      onTap: trip.canReplan
          ? () {
              context.read<AppState>().replan(trip);
              showMessage(context, 'Trip loaded. Set your battery and tap Find best charger.');
            }
          : null,
      child: Row(
        children: [
          const CircleAvatar(
            backgroundColor: AppColors.brandSoft,
            child: Icon(Icons.route_rounded, color: AppColors.brand),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${trip.origin.name} → ${trip.destination.name}',
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 3),
                Text(
                  trip.stationName == null ? trip.summary : '${trip.stationName}\n${trip.summary}',
                  style: const TextStyle(color: AppColors.muted, fontSize: 13, height: 1.35),
                ),
                const SizedBox(height: 4),
                Text(fmtWhen(trip.when), style: const TextStyle(color: AppColors.muted, fontSize: 12)),
              ],
            ),
          ),
          if (trip.canReplan)
            const Tooltip(message: 'Plan again', child: Icon(Icons.replay_rounded, color: AppColors.brand)),
        ],
      ),
    );
  }
}
