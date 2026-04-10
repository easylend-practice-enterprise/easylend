# EasyLend Kiosk App

## Emulator Kiosk Mode Setup (Android)

Use this when you want to reproduce lock task (kiosk) behavior on an Android emulator.

Prerequisites:

- Android emulator is running and visible via `adb devices`
- Build variant uses this app ID: `be.easylend.easylend_kiosk`
- Device admin receiver class: `be.easylend.easylend_kiosk/.KioskDeviceAdminReceiver`

### 1) Clean emulator owner state (recommended before setup)

Run:

    adb shell dpm remove-active-admin be.easylend.easylend_kiosk/.KioskDeviceAdminReceiver

If the command says admin is not active, continue.

### 2) Install and set app as device owner

From `kiosk-app/easylend_kiosk`:

    flutter clean
    flutter pub get
    flutter run -d emulator-5554

Stop the app once installed, then run:

    adb shell dpm set-device-owner be.easylend.easylend_kiosk/.KioskDeviceAdminReceiver

Expected result includes:

    Success: Device owner set to package ComponentInfo{be.easylend.easylend_kiosk/be.easylend.easylend_kiosk.KioskDeviceAdminReceiver}

### 3) Start app and verify kiosk policies are applied

Run app again:

    flutter run -d emulator-5554

The app configures lock task allowlisting in `MainActivity` during startup.
Implementation references:

- `android/app/src/main/AndroidManifest.xml` (`android:lockTaskMode="if_whitelisted"` + receiver)
- `android/app/src/main/kotlin/be/easylend/easylend_kiosk/MainActivity.kt` (`setLockTaskPackages`)
- `android/app/src/main/kotlin/be/easylend/easylend_kiosk/KioskDeviceAdminReceiver.kt`

### 4) Troubleshooting

- Error: device owner can only be set on a fresh device
  - Wipe emulator data, boot again, reinstall app, rerun set-device-owner.
- Error: not allowed to set the device owner because there are already several users
  - Use a fresh emulator image/user profile.
- App does not enter kiosk behavior
  - Confirm package name matches `be.easylend.easylend_kiosk`.
  - Confirm receiver class path exactly matches `.KioskDeviceAdminReceiver`.

### 5) Reset/remove kiosk mode from emulator

Run:

    adb shell dpm remove-active-admin be.easylend.easylend_kiosk/.KioskDeviceAdminReceiver

If state is stuck, wipe emulator data and recreate the AVD.

## Project File Structure

- `app/`  Core app setup (themes, routing).

- `models/`  Data models and enums.
  - `api/`: API response models.
  - `assets/`: Asset-related models.
  - `auth/`: Authentication-related models.

- `providers/`  State management layer (e.g., blocs/controllers).

- `screens/`  Top-level screens of the app.
  - `auth/`: Login and authentication screens.
  - `dashboard/`: Main dashboard and asset management screens.
  - `modals/`: Modal dialogs and overlays.

- `services/`  Business logic and service classes.
  - `api/`: API communication services.
  - `auth/`: Authentication services.
  - `local/`: Local storage and device-specific services.

- `utils/`  Utility classes, constants, and helpers.
  - `constants/`: Global constants (colors, strings, dimensions).
  - `extensions/`: Extension methods for Dart/Flutter classes.
  - `helpers/`: Helper classes for common tasks.

- `widgets/`  Reusable UI components.
  - `buttons/`: Reusable button widgets.
  - `cards/`: Reusable card widgets.
  - `shared/`: Utility widgets (e.g., timers, animations).
