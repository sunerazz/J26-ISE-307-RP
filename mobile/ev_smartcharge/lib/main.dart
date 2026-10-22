import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app_state.dart';
import 'shell.dart';
import 'theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const SmartChargeApp());
}

class SmartChargeApp extends StatelessWidget {
  const SmartChargeApp({super.key, this.state});

  /// Lets tests supply their own state.
  final AppState? state;

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => state ?? (AppState()..load()),
      child: MaterialApp(
        title: 'EV SmartCharge',
        debugShowCheckedModeBanner: false,
        theme: buildTheme(),
        home: const HomeShell(),
      ),
    );
  }
}
