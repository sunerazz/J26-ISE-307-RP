import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../app_state.dart';
import '../models.dart';

class ProfilePage extends StatefulWidget {
  const ProfilePage({super.key});

  @override
  State<ProfilePage> createState() => _ProfilePageState();
}

class _ProfilePageState extends State<ProfilePage> {
  final _tariff = TextEditingController();
  final _efficiency = TextEditingController();
  double _reserve = 10;

  @override
  void initState() {
    super.initState();
    final profile = context.read<AppState>().profile;
    _reserve = profile.reservePercent;
    _tariff.text = profile.scenarioTariffLkr?.toString() ?? '';
    _efficiency.text = profile.chargingEfficiency?.toString() ?? '';
  }

  @override
  void dispose() {
    _tariff.dispose();
    _efficiency.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final tariff = double.tryParse(_tariff.text.trim());
    final efficiency = double.tryParse(_efficiency.text.trim());
    if (_efficiency.text.trim().isNotEmpty && (efficiency == null || efficiency <= 0 || efficiency > 1)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Efficiency must be above 0 and at most 1, or left blank.')),
      );
      return;
    }
    await context.read<AppState>().updateProfile(
          DriverProfile(
            reservePercent: _reserve,
            scenarioTariffLkr: _tariff.text.trim().isEmpty ? null : tariff,
            chargingEfficiency: _efficiency.text.trim().isEmpty ? null : efficiency,
          ),
        );
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Saved on this phone.')));
  }

  @override
  Widget build(BuildContext context) {
    final base = context.watch<AppState>().apiBaseUrl;
    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('API address: $base'),
          const SizedBox(height: 8),
          const Text(
            'A phone cannot use 127.0.0.1. Build with --dart-define=API_BASE_URL=https://your-app.up.railway.app',
            style: TextStyle(color: Color(0xFF6B7280)),
          ),
          const SizedBox(height: 16),
          Text('Minimum reserve: ${_reserve.round()}%'),
          Slider(
            value: _reserve,
            min: 0,
            max: 40,
            divisions: 8,
            label: '${_reserve.round()}%',
            onChanged: (value) => setState(() => _reserve = value),
          ),
          TextField(
            controller: _tariff,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
              labelText: 'Scenario tariff (LKR per kWh)',
              helperText: 'Optional. Used only as a labelled scenario, not as the station price.',
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _efficiency,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
              labelText: 'Charging efficiency (optional)',
              helperText: 'Between 0 and 1. Grid energy is battery kWh divided by this value.',
            ),
          ),
          const SizedBox(height: 16),
          FilledButton(onPressed: _save, child: const Text('Save')),
        ],
      ),
    );
  }
}
