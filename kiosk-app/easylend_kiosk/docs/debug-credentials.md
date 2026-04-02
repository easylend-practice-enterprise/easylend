# Debug Mode Configuration

> **WARNING: These features are for DEBUG builds only.**
> They are disabled in release/production builds.

## Unified Debug Toggle

All debug features are controlled by a single toggle in `lib/config/debug_credentials.dart`:

```dart
class DebugConfig {
  /// Master switch for all debug features.
  /// In release builds, this is always false regardless of this value.
  static const bool debugEnabled = true;  // <-- Toggle this
}
```

When `debugEnabled = false` OR the app is running in release mode, all debug features are disabled.

## Test Credentials

### Standard User
| Field | Value |
|-------|-------|
| Username | `testuser` |
| Password | `testpass123` |
| Role | `user` |

### Admin User
| Field | Value |
|-------|-------|
| Username | `admin` |
| Password | `admin123` |
| Role | `admin` |

**Note:** Admin features may not work without a connected backend.

## Debug Features

### Login Screen
- Shows **"Debug Login"** button (orange) when debug is active
- Opens a credentials dialog for testing authentication

### Asset Catalog Screen
- Bottom navigation is simplified to only show **Scan Aztec** button
- Transfer and History buttons are hidden in debug mode

### Screen Switcher (`/debug`)
- Simplified to show only the **Scan Aztec** button
- Shows a banner indicating debug mode is active

## How to Disable Debug Mode

Set `debugEnabled = false` in `lib/config/debug_credentials.dart`:

```dart
static const bool debugEnabled = false;
```

## Security Notes

- The `debugEnabled` flag uses `assert()` statements that are stripped in release builds
- Debug login button only appears when `DebugConfig.isActive` is true
- In release builds, the app falls back to normal NFC/PIN login flow
