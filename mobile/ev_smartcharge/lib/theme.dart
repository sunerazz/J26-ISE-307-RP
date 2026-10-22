import 'package:flutter/material.dart';

/// Dark premium palette: deep navy surfaces, an electric emerald→cyan accent, champagne highlights.
/// The *Soft colours are translucent tints for chips and icon wells on dark surfaces.
class AppColors {
  static const background = Color(0xFF070B10);
  static const surface = Color(0xFF0F161E);
  static const surfaceHigh = Color(0xFF17212C);
  static const line = Color(0xFF223040);

  static const ink = Color(0xFFF2F6FA);
  static const muted = Color(0xFF8D9CAE);

  static const brand = Color(0xFF2EE6A6);
  static const brandDark = Color(0xFF14B883);
  static const brandSoft = Color(0x262EE6A6);
  static const cyan = Color(0xFF3BC7FF);
  static const gold = Color(0xFFE8C37E);
  static const goldSoft = Color(0x26E8C37E);

  static const good = Color(0xFF34D399);
  static const goodSoft = Color(0x2634D399);
  static const warn = Color(0xFFFBBF24);
  static const warnSoft = Color(0x26FBBF24);
  static const bad = Color(0xFFF87171);
  static const badSoft = Color(0x26F87171);
  static const info = Color(0xFF60A5FA);
  static const infoSoft = Color(0x2660A5FA);
  static const neutralSoft = Color(0x1AFFFFFF);

  static const accentGradient = LinearGradient(
    colors: [brand, cyan],
    begin: Alignment.centerLeft,
    end: Alignment.centerRight,
  );
}

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: AppColors.brand,
    brightness: Brightness.dark,
    primary: AppColors.brand,
    onPrimary: const Color(0xFF04130D),
    secondary: AppColors.cyan,
    surface: AppColors.surface,
    onSurface: AppColors.ink,
  );
  final base = ThemeData(colorScheme: scheme, useMaterial3: true, brightness: Brightness.dark);
  final text = base.textTheme.apply(bodyColor: AppColors.ink, displayColor: AppColors.ink);
  return base.copyWith(
    scaffoldBackgroundColor: AppColors.background,
    textTheme: text.copyWith(
      headlineMedium: text.headlineMedium?.copyWith(fontWeight: FontWeight.w800, letterSpacing: -0.6),
      titleLarge: text.titleLarge?.copyWith(fontWeight: FontWeight.w800, letterSpacing: -0.3),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.background,
      foregroundColor: AppColors.ink,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: AppColors.ink, letterSpacing: -0.4),
    ),
    cardTheme: CardThemeData(
      color: AppColors.surface,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(22),
        side: const BorderSide(color: AppColors.line),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.brand,
        foregroundColor: const Color(0xFF04130D),
        disabledBackgroundColor: AppColors.surfaceHigh,
        minimumSize: const Size.fromHeight(56),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
        textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800, letterSpacing: 0.2),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.ink,
        minimumSize: const Size.fromHeight(50),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        side: const BorderSide(color: AppColors.line),
        textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
      ),
    ),
    textButtonTheme: TextButtonThemeData(style: TextButton.styleFrom(foregroundColor: AppColors.brand)),
    chipTheme: base.chipTheme.copyWith(
      backgroundColor: AppColors.surfaceHigh,
      selectedColor: AppColors.brandSoft,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      side: const BorderSide(color: AppColors.line),
      labelStyle: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.ink),
      checkmarkColor: AppColors.brand,
    ),
    sliderTheme: base.sliderTheme.copyWith(
      inactiveTrackColor: AppColors.surfaceHigh,
      trackHeight: 8,
      overlayColor: AppColors.brandSoft,
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: SegmentedButton.styleFrom(
        backgroundColor: AppColors.surface,
        selectedBackgroundColor: AppColors.brandSoft,
        selectedForegroundColor: AppColors.brand,
        side: const BorderSide(color: AppColors.line),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.surfaceHigh,
      hintStyle: const TextStyle(color: AppColors.muted),
      prefixIconColor: AppColors.muted,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide.none),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide.none),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: AppColors.brand, width: 1.4),
      ),
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: AppColors.surface,
      showDragHandle: true,
      dragHandleColor: AppColors.line,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(28))),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: AppColors.surface,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
    ),
    listTileTheme: const ListTileThemeData(iconColor: AppColors.muted, textColor: AppColors.ink),
    dividerTheme: const DividerThemeData(color: AppColors.line, thickness: 1),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? AppColors.background : AppColors.muted),
      trackColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? AppColors.brand : AppColors.surfaceHigh),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: AppColors.surface,
      indicatorColor: AppColors.brandSoft,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      height: 70,
      iconTheme: WidgetStateProperty.resolveWith(
        (states) => IconThemeData(color: states.contains(WidgetState.selected) ? AppColors.brand : AppColors.muted),
      ),
      labelTextStyle: WidgetStateProperty.resolveWith(
        (states) => TextStyle(
          fontSize: 12,
          color: states.contains(WidgetState.selected) ? AppColors.ink : AppColors.muted,
          fontWeight: states.contains(WidgetState.selected) ? FontWeight.w800 : FontWeight.w500,
        ),
      ),
    ),
    snackBarTheme: const SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: AppColors.surfaceHigh,
      contentTextStyle: TextStyle(color: AppColors.ink),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(color: AppColors.brand),
  );
}
