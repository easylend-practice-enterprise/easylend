import 'package:flutter/material.dart';

class AppColors {
  AppColors._();
  // Use runtime getters so colors can update on hot reload.
  static Color get primary => const Color.fromARGB(255, 87, 87, 87);
  // used for buttons and major ui elements
  static Color get accent => const Color.fromARGB(255, 14, 115, 209);
  // used for smaller ui elements and
  static Color get background => const Color.fromARGB(255, 0, 0, 0);
  // used as background color
  static Color get surface => const Color.fromARGB(255, 90, 90, 90);
  //used as a transition between screen transitions
  static Color get text => const Color.fromARGB(255, 255, 255, 255);
  // secondary/utility text color, used for subtitles and exit buttons
  static Color get onPrimary => const Color.fromARGB(255, 255, 0, 200);
  // thin divider/separator used across the UI
  static Color get divider => const Color.fromARGB(255, 255, 0, 0);
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
