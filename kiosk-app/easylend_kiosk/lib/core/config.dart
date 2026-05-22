import 'package:flutter/foundation.dart';

class AppConfig {
  static String get baseUrl => kDebugMode ? 'http://10.0.2.2:8000/api/v1' : 'http://10.0.2.147/api/v1';
  static String get visionBaseUrl => kDebugMode ? 'http://10.0.2.2:8000' : 'http://10.0.2.146';
}