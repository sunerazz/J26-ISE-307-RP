import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

import '../format.dart';
import '../models.dart';
import '../theme.dart';
import 'common.dart';
import 'route_map.dart';

/// The station facts both the results and the station list can show.
class StationInfo {
  StationInfo({
    required this.name,
    required this.address,
    required this.latitude,
    required this.longitude,
    required this.connectors,
    required this.powerKw,
    required this.tariffRaw,
    required this.sourceUrl,
    this.operator,
  });

  factory StationInfo.fromListing(StationListing station) => StationInfo(
        name: station.name,
        address: station.address,
        latitude: station.latitude,
        longitude: station.longitude,
        connectors: station.connectors,
        powerKw: station.powerKw,
        tariffRaw: station.tariffRaw,
        sourceUrl: station.sourceUrl,
        operator: station.operator,
      );

  factory StationInfo.fromRanked(RankedStation station) => StationInfo(
        name: station.name,
        address: station.address,
        latitude: station.latitude,
        longitude: station.longitude,
        connectors: station.connectors,
        powerKw: station.powerKw,
        tariffRaw: station.tariffRaw,
        sourceUrl: station.sourceUrl,
      );

  final String name;
  final String address;
  final double latitude;
  final double longitude;
  final List<String> connectors;
  final double? powerKw;
  final String? tariffRaw;
  final String? sourceUrl;
  final String? operator;
}

Future<void> showStationSheet(BuildContext context, StationInfo station) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (context) => DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.6,
      maxChildSize: 0.92,
      builder: (context, controller) => _StationSheet(station: station, controller: controller),
    ),
  );
}

class _StationSheet extends StatelessWidget {
  const _StationSheet({required this.station, required this.controller});
  final StationInfo station;
  final ScrollController controller;

  @override
  Widget build(BuildContext context) {
    final prices = fmtListedPrices(station.tariffRaw);
    final operator = station.operator?.trim() ?? '';
    return ListView(
      controller: controller,
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 28),
      children: [
        Text(station.name, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
        const SizedBox(height: 4),
        Text(station.address, style: const TextStyle(color: AppColors.muted, height: 1.35)),
        if (operator.isNotEmpty) ...[
          const SizedBox(height: 4),
          Text('Run by $operator', style: const TextStyle(color: AppColors.muted)),
        ],
        const SizedBox(height: 14),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            Tag(fmtPower(station.powerKw), icon: Icons.bolt_rounded, tone: Tone.info),
            for (final plug in station.connectors) Tag(fmtPlug(plug), icon: Icons.power_rounded),
          ],
        ),
        const SizedBox(height: 16),
        _Row(
          icon: Icons.payments_outlined,
          title: 'Price',
          body: prices.isEmpty
              ? 'Price not listed. Ask the operator before charging.'
              : '${prices.join('\n')}\nListed price — confirm at the station.',
        ),
        const _Row(
          icon: Icons.schedule_rounded,
          title: 'Availability',
          body: 'Live availability isn’t available for this charger. Check it’s free and working before you go.',
        ),
        const SizedBox(height: 16),
        FilledButton.icon(
          onPressed: () => openDirections(destination: LatLng(station.latitude, station.longitude)),
          icon: const Icon(Icons.navigation_rounded),
          label: const Text('Directions'),
        ),
        if (station.sourceUrl != null) ...[
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: () => launchUrl(Uri.parse(station.sourceUrl!), mode: LaunchMode.externalApplication),
            icon: const Icon(Icons.open_in_new_rounded),
            label: const Text('More info and photos'),
          ),
        ],
      ],
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({required this.icon, required this.title, required this.body});
  final IconData icon;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: AppColors.brand),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
                const SizedBox(height: 2),
                Text(body, style: const TextStyle(color: AppColors.muted, height: 1.4)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
