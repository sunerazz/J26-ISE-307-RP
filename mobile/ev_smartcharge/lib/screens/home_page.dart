import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../app_state.dart';
import '../config.dart';
import '../format.dart';
import '../models.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  int _from = 0;
  int _to = 6;
  int _soc = 40;
  int _capacity = 60;
  int _consumption = 15;
  String _connector = 'CHAdeMO';
  int? _targetSoc = 80;
  bool _busy = false;
  String? _error;
  bool _energyOn = false;
  bool _energyComplete = false;
  Map<String, dynamic>? _energyConditions;

  Future<void> _search() async {
    final state = context.read<AppState>();
    final origin = places[_from];
    final destination = places[_to];
    setState(() {
      _busy = true;
      _error = null;
    });
    if (_energyOn && !_energyComplete) {
      setState(() {
        _busy = false;
        _error = 'Fill every energy-model field, or turn that section off. Empty fields are not guessed.';
      });
      return;
    }
    final payload = <String, dynamic>{
      'origin_latitude': origin.latitude,
      'origin_longitude': origin.longitude,
      'destination_latitude': destination.latitude,
      'destination_longitude': destination.longitude,
      'current_soc_percent': _soc,
      'usable_battery_capacity_kwh': _capacity,
      'consumption_kwh_per_100km': _consumption,
      'minimum_reserve_percent': state.profile.reservePercent,
      'required_connector': _connector,
      'target_soc_percent': _targetSoc,
      'user_tariff_lkr_per_kwh': state.profile.scenarioTariffLkr,
      'charging_efficiency': state.profile.chargingEfficiency,
      'include_explanation': true,
      if (_energyOn && _energyConditions != null) 'energy_conditions': _energyConditions,
    };
    try {
      final result = await state.recommend(payload);
      final chosen = result.recommended;
      await state.remember(
        SavedTrip(
          when: DateTime.now().toIso8601String(),
          originName: origin.name,
          destinationName: destination.name,
          stationId: chosen?.id,
          stationName: chosen?.name,
          summary: result.quickAnswer.isEmpty
              ? (chosen == null ? 'No station matched these inputs.' : chosen.name)
              : result.quickAnswer.first,
        ),
      );
    } catch (error) {
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final result = context.watch<AppState>().latest;
    final origin = places[_from];
    final destination = places[_to];
    return Scaffold(
      backgroundColor: const Color(0xFFF3F5F7),
      body: Column(
        children: [
          _Header(
            from: origin.name,
            to: destination.name,
            onFrom: (value) => setState(() => _from = value),
            onTo: (value) => setState(() => _to = value),
            onSwap: () => setState(() {
              final swap = _from;
              _from = _to;
              _to = swap;
            }),
            soc: _soc,
            capacity: _capacity,
            consumption: _consumption,
            connector: _connector,
            target: _targetSoc,
            onSoc: (value) => setState(() => _soc = value),
            onCapacity: (value) => setState(() => _capacity = value),
            onConsumption: (value) => setState(() => _consumption = value),
            onConnector: (value) => setState(() => _connector = value),
            onTarget: (value) => setState(() => _targetSoc = value),
            busy: _busy,
            onSearch: _search,
            beforeSearch: _EnergyPanel(
              onChanged: (enabled, complete, values) {
                setState(() {
                  _energyOn = enabled;
                  _energyComplete = complete;
                  _energyConditions = values;
                });
              },
            ),
          ),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
              children: [
                if (_error != null) _ErrorBox(text: _error!),
                _RouteMap(origin: origin, destination: destination, result: result, stations: result?.all ?? const []),
                const SizedBox(height: 12),
                if (result == null)
                  const _HintCard()
                else ...[
                  _RecommendedCard(
                    station: result.recommended,
                    warnings: result.warnings,
                    notes: result.quickAnswer,
                    energyNote: result.energyModelReason,
                  ),
                  const SizedBox(height: 14),
                  const Text('Other options', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 8),
                  ...result.alternatives.map((station) => Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: _OptionTile(station: station),
                      )),
                  if (result.explanation != null) ...[
                    const SizedBox(height: 8),
                    _Explanation(text: result.explanation!),
                  ],
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({
    required this.from,
    required this.to,
    required this.onFrom,
    required this.onTo,
    required this.onSwap,
    required this.soc,
    required this.capacity,
    required this.consumption,
    required this.connector,
    required this.target,
    required this.onSoc,
    required this.onCapacity,
    required this.onConsumption,
    required this.onConnector,
    required this.onTarget,
    required this.busy,
    required this.onSearch,
    required this.beforeSearch,
  });

  final String from;
  final String to;
  final ValueChanged<int> onFrom;
  final ValueChanged<int> onTo;
  final VoidCallback onSwap;
  final int soc;
  final int capacity;
  final int consumption;
  final String connector;
  final int? target;
  final ValueChanged<int> onSoc;
  final ValueChanged<int> onCapacity;
  final ValueChanged<int> onConsumption;
  final ValueChanged<String> onConnector;
  final ValueChanged<int?> onTarget;
  final bool busy;
  final VoidCallback onSearch;
  final Widget beforeSearch;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFF0E7A3A),
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
          child: Column(
            children: [
              const Row(
                children: [
                  CircleAvatar(
                    backgroundColor: Colors.white,
                    child: Icon(Icons.energy_savings_leaf, color: Color(0xFF0E7A3A)),
                  ),
                  SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('EV SmartCharge', style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w800)),
                        Text('Charging decision support', style: TextStyle(color: Color(0xFFD7F5E3), fontSize: 12)),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Material(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    children: [
                      Row(
                        children: [
                          Expanded(child: _PlaceMenu(label: 'From', value: from, onChanged: onFrom)),
                          IconButton(onPressed: onSwap, icon: const Icon(Icons.swap_horiz, color: Color(0xFF0E7A3A))),
                          Expanded(child: _PlaceMenu(label: 'To', value: to, onChanged: onTo)),
                        ],
                      ),
                      const Divider(height: 16),
                      Row(
                        children: [
                          _StatMenu(icon: Icons.battery_5_bar, label: 'Current SOC', value: '$soc%', options: [for (var n = 10; n <= 100; n += 10) n], selected: soc, onPick: onSoc),
                          _StatMenu(icon: Icons.battery_charging_full, label: 'Battery', value: '$capacity kWh', options: const [40, 50, 60, 75, 82], selected: capacity, onPick: onCapacity),
                          _StatMenu(icon: Icons.directions_car, label: 'Consumption', value: '$consumption kWh/100km', options: const [12, 15, 17, 20], selected: consumption, onPick: onConsumption),
                        ],
                      ),
                      const Divider(height: 16),
                      Row(
                        children: [
                          Expanded(
                            child: DropdownButtonFormField<String>(
                              initialValue: connector,
                              decoration: const InputDecoration(labelText: 'Connector', isDense: true),
                              items: connectors.map((item) => DropdownMenuItem(value: item, child: Text(item))).toList(),
                              onChanged: (value) {
                                if (value != null) onConnector(value);
                              },
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: DropdownButtonFormField<int?>(
                              initialValue: target,
                              decoration: const InputDecoration(labelText: 'Target SOC', isDense: true),
                              items: [
                                const DropdownMenuItem<int?>(value: null, child: Text('Not set')),
                                for (final n in [60, 70, 80, 90, 100]) DropdownMenuItem<int?>(value: n, child: Text('$n%')),
                              ],
                              onChanged: onTarget,
                            ),
                          ),
                        ],
                      ),
                      if (connector == 'CCS2 (DC)')
                        const Padding(
                          padding: EdgeInsets.only(top: 8),
                          child: Text(
                            'None of the four Colombo listings include CCS2. A search will not invent a match.',
                            style: TextStyle(color: Color(0xFF9A3412), fontSize: 12),
                          ),
                        ),
                      const SizedBox(height: 8),
                      beforeSearch,
                      const SizedBox(height: 12),
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton.icon(
                          style: FilledButton.styleFrom(
                            backgroundColor: const Color(0xFF1FAF4B),
                            padding: const EdgeInsets.symmetric(vertical: 14),
                          ),
                          onPressed: busy ? null : onSearch,
                          icon: busy
                              ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                              : const Icon(Icons.search),
                          label: Text(busy ? 'Checking road routes…' : 'Find best charging station'),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PlaceMenu extends StatelessWidget {
  const _PlaceMenu({required this.label, required this.value, required this.onChanged});
  final String label;
  final String value;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    final index = places.indexWhere((place) => place.name == value);
    return DropdownButtonFormField<int>(
      initialValue: index < 0 ? 0 : index,
      isExpanded: true,
      decoration: InputDecoration(labelText: label, isDense: true, border: InputBorder.none),
      items: [for (var i = 0; i < places.length; i++) DropdownMenuItem(value: i, child: Text(places[i].name, overflow: TextOverflow.ellipsis))],
      onChanged: (next) {
        if (next != null) onChanged(next);
      },
    );
  }
}

class _StatMenu extends StatelessWidget {
  const _StatMenu({
    required this.icon,
    required this.label,
    required this.value,
    required this.options,
    required this.selected,
    required this.onPick,
  });

  final IconData icon;
  final String label;
  final String value;
  final List<int> options;
  final int selected;
  final ValueChanged<int> onPick;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: PopupMenuButton<int>(
        onSelected: onPick,
        itemBuilder: (context) => options.map((option) => PopupMenuItem(value: option, child: Text('$option'))).toList(),
        child: Column(
          children: [
            Icon(icon, color: const Color(0xFF0E7A3A), size: 18),
            Text(value, textAlign: TextAlign.center, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12)),
            Text(label, textAlign: TextAlign.center, style: const TextStyle(color: Color(0xFF6B7280), fontSize: 10)),
          ],
        ),
      ),
    );
  }
}

class _RouteMap extends StatelessWidget {
  const _RouteMap({
    required this.origin,
    required this.destination,
    required this.result,
    required this.stations,
  });

  final PlacePreset origin;
  final PlacePreset destination;
  final TripResult? result;
  final List<RankedStation> stations;

  @override
  Widget build(BuildContext context) {
    final line = result?.recommendedGeometry ?? const <List<double>>[];
    final points = <LatLng>[
      LatLng(origin.latitude, origin.longitude),
      LatLng(destination.latitude, destination.longitude),
      ...stations.map((station) => LatLng(station.latitude, station.longitude)),
      ...line.map((pair) => LatLng(pair[0], pair[1])),
    ];
    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: SizedBox(
        height: 250,
        child: FlutterMap(
          options: MapOptions(
            initialCameraFit: CameraFit.coordinates(
              coordinates: points,
              padding: const EdgeInsets.all(36),
            ),
          ),
          children: [
            TileLayer(
              urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
              userAgentPackageName: 'com.evsmartcharge.ev_smartcharge',
            ),
            if (line.length >= 2)
              PolylineLayer(
                polylines: [
                  Polyline(points: line.map((pair) => LatLng(pair[0], pair[1])).toList(), color: const Color(0xFF1D4ED8), strokeWidth: 4),
                ],
              ),
            MarkerLayer(
              markers: [
                Marker(point: LatLng(origin.latitude, origin.longitude), width: 70, height: 40, child: const _Pin(color: Color(0xFF16A34A), label: 'Start')),
                Marker(point: LatLng(destination.latitude, destination.longitude), width: 90, height: 40, child: const _Pin(color: Color(0xFFDC2626), label: 'Destination')),
                ...stations.map(
                  (station) => Marker(
                    point: LatLng(station.latitude, station.longitude),
                    width: 64,
                    height: 36,
                    child: _Pin(color: const Color(0xFF0284C7), label: station.id),
                  ),
                ),
              ],
            ),
            const RichAttributionWidget(attributions: [TextSourceAttribution('OpenStreetMap contributors')]),
          ],
        ),
      ),
    );
  }
}

class _Pin extends StatelessWidget {
  const _Pin({required this.color, required this.label});
  final Color color;
  final String label;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(8)),
      child: Center(child: Text(label, style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700))),
    );
  }
}

class _RecommendedCard extends StatelessWidget {
  const _RecommendedCard({required this.station, required this.warnings, required this.notes, required this.energyNote});
  final RankedStation? station;
  final List<String> warnings;
  final List<String> notes;
  final String? energyNote;

  @override
  Widget build(BuildContext context) {
    if (station == null) {
      return _Panel(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('No station fits these inputs', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
            const SizedBox(height: 8),
            ...notes.map((line) => Padding(padding: const EdgeInsets.only(bottom: 6), child: Text(line))),
            ...warnings.map((line) => Text(line, style: const TextStyle(color: Color(0xFF9A3412)))),
            if (energyNote != null) ...[
              const SizedBox(height: 8),
              Text(energyNote!, style: const TextStyle(fontSize: 12, color: Color(0xFF6B7280))),
            ],
          ],
        ),
      );
    }
    final reachable = station!.batteryStatus == 'feasible';
    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(child: Text('Recommended station', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800))),
              if (station!.included) const _Badge('Best listed option'),
            ],
          ),
          const SizedBox(height: 8),
          Text('${station!.id} · ${station!.name}', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
          Text(station!.address, style: const TextStyle(color: Color(0xFF6B7280))),
          const SizedBox(height: 4),
          Text(
            '${fmtKm(station!.toStation?.distanceKm)} by road from the origin · detour ${fmtKm(station!.detourKm)}',
            style: const TextStyle(color: Color(0xFF374151)),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              _Metric(icon: Icons.route, value: fmtMinutes(station!.detourMin), label: 'Added time'),
              _Metric(icon: Icons.schedule, value: 'Unavailable', label: 'Est. waiting'),
              _Metric(icon: Icons.bolt, value: fmtMinutes(station!.chargeMinutes), label: 'Charge time'),
              _Metric(icon: Icons.payments, value: fmtLkr(station!.scenarioCostLkr), label: 'Scenario cost'),
            ],
          ),
          const SizedBox(height: 8),
          const Text(
            'Waiting time is unavailable. These listings have no queue observation, and the waiting model was trained on synthetic stations.',
            style: TextStyle(fontSize: 12, color: Color(0xFF6B7280)),
          ),
          Text(
            station!.chargeMinutes == null
                ? 'Charge time is unavailable until a target state of charge is set. It is a listed-power estimate, not the duration model.'
                : 'Charge time uses listed kilowatts, not the duration model.',
            style: const TextStyle(fontSize: 12, color: Color(0xFF6B7280)),
          ),
          if (energyNote != null)
            Text(energyNote!, style: const TextStyle(fontSize: 12, color: Color(0xFF6B7280))),
          if (station!.scenarioCostLkr == null)
            const Text(
              'Cost is unavailable until you enter a scenario tariff in Profile. Listed tariff text is not a bill.',
              style: TextStyle(fontSize: 12, color: Color(0xFF6B7280)),
            ),
          const SizedBox(height: 10),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: reachable ? const Color(0xFFE8F8EE) : const Color(0xFFFFF1F2),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              reachable
                  ? 'Feasible with the battery figures you entered. Energy to reach the station: ${fmtKwh(station!.energyToReachKwh)}. This is an estimate, not a guarantee.'
                  : 'Battery status: ${station!.batteryStatus}. ${station!.exclusion ?? ''}',
            ),
          ),
        ],
      ),
    );
  }
}

class _OptionTile extends StatelessWidget {
  const _OptionTile({required this.station});
  final RankedStation station;

  @override
  Widget build(BuildContext context) {
    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('${station.id} · ${station.name}', style: const TextStyle(fontWeight: FontWeight.w700)),
          Text(
            station.included
                ? '${fmtKm(station.toStation?.distanceKm)} by road · detour ${fmtKm(station.detourKm)}'
                : (station.exclusion ?? 'Excluded'),
            style: const TextStyle(color: Color(0xFF6B7280)),
          ),
          const SizedBox(height: 4),
          Text(
            'Availability ${station.availability}. Congestion unavailable.',
            style: const TextStyle(fontSize: 12, color: Color(0xFF6B7280)),
          ),
        ],
      ),
    );
  }
}

class _Explanation extends StatelessWidget {
  const _Explanation({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Why this result', style: TextStyle(fontWeight: FontWeight.w800)),
          const SizedBox(height: 6),
          Text(text),
        ],
      ),
    );
  }
}

class _HintCard extends StatelessWidget {
  const _HintCard();

  @override
  Widget build(BuildContext context) {
    return const _Panel(
      child: Text(
        'Choose a trip and press Find. Distances come from road routing. The map draws a line only when the routing service returns the road shape.',
      ),
    );
  }
}

class _ErrorBox extends StatelessWidget {
  const _ErrorBox({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: const Color(0xFFFFF1F2), borderRadius: BorderRadius.circular(12)),
      child: Text(text),
    );
  }
}

class _Panel extends StatelessWidget {
  const _Panel({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(16)),
      child: child,
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(color: const Color(0xFFDCFCE7), borderRadius: BorderRadius.circular(20)),
      child: Padding(padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4), child: Text(text, style: const TextStyle(fontSize: 11, color: Color(0xFF166534)))),
    );
  }
}

class _EnergyPanel extends StatefulWidget {
  const _EnergyPanel({required this.onChanged});
  final void Function(bool enabled, bool complete, Map<String, dynamic>? values) onChanged;

  @override
  State<_EnergyPanel> createState() => _EnergyPanelState();
}

class _EnergyPanelState extends State<_EnergyPanel> {
  bool _enabled = false;
  bool _ac = false;
  String? _traffic;
  String? _road;
  final _gain = TextEditingController();
  final _loss = TextEditingController();
  final _temp = TextEditingController();
  final _mass = TextEditingController();

  @override
  void initState() {
    super.initState();
    for (final controller in [_gain, _loss, _temp, _mass]) {
      controller.addListener(_emit);
    }
    WidgetsBinding.instance.addPostFrameCallback((_) => _emit());
  }

  @override
  void dispose() {
    for (final controller in [_gain, _loss, _temp, _mass]) {
      controller.dispose();
    }
    super.dispose();
  }

  void _emit() {
    if (!_enabled) {
      widget.onChanged(false, false, null);
      return;
    }
    final gain = double.tryParse(_gain.text.trim());
    final loss = double.tryParse(_loss.text.trim());
    final temp = double.tryParse(_temp.text.trim());
    final mass = double.tryParse(_mass.text.trim());
    final complete = gain != null && gain >= 0 && loss != null && loss >= 0 && temp != null && mass != null && mass > 0 && _traffic != null && _road != null;
    widget.onChanged(
      true,
      complete,
      complete
          ? {
              'elevation_gain_m': gain,
              'elevation_loss_m': loss,
              'ambient_temperature_c': temp,
              'ac_on': _ac ? 1 : 0,
              'traffic_level': _traffic,
              'road_type': _road,
              'vehicle_mass_kg': mass,
            }
          : null,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Use energy model', style: TextStyle(fontSize: 14)),
          subtitle: const Text('Leave this off to keep the kWh/100 km figure. Empty conditions are not guessed.', style: TextStyle(fontSize: 11)),
          value: _enabled,
          onChanged: (value) => setState(() {
            _enabled = value;
            _emit();
          }),
        ),
        if (_enabled) ...[
          Row(
            children: [
              Expanded(child: TextField(controller: _gain, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Elevation gain m', isDense: true))),
              const SizedBox(width: 8),
              Expanded(child: TextField(controller: _loss, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Elevation loss m', isDense: true))),
            ],
          ),
          Row(
            children: [
              Expanded(child: TextField(controller: _temp, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Temperature °C', isDense: true))),
              const SizedBox(width: 8),
              Expanded(child: TextField(controller: _mass, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Vehicle mass kg', isDense: true))),
            ],
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Air conditioning on', style: TextStyle(fontSize: 14)),
            value: _ac,
            onChanged: (value) => setState(() {
              _ac = value;
              _emit();
            }),
          ),
          DropdownButtonFormField<String>(
            initialValue: _traffic,
            decoration: const InputDecoration(labelText: 'Traffic', isDense: true),
            items: const ['low', 'medium', 'high'].map((item) => DropdownMenuItem(value: item, child: Text(item))).toList(),
            onChanged: (value) => setState(() {
              _traffic = value;
              _emit();
            }),
          ),
          DropdownButtonFormField<String>(
            initialValue: _road,
            decoration: const InputDecoration(labelText: 'Road type', isDense: true),
            items: const ['highway', 'urban', 'mixed'].map((item) => DropdownMenuItem(value: item, child: Text(item))).toList(),
            onChanged: (value) => setState(() {
              _road = value;
              _emit();
            }),
          ),
        ],
      ],
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.icon, required this.value, required this.label});
  final IconData icon;
  final String value;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        children: [
          Icon(icon, size: 18, color: const Color(0xFF0E7A3A)),
          Text(value, textAlign: TextAlign.center, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 12)),
          Text(label, textAlign: TextAlign.center, style: const TextStyle(fontSize: 10, color: Color(0xFF6B7280))),
        ],
      ),
    );
  }
}
