import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart' hide Path;
import 'package:url_launcher/url_launcher.dart';

import '../config.dart';
import '../theme.dart';

class MapPin {
  const MapPin({required this.point, required this.label, required this.color, this.icon, this.emphasis = false});
  final LatLng point;
  final String label;
  final Color color;
  final IconData? icon;
  final bool emphasis;
}

/// Free dark basemap from CARTO (OpenStreetMap data, no key). A MapTiler key passed with
/// --dart-define=MAPTILER_API_KEY=... is used instead when one is given.
String get _tileUrl => mapTilerConfigured
    ? 'https://api.maptiler.com/maps/dataviz-dark/{z}/{x}/{y}@2x.png?key=$mapTilerApiKey'
    : 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png';

/// Map with pins and an optional road line. The camera fits everything shown.
class RouteMap extends StatelessWidget {
  const RouteMap({
    super.key,
    required this.pins,
    this.line = const [],
    this.height = 240,
    this.radius = 22,
    this.interactive = true,
    this.fitPadding = const EdgeInsets.all(56),
  });

  final List<MapPin> pins;
  final List<LatLng> line;
  final double height;
  final double radius;
  final bool interactive;

  /// Space kept clear around the pins, e.g. under a header drawn over the map.
  final EdgeInsets fitPadding;

  @override
  Widget build(BuildContext context) {
    final points = [...pins.map((pin) => pin.point), ...line];
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: SizedBox(
        height: height,
        child: Stack(
          children: [
            FlutterMap(
              // A new key per content refits the camera when the pins or route change.
              key: ValueKey(Object.hashAll(points)),
              options: MapOptions(
                backgroundColor: const Color(0xFF0E1419),
                initialCameraFit: points.length >= 2
                    ? CameraFit.coordinates(coordinates: points, padding: fitPadding, maxZoom: 15)
                    : null,
                initialCenter: points.isEmpty ? const LatLng(6.9271, 79.8612) : points.first,
                initialZoom: 13,
                interactionOptions: InteractionOptions(
                  flags: interactive ? InteractiveFlag.all & ~InteractiveFlag.rotate : InteractiveFlag.none,
                ),
              ),
              children: [
                TileLayer(
                  urlTemplate: _tileUrl,
                  subdomains: const ['a', 'b', 'c', 'd'],
                  retinaMode: false,
                  userAgentPackageName: 'com.evsmartcharge.ev_smartcharge',
                  maxNativeZoom: 19,
                ),
                if (line.length >= 2)
                  PolylineLayer(
                    polylines: [
                      Polyline(points: line, color: AppColors.cyan.withValues(alpha: 0.18), strokeWidth: 14),
                      Polyline(
                        points: line,
                        strokeWidth: 5,
                        gradientColors: const [AppColors.brand, AppColors.cyan],
                      ),
                    ],
                  ),
                MarkerLayer(
                  markers: [
                    for (final pin in pins)
                      Marker(
                        point: pin.point,
                        width: 150,
                        height: 64,
                        alignment: Alignment.topCenter,
                        child: _Pin(pin: pin),
                      ),
                  ],
                ),
                const RichAttributionWidget(
                  alignment: AttributionAlignment.bottomLeft,
                  attributions: [
                    TextSourceAttribution('OpenStreetMap contributors', prependCopyright: true),
                    TextSourceAttribution('CARTO', prependCopyright: true),
                  ],
                ),
              ],
            ),
            // Soft fade at the bottom edge so the map blends into the page.
            IgnorePointer(
              child: Align(
                alignment: Alignment.bottomCenter,
                child: Container(
                  height: 36,
                  decoration: const BoxDecoration(
                    gradient: LinearGradient(
                      colors: [Color(0x00070B10), Color(0x88070B10)],
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Pin extends StatelessWidget {
  const _Pin({required this.pin});
  final MapPin pin;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          padding: EdgeInsets.symmetric(horizontal: 9, vertical: pin.emphasis ? 6 : 4),
          decoration: BoxDecoration(
            color: const Color(0xEE0F161E),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: pin.color.withValues(alpha: 0.9), width: pin.emphasis ? 1.6 : 1),
            boxShadow: [BoxShadow(color: pin.color.withValues(alpha: 0.35), blurRadius: pin.emphasis ? 16 : 8)],
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (pin.icon != null) ...[
                Icon(pin.icon, size: 14, color: pin.color),
                const SizedBox(width: 5),
              ],
              Flexible(
                child: Text(
                  pin.label,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: AppColors.ink,
                    fontSize: pin.emphasis ? 12.5 : 11,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 3),
        Container(
          width: pin.emphasis ? 14 : 11,
          height: pin.emphasis ? 14 : 11,
          decoration: BoxDecoration(
            color: pin.color,
            shape: BoxShape.circle,
            border: Border.all(color: const Color(0xFF070B10), width: 2.5),
            boxShadow: [BoxShadow(color: pin.color.withValues(alpha: 0.7), blurRadius: 12, spreadRadius: 1)],
          ),
        ),
      ],
    );
  }
}

/// Opens Google Maps (app or web) with driving directions, through the charger when one is given.
Future<bool> openDirections({required LatLng destination, LatLng? origin, LatLng? via}) {
  final params = <String, String>{
    'api': '1',
    'travelmode': 'driving',
    'destination': '${destination.latitude},${destination.longitude}',
    if (origin != null) 'origin': '${origin.latitude},${origin.longitude}',
    if (via != null) 'waypoints': '${via.latitude},${via.longitude}',
  };
  final uri = Uri.https('www.google.com', '/maps/dir/', params);
  return launchUrl(uri, mode: LaunchMode.externalApplication);
}
