# Implementation Plan: EasyLend Kiosk App

## Current Implementation State

**Last Updated:** 2026-04-02

### What's Built

| Item | Status | Notes |
| :--- | :--- | :--- |
| Project structure | ✅ Done | Basic Flutter project with screens/, providers/, models/, services/, utils/, widgets/ directories |
| pubspec.yaml | ✅ Done | camera, google_mlkit_barcode_scanning, cupertino_icons |
| theme.dart | ✅ Done | AppColors, AppTheme with dark mode |
| main.dart | ✅ Done | Debug/Prod split using kDebugMode |
| ScreenSwitcher | ✅ Done | Debug navigation tool for testing screens |
| LoginScreen | ✅ Partial | UI only - NFC animation, no NFC/API integration |
| AssetCatalogScreen | ✅ Partial | Mock data display, no API integration |
| ScanAztecScreen | ✅ Done | Working camera + ML Kit Aztec scanning |
| ReturnStatusScreen | ✅ Partial | UI only, hardcoded 65% progress |
| LendingCompleteScreen | ✅ Partial | UI only, no API integration |
| InactivityModal | ✅ Partial | UI only, no countdown logic |
| app.dart | ❌ Empty | Needs implementation |
| app_router.dart | ❌ Empty | Needs go_router setup |
| All providers | ❌ Empty | api_provider, auth_provider, asset_provider |
| All models | ❌ Empty | user, auth_response, asset, asset_status, api_response, error_response |
| All services | ❌ Empty | api_service, websocket_service, auth_service |
| secure_storage | ❌ Empty | |
| All utils/constants | ❌ Empty | colors, strings, dimensions, context_extensions, validation_helper, date_helper |
| All widgets | ❌ Empty | primary_button, secondary_button, asset_card, countdown_timer, nfc_scan_animation |

---

## Project Overview

High-Level Goals:

1. Security: 2FA for Admins and JWT-based session management for all users.
2. Hardware Synergy: Robust interaction with the Vision Box (locker system) via optimized polling.
3. Resilience: Graceful handling of hardware timeouts and offline states.

### Tools and Libraries Stack

| Category | Tool/Library | Purpose |
| :--- | :--- | :--- |
| Framework | Flutter | Android tablet target (landscape UI). |
| State Management | Riverpod | `flutter_riverpod` for global state (auth, assets, loans). |
| Networking | `dio` + `retrofit` | Type-safe HTTP client with JWT interceptors. |
| Hardware | `nfc_manager` | NFC badge reading. |
| Vision/Camera | `mobile_scanner` | Fast Aztec/barcode scanning via ML Kit. |
| Navigation | `go_router` | Declarative routing with secure Admin guards. |
| Secure Storage | `flutter_secure_storage` | JWT token storage. |

---

## Phase 1: Foundation & API Alignment

**Focus:** Environment setup and resolving specification gaps.

### ELP-36: Android project setup and dependencies

- [x] Initialize project with flavors (dev/prod)
- [x] Install `camera` and `google_mlkit_barcode_scanning` ✅ **Done**
- [ ] Install `dio`, `retrofit`, `flutter_riverpod`
- [ ] Install `nfc_manager` and `flutter_secure_storage`
- [ ] Add `go_router` for navigation

### ELP-37: Kiosk mode implementation

- [ ] Implement `startLockTask()` and hide system UI to prevent users from exiting the app.

### ELP-47: Auth & retry via interceptor

- [ ] Implement a `Dio` interceptor to handle `401 Unauthorized` by calling `POST /api/v1/auth/refresh` and retrying the original request.

### ELP-49: Error handling (network/hardware)

- [ ] Build a global "System Maintenance" overlay that triggers if the Health Check API fails or the Vision Box is reported offline.

---

## Phase 2: Authentication & Secure Admin Access

**Focus:** Implementing 2-step login and secure admin entry.

### ELP-38 & ELP-39: NFC integration

- [ ] Implement background listener for `POST /api/v1/auth/nfc`.
- [ ] Handle NFC tag detection and send to backend.

### ELP-40: Login screen & Admin 2FA

- [x] Login screen UI with NFC badge animation ✅ **Done (UI only)**
- [ ] Standard user: NFC badge + 4-digit PIN (API integration)
- [ ] Admin entry: Dedicated Admin NFC badge (unique UID) plus Admin PIN
- [ ] PIN entry screen (PIN_ENTRY not yet implemented)
- [ ] Audit logging: Every successful Admin login must trigger a log entry
- [ ] Inactivity: A 60-second timer triggers `POST /api/v1/auth/logout` and clears sensitive data from memory

---

## Phase 3: Asset Catalog & Role-Based UI

**Focus:** Navigational guards and data fetching.

### ELP-41 & ELP-48: Fetch assets

- [x] Asset catalog screen UI (mock data) ✅ **Done (mock data only)**
- [ ] API integration to fetch `/api/v1/equipment/catalog`
- [ ] Role logic: Use `go_router` redirects. If the JWT `role` claim is not `"ADMIN"`, block access to `/admin/*`.
- [ ] Standard view: Display category grid (e.g., "Handheld Scanners: 4 Available").
- [ ] Admin view: Full asset list showing who has which item and ability to force-open lockers.
- [ ] Riverpod providers for auth state and asset state

---

## Phase 4: Optimized Transaction Wizards

**Focus:** Managing the physical locker interaction cycle.

### ELP-42 & ELP-48: Checkout/return flow

- [ ] Implement `POST /api/v1/loans/checkout` with idempotency key
- [ ] Implement `POST /api/v1/loans/return/initiate`
- [ ] Polling strategy (exponential backoff):
  - 0–10s: poll every 2 seconds.
  - 10–30s: poll every 5 seconds.
  - 30–45s: poll every 10 seconds.
- [ ] Hard timeout handling: At the configured timeout, transition UI to a "Transaction Pending" screen and finalize in the background.
- [ ] WebSocket integration for Vision Box communication

### ELP-45 & ELP-46: Aztec integration

- [x] Aztec scanning with `mobile_scanner` ✅ **Done (ML Kit integration working)**
- [ ] On successful scan, call `POST /api/v1/loans/return/initiate`

---

## Phase 5: UX Polish & UI Details

**Focus:** Visual feedback and error recovery.

### ELP-43: UX (dialogs and errors)

- [ ] Create dialogs for "Locker Jammed," "Item Not Found," and "Unauthorized Return."
- [ ] Inactivity timeout modal with live countdown (currently static UI)

### ELP-44: UI polish

- [ ] Add animations, theming, and accessibility checks
- [ ] Ensure clear success/error states and concise copy
- [ ] Implement countdown timer logic in InactivityModal
- [ ] Implement countdown timer in LendingCompleteScreen
- [ ] All widget buttons and cards need implementation (currently empty files)

---

## Milestones

| Milestone | Target | Owner | Status |
| :--- | :--- | :--- | :--- |
| API contract & Phase 1 complete | TBD | Frontend & Backend | Not Started |
| Admin 2FA & secure auth verified | TBD | Security / Frontend | Not Started |
| E2E transaction (optimized polling) | TBD | Full Team | Not Started |
| Field readiness (kiosk mode test) | TBD | Hardware / QA | Not Started |

---

## Success Metrics

| Metric | Target | Measurement Method |
| :--- | :--- | :--- |
| Admin security | 100% | No entry without Admin NFC + PIN; all entries logged. |
| Transaction latency | < 12s | Time from NFC tap to "Locker Open" signal. |
| Network efficiency | Optimized | Polling frequency decreases over time to save resources. |
| System uptime | High | Circuit breaker / offline mode prevents app crashes. |

---

## Files Overview

```txt
lib/
├── main.dart                     ✅ Debug/prod entry split
├── theme.dart                    ✅ AppColors + AppTheme
├── app.dart                      ❌ Empty - needs app configuration
├── app_router.dart               ❌ Empty - needs go_router setup
├── screens/
│   ├── auth/
│   │   ├── login_screen.dart     ✅ Partial - UI only
│   │   └── pin_entry_screen.dart ❌ Empty
│   ├── dashboard/
│   │   ├── dashboard_screen.dart  ❌ Empty
│   │   ├── asset_catalog_screen.dart ✅ Partial - mock data
│   │   └── return_status_screen.dart ✅ Partial - hardcoded UI
│   ├── scan_aztec_screen.dart    ✅ Done - working camera + ML Kit
│   ├── lending_complete_screen.dart ✅ Partial - UI only
│   ├── shell/
│   │   └── screen_switcher.dart  ✅ Done - debug navigation
│   └── modals/
│       ├── inactivity_modal.dart          ✅ Partial - UI only
│       ├── inactivity_timeout_modal.dart   ❌ Empty
│       └── return_status_modal.dart        ❌ Empty
├── providers/
│   ├── api_provider.dart   ❌ Empty
│   ├── auth_provider.dart ❌ Empty
│   └── asset_provider.dart ❌ Empty
├── models/
│   ├── auth/
│   │   ├── user.dart          ❌ Empty
│   │   └── auth_response.dart ❌ Empty
│   ├── assets/
│   │   ├── asset.dart         ❌ Empty
│   │   └── asset_status.dart  ❌ Empty
│   └── api/
│       ├── api_response.dart  ❌ Empty
│       └── error_response.dart ❌ Empty
├── services/
│   ├── api/
│   │   ├── api_service.dart        ❌ Empty
│   │   └── websocket_service.dart ❌ Empty
│   ├── auth/
│   │   └── auth_service.dart      ❌ Empty
│   └── local/
│       └── secure_storage.dart    ❌ Empty
├── utils/
│   ├── constants/
│   │   ├── colors.dart         ❌ Empty
│   │   ├── strings.dart        ❌ Empty
│   │   └── dimensions.dart     ❌ Empty
│   ├── extensions/
│   │   └── context_extensions.dart ❌ Empty
│   └── helpers/
│       ├── validation_helper.dart ❌ Empty
│       └── date_helper.dart      ❌ Empty
└── widgets/
    ├── buttons/
    │   ├── primary_button.dart   ❌ Empty
    │   └── secondary_button.dart ❌ Empty
    ├── cards/
    │   └── asset_card.dart      ❌ Empty
    └── shared/
        ├── countdown_timer.dart      ❌ Empty
        └── nfc_scan_animation.dart   ❌ Empty
```

---

## Missing Dependencies (pubspec.yaml)

Add the following to `pubspec.yaml`:

```yaml
dependencies:
  flutter:
    sdk: flutter
  cupertino_icons: ^1.0.8
  camera: ^0.10.0
  google_mlkit_barcode_scanning: ^0.5.0
  flutter_riverpod: ^2.4.0    # State management
  dio: ^5.4.0                # HTTP client
  flutter_secure_storage: ^9.0.0  # Secure token storage
  nfc_manager: ^3.0.0        # NFC badge reading
  go_router: ^13.0.0         # Declarative routing
  json_annotation: ^4.8.0    # JSON serialization

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^6.0.0
  build_runner: ^2.4.0
  json_serializable: ^6.7.0
```
