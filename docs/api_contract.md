# EasyLend API Contract (ELP-68)

Audience: Frontend team (Maxim) and Hardware team (Vision Box / Simulation).

Scope: This contract defines authentication, core REST calls, idempotency and polling behavior, and the websocket protocol required for kiosk-hardware orchestration.

## 1. Authentication Deep-Dive

### User Auth (JWT)

The kiosk user flow is a two-step login:

1. Validate NFC badge.
2. Validate PIN and issue JWT tokens.

#### Step 1: Obtain badge pre-check

Endpoint: POST /api/v1/auth/nfc

Request body:

```json
{
  "nfc_tag_id": "string (1..100)"
}
```

Success response (200):

```json
{
  "detail": "NFC badge recognized. Enter PIN."
}
```

Common errors:

- 401: Invalid NFC badge or account status.
- 429: Too Many Requests (IP rate limit).

#### Step 2: Obtain access + refresh tokens

Endpoint: POST /api/v1/auth/pin

Request body:

```json
{
  "nfc_tag_id": "string (1..100)",
  "pin": "string (4..32)"
}
```

Success response (200):

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "Bearer"
}
```

Common errors:

- 401: Invalid NFC badge/account, incorrect PIN, or account lockout.
- 409: Account row is currently locked by another login attempt.
- 429: Too Many Requests (IP rate limit).
- 503: Redis unavailable during refresh-token storage.

#### Access token usage

For protected user endpoints, send:

Authorization: Bearer <access_token>

If missing/invalid/expired, API responds 401. Typical details include:

- Not authenticated
- Invalid or expired token.

#### Refresh token flow via Redis (single-use rotation)

Endpoint: POST /api/v1/auth/refresh

Request body:

```json
{
  "refresh_token": "<jwt>"
}
```

Behavior:

1. API verifies JWT signature, expiry, and type=refresh.
2. API atomically consumes the refresh token in Redis using key pattern refresh:{user_id}:{jti}.
3. If token already consumed or not found, API returns 401 Invalid refresh token.
4. API loads user, validates account status, and issues a new token pair.
5. New refresh token is stored in Redis with TTL based on JWT_REFRESH_TOKEN_EXPIRE_DAYS.

Response on success (200): same token schema as /auth/pin.

Service degradation behavior:

- 503 when Redis revoke/store operations fail.

### Machine-to-Machine (M2M)

Vision Box and Simulation can authenticate with a static device token instead of JWT.

Header:

X-Device-Token: <static_device_secret>

Important:

- This bypasses user JWT auth for machine endpoints/websocket handshake.
- Validation uses timing-safe comparison against configured secrets.
- Missing/invalid token returns 401 with WWW-Authenticate: X-Device-Token.
- Two accepted token types are configured separately:
  - Vision Box token (VISION_BOX_API_KEY)
  - Simulation token (SIMULATION_API_KEY)

## 2. Core REST Endpoints (Include HTTP methods, paths, request bodies, and success/error responses)

### POST /api/v1/auth/nfc

Auth:

- Public endpoint (no JWT required)

Request body:

```json
{
  "nfc_tag_id": "string (1..100)"
}
```

Success response:

- 200

```json
{
  "detail": "NFC badge recognized. Enter PIN."
}
```

Error responses:

- 401: {"detail": "Invalid NFC badge or account status."}
- 429: {"detail": "Too Many Requests"}

### POST /api/v1/auth/pin

Auth:

- Public endpoint (no JWT required)

Request body:

```json
{
  "nfc_tag_id": "string (1..100)",
  "pin": "string (4..32)"
}
```

Success response:

- 200

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "Bearer"
}
```

Error responses (common):

- 401: Invalid badge/account/PIN or lockout.
- 409: {"detail": "Account is currently in use. Please try again."}
- 429: {"detail": "Too Many Requests"}
- 503: {"detail": "Authentication service is temporarily unavailable. Please try again later."}

### GET /api/v1/catalog

Auth:

- Required: Authorization: Bearer <access_token>

Query params:

- skip: integer, default 0
- limit: integer, default 100, max 1000

Success response:

- 200

For non-admin users (grouped counts):

```json
[
  {
    "category_id": "<uuid>",
    "category_name": "Laptops",
    "available_count": 2
  },
  {
    "category_id": "<uuid>",
    "category_name": "Tablets",
    "available_count": 0
  }
]
```

For admins (per-asset detail):

```json
[
  {
    "asset_id": "<uuid>",
    "asset_name": "Dell XPS",
    "category_id": "<uuid>",
    "asset_status": "BORROWED",
    "locker_id": "<uuid>",
    "is_deleted": false,
    "loan_status": "ACTIVE",
    "borrower_first_name": "Borrower",
    "borrower_last_name": "Example"
  }
]
```

Error responses:

- 401: Not authenticated / invalid token

### POST /api/v1/loans/checkout

Auth and headers:

- Required: Authorization: Bearer <access_token>
- Required: Idempotency-Key: <client_generated_unique_key>

Request body:

```json
{
  "aztec_code": "string (1..100)"
}
```

Success response:

- 202 Accepted

```json
{
  "loan_id": "<uuid>",
  "asset_id": "<uuid>",
  "checkout_locker_id": "<uuid>",
  "return_locker_id": null,
  "reserved_at": "<datetime>",
  "borrowed_at": null,
  "due_date": null,
  "returned_at": null,
  "loan_status": "RESERVED"
}
```

Error responses (common):

- 400:
  - {"detail": "Idempotency-Key header is required"}
  - {"detail": "Asset not found."}
  - {"detail": "Asset is not available for checkout."}
  - {"detail": "Asset has no assigned locker and cannot be checked out."}
- 401: Not authenticated / invalid token
- 404: {"detail": "Locker not found."}
- 409:
  - lock contention (asset/locker currently being processed)
  - duplicate idempotency key
- 429: {"detail": "Too Many Requests"}
- 503:
  - Vision Box offline for that kiosk
  - Redis unavailable during idempotency guard

### POST /api/v1/loans/return/initiate

Auth and headers:

- Required: Authorization: Bearer <access_token>
- Required: Idempotency-Key: <client_generated_unique_key>

Request body:

```json
{
  "loan_id": "<uuid>",
  "kiosk_id": "<uuid>"
}
```

Success response:

- 202 Accepted

```json
{
  "loan_id": "<uuid>",
  "asset_id": "<uuid>",
  "checkout_locker_id": "<uuid>",
  "return_locker_id": "<uuid>",
  "reserved_at": "<datetime>",
  "borrowed_at": "<datetime>",
  "due_date": "<datetime>",
  "returned_at": null,
  "loan_status": "RETURNING"
}
```

Error responses (common):

- 400:
  - {"detail": "Idempotency-Key header is required"}
  - {"detail": "Loan is not active and cannot be returned."}
- 401: Not authenticated / invalid token
- 403: {"detail": "You do not have permission to return this loan."}
- 404:
  - {"detail": "Loan not found."}
  - {"detail": "Kiosk not found."}
- 409:
  - return already in progress / loan state changed
  - duplicate idempotency key
- 429: {"detail": "Too Many Requests"}
- 503:
  - {"detail": "No available lockers at this kiosk. Please try again shortly."}
  - Vision Box offline for the chosen kiosk
  - Redis unavailable during idempotency guard

### GET /api/v1/loans/{loan_id}/status

Auth:

- Required: Authorization: Bearer <access_token>

Request body:

- None

Success response:

- 200

```json
{
  "loan_id": "<uuid>",
  "loan_status": "ACTIVE"
}
```

Possible loan_status values:

- RESERVED
- ACTIVE
- RETURNING
- OVERDUE
- COMPLETED
- FRAUD_SUSPECTED
- DISPUTED
- PENDING_INSPECTION

Error responses:

- 401: Not authenticated / invalid token
- 403: {"detail": "You do not have permission to view this loan."}
- 404: {"detail": "Loan not found."}

## 3. CRITICAL: Transaction Rules (Idempotency & Polling)

### Mandatory Idempotency-Key for checkout/return

Applies to:

- POST /api/v1/loans/checkout
- POST /api/v1/loans/return/initiate

Rules:

1. Header is mandatory. Missing header returns 400.
2. Maximum key length is 256 chars. Longer keys return 400.
3. Duplicate keys return 409:

   Duplicate request with this idempotency key is already being processed or has completed.

4. Keys are stored in Redis with TTL 24h (SET NX EX).
5. If Redis is unavailable during idempotency checks, API returns 503.
6. Key release behavior is intentional:
   - If transaction fails before DB commit, key can be released for safe retry.
   - If DB commit already happened, key remains consumed to prevent duplicate side effects.

### The Snoepautomaat Logic

Checkout and return-initiate are commit-first, hardware-second flows.

What this means:

1. API commits database transaction first.
2. API returns 202 Accepted after successful commit.
3. Hardware websocket command (open_slot) is sent after commit.
4. Hardware send can fail after the 202 response.
5. Therefore, 202 means request is persisted, not that the physical door action already succeeded.

Client obligations:

1. After any 202 from checkout/return-initiate, immediately start polling GET /api/v1/loans/{loan_id}/status.
2. Continue polling until state resolves to expected business outcome:
   - Checkout success target: ACTIVE
   - Return success target: COMPLETED
3. Treat these statuses as intervention/exception states:
   - FRAUD_SUSPECTED
   - PENDING_INSPECTION
   - DISPUTED
4. If checkout remains RESERVED too long, backend timeout worker can move it to PENDING_INSPECTION (requires human follow-up).

## 4. WebSocket Protocol (Vision Box / Simulation)

### Connection URL

`wss://<host>/api/v1/ws/visionbox/{kiosk_id}`

Handshake requirements:

- Header required: X-Device-Token
- Accepted: Vision Box token or Simulation token
- Missing/invalid token: connection rejected (policy violation)

Implementation note:

- Backend websocket route is mounted at /ws/visionbox/{kiosk_id}. In deployments where API traffic is prefixed with /api/v1, expose it as /api/v1/ws/visionbox/{kiosk_id}.

### Server-to-Client payloads

#### open_slot

Primary checkout/return command shape:

```json
{
  "action": "open_slot",
  "locker_id": 12,
  "loan_id": "<uuid>",
  "evaluation_type": "CHECKOUT"
}
```

Return variant uses evaluation_type: RETURN.

Admin force-open variant may omit loan/evaluation fields:

```json
{
  "action": "open_slot",
  "locker_id": "12"
}
```

#### set_led

```json
{
  "action": "set_led",
  "locker_id": 12,
  "color": "green"
}
```

Observed colors in flows: green, orange, red.

### Client-to-Server payloads

#### slot_closed

```json
{
  "event": "slot_closed",
  "locker_id": "12"
}
```

Current backend behavior:

- Accepts JSON messages.
- Logs slot_closed events.
- Does not currently emit an acknowledgment payload for slot_closed.
