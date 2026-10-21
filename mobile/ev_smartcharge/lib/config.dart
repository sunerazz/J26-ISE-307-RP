/// Public API root. Pass it when you build or run the app:
/// flutter run --dart-define=API_BASE_URL=https://your-app.up.railway.app
const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://127.0.0.1:8000',
);

class PlacePreset {
  const PlacePreset(this.name, this.latitude, this.longitude);
  final String name;
  final double latitude;
  final double longitude;
}

/// Approximate area centres for the trip form. They are not charger locations.
const places = <PlacePreset>[
  PlacePreset('Fort, Colombo 01', 6.9339, 79.8500),
  PlacePreset('Kollupitiya', 6.9110, 79.8510),
  PlacePreset('Bambalapitiya', 6.8890, 79.8560),
  PlacePreset('Wellawatte', 6.8740, 79.8600),
  PlacePreset('Borella', 6.9150, 79.8780),
  PlacePreset('Dehiwala', 6.8510, 79.8650),
  PlacePreset('Mount Lavinia, Colombo', 6.8300, 79.8650),
  PlacePreset('Nugegoda', 6.8649, 79.8997),
];

const connectors = <String>[
  'CHAdeMO',
  'Type 1 (J1772)',
  'Type 2 socket',
  'CCS2 (DC)',
];
