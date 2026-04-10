# Implementation Plan: EasyLend Kiosk App

## Current Implementation State

**Last Updated:** 2026-04-10

### What's Built

| Item | Status | Notes |
| :--- | :--- | :--- |
| Project structure | ✅ Done | Basic Flutter project with screens/, providers/, models/, services/, utils/, widgets/ directories |
| pubspec.yaml | ✅ Done | Includes dio/retrofit/riverpod/go_router/flutter_secure_storage/camera/mlkit/uuid/kiosk_mode |
| theme.dart | ✅ Done | AppColors, AppTheme with dark mode |
| main.dart | ✅ Done | App entrypoint with ProviderScope + App() |
| ScreenSwitcher | ✅ Done | Debug navigation tool for testing screens |
| LoginScreen | ✅ Partial | UI only - NFC animation/manual debug input; no real NFC hardware integration |
| AssetCatalogScreen | ✅ Partial | UI and local state wiring; backend/API contract validation still pending |
| ScanAztecScreen | ✅ Done | Working camera + ML Kit Aztec scanning |
| ReturnStatusScreen | ✅ Partial | UI with polling structure; backend-dependent behavior still pending validation |
| LendingCompleteScreen | ✅ Partial | Implemented screen + live countdown timer; business integration still partial |
| InactivityModal | ✅ Done | Includes live countdown timer and stay/logout actions |
| app.dart | ✅ Done | Root app widget implemented and wired into the application flow |
| app_router.dart | ✅ Done | Router configuration added for the current screen/navigation flow |
| All providers | ✅ Partial | Runtime providers are centralized in providers/providers.dart; legacy provider stub files remain empty |
| All models | ✅ Partial | Model scaffolding is present; several legacy placeholder model files remain empty |
| All services | ✅ Partial | Service scaffolding is present; websocket/auth_service placeholder files remain empty |
| secure_storage | ✅ Done | Secure storage helper added for persisted sensitive/local session data |
| All utils/constants | ✅ Partial | Legacy utils/constants placeholder files remain empty and are not currently the active source of truth |
| All widgets | ✅ Partial | Several reusable widget placeholder files remain empty; screens currently use inline/local UI components |

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
| Vision/Camera | `camera` + `google_mlkit_barcode_scanning` | Camera preview with ML Kit Aztec/barcode scanning. |
| Navigation | `go_router` | Declarative routing with secure Admin guards. |
| Secure Storage | `flutter_secure_storage` | JWT token storage. |

---

## Phase 1: Foundation & API Alignment

**Focus:** Environment setup and resolving specification gaps.

### ELP-36: Android project setup and dependencies

- [x] Initialize project with flavors (dev/prod)
- [x] Install `camera` and `google_mlkit_barcode_scanning` ✅ **Done**
- [x] Install `dio`, `retrofit`, `flutter_riverpod` ✅ **Done**
- [ ] Install `nfc_manager` and `flutter_secure_storage` (`flutter_secure_storage` done, `nfc_manager` still pending)
- [x] Add `go_router` for navigation ✅ **Done**

### ELP-37: Kiosk mode implementation

- [x] Implement lock task allowlisting and kiosk activation wrapper ✅ **Done (current approach)**

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

- [x] Login screen UI with NFC badge animation ✅ **Done**
- [ ] Standard user: NFC badge + 4-digit PIN (API integration)
- [ ] Admin entry: Dedicated Admin NFC badge (unique UID) plus Admin PIN
- [x] PIN entry screen ✅ **Done (UI implemented)**
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

- [x] Aztec scanning with `camera` + `google_mlkit_barcode_scanning` ✅ **Done (ML Kit integration working)**
- [ ] On successful scan, call `POST /api/v1/loans/return/initiate` (current scan flow calls checkout)

---

## Phase 5: UX Polish & UI Details

**Focus:** Visual feedback and error recovery.

### ELP-43: UX (dialogs and errors)

- [ ] Create dialogs for "Locker Jammed," "Item Not Found," and "Unauthorized Return."
- [x] Inactivity timeout modal with live countdown ✅ **Done**

### ELP-44: UI polish

- [ ] Add animations, theming, and accessibility checks
- [ ] Ensure clear success/error states and concise copy
- [x] Implement countdown timer logic in InactivityModal ✅ **Done**
- [x] Implement countdown timer in LendingCompleteScreen ✅ **Done**
- [ ] Fill remaining reusable widget placeholder files (several still empty)

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

Current snapshot highlights:

- Active app bootstrap and routing are implemented in `lib/main.dart`, `lib/app.dart`, and `lib/app_router.dart`.
- Core runtime providers are implemented in `lib/providers/providers.dart`.
- API/auth/storage client scaffolding is present in `lib/services/api/api_service.dart`, `lib/services/api/api_client.dart`, and `lib/services/local/secure_storage_service.dart`.
- Kiosk wrapper/services are implemented in `lib/services/kiosk/`.
- Several legacy placeholder files still exist and are currently empty (not used by active runtime path), including:
  - `lib/providers/api_provider.dart`, `lib/providers/auth_provider.dart`, `lib/providers/asset_provider.dart`
  - `lib/screens/dashboard/dashboard_screen.dart`, `lib/screens/modals/inactivity_timeout_modal.dart`, `lib/screens/modals/return_status_modal.dart`
  - `lib/widgets/buttons/primary_button.dart`, `lib/widgets/buttons/secondary_button.dart`, `lib/widgets/cards/asset_card.dart`, `lib/widgets/shared/countdown_timer.dart`, `lib/widgets/shared/nfc_scan_animation.dart`
  - `lib/services/api/websocket_service.dart`, `lib/services/auth/auth_service.dart`, `lib/services/local/secure_storage.dart`
  - `lib/utils/constants/*.dart`, `lib/utils/extensions/context_extensions.dart`, `lib/utils/helpers/*.dart`
  - `lib/models/auth/auth_response.dart`, `lib/models/assets/asset.dart`, `lib/models/assets/asset_status.dart`, `lib/models/api/api_response.dart`

---

## Dependency Gaps (pubspec.yaml)

Current dependency status:

- Already present: `dio`, `retrofit`, `flutter_riverpod`, `go_router`, `flutter_secure_storage`, `camera`, `google_mlkit_barcode_scanning`, `json_annotation`, `uuid`, `kiosk_mode`
- Still missing for planned hardware NFC implementation: `nfc_manager`
