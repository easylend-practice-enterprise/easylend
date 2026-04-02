import 'package:flutter/material.dart';

class AppColors {
  AppColors._();
  // Primary color - used for buttons and major UI elements
  static Color get primary => const Color.fromARGB(255, 14, 115, 209);
  // Accent color - used for highlights and secondary actions
  static Color get accent => const Color.fromARGB(255, 0, 229, 255);
  // Background color - main screen background
  static Color get background => const Color.fromARGB(255, 0, 0, 0);
  // Surface color - cards, dialogs, bottom navigation
  static Color get surface => const Color.fromARGB(255, 24, 24, 24);
  // Text color - primary text on dark backgrounds
  static Color get text => const Color.fromARGB(255, 255, 255, 255);
  // On-primary color - text color on primary-colored buttons
  static Color get onPrimary => const Color.fromARGB(255, 255, 255, 255);
  // Divider color - subtle separator lines
  static Color get divider => const Color.fromARGB(255, 64, 64, 64);
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
    colorScheme: ColorScheme.dark(
      primary: AppColors.primary,
      secondary: AppColors.accent,
      surface: AppColors.surface,
      onPrimary: AppColors.onPrimary,
      onSurface: Colors.white,
    ),
    scaffoldBackgroundColor: AppColors.background,
    canvasColor: AppColors.surface,
    primaryColor: AppColors.primary,
    fontFamily: 'Roboto',
    textTheme: _textTheme,
    appBarTheme: AppBarTheme(
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
    bottomAppBarTheme: BottomAppBarThemeData(color: AppColors.surface),
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
        side: BorderSide(color: AppColors.divider),
      ),
    ),
  );
}

// Convenience accessors used by UI code until components are fully refactored
extension AppThemeExt on BuildContext {
  ThemeData get appTheme => Theme.of(this);
  ColorScheme get colors => Theme.of(this).colorScheme;
}
