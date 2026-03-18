# Implementation Plan: EasyLend Kiosk App

## Project Overview

High-Level Goals:

1. Security: 2FA for Admins and JWT-based session management for all users.
2. Hardware Synergy: Robust interaction with the Vision Box (locker system) via optimized polling.
3. Resilience: Graceful handling of hardware timeouts and offline states.

### Tools and Libraries Stack

| Category | Tool/Library | Purpose |
| :--- | :--- | :--- |
| Framework | Flutter | Android tablet target (landscape UI). |
| State Management | `flutter_bloc` | Handles complex states (Auth, Transaction Polling). |
| Networking | `dio` + `retrofit` | Type-safe HTTP client with JWT interceptors. |
| Hardware | `nfc_manager` | NFC badge reading. |
| Vision/Camera | `mobile_scanner` | Fast Aztec/barcode scanning via ML Kit. |
| Navigation | `go_router` | Declarative routing with secure Admin guards. |

### Phase 1: Foundation & API Alignment

Focus: Environment setup and resolving specification gaps.

- ELP-36: Android project setup and dependencies
  - Initialize project with flavors (dev/prod). Install `dio`, `flutter_bloc`, `nfc_manager`, and `flutter_secure_storage`.
- ELP-37: Kiosk mode implementation
  - Implement `startLockTask()` and hide system UI to prevent users from exiting the app.
- ELP-47: Auth & retry via interceptor
  - Implement a `Dio` interceptor to handle `401 Unauthorized` by calling `POST /api/v1/auth/refresh` and retrying the original request.
- ELP-49: Error handling (network/hardware)
  - Build a global "System Maintenance" overlay that triggers if the Health Check API fails or the Vision Box is reported offline.

### Phase 2: Authentication & Secure Admin Access

Focus: Implementing 2-step login and secure admin entry.

- ELP-38 & ELP-39: NFC integration
  - Implement background listener for `POST /api/v1/auth/nfc`.
- ELP-40: Login screen & Admin 2FA
  - Standard user: NFC badge + 4-digit PIN.
  - Admin entry: Dedicated Admin NFC badge (unique UID) plus Admin PIN.
  - Audit logging: Every successful Admin login must trigger a log entry (`POST /api/v1/audit/logs`).
  - Inactivity: A 60-second timer triggers `POST /api/v1/auth/logout` and clears sensitive data from memory.

### Phase 3: Asset Catalog & Role-Based UI

Focus: Navigational guards and data fetching.

- ELP-41 & ELP-48: Fetch assets
  - Role logic: Use `go_router` redirects. If JWT claim `role != "admin"`, block access to `/admin/*`.
  - Standard view: Display category grid (e.g., "Handheld Scanners: 4 Available").
  - Admin view: Full asset list showing who has which item and ability to force-open lockers.

### Phase 4: Optimized Transaction Wizards

Focus: Managing the physical locker interaction cycle.

- ELP-42 & ELP-48: Checkout/return flow
  - Polling strategy (exponential backoff):
    - 0–10s: poll every 2 seconds.
    - 10–30s: poll every 5 seconds.
    - 30–45s: poll every 10 seconds.
  - Hard timeout handling: At the configured timeout, transition UI to a "Transaction Pending" screen and finalize in background.
- ELP-45 & ELP-46: Aztec integration
  - Integrate `mobile_scanner` for returns. On successful scan, call `POST /api/v1/loans/return/initiate`.

### Phase 5: UX Polish & UI Details

Focus: Visual feedback and error recovery.

- ELP-43: UX (dialogs and errors)
  - Create dialogs for "Locker Jammed," "Item Not Found," and "Unauthorized Return."
- ELP-44: UI polish

### Milestones

| Milestone | Target | Owner |
| :--- | :--- | :--- |
| API contract & Phase 1 complete | TBD | Frontend & Backend |
| Admin 2FA & secure auth verified | TBD | Security / Frontend |
| E2E transaction (optimized polling) | TBD | Full Team |
| Field readiness (kiosk mode test) | TBD | Hardware / QA |

### Success Metrics

| Metric | Target | Measurement Method |
| :--- | :--- | :--- |
| Admin security | 100% | No entry without Admin NFC + PIN; all entries logged. |
| Transaction latency | < 12s | Time from NFC tap to "Locker Open" signal. |
| Network efficiency | Optimized | Polling frequency decreases over time to save resources. |
| System uptime | High | Circuit breaker / offline mode prevents app crashes. |
