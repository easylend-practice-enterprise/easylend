# EasyLend API Contract

> **Version:** 1.0.0 · **Source of Truth:** `backend/api/openapi.json` · **Last Updated:** 2026-04-25
>
> **Audience:** Flutter Frontend team (Kiosk app).
>
> **Scope:** Authentication, all kiosk-relevant REST endpoints, idempotency & polling rules, WebSocket protocol, and UX dead-end handling.

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [Current User](#2-current-user)
3. [Catalog & Assets](#3-catalog--assets)
4. [Loan Transactions](#4-loan-transactions)
5. [Status Polling & UX State Machine](#5-status-polling--ux-state-machine)
6. [Damage Reporting](#6-damage-reporting)
7. [Transaction Rules: Idempotency & Polling](#7-transaction-rules-idempotency--polling)
8. [WebSocket Protocol](#8-websocket-protocol)
9. [Schema Reference](#9-schema-reference)

---

## 1. Authentication

### 1.1 User Auth — Two-Step NFC + PIN Login

The kiosk sign-in flow is a two-step process:

1. Validate NFC badge → backend confirms it's recognized.
2. Validate PIN → backend issues JWT tokens.

---

#### Step 1 — NFC Badge Pre-Check

`POST /api/v1/auth/nfc` · **Public** (no JWT required)

Rate-limited: 500 req/min per IP.

**Request Body** — `NfcLoginRequest`:

```json
{
  "nfc_tag_id": "string"   // required, 1–100 chars
}
```

**Success Response** — `200 OK`:

```json
{
  "detail": "NFC badge recognized. Enter PIN."
}
```

| Error | Meaning |
|-------|---------|
| `401` | Invalid NFC badge or account status |
| `429` | Too Many Requests (IP rate limit) |

---

#### Step 2 — PIN Verification → Token Pair

`POST /api/v1/auth/pin` · **Public** (no JWT required)

Rate-limited: 500 req/min per IP.

**Request Body** — `PinLoginRequest`:

```json
{
  "nfc_tag_id": "string",  // required, 1–100 chars
  "pin": "string"          // required, exactly 6 digits (regex: ^\d{6}$)
}
```

**Success Response** — `200 OK` — `TokenResponse`:

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "Bearer"
}
```

| Error | Meaning |
|-------|---------|
| `401` | Invalid NFC badge/account, incorrect PIN, or account lockout |
| `409` | Account row is currently locked by another login attempt — `"Account is currently in use. Please try again."` |
| `429` | Too Many Requests (IP rate limit) |
| `503` | Redis unavailable during refresh-token storage |

---

#### Access Token Usage

All protected endpoints require the header:

```
Authorization: Bearer <access_token>
```

If the token is missing, invalid, or expired, the API returns `401`.

---

#### Refresh Token Rotation

`POST /api/v1/auth/refresh` · **Public**

Rate-limited: 500 req/min per IP.

**Request Body** — `RefreshTokenRequest`:

```json
{
  "refresh_token": "string"  // required, 1–2048 chars
}
```

**Behavior:**

1. Verifies JWT signature, expiry, and `type=refresh`.
2. Atomically consumes the refresh token in Redis (key: `refresh:{user_id}:{jti}`).
3. If already consumed or not found → `401 Invalid refresh token`.
4. Loads user, validates account status, issues **new** token pair.
5. Stores new refresh token in Redis with TTL = `JWT_REFRESH_TOKEN_EXPIRE_DAYS`.

**Success Response** — `200 OK` — `TokenResponse` (same schema as `/auth/pin`).

| Error | Meaning |
|-------|---------|
| `401` | Invalid, expired, or already-consumed refresh token |
| `503` | Redis revoke/store operation failed |

---

#### Logout

`POST /api/v1/auth/logout` · **Public** · **Idempotent**

**Request Body** — `RefreshTokenRequest`:

```json
{
  "refresh_token": "string"  // required, 1–2048 chars
}
```

**Success Response** — `200 OK`:

```json
{
  "detail": "Logged out."
}
```

---

### 1.2 Machine-to-Machine (M2M) — Device Tokens

Vision Box and Simulation authenticate via static device token.

```
X-Device-Token: <static_device_secret>
```

- Bypasses user JWT auth for machine endpoints and WebSocket handshake.
- Uses timing-safe comparison against configured secrets.
- Missing/invalid → `401` with `WWW-Authenticate: X-Device-Token`.
- Two accepted tokens configured separately:
  - **Vision Box** — `VISION_BOX_API_KEY`
  - **Simulation** — `SIMULATION_API_KEY`

---

## 2. Current User

### Get Current User Profile

`GET /api/v1/users/me` · **Auth:** Bearer JWT

**Success Response** — `200 OK` — `UserResponse`:

```json
{
  "user_id": "<uuid>",
  "role_id": "<uuid>",
  "role_name": "student",
  "first_name": "Jane",
  "last_name": "Doe",
  "email": "jane.doe@school.be",
  "nfc_tag_id": "ABC123",         // nullable
  "failed_login_attempts": 0,
  "locked_until": null,            // nullable, datetime
  "status": "ACTIVE",             // enum: ACTIVE | INACTIVE | BANNED | ANONYMIZED
  "ban_reason": null,              // nullable
  "accepted_privacy_policy": true
}
```

| Error | Meaning |
|-------|---------|
| `401` | Not authenticated / invalid token |

---

## 3. Catalog & Assets

### Get Catalog (Role-Aware)

`GET /api/v1/catalog` · **Auth:** Bearer JWT

| Query Param | Type | Default | Max |
|-------------|------|---------|-----|
| `skip` | integer ≥ 0 | `0` | — |
| `limit` | integer 1–1000 | `100` | `1000` |

**Non-admin response** — `200 OK` — `CatalogUserView[]`:

```json
[
  {
    "category_id": "<uuid>",
    "category_name": "Laptops",
    "available_count": 2
  }
]
```

**Admin response** — `200 OK` — `CatalogAdminView[]`:

```json
[
  {
    "asset_id": "<uuid>",
    "asset_name": "Dell XPS 15",
    "category_id": "<uuid>",
    "asset_status": "BORROWED",
    "locker_id": "<uuid>",           // nullable
    "is_deleted": false,
    "loan_status": "ACTIVE",         // nullable
    "borrower_first_name": "Jane",   // nullable
    "borrower_last_name": "Doe"      // nullable
  }
]
```

| Error | Meaning |
|-------|---------|
| `401` | Not authenticated |

---

## 4. Loan Transactions

### 4.1 Checkout — Scan Aztec Barcode

`POST /api/v1/loans/checkout` · **Auth:** Bearer JWT

**Required Header:** `Idempotency-Key: <client_generated_unique_key>`

Rate-limited: 60 req/min per authenticated user.

**Request Body** — `CheckoutRequest`:

```json
{
  "aztec_code": "string"  // required, 1–100 chars — scanned from asset label
}
```

> The backend resolves the associated asset from the `aztec_code`, locks the asset/locker rows with `SELECT … FOR UPDATE NOWAIT`, creates the loan record, and sends the hardware open command.

**Success Response** — `202 Accepted` — `LoanPublicResponse`:

```json
{
  "loan_id": "<uuid>",
  "asset_id": "<uuid>",
  "checkout_locker_id": "<uuid>",
  "return_locker_id": null,
  "reserved_at": "2026-04-25T12:00:00Z",
  "borrowed_at": null,
  "due_date": null,
  "returned_at": null,
  "loan_status": "RESERVED"
}
```

| Error | Meaning |
|-------|---------|
| `400` | `"Idempotency-Key header is required"` / `"Asset not found."` / `"Asset is not available for checkout."` / `"Asset has no assigned locker and cannot be checked out."` |
| `401` | Not authenticated |
| `404` | `"Locker not found."` |
| `409` | Lock contention (asset/locker currently being processed) or duplicate idempotency key |
| `429` | Too Many Requests |
| `503` | Vision Box offline for that kiosk / Redis unavailable during idempotency guard |

---

### 4.2 Return — Scan Aztec Barcode

> ⚠️ **BREAKING CHANGE:** `ReturnInitiateRequest` now uses `aztec_code` (the scanned barcode) instead of `loan_id`. The backend resolves the active loan from the asset's Aztec code.

`POST /api/v1/loans/return/initiate` · **Auth:** Bearer JWT

**Required Header:** `Idempotency-Key: <client_generated_unique_key>`

Rate-limited: 60 req/min per authenticated user.

**Request Body** — `ReturnInitiateRequest`:

```json
{
  "aztec_code": "string",  // required, 1–100 chars — scanned from the asset
  "kiosk_id": "<uuid>"     // required — the kiosk where the user is standing
}
```

> The backend resolves the active loan from the scanned `aztec_code`, finds a free locker at the kiosk identified by `kiosk_id`, and begins the return process.

**State transitions:**

- `Locker.locker_status`: `AVAILABLE` → `OCCUPIED` (reserved for this return)
- `Loan.return_locker_id`: assigned to the chosen locker
- `Loan.loan_status`: `ACTIVE` → `RETURNING`

**Success Response** — `202 Accepted` — `LoanPublicResponse`:

```json
{
  "loan_id": "<uuid>",
  "asset_id": "<uuid>",
  "checkout_locker_id": "<uuid>",
  "return_locker_id": "<uuid>",
  "reserved_at": "2026-04-25T10:00:00Z",
  "borrowed_at": "2026-04-25T10:05:00Z",
  "due_date": "2026-05-09T10:05:00Z",
  "returned_at": null,
  "loan_status": "RETURNING"
}
```

| Error | Meaning |
|-------|---------|
| `400` | `"Idempotency-Key header is required"` / `"Loan is not active and cannot be returned."` / `"No active loan found for this asset."` / `"Asset not found."` |
| `401` | Not authenticated |
| `403` | `"You do not have permission to return this loan."` |
| `404` | `"Kiosk not found."` |
| `409` | Return already in progress / loan state changed / duplicate idempotency key |
| `429` | Too Many Requests |
| `503` | `"No available lockers at this kiosk. Please try again shortly."` / Vision Box offline / Redis unavailable |

---

### 4.3 List My Loans

`GET /api/v1/loans` · **Auth:** Bearer JWT

| Query Param | Type | Default | Max |
|-------------|------|---------|-----|
| `skip` | integer ≥ 0 | `0` | — |
| `limit` | integer 1–1000 | `100` | `1000` |

**Non-admin response** — `200 OK` — `LoanPublicListResponse`:

```json
{
  "items": [
    {
      "loan_id": "<uuid>",
      "asset_id": "<uuid>",
      "checkout_locker_id": "<uuid>",
      "return_locker_id": null,
      "reserved_at": "2026-04-25T10:00:00Z",
      "borrowed_at": "2026-04-25T10:05:00Z",
      "due_date": "2026-05-09T10:05:00Z",
      "returned_at": null,
      "loan_status": "ACTIVE"
    }
  ],
  "total": 1
}
```

> **Note:** Non-admin responses use `LoanPublicResponse` (no `user_id` field) to prevent IDOR. Admin responses use `LoanResponse` which includes `user_id`.

| Error | Meaning |
|-------|---------|
| `401` | Not authenticated |

---

## 5. Status Polling & UX State Machine

### 5.1 Poll Loan Status

`GET /api/v1/loans/{loan_id}/status` · **Auth:** Bearer JWT

Lightweight polling endpoint. Non-admin users may only poll their own loans.

**Success Response** — `200 OK` — `LoanStatusResponse`:

```json
{
  "loan_id": "<uuid>",
  "loan_status": "ACTIVE"
}
```

| Error | Meaning |
|-------|---------|
| `401` | Not authenticated |
| `403` | `"You do not have permission to view this loan."` — not the loan owner (non-admin) |
| `404` | `"Loan not found."` |

---

### 5.2 Loan Status — UX Mapping Table

The `loan_status` enum determines what the kiosk UI should display:

| `loan_status` | Context | Kiosk UI Action |
|---|---|---|
| `RESERVED` | After `POST /checkout` | Show **"Opening locker…"** spinner. Poll every 2s. Backend is waiting for the Vision Box to confirm the asset was picked up. |
| `ACTIVE` | Checkout confirmed | Show **"Checkout Complete ✓"** success screen. The user may now leave with the asset. Stop polling. |
| `RETURNING` | After `POST /return/initiate` | Show **"Place item in locker X"** instruction. Poll every 2s. Backend is waiting for the Vision Box to confirm the asset was returned. |
| `COMPLETED` | Return confirmed | Show **"Return Complete ✓"** success screen. Stop polling. |
| `OVERDUE` | Due date passed | Show **"This item is overdue. Please return it immediately."** warning banner on the user's loan overview. |
| `PENDING_INSPECTION` | AI flagged anomaly during checkout/return, **or** a RESERVED loan timed out | Show **"Item under inspection. Please wait for staff assistance."** Screen must remain visible — user CANNOT dismiss. |
| `FRAUD_SUSPECTED` | AI + Vision determined locker was empty on checkout | Show **"Please contact a staff member immediately."** Screen MUST block further interaction. |
| `DISPUTED` | Admin confirmed AI's damage flag | Show **"Damage confirmed. Please contact the service desk."** Block further kiosk interaction for this loan. |

> [!CAUTION]
> **Dead-end states:** `PENDING_INSPECTION`, `FRAUD_SUSPECTED`, and `DISPUTED` are dead-end states from the kiosk's perspective. The kiosk **must not** offer any action buttons (retry, cancel, dismiss) for these statuses. Only a backend admin can resolve them.

---

### 5.3 Locker Status — UX Awareness

The kiosk does not directly poll locker status, but the frontend should understand these values when returned in other responses:

| `locker_status` | Meaning |
|---|---|
| `AVAILABLE` | Locker is free and can be used for checkout/return |
| `OCCUPIED` | Locker is currently assigned to an active loan or return-in-progress |
| `MAINTENANCE` | Locker is disabled by admin — skip in UI |
| `ERROR_OPEN` | Locker door is stuck open (sensor failure). Show **"Locker malfunction — contact staff"** if the user's assigned locker enters this state |

---

## 6. Damage Reporting

### Report Damage (Post-Checkout Grace Period)

`POST /api/v1/loans/{loan_id}/report-damage` · **Auth:** Bearer JWT

**Optional Header:** `Idempotency-Key: <client_generated_unique_key>`

Allows a user to report that the asset was already damaged when they received it. Only valid during the immediate post-checkout grace period.

**Path Param:** `loan_id` (uuid)

**Success Response** — `200 OK` — `LoanPublicResponse`

| Error | Meaning |
|-------|---------|
| `400` | Invalid state or grace period elapsed |
| `401` | Not authenticated |
| `403` | Not the loan owner |
| `404` | Loan, asset, locker, or user not found |
| `409` | Lock contention or duplicate idempotency key |

---

## 7. Transaction Rules: Idempotency & Polling

### 7.1 Mandatory Idempotency-Key

**Applies to:**

- `POST /api/v1/loans/checkout`
- `POST /api/v1/loans/return/initiate`
- `POST /api/v1/loans/{loan_id}/report-damage` (optional but recommended)

**Rules:**

1. **Header is mandatory** for checkout and return. Missing header → `400`.
2. **Maximum key length:** 256 characters. Longer keys → `400`.
3. **Duplicate keys** → `409`:
   > `"Duplicate request with this idempotency key is already being processed or has completed."`
4. Keys are stored in Redis with a **24-hour TTL** (`SET NX EX`).
5. If Redis is unavailable during the idempotency check → `503`.
6. **Key release behavior:**
   - If the transaction fails **before** DB commit → key is released (safe retry).
   - If DB commit already happened → key remains consumed (prevents duplicate side effects).

---

### 7.2 The "Snoepautomaat" Pattern — Commit-First, Hardware-Second

Checkout and return-initiate follow a **commit-first, hardware-second** architecture:

```
┌────────┐       ┌──────────┐       ┌────────────┐
│  Kiosk │──────►│ Backend  │──────►│ Vision Box │
│  (App) │◄──────│  (API)   │       │ (Hardware) │
└────────┘       └──────────┘       └────────────┘
    │                 │                    │
    │  POST /checkout │                    │
    │────────────────►│                    │
    │                 │  DB COMMIT         │
    │                 │  (loan created)    │
    │  202 Accepted   │                    │
    │◄────────────────│                    │
    │                 │  WSS: open_slot    │
    │                 │───────────────────►│
    │                 │                    │  (door opens)
    │  Poll status    │                    │
    │────────────────►│                    │
    │  loan_status    │                    │
    │◄────────────────│                    │
```

**What `202 Accepted` means:**

- The request is **persisted** in the database.
- The physical door action has **not necessarily happened yet**.
- The WSS `open_slot` command is sent **after** the 202 response.

**Client obligations after receiving `202`:**

1. **Immediately** start polling `GET /api/v1/loans/{loan_id}/status`.
2. Poll every **2 seconds**.
3. Continue until the status resolves to the expected outcome:
   - **Checkout:** target = `ACTIVE`
   - **Return:** target = `COMPLETED`
4. Handle exception states (`PENDING_INSPECTION`, `FRAUD_SUSPECTED`, `DISPUTED`) as documented in the [UX Mapping Table](#52-loan-status--ux-mapping-table).

> [!WARNING]
> **Hardware Timeout Rule:** If the backend returns `202 Accepted` but the loan status does **not** progress beyond `RESERVED` (checkout) or `RETURNING` (return) within **10 seconds**, the frontend **must** display a **"Hardware Timeout — Please contact staff"** error screen. Do not retry the transaction. The backend timeout worker will eventually resolve the state.

---

## 8. WebSocket Protocol

### 8.1 Connection

**URL:** `ws://<host>/ws/visionbox/{kiosk_id}`

> In deployments where API traffic is prefixed with `/api/v1`, the full URL becomes:
> `wss://<host>/api/v1/ws/visionbox/{kiosk_id}`

**Handshake Requirements:**

| Header | Value | Required |
|--------|-------|----------|
| `X-Device-Token` | Vision Box token or Simulation token | **Yes** |

- Missing or invalid token → connection rejected with `WS_1008_POLICY_VIOLATION`.
- The `kiosk_id` path parameter must reference a registered kiosk in the database. Unknown kiosks → rejected.
- **Global connection limit:** 100 concurrent WebSocket connections. Exceeded → rejected with close code `1013` (`"Connection limit reached"`).
- If a connection for the same `kiosk_id` already exists, the **old** connection is closed before the new one is accepted.

> [!CAUTION]
> **Dead connection detection:** The app relies on **Uvicorn's ASGI ping/pong frames** (`ws_ping_interval` / `ws_ping_timeout`) to detect dead TCP connections. The application-level presence heartbeat only refreshes a Redis TTL key every 10 seconds — it does **NOT** actively detect broken sockets. Do **not** deploy behind proxies that strip WebSocket control frames without ensuring the ASGI server's ping timeout is set appropriately (e.g., Uvicorn: `--ws-ping-timeout 30`).

---

### 8.2 Server-to-Client Messages

#### `open_slot` — Checkout / Return

Sent when a checkout or return is initiated. The Vision Box must physically open the specified locker.

```json
{
  "action": "open_slot",
  "locker_id": 12,
  "loan_id": "<uuid>",
  "evaluation_type": "CHECKOUT"
}
```

- `evaluation_type`: `"CHECKOUT"` or `"RETURN"`
- `locker_id`: the `logical_number` (integer) of the physical locker slot

**Admin force-open variant** — may omit `loan_id` and `evaluation_type`:

```json
{
  "action": "open_slot",
  "locker_id": "12"
}
```

#### `set_led` — LED Indicator

Sent to change the LED color on a specific locker slot.

```json
{
  "action": "set_led",
  "locker_id": 12,
  "color": "green"
}
```

Observed colors in production flows: `green`, `orange`, `red`.

---

### 8.3 Client-to-Server Messages

#### `slot_closed`

Sent by the Vision Box when a locker door sensor detects closure.

```json
{
  "event": "slot_closed",
  "locker_id": "12"
}
```

**Backend behavior:**

- Accepts JSON text frames only. Non-JSON messages are logged and ignored.
- Logs `slot_closed` events.
- Does **not** currently send an acknowledgment payload back to the client.

---

## 9. Schema Reference

### Enums

#### `LoanStatus`

```
RESERVED | ACTIVE | RETURNING | OVERDUE | COMPLETED | FRAUD_SUSPECTED | DISPUTED | PENDING_INSPECTION
```

#### `AssetStatus`

```
AVAILABLE | BORROWED | RESERVED | PENDING_INSPECTION | MAINTENANCE | LOST
```

#### `LockerStatus`

```
AVAILABLE | OCCUPIED | MAINTENANCE | ERROR_OPEN
```

#### `KioskStatus`

```
ONLINE | OFFLINE | MAINTENANCE
```

#### `UserStatus`

```
ACTIVE | INACTIVE | BANNED | ANONYMIZED
```

#### `EvaluationType`

```
CHECKOUT | RETURN
```

---

### Request Schemas

#### `NfcLoginRequest`

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `nfc_tag_id` | string | ✅ | 1–100 chars |

#### `PinLoginRequest`

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `nfc_tag_id` | string | ✅ | 1–100 chars |
| `pin` | string | ✅ | exactly 6 digits |

#### `RefreshTokenRequest`

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `refresh_token` | string | ✅ | 1–2048 chars |

#### `CheckoutRequest`

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `aztec_code` | string | ✅ | 1–100 chars |

#### `ReturnInitiateRequest`

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `aztec_code` | string | ✅ | 1–100 chars |
| `kiosk_id` | uuid | ✅ | — |

> **Note:** This schema previously used `loan_id`. It now uses `aztec_code` — the scanned barcode from the asset label. The backend resolves the active loan automatically.

---

### Response Schemas

#### `TokenResponse`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `access_token` | string | ✅ | — |
| `refresh_token` | string | ✅ | — |
| `token_type` | string | — | `"Bearer"` |

#### `UserResponse`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `user_id` | uuid | ✅ | |
| `role_id` | uuid | ✅ | |
| `role_name` | string | ✅ | |
| `first_name` | string | ✅ | |
| `last_name` | string | ✅ | |
| `email` | string | ✅ | |
| `nfc_tag_id` | string \| null | ✅ | HMAC-SHA256 hashed digest (raw tag never returned) |
| `failed_login_attempts` | integer | ✅ | |
| `locked_until` | datetime \| null | ✅ | |
| `status` | `UserStatus` | ✅ | |
| `ban_reason` | string \| null | ✅ | |
| `accepted_privacy_policy` | boolean | ✅ | |

#### `LoanPublicResponse`

Used for checkout/return responses and non-admin loan listings. Excludes `user_id` to prevent IDOR.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `loan_id` | uuid | ✅ | |
| `asset_id` | uuid | ✅ | |
| `checkout_locker_id` | uuid | ✅ | |
| `return_locker_id` | uuid \| null | ✅ | null until return initiated |
| `reserved_at` | datetime \| null | ✅ | |
| `borrowed_at` | datetime \| null | ✅ | null until pickup confirmed |
| `due_date` | datetime \| null | ✅ | null until pickup confirmed |
| `returned_at` | datetime \| null | ✅ | null until return completed |
| `loan_status` | `LoanStatus` | ✅ | |

#### `LoanStatusResponse`

Minimal payload returned by the polling endpoint.

| Field | Type | Required |
|-------|------|----------|
| `loan_id` | uuid | ✅ |
| `loan_status` | `LoanStatus` | ✅ |

#### `LoanPublicListResponse`

| Field | Type | Required |
|-------|------|----------|
| `items` | `LoanPublicResponse[]` | ✅ |
| `total` | integer | ✅ |

#### `CatalogUserView`

| Field | Type | Required |
|-------|------|----------|
| `category_id` | uuid | ✅ |
| `category_name` | string | ✅ |
| `available_count` | integer ≥ 0 | ✅ |

#### `CatalogAdminView`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `asset_id` | uuid | ✅ | |
| `asset_name` | string | ✅ | |
| `category_id` | uuid | ✅ | |
| `asset_status` | `AssetStatus` | ✅ | |
| `locker_id` | uuid \| null | ✅ | |
| `is_deleted` | boolean | ✅ | |
| `loan_status` | `LoanStatus` \| null | ✅ | null if no active loan |
| `borrower_first_name` | string \| null | ✅ | |
| `borrower_last_name` | string \| null | ✅ | |

---

## 10. Webhooks

### Update AI Model (Vision Box)

**External Contract:** `PATCH /api/v1/update-model`
**Internal Proxied Contract:** `POST /update-model` (to Vision Microservice)

Allows the hardware orchestrator or external admin services to dynamically update the underlying models used by the Vision Box. This endpoint provides support for updating the YOLO26 Dual-Model architecture (Detection & Segmentation).

This endpoint implements a dual-layer reverse proxy architecture:

1. **Main API Layer:** Receives the `PATCH /api/v1/update-model` request with the JSON payload, verifies the `verify_vision_box_token` dependency (`X-Device-Token`), translates the HTTP method to `POST`, attaches the `Authorization: Bearer <VISION_API_KEY>` header, and forwards the request.
2. **Vision Microservice Layer:** Receives the internal `POST /update-model` request, verifies the bearer token, downloads the model(s) with Fail-Fast behavior, and schedules a `BackgroundTask` to restart the server upon successful download.

**Required Header (External):** `X-Device-Token: <static_device_secret>`

**Request Body** — `ModelUpdateRequest`:

```json
{
  "object_detection_url": "https://models.example.com/object.pt",
  "segmentation_url": "https://models.example.com/segmentation.pt"
}
```

**Success Response** — `200 OK`:

```json
{
  "message": "Model update received successfully."
}
```
