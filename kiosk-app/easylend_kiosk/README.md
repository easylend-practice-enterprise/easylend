# 🛠️ EasyLend: Kiosk App (Operational Guide)

> **Note:** For high-level architecture, business logic, and system-wide design decisions, please refer to the **[Global Documentation Index](../../docs/INDEX.md)**.

This directory contains the Flutter-based kiosk application for Android tablets.

## Prerequisites
- Flutter SDK (3.11+)
- Android Studio / ADB

## Development Setup

```bash
# Install dependencies
flutter pub get

# Run on connected device/emulator
flutter run
```

## Emulator Kiosk Mode Setup
To reproduce lock task behavior on an emulator:
```bash
adb shell dpm set-device-owner be.school.easylend_kiosk/.AdminReceiver
```

## Deployment
```bash
# Build Android APK
flutter build apk --release
```
