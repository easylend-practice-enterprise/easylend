# Easylend kiosk app

## Project File Structure

- `app/`  Core app setup (themes, routing).

- `models/`  Data models and enums.
  - `api/`: API response models.
  - `assets/`: Asset-related models.
  - `auth/`: Authentication-related models.

- `providers/`  Riverpod providers for state management.

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
