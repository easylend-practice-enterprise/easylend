import 'package:flutter/material.dart';

class AppColors {
  AppColors._();

  static const Color primary = Color.fromARGB(255, 87, 87, 87);
  // Primary brand/action color, used for main buttons and prominent UI elements.

  static const Color accent = Color.fromARGB(255, 14, 115, 209);
  // Accent/secondary color, used for smaller interactive elements and visual highlights.

  static const Color background = Color.fromARGB(255, 0, 0, 0);
  // App background color for the scaffold and full-screen areas.

  static const Color surface = Color.fromARGB(255, 90, 90, 90);
  // Surface color used for cards, panels, app bars, and other elevated surfaces.

  static const Color text = Color.fromARGB(255, 255, 255, 255);
  // Primary text color on dark surfaces, used for headings, labels, and key text.

  static const Color onPrimary = Color.fromARGB(255, 255, 0, 200);
  // Foreground color (text/icons) used on primary-colored components like buttons.

  static const Color divider = Color.fromARGB(255, 255, 0, 0);
  // Divider/border color used for outlines and thin separators in the UI.
}

class AppTheme {
  AppTheme._();

  static final TextTheme _textTheme = TextTheme(
    displayLarge: TextStyle(
      fontSize: 48,
      fontWeight: FontWeight.bold,
      color: AppColors.text,
    ),
    displayMedium: TextStyle(
      fontSize: 36,
      fontWeight: FontWeight.bold,
      color: AppColors.text,
    ),
    headlineMedium: TextStyle(
      fontSize: 20,
      fontWeight: FontWeight.w700,
      color: AppColors.text,
    ),
    bodyLarge: TextStyle(fontSize: 16, color: Colors.white70),
    bodyMedium: TextStyle(fontSize: 14, color: Colors.white70),
    labelLarge: TextStyle(
      fontSize: 14,
      fontWeight: FontWeight.w600,
      color: AppColors.text,
    ),
  );

  static final ThemeData dark = ThemeData(
    brightness: Brightness.dark,
    colorScheme: const ColorScheme.dark(
      primary: AppColors.primary,
      secondary: AppColors.accent,
      surface: AppColors.surface,
      onPrimary: Colors.black,
      onSurface: Colors.white,
    ),
    scaffoldBackgroundColor: AppColors.background,
    canvasColor: AppColors.surface,
    primaryColor: AppColors.primary,
    fontFamily: 'Roboto',
    textTheme: _textTheme,
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.background,
      elevation: 0,
      centerTitle: true,
      titleTextStyle: TextStyle(
        color: AppColors.text,
        fontSize: 18,
        fontWeight: FontWeight.bold,
      ),
      iconTheme: IconThemeData(color: AppColors.text),
    ),
    bottomAppBarTheme: const BottomAppBarThemeData(color: AppColors.surface),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.primary,
        foregroundColor: AppColors.onPrimary,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        minimumSize: const Size.fromHeight(48),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(foregroundColor: AppColors.text),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.text,
        side: const BorderSide(color: AppColors.divider),
      ),
    ),
  );
}

// Convenience accessors used by UI code until components are fully refactored
extension AppThemeExt on BuildContext {
  ThemeData get appTheme => Theme.of(this);
  ColorScheme get colors => Theme.of(this).colorScheme;
}
