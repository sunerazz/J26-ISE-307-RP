import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../app_state.dart';
import '../config.dart';
import '../format.dart';
import '../models.dart';
import '../theme.dart';
import '../widgets/common.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  final _battery = TextEditingController();
  final _consumption = TextEditingController();
  final _tariff = TextEditingController();
  final _loss = TextEditingController();
  String _carName = '';
  String _plug = 'CHAdeMO';
  double _reserve = 10;
  bool _filled = false;
  bool _dirty = false;
  bool _saving = false;

  static const _otherCar = 'Other car';

  @override
  void dispose() {
    for (final controller in [_battery, _consumption, _tariff, _loss]) {
      controller.dispose();
    }
    super.dispose();
  }

  void _fill(DriverProfile profile) {
    _carName = profile.carName;
    _plug = profile.plug;
    _reserve = profile.reservePercent;
    _battery.text = fmtNumber(profile.batteryKwh);
    _consumption.text = fmtNumber(profile.consumption);
    _tariff.text = profile.tariffLkr == null ? '' : fmtNumber(profile.tariffLkr!);
    _loss.text = profile.chargingLossPercent == null ? '' : fmtNumber(profile.chargingLossPercent!);
    _filled = true;
    _dirty = false;
  }

  void _changed(VoidCallback update) => setState(() {
        update();
        _dirty = true;
      });

  void _pickCar(String? name) {
    if (name == null) return;
    _changed(() {
      _carName = name;
      for (final preset in carPresets) {
        if (preset.name == name) {
          _battery.text = fmtNumber(preset.batteryKwh);
          _consumption.text = fmtNumber(preset.consumption);
          _plug = preset.plug;
        }
      }
    });
  }

  String? _check(String text, String label, double min, double max, {bool optional = false}) {
    if (text.trim().isEmpty) return optional ? null : '$label is needed';
    final value = double.tryParse(text.trim());
    if (value == null || value < min || value > max) {
      return '$label should be between ${fmtNumber(min)} and ${fmtNumber(max)}';
    }
    return null;
  }

  Future<void> _save() async {
    final problem = _check(_battery.text, 'Battery size', 10, 200) ??
        _check(_consumption.text, 'Energy use', 8, 40) ??
        _check(_tariff.text, 'Electricity price', 1, 1000, optional: true) ??
        _check(_loss.text, 'Charging losses', 0, 30, optional: true);
    if (problem != null) {
      showMessage(context, problem);
      return;
    }
    final state = context.read<AppState>();
    setState(() => _saving = true);
    try {
      await state.updateProfile(
        DriverProfile(
          carName: _carName,
          batteryKwh: double.parse(_battery.text.trim()),
          consumption: double.parse(_consumption.text.trim()),
          plug: _plug,
          reservePercent: _reserve,
          tariffLkr: _tariff.text.trim().isEmpty ? null : double.parse(_tariff.text.trim()),
          chargingLossPercent: _loss.text.trim().isEmpty ? null : double.parse(_loss.text.trim()),
        ),
      );
      if (!mounted) return;
      setState(() => _dirty = false);
      showMessage(context, 'Settings saved');
    } catch (_) {
      if (mounted) showMessage(context, 'Saved on this phone. Backing up to your account failed — it will retry next time.');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    if (state.ready && !_filled) _fill(state.profile);
    final carChoices = [...carPresets.map((preset) => preset.name), _otherCar];
    final selectedCar = carChoices.contains(_carName) ? _carName : _otherCar;
    final decimal = [FilteringTextInputFormatter.allow(RegExp(r'[0-9.]'))];

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      bottomNavigationBar: _dirty
          ? SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                child: FilledButton(
                  onPressed: _saving ? null : _save,
                  child: Text(_saving ? 'Saving…' : 'Save changes'),
                ),
              ),
            )
          : null,
      body: !state.ready
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
              children: [
                const SectionTitle('My car'),
                Panel(
                  child: Column(
                    children: [
                      DropdownButtonFormField<String>(
                        key: ValueKey(selectedCar),
                        initialValue: selectedCar,
                        isExpanded: true,
                        decoration: const InputDecoration(labelText: 'Car'),
                        items: [for (final name in carChoices) DropdownMenuItem(value: name, child: Text(name))],
                        onChanged: _pickCar,
                      ),
                      const SizedBox(height: 12),
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _battery,
                              keyboardType: const TextInputType.numberWithOptions(decimal: true),
                              inputFormatters: decimal,
                              decoration: const InputDecoration(labelText: 'Usable battery', suffixText: 'kWh'),
                              onChanged: (_) => _changed(() => _carName = _otherCar),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: TextField(
                              controller: _consumption,
                              keyboardType: const TextInputType.numberWithOptions(decimal: true),
                              inputFormatters: decimal,
                              decoration: const InputDecoration(labelText: 'Energy use', suffixText: 'kWh/100km'),
                              onChanged: (_) => _changed(() => _carName = _otherCar),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 6),
                      const Text(
                        'Energy use is on your car’s trip screen. Most cars use 13–20 kWh per 100 km in the city.',
                        style: TextStyle(color: AppColors.muted, fontSize: 12.5),
                      ),
                    ],
                  ),
                ),
                const SectionTitle('Charging plug'),
                Panel(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: RadioGroup<String>(
                    groupValue: _plug,
                    onChanged: (value) {
                      if (value != null) _changed(() => _plug = value);
                    },
                    child: Column(
                      children: [
                        for (final plug in plugs)
                          RadioListTile<String>(
                            value: plug.apiValue,
                            title: Text(plug.label, style: const TextStyle(fontWeight: FontWeight.w700)),
                            subtitle: Text(plug.hint),
                          ),
                      ],
                    ),
                  ),
                ),
                const SectionTitle('Safety reserve'),
                Panel(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const Expanded(child: Text('Always keep at least')),
                          Text('${_reserve.round()}%', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
                        ],
                      ),
                      Slider(
                        value: _reserve,
                        min: 5,
                        max: 40,
                        divisions: 7,
                        label: '${_reserve.round()}%',
                        onChanged: (value) => _changed(() => _reserve = value),
                      ),
                      const Text(
                        'We only suggest chargers you can reach without going below this level.',
                        style: TextStyle(color: AppColors.muted, fontSize: 12.5),
                      ),
                    ],
                  ),
                ),
                const SectionTitle('Charging cost (optional)'),
                Panel(
                  child: Column(
                    children: [
                      TextField(
                        controller: _tariff,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        inputFormatters: decimal,
                        decoration: const InputDecoration(
                          labelText: 'Electricity price',
                          prefixText: 'Rs. ',
                          suffixText: 'per kWh',
                          helperText: 'Your own estimate. Leave empty to hide costs.',
                        ),
                        onChanged: (_) => _changed(() {}),
                      ),
                      const SizedBox(height: 14),
                      TextField(
                        controller: _loss,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        inputFormatters: decimal,
                        decoration: const InputDecoration(
                          labelText: 'Energy lost while charging',
                          suffixText: '%',
                          helperText: 'Usually around 10%. Leave empty to ignore.',
                        ),
                        onChanged: (_) => _changed(() {}),
                      ),
                    ],
                  ),
                ),
                const SectionTitle('About'),
                Panel(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Column(
                    children: [
                      ListTile(
                        leading: Icon(
                          state.syncedToCloud ? Icons.cloud_done_outlined : Icons.phone_android_rounded,
                          color: AppColors.brand,
                        ),
                        title: Text(state.syncedToCloud ? 'Backed up to your account' : 'Saved on this phone'),
                        subtitle: const Text('Your settings and trip history'),
                      ),
                      const Divider(height: 1, indent: 16, endIndent: 16),
                      const ExpansionTile(
                        leading: Icon(Icons.help_outline_rounded, color: AppColors.brand),
                        title: Text('How suggestions work'),
                        shape: Border(),
                        childrenPadding: EdgeInsets.fromLTRB(16, 0, 16, 16),
                        expandedCrossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _Help(
                            'We check real road routes from your start, to each charger, and on to your destination.',
                          ),
                          _Help(
                            'A charger is suggested only if it has your plug and you can reach it above your safety reserve.',
                          ),
                          _Help(
                            'Among those, the best one adds the least extra driving, then the shortest charging time and the lowest cost.',
                          ),
                          _Help(
                            'Battery use is estimated from your car’s energy use, so hills, heavy traffic and air-conditioning can change it.',
                          ),
                          _Help(
                            'Queue, waiting time and congestion are estimates from the synthetic town model when the charger is near Nugegoda, Rajagiriya, Malabe, Pannipitiya or Panadura. They are not a count at the charger, so check before you go.',
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
    );
  }
}

class _Help extends StatelessWidget {
  const _Help(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('•  ', style: TextStyle(fontWeight: FontWeight.w800, color: AppColors.brand)),
          Expanded(child: Text(text, style: const TextStyle(height: 1.4))),
        ],
      ),
    );
  }
}
