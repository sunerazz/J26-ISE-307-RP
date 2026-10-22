import 'models.dart';

/// Public decision API. Override with --dart-define=API_BASE_URL=...
const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'https://j26-ise-307-rp.onrender.com',
);

/// Supabase project URL. Override with --dart-define=SUPABASE_URL=...
const String supabaseUrl = String.fromEnvironment(
  'SUPABASE_URL',
  defaultValue: 'https://auxyonwvfpjfonzhubgf.supabase.co',
);

/// Supabase anon public key. Do not replace this with a secret or service-role key.
const String supabaseAnonKey = String.fromEnvironment(
  'SUPABASE_ANON_KEY',
  defaultValue:
      'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF1eHlvbnd2ZnBmam9uemh1YmdmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTI1OTA0NjgsImV4cCI6MjEwODE2NjQ2OH0.lmEKFrHviVfH5gXZSw0uRFgm1C5t8Pw4TtXfjCVS2xs',
);

/// Optional MapTiler key, passed with --dart-define=MAPTILER_API_KEY=...
/// Empty by default: the map uses CARTO's free dark tiles, which need no key.
/// (The key previously built in was refused by MapTiler with HTTP 403.)
const String mapTilerApiKey = String.fromEnvironment('MAPTILER_API_KEY');

bool get supabaseConfigured => supabaseUrl.isNotEmpty && supabaseAnonKey.isNotEmpty;
bool get mapTilerConfigured => mapTilerApiKey.isNotEmpty;

/// Trip start and end points. Charger areas use the Component 4 pin (or the mean of
/// the pins in that area). Nugegoda, Rajagiriya, Malabe and Panadura are the
/// queue-model towns; the inventory has no charger pin there.
const places = <Place>[
  Place('Colombo 01', 6.93374, 79.84411),
  Place('Nugegoda', 6.86490, 79.89970),
  Place('Rajagiriya', 6.90900, 79.89600),
  Place('Malabe', 6.90630, 79.96960),
  Place('Panadura', 6.71320, 79.90260),
  Place('Colombo 02', 6.91750, 79.85580),
  Place('Colombo 07', 6.91145, 79.86512),
  Place('Colombo 3', 6.91657, 79.84932),
  Place('Colombo 6', 6.87094, 79.86528),
  Place('Colombo 9', 6.93363, 79.87916),
  Place('Maradana / Colombo 10', 6.92936, 79.86104),
  Place('Battaramulla', 6.90845, 79.93925),
  Place('Pannipitiya', 6.84284, 79.95336),
  Place('Dehiwala', 6.84256, 79.88459),
  Place('Dehiwala-Mount Lavinia', 6.86217, 79.86513),
  Place('Moratuwa', 6.79517, 79.88741),
  Place('Wattala', 6.98869, 79.89691),
  Place('Homagama', 6.82584, 80.03807),
  Place('Negombo', 7.18682, 79.85954),
  Place('Gampaha', 7.00639, 79.95439),
  Place('Ja-Ela', 7.05990, 79.89651),
  Place('Kalutara', 6.62528, 79.94220),
  Place('Beruwala', 6.45299, 79.99214),
  Place('Galle', 6.06932, 80.23406),
  Place('Hikkaduwa', 6.13055, 80.11700),
  Place('Matara', 5.96849, 80.53129),
  Place('Kandy', 7.29850, 80.64356),
  Place('Peradeniya', 7.26841, 80.58078),
  Place('Katugastota', 7.32478, 80.64447),
  Place('Nuwara Eliya', 6.96580, 80.77193),
  Place('Kegalle', 7.24829, 80.34108),
  Place('Mawanella', 7.24773, 80.46596),
  Place('Avissawella', 6.94759, 80.21437),
  Place('Dambulla', 7.82372, 80.65469),
  Place('Habarana', 8.03740, 80.75116),
  Place('Anuradhapura', 8.32699, 80.39574),
  Place('Puttalam', 8.02802, 79.83712),
  Place('Trincomalee', 8.62308, 81.21150),
  Place('Batticaloa', 7.72006, 81.71013),
  Place('Tissamaharama', 6.27441, 81.34010),
];

Place? placeNamed(String name) {
  for (final place in places) {
    if (place.name == name) return place;
  }
  // Names used by earlier versions of the app.
  const renamed = {
    'Fort, Colombo 01': 'Colombo 01',
    'Colombo Fort': 'Colombo 01',
    'Maradana': 'Maradana / Colombo 10',
    'Mount Lavinia': 'Dehiwala-Mount Lavinia',
    'Mount Lavinia, Colombo': 'Dehiwala-Mount Lavinia',
    'Pettah': 'Colombo 01',
    'Kollupitiya': 'Colombo 3',
    'Borella': 'Colombo 07',
    'Bambalapitiya': 'Colombo 6',
    'Wellawatte': 'Colombo 6',
  };
  final next = renamed[name];
  return next == null ? null : placeNamed(next);
}

class Plug {
  const Plug(this.label, this.apiValue, this.hint);
  final String label;

  /// Matched against the station's connector list by the API (case-insensitive substring).
  final String apiValue;
  final String hint;
}

const plugs = <Plug>[
  Plug('CHAdeMO', 'CHAdeMO', 'Fast DC plug on Nissan Leaf and older Japanese EVs'),
  Plug('CCS2', 'CCS2', 'Fast DC plug on most new cars (BYD, MG, Hyundai, Kia)'),
  Plug('Type 2', 'Type 2', 'AC plug, slower home-style charging'),
  Plug('Type 1', 'Type 1', 'Older AC plug (J1772)'),
];

Plug plugFor(String apiValue) =>
    plugs.firstWhere((plug) => plug.apiValue == apiValue, orElse: () => plugs.first);

class CarPreset {
  const CarPreset(this.name, this.batteryKwh, this.consumption, this.plug);
  final String name;
  final double batteryKwh;
  final double consumption;
  final String plug;
}

/// Typical usable battery and city consumption. Drivers can adjust both in Settings.
const carPresets = <CarPreset>[
  CarPreset('Nissan Leaf (40 kWh)', 39, 16, 'CHAdeMO'),
  CarPreset('Nissan Leaf e+ (62 kWh)', 59, 17, 'CHAdeMO'),
  CarPreset('BYD Atto 3', 60, 17, 'CCS2'),
];

/// Kerb weight plus about 100 kg for driver and a passenger, for the energy model.
/// Manufacturer kerb weights: Leaf 40 kWh 1,580 kg; Leaf e+ 1,748 kg; Atto 3 1,750 kg.
double vehicleMassFor(String carName) {
  const masses = {
    'Nissan Leaf (40 kWh)': 1680.0,
    'Nissan Leaf e+ (62 kWh)': 1850.0,
    'BYD Atto 3': 1850.0,
  };
  return masses[carName] ?? 1750.0;
}
