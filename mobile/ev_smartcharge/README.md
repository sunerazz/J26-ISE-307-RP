# EV SmartCharge

Phone app for the Colombo station recommendation API.

## How it is organised

- `lib/screens/plan_page.dart` — pick start (or GPS) and destination, set battery, choose how much to charge.
- `lib/screens/results_page.dart` — best charger, extra drive, battery on arrival, charge time and cost, reasons, other chargers with why they were skipped, and Google Maps navigation through the charger.
- `lib/screens/stations_page.dart` — every charger on a map, with plugs, power and listed prices.
- `lib/screens/history_page.dart` — past trips; tap one to plan it again.
- `lib/screens/settings_page.dart` — car (preset or custom), plug, safety reserve, electricity price and charging losses. Saved once and used for every search.
- `lib/app_state.dart` — trip draft, search, location and history; `lib/widgets/` — shared UI.

Car details are stored on the phone. Reserve, price and charging efficiency are also backed up to Supabase when sign-in works.

Run the tests with `flutter test`.

The default API is `https://j26-ise-307-rp.onrender.com`. The Supabase URL, anon public key, and MapTiler key are the defaults in `lib/config.dart`. A `--dart-define` flag replaces a default when you pass one.

## Environment values

Pass these on the computer that builds the app. Do not put the Supabase service-role key or a MapTiler secret in source code.

```powershell
flutter pub get
flutter run `
  --dart-define=API_BASE_URL=https://j26-ise-307-rp.onrender.com `
  --dart-define=SUPABASE_URL=https://YOUR-PROJECT.supabase.co `
  --dart-define=SUPABASE_ANON_KEY=YOUR-ANON-KEY `
  --dart-define=MAPTILER_API_KEY=YOUR-MAPTILER-KEY
```

The same three `--dart-define` flags belong on `flutter build apk`.

## Supabase

1. Create a project at https://supabase.com.
2. Open **SQL Editor**, paste `supabase/schema.sql`, and run it.
3. Open **Authentication → Sign In / Providers** and turn on **Anonymous Sign-Ins**.
4. Open **Project Settings → API**. Copy the project URL and the `anon` `public` key.

## MapTiler

1. Create a key at https://cloud.maptiler.com/account/keys/.
2. Pass it as `MAPTILER_API_KEY`.

Road distance and the blue line still come from the API’s OSRM route. MapTiler only draws the background map.
