import 'package:flutter/foundation.dart';

class DebugConfig {
  static const bool debugEnabled = true;

  static bool get isActive => debugEnabled && kDebugMode;
}
