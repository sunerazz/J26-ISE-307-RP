import 'dart:async';

import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../app_state.dart';
import '../config.dart';
import '../models.dart';
import '../services.dart';
import '../shell.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/route_map.dart';
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
          icon: const Icon(Icons.cloud_off_rounded, color: AppColors.warn),
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
      body: ListView(
        padding: EdgeInsets.zero,
        children: [
          _Hero(state: state),
          Transform.translate(
            offset: const Offset(0, -44),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: _RouteCard(state: state),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Transform.translate(offset: const Offset(0, -28), child: _BatteryCard(state: state)),
                const SectionTitle('Charge goal'),
                _ChargeChoice(state: state),
                const SizedBox(height: 16),
                _CarSummary(profile: state.profile),
                const SizedBox(height: 22),
                _FindButton(state: state, onPressed: () => _find(context)),
                if (state.searching)
                  const Padding(
                    padding: EdgeInsets.only(top: 12),
                    child: Text(
                      'Checking real road routes, live weather and the climb on your route. The first search of the day can take up to a minute.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: AppColors.muted, fontSize: 13, height: 1.4),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Hero extends StatelessWidget {
  const _Hero({required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    final hour = DateTime.now().hour;
    final hello = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
    final top = MediaQuery.paddingOf(context).top;
    return SizedBox(
      height: 330 + top,
      child: Stack(
        children: [
          // The map starts below the heading and weather, so no pin can sit under them.
          Positioned(
            left: 0,
            right: 0,
            top: top + 96,
            bottom: 0,
            child: RouteMap(
              radius: 0,
              height: 234,
              interactive: false,
              // Keep pins clear of the route card that overlaps the bottom of the map.
              fitPadding: const EdgeInsets.fromLTRB(70, 80, 70, 70),
              pins: [
                MapPin(
                  point: LatLng(state.origin.latitude, state.origin.longitude),
                  label: state.origin.isCurrentLocation ? 'You are here' : 'Start',
                  color: AppColors.brand,
                  icon: state.origin.isCurrentLocation ? Icons.my_location_rounded : Icons.trip_origin_rounded,
                  emphasis: true,
                ),
                MapPin(
                  point: LatLng(state.destination.latitude, state.destination.longitude),
                  label: 'Destination',
                  color: AppColors.gold,
                  icon: Icons.flag_rounded,
                ),
              ],
            ),
          ),
          // Darken the top so the heading reads over the map.
          IgnorePointer(
            child: Container(
              height: 140 + top,
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  colors: [Color(0xEE070B10), Color(0x00070B10)],
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                ),
              ),
            ),
          ),
          Positioned(
            left: 20,
            right: 16,
            top: top + 14,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(hello, style: const TextStyle(color: AppColors.muted, fontSize: 14, fontWeight: FontWeight.w600)),
                      const SizedBox(height: 2),
                      const Text(
                        'Where to today?',
                        style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800, letterSpacing: -0.8),
                      ),
                    ],
                  ),
                ),
                _WeatherPill(weather: state.weather),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

IconData weatherIcon(Weather weather) {
  final code = weather.code;
  if (code >= 95) return Icons.thunderstorm_rounded;
  if (code >= 51) return Icons.water_drop_rounded;
  if (code == 45 || code == 48) return Icons.foggy;
  if (code >= 2) return Icons.cloud_rounded;
  return weather.isDay ? Icons.wb_sunny_rounded : Icons.nightlight_round;
}

class _WeatherPill extends StatelessWidget {
  const _WeatherPill({required this.weather});
  final Weather? weather;

  @override
  Widget build(BuildContext context) {
    final now = weather;
    return Container(
      padding: const EdgeInsets.fromLTRB(10, 8, 14, 8),
      decoration: BoxDecoration(
        color: const Color(0xCC0F161E),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.line),
      ),
      child: now == null
          ? const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.thermostat_rounded, color: AppColors.muted, size: 20),
                SizedBox(width: 4),
                Text('—°', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
              ],
            )
          : Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(weatherIcon(now), color: AppColors.gold, size: 22),
                const SizedBox(width: 6),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('${now.temperatureC.round()}°C', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
                    Text(now.text, style: const TextStyle(fontSize: 11, color: AppColors.muted)),
                  ],
                ),
              ],
            ),
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
                icon: state.origin.isCurrentLocation ? Icons.my_location_rounded : Icons.trip_origin_rounded,
                color: AppColors.brand,
                label: 'From',
                place: state.origin,
                busy: state.locating,
                onTap: () => _pick(context, origin: true),
              ),
              const Divider(height: 1, indent: 56, endIndent: 64),
              _PlaceRow(
                icon: Icons.flag_rounded,
                color: AppColors.gold,
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
              style: IconButton.styleFrom(backgroundColor: AppColors.surfaceHigh, foregroundColor: AppColors.ink),
              onPressed: state.swapPlaces,
              icon: const Icon(Icons.swap_vert_rounded),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _pick(BuildContext context, {required bool origin}) async {
    final state = context.read<AppState>();
    final picked = await showModalBottomSheet<Object>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _PlaceSheet(
        title: origin ? 'Start from' : 'Where are you going?',
        allowCurrentLocation: origin,
        services: state.services,
        near: state.origin,
      ),
    );
    if (!context.mounted || picked == null) return;
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
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(color: color.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(12)),
              child: Icon(icon, color: color, size: 20),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label, style: const TextStyle(fontSize: 12, color: AppColors.muted, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 2),
                  busy
                      ? const Text('Finding your location…', style: TextStyle(fontSize: 16, color: AppColors.muted))
                      : Text(
                          place.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
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
  const _PlaceSheet({
    required this.title,
    required this.allowCurrentLocation,
    required this.services,
    required this.near,
  });
  final String title;
  final bool allowCurrentLocation;
  final PlaceServices services;
  final Place near;

  static const currentLocation = 'current-location';

  @override
  State<_PlaceSheet> createState() => _PlaceSheetState();
}

class _PlaceSheetState extends State<_PlaceSheet> {
  String _query = '';
  List<Place> _found = const [];
  bool _searching = false;
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    super.dispose();
  }

  void _changed(String value) {
    setState(() => _query = value.trim());
    _debounce?.cancel();
    if (_query.length < 2) {
      setState(() => _found = const []);
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 350), () async {
      setState(() => _searching = true);
      final query = _query;
      final results = await widget.services.search(
        query,
        nearLatitude: widget.near.latitude,
        nearLongitude: widget.near.longitude,
      );
      if (!mounted || query != _query) return;
      setState(() {
        _found = results;
        _searching = false;
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    final presets = places.where((place) => place.name.toLowerCase().contains(_query.toLowerCase())).toList();
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: SizedBox(
        height: MediaQuery.sizeOf(context).height * 0.8,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 12),
              child: Text(widget.title, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: TextField(
                decoration: InputDecoration(
                  prefixIcon: const Icon(Icons.search_rounded),
                  hintText: 'Search any town or place in Sri Lanka',
                  suffixIcon: _searching
                      ? const Padding(
                          padding: EdgeInsets.all(14),
                          child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                        )
                      : null,
                ),
                onChanged: _changed,
              ),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: ListView(
                children: [
                  if (widget.allowCurrentLocation && _query.isEmpty)
                    _PlaceTile(
                      icon: Icons.my_location_rounded,
                      color: AppColors.brand,
                      title: 'Use my current location',
                      subtitle: 'From your phone’s GPS',
                      onTap: () => Navigator.pop(context, _PlaceSheet.currentLocation),
                    ),
                  for (final place in _found)
                    _PlaceTile(
                      icon: Icons.place_rounded,
                      color: AppColors.cyan,
                      title: place.name.split(',').first,
                      subtitle: place.name.contains(',') ? place.name.substring(place.name.indexOf(',') + 2) : 'Sri Lanka',
                      onTap: () => Navigator.pop(context, place),
                    ),
                  if (presets.isNotEmpty)
                    const Padding(
                      padding: EdgeInsets.fromLTRB(20, 12, 20, 4),
                      child: Text('Popular places', style: TextStyle(color: AppColors.muted, fontWeight: FontWeight.w700)),
                    ),
                  for (final place in presets)
                    _PlaceTile(
                      icon: Icons.history_toggle_off_rounded,
                      color: AppColors.muted,
                      title: place.name,
                      onTap: () => Navigator.pop(context, place),
                    ),
                  if (presets.isEmpty && _found.isEmpty && !_searching)
                    const Padding(
                      padding: EdgeInsets.all(24),
                      child: Text('No place with that name. Try a nearby town.', style: TextStyle(color: AppColors.muted)),
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

class _PlaceTile extends StatelessWidget {
  const _PlaceTile({required this.icon, required this.color, required this.title, required this.onTap, this.subtitle});
  final IconData icon;
  final Color color;
  final String title;
  final String? subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Container(
        padding: const EdgeInsets.all(9),
        decoration: BoxDecoration(color: color.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(12)),
        child: Icon(icon, color: color, size: 20),
      ),
      title: Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
      subtitle: subtitle == null ? null : Text(subtitle!, style: const TextStyle(color: AppColors.muted)),
      onTap: onTap,
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
    final color = level <= 20 ? AppColors.bad : level <= 40 ? AppColors.warn : AppColors.brand;
    final usableKm = (level - profile.reservePercent) / 100 * profile.batteryKwh / profile.consumption * 100;
    final kwh = profile.batteryKwh * level / 100;
    return Panel(
      padding: const EdgeInsets.fromLTRB(18, 16, 18, 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Battery now', style: TextStyle(fontSize: 13, color: AppColors.muted, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 2),
                  level > 40
                      ? GradientText('${level.round()}%', style: const TextStyle(fontSize: 40, fontWeight: FontWeight.w800, height: 1))
                      : Text('${level.round()}%', style: TextStyle(fontSize: 40, fontWeight: FontWeight.w800, height: 1, color: color)),
                ],
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  alignment: Alignment.bottomRight,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(
                        usableKm > 0 ? '≈ ${usableKm.round()} km' : '0 km',
                        style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
                      ),
                      Text(
                        '${kwh.toStringAsFixed(1)} kWh in battery',
                        style: const TextStyle(fontSize: 12, color: AppColors.muted),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
          SliderTheme(
            data: SliderTheme.of(context).copyWith(activeTrackColor: color, thumbColor: AppColors.ink),
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
                ? 'Range before your ${profile.reservePercent.round()}% safety reserve, at your car’s usual consumption.'
                : 'You are already at your ${profile.reservePercent.round()}% safety reserve.',
            style: const TextStyle(color: AppColors.muted, fontSize: 12.5),
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
              ),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          state.chargeTo == null
              ? 'We’ll tell you the smallest charge that gets you there safely.'
              : 'Charging time comes from the duration model and follows the charger power and the charge up to ${state.chargeTo}%. Energy${state.profile.tariffLkr != null ? ' and cost' : ''} use that same charge level.',
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
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(color: AppColors.goldSoft, borderRadius: BorderRadius.circular(14)),
            child: const Icon(Icons.directions_car_filled_rounded, color: AppColors.gold),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(profile.carName, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                Text(
                  '${plugFor(profile.plug).label} plug · ${profile.batteryKwh.round()} kWh · ${profile.consumption.toStringAsFixed(0)} kWh/100 km',
                  style: const TextStyle(color: AppColors.muted, fontSize: 12.5),
                ),
              ],
            ),
          ),
          const Icon(Icons.chevron_right_rounded, color: AppColors.muted),
        ],
      ),
    );
  }
}

class _FindButton extends StatelessWidget {
  const _FindButton({required this.state, required this.onPressed});
  final AppState state;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final busy = state.searching;
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: busy ? null : AppColors.accentGradient,
        color: busy ? AppColors.surfaceHigh : null,
        borderRadius: BorderRadius.circular(18),
        boxShadow: busy ? null : const [BoxShadow(color: Color(0x552EE6A6), blurRadius: 24, offset: Offset(0, 8))],
      ),
      child: FilledButton.icon(
        style: FilledButton.styleFrom(
          backgroundColor: Colors.transparent,
          disabledBackgroundColor: Colors.transparent,
          shadowColor: Colors.transparent,
        ),
        onPressed: busy ? null : onPressed,
        icon: busy
            ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2.5))
            : const Icon(Icons.bolt_rounded),
        label: Text(busy ? 'Planning your trip…' : 'Find best charger'),
      ),
    );
  }
}
