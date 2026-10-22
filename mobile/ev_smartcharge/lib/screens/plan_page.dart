import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../app_state.dart';
import '../config.dart';
import '../models.dart';
import '../shell.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'results_page.dart';

class PlanPage extends StatelessWidget {
  const PlanPage({super.key});

  Future<void> _find(BuildContext context) async {
    final state = context.read<AppState>();
    final problem = state.validatePlan();
    if (problem != null) {
      showMessage(context, problem);
      return;
    }
    try {
      final result = await state.search();
      if (!context.mounted) return;
      await Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => ResultsPage(result: result)));
    } catch (error) {
      if (!context.mounted) return;
      showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          icon: const Icon(Icons.cloud_off_rounded),
          title: const Text('Couldn’t find chargers'),
          content: Text(error.toString()),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Close')),
            FilledButton(
              style: FilledButton.styleFrom(minimumSize: const Size(0, 44)),
              onPressed: () {
                Navigator.pop(dialogContext);
                _find(context);
              },
              child: const Text('Try again'),
            ),
          ],
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
          children: [
            const _Greeting(),
            const SizedBox(height: 16),
            _RouteCard(state: state),
            const SectionTitle('Battery'),
            _BatteryCard(state: state),
            const SectionTitle('How much do you want to charge?'),
            _ChargeChoice(state: state),
            const SizedBox(height: 16),
            _CarSummary(profile: state.profile),
            const SizedBox(height: 20),
            FilledButton.icon(
              onPressed: state.searching ? null : () => _find(context),
              icon: state.searching
                  ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2.5))
                  : const Icon(Icons.bolt_rounded),
              label: Text(state.searching ? 'Finding the best charger…' : 'Find best charger'),
            ),
            if (state.searching)
              const Padding(
                padding: EdgeInsets.only(top: 10),
                child: Text(
                  'Checking real road routes. The first search of the day can take up to a minute.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: AppColors.muted, fontSize: 13),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _Greeting extends StatelessWidget {
  const _Greeting();

  @override
  Widget build(BuildContext context) {
    final hour = DateTime.now().hour;
    final hello = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(hello, style: const TextStyle(color: AppColors.muted, fontSize: 15)),
              const SizedBox(height: 2),
              const Text('Where are you driving?', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800)),
            ],
          ),
        ),
        const CircleAvatar(
          radius: 24,
          backgroundColor: AppColors.brandSoft,
          child: Icon(Icons.electric_car_rounded, color: AppColors.brand),
        ),
      ],
    );
  }
}

class _RouteCard extends StatelessWidget {
  const _RouteCard({required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    return Panel(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Stack(
        alignment: Alignment.centerRight,
        children: [
          Column(
            children: [
              _PlaceRow(
                icon: Icons.trip_origin_rounded,
                color: AppColors.good,
                label: 'From',
                place: state.origin,
                busy: state.locating,
                onTap: () => _pick(context, origin: true),
              ),
              const Divider(height: 1, indent: 56, endIndent: 64),
              _PlaceRow(
                icon: Icons.location_on_rounded,
                color: AppColors.bad,
                label: 'To',
                place: state.destination,
                onTap: () => _pick(context, origin: false),
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: IconButton.filledTonal(
              tooltip: 'Swap start and destination',
              onPressed: state.swapPlaces,
              icon: const Icon(Icons.swap_vert_rounded),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _pick(BuildContext context, {required bool origin}) async {
    final picked = await showModalBottomSheet<Object>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => _PlaceSheet(title: origin ? 'Start from' : 'Going to', allowCurrentLocation: origin),
    );
    if (!context.mounted || picked == null) return;
    final state = context.read<AppState>();
    if (picked == _PlaceSheet.currentLocation) {
      final problem = await state.useCurrentLocation();
      if (problem != null && context.mounted) showMessage(context, problem);
    } else if (picked is Place) {
      origin ? state.setOrigin(picked) : state.setDestination(picked);
    }
  }
}

class _PlaceRow extends StatelessWidget {
  const _PlaceRow({
    required this.icon,
    required this.color,
    required this.label,
    required this.place,
    required this.onTap,
    this.busy = false,
  });

  final IconData icon;
  final Color color;
  final String label;
  final Place place;
  final VoidCallback onTap;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 72, 12),
        child: Row(
          children: [
            Icon(icon, color: color),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label, style: const TextStyle(fontSize: 12, color: AppColors.muted)),
                  const SizedBox(height: 2),
                  busy
                      ? const Text('Finding your location…', style: TextStyle(fontSize: 16, color: AppColors.muted))
                      : Text(
                          place.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                        ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PlaceSheet extends StatefulWidget {
  const _PlaceSheet({required this.title, required this.allowCurrentLocation});
  final String title;
  final bool allowCurrentLocation;

  static const currentLocation = 'current-location';

  @override
  State<_PlaceSheet> createState() => _PlaceSheetState();
}

class _PlaceSheetState extends State<_PlaceSheet> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final matches = places.where((place) => place.name.toLowerCase().contains(_query.toLowerCase())).toList();
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: SizedBox(
        height: MediaQuery.sizeOf(context).height * 0.75,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 12),
              child: Text(widget.title, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: TextField(
                autofocus: false,
                decoration: const InputDecoration(prefixIcon: Icon(Icons.search_rounded), hintText: 'Search an area'),
                onChanged: (value) => setState(() => _query = value.trim()),
              ),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: ListView(
                children: [
                  if (widget.allowCurrentLocation && _query.isEmpty)
                    ListTile(
                      leading: const CircleAvatar(
                        backgroundColor: AppColors.infoSoft,
                        child: Icon(Icons.my_location_rounded, color: AppColors.info),
                      ),
                      title: const Text('Use my current location', style: TextStyle(fontWeight: FontWeight.w700)),
                      onTap: () => Navigator.pop(context, _PlaceSheet.currentLocation),
                    ),
                  for (final place in matches)
                    ListTile(
                      leading: const CircleAvatar(
                        backgroundColor: AppColors.background,
                        child: Icon(Icons.place_outlined, color: AppColors.muted),
                      ),
                      title: Text(place.name),
                      subtitle: const Text('Colombo area'),
                      onTap: () => Navigator.pop(context, place),
                    ),
                  if (matches.isEmpty)
                    const Padding(
                      padding: EdgeInsets.all(24),
                      child: Text('No area with that name yet.', style: TextStyle(color: AppColors.muted)),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BatteryCard extends StatelessWidget {
  const _BatteryCard({required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    final level = state.batteryNow;
    final profile = state.profile;
    final color = level <= 20 ? AppColors.bad : level <= 40 ? AppColors.warn : AppColors.good;
    final usableKm = (level - profile.reservePercent) / 100 * profile.batteryKwh / profile.consumption * 100;
    return Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.battery_charging_full_rounded, color: color, size: 28),
              const SizedBox(width: 8),
              const Text('Battery now', style: TextStyle(fontSize: 15, color: AppColors.muted)),
              const Spacer(),
              Text('${level.round()}%', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800, color: color)),
            ],
          ),
          SliderTheme(
            data: SliderTheme.of(context).copyWith(activeTrackColor: color, thumbColor: color, trackHeight: 8),
            child: Slider(
              value: level,
              min: 1,
              max: 100,
              divisions: 99,
              label: '${level.round()}%',
              onChanged: state.setBatteryNow,
            ),
          ),
          Text(
            usableKm > 0
                ? 'About ${usableKm.round()} km of driving before your ${profile.reservePercent.round()}% safety reserve.'
                : 'You are already at your ${profile.reservePercent.round()}% safety reserve.',
            style: const TextStyle(color: AppColors.muted, fontSize: 13),
          ),
        ],
      ),
    );
  }
}

class _ChargeChoice extends StatelessWidget {
  const _ChargeChoice({required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    const options = <int?>[null, 80, 90, 100];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final option in options)
              ChoiceChip(
                label: Text(option == null ? 'Just enough' : 'Up to $option%'),
                selected: state.chargeTo == option,
                onSelected: (_) => state.setChargeTo(option),
                selectedColor: AppColors.brandSoft,
              ),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          state.chargeTo == null
              ? 'We’ll tell you the smallest charge that gets you there safely.'
              : 'We’ll estimate charging time${state.profile.tariffLkr != null ? ' and cost' : ''} to reach ${state.chargeTo}%.',
          style: const TextStyle(color: AppColors.muted, fontSize: 13),
        ),
      ],
    );
  }
}

class _CarSummary extends StatelessWidget {
  const _CarSummary({required this.profile});
  final DriverProfile profile;

  @override
  Widget build(BuildContext context) {
    return Panel(
      onTap: () => HomeShell.of(context).goTo(HomeShell.settingsTab),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          const Icon(Icons.directions_car_filled_rounded, color: AppColors.brand),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(profile.carName, style: const TextStyle(fontWeight: FontWeight.w700)),
                Text(
                  '${plugFor(profile.plug).label} plug · ${profile.batteryKwh.round()} kWh battery',
                  style: const TextStyle(color: AppColors.muted, fontSize: 13),
                ),
              ],
            ),
          ),
          const Text('Change', style: TextStyle(color: AppColors.brand, fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }
}
