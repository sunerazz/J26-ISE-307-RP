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

/// Background map with pins and an optional road line. The camera fits everything shown.
class RouteMap extends StatelessWidget {
  const RouteMap({super.key, required this.pins, this.line = const [], this.height = 240});

  final List<MapPin> pins;
  final List<LatLng> line;
  final double height;

  @override
  Widget build(BuildContext context) {
    final points = [...pins.map((pin) => pin.point), ...line];
    return ClipRRect(
      borderRadius: BorderRadius.circular(20),
      child: SizedBox(
        height: height,
        child: FlutterMap(
          // A new key per content refits the camera when the pins or route change.
          key: ValueKey(Object.hashAll(points)),
          options: MapOptions(
            initialCameraFit: points.length >= 2
                ? CameraFit.coordinates(coordinates: points, padding: const EdgeInsets.all(48), maxZoom: 16)
                : null,
            initialCenter: points.isEmpty ? const LatLng(6.9, 79.86) : points.first,
            initialZoom: 13,
            interactionOptions: const InteractionOptions(flags: InteractiveFlag.all & ~InteractiveFlag.rotate),
          ),
          children: [
            TileLayer(
              urlTemplate: mapTilerConfigured
                  ? 'https://api.maptiler.com/maps/streets-v2/{z}/{x}/{y}.png?key=$mapTilerApiKey'
                  : 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
              userAgentPackageName: 'com.evsmartcharge.ev_smartcharge',
            ),
            if (line.length >= 2)
              PolylineLayer(
                polylines: [
                  Polyline(points: line, color: Colors.white, strokeWidth: 8),
                  Polyline(points: line, color: AppColors.info, strokeWidth: 5),
                ],
              ),
            MarkerLayer(
              markers: [
                for (final pin in pins)
                  Marker(
                    point: pin.point,
                    width: 140,
                    height: 56,
                    alignment: Alignment.topCenter,
                    child: _Pin(pin: pin),
                  ),
              ],
            ),
            RichAttributionWidget(
              attributions: [
                if (mapTilerConfigured) const TextSourceAttribution('MapTiler', prependCopyright: true),
                const TextSourceAttribution('OpenStreetMap contributors', prependCopyright: true),
              ],
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
          padding: EdgeInsets.symmetric(horizontal: 8, vertical: pin.emphasis ? 6 : 4),
          decoration: BoxDecoration(
            color: pin.color,
            borderRadius: BorderRadius.circular(10),
            boxShadow: const [BoxShadow(color: Color(0x33000000), blurRadius: 4, offset: Offset(0, 2))],
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (pin.icon != null) ...[
                Icon(pin.icon, size: 14, color: Colors.white),
                const SizedBox(width: 4),
              ],
              Flexible(
                child: Text(
                  pin.label,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: pin.emphasis ? 12.5 : 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
        ),
        CustomPaint(size: const Size(10, 6), painter: _Tail(pin.color)),
      ],
    );
  }
}

class _Tail extends CustomPainter {
  _Tail(this.color);
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final path = Path()
      ..moveTo(0, 0)
      ..lineTo(size.width, 0)
      ..lineTo(size.width / 2, size.height)
      ..close();
    canvas.drawPath(path, Paint()..color = color);
  }

  @override
  bool shouldRepaint(_Tail oldDelegate) => oldDelegate.color != color;
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
