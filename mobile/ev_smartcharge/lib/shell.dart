import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app_state.dart';
import 'screens/history_page.dart';
import 'screens/plan_page.dart';
import 'screens/settings_page.dart';
import 'screens/stations_page.dart';

/// Bottom-tab layout. Tabs keep their scroll position and inputs when you switch.
class HomeShell extends StatelessWidget {
  const HomeShell({super.key});

  static const planTab = 0;
  static const stationsTab = 1;
  static const historyTab = 2;
  static const settingsTab = 3;

  static TabSwitcher of(BuildContext context) => TabSwitcher(context.read<AppState>());

  @override
  Widget build(BuildContext context) {
    final tab = context.select<AppState, int>((state) => state.tab);
    return Scaffold(
      body: IndexedStack(
        index: tab,
        children: const [PlanPage(), StationsPage(), HistoryPage(), SettingsPage()],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: context.read<AppState>().goToTab,
        destinations: const [
          NavigationDestination(icon: Icon(Icons.bolt_outlined), selectedIcon: Icon(Icons.bolt), label: 'Plan'),
          NavigationDestination(
            icon: Icon(Icons.ev_station_outlined),
            selectedIcon: Icon(Icons.ev_station),
            label: 'Chargers',
          ),
          NavigationDestination(icon: Icon(Icons.history_rounded), label: 'History'),
          NavigationDestination(
            icon: Icon(Icons.settings_outlined),
            selectedIcon: Icon(Icons.settings),
            label: 'Settings',
          ),
        ],
      ),
    );
  }
}

class TabSwitcher {
  TabSwitcher(this._state);
  final AppState _state;

  void goTo(int tab) => _state.goToTab(tab);
}
