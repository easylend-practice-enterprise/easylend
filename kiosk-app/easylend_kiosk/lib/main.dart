import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'screens/auth/login_screen.dart';
import 'screens/shell/screen_switcher.dart';
import 'theme.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  // This widget is the root of your application.
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'EasyLend Kiosk',
      theme: AppTheme.dark,
      home: kDebugMode ? const ScreenSwitcher() : const LoginScreen(),
    );
  }
}
