# EV SmartCharge

Phone app for the Colombo station recommendation API.

The home screen follows the research dashboard layout: origin, destination, battery, connector, a map, one recommended listing, and the other candidates. Waiting time, congestion, and cost stay unavailable unless the API actually has those values. The sample numbers in the design mock are not stored in the app.

## Run on a phone or emulator

From this folder, after the API is reachable:

```powershell
flutter pub get
flutter run --dart-define=API_BASE_URL=https://YOUR-APP.up.railway.app
```

An installable Android package:

```powershell
flutter build apk --dart-define=API_BASE_URL=https://YOUR-APP.up.railway.app
```

The APK is written to `build/app/outputs/flutter-apk/app-release.apk`.

`127.0.0.1` points at the phone itself. Use the Railway URL, or your computer's LAN address, when the API is running on a computer.

Place names such as Fort and Mount Lavinia are approximate centres for the form. Station names and coordinates come from the API.
