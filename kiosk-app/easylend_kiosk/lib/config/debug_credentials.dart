import 'package:flutter/foundation.dart';

/// Centralized debug mode configuration.
///
/// Set [debugEnabled] to true to enable debug features across the app.
/// This should ALWAYS be false in production/release builds.
class DebugConfig {
  /// Master switch for all debug features.
  /// In release builds, this is always false regardless of this value.
  static const bool debugEnabled = true;

  /// Whether debug mode is truly active (debugEnabled AND running in debug mode)
  static bool get isActive => debugEnabled && kDebugMode;
}
