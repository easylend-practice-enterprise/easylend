# EasyLend Backend: Step-by-Step Plan

> Order based on technical dependencies. Auth must be fully complete before CRUD, CRUD before business logic.

## Step 1: Password Hashing (complete)

**Ticket:** ELP-23 · **Status:** ✅ Done

- Integrate `passlib` or `bcrypt` into the FastAPI app
- Hash password on registration / update
- Verify on login
- **Done criteria:** unit test that validates hash + verify

> **Seed script (chore, no ticket):** `seed.py` is available under `backend/api/scripts/seed.py`. Pay attention to the **FK order**, the DB enforces referential integrity:
>
> ```text
> Step 1: ROLES (role_id becomes FK in USERS)
> Step 2: CATEGORIES (category_id becomes FK in ASSETS)
> Step 3: KIOSKS (kiosk_id becomes FK in LOCKERS)
> Step 4: LOCKERS (locker_id becomes FK in ASSETS)
> Step 5: USERS with role_id --> ASSETS with category_id + locker_id
> ```
>
> Run in local test environment: `uv run python scripts/seed.py`

## Step 2: Finish Auth Research

**Ticket:** ELP-82 · **Status:** ✅ Done

ELP-82 is research, not implementation. Mark this done once a decision has been made on:

- [x] JWT algorithm (HS256 vs RS256)
- [x] Access token TTL (e.g. 15 min)
- [x] Refresh token TTL (e.g. 7 days)
- [x] Refresh token storage: Redis key structure (`refresh:{user_id}:{jti}`, multi-session, value = `"active"`)

## Step 3: Define JWT Model

**Ticket:** ELP-21 · **Status:** ✅ Done · *Requires: step 2*

- Pydantic model for JWT payload:

  ```python
  class TokenPayload(BaseModel):
      sub: UUID  # user_id
      role: str
      exp: datetime
      jti: UUID  # token ID (for revocation)
  ```

- Separate `schemas/token.py`

- [x] Implemented in `backend/api/app/schemas/token.py`

## Step 4: Create JWT Tokens

**Ticket:** ELP-22 · **Status:** ✅ Done · *Requires: step 3*

- `create_access_token()` and `verify_access_token()` functions
- FastAPI dependency `get_current_user` via `Authorization: Bearer`
- Endpoints:
  - `POST /api/v1/auth/nfc` --> start login via NFC (provides temporary context)
  - `POST /api/v1/auth/pin` --> verifies PIN and returns access + refresh token
  - `POST /api/v1/auth/logout`

  - [x] Implemented in `backend/api/app/core/security.py`, `backend/api/app/api/deps.py`, and `backend/api/app/api/v1/endpoints/auth.py`
    - [x] API tests available in `backend/api/app/tests/test_auth_api.py`

> **Test with seed data (step 1)**: no User CRUD needed to test this.

## Step 5: Refresh Token Mechanism

**Ticket:** ELP-24 · **Status:** ✅ Done · *Requires: step 4*

- `POST /api/v1/auth/refresh` endpoint
- Validate refresh token --> issue new access token
- Invalidate refresh token after use (rotation)

- [x] Endpoint + rotation implemented in `backend/api/app/api/v1/endpoints/auth.py`
- [x] Single-use and logout revocation tested in `backend/api/app/tests/test_auth_api.py`

## Step 6: Redis Integration (refresh tokens)

**Ticket:** ELP-25 · **Status:** ✅ Done · *Requires: step 5*

- Redis config is already ready (ELP-17 ✅ Done)
- Store refresh tokens in Redis with TTL (Multi-session):

  ```text
  SET refresh:{user_id}:{jti} "active" EX 604800
  ```

- Revocation check on every refresh request
- On logout: DEL key (or `revoke_all` on account compromise)

- [x] Implemented in `backend/api/app/db/redis.py` and used in auth endpoints
- [x] Redis failure paths (`503`) tested in `backend/api/app/tests/test_auth_api.py`

## Step 7: CRUD: Users & Permissions

**Ticket:** ELP-27 · **Status:** ✅ Done · *Requires: step 4 (auth middleware)*

- [x] `GET /api/v1/users` (admin: list of all users, pagination via `skip`/`limit`)
- [x] `GET /api/v1/users/me`
- [x] `GET /api/v1/users/{id}` (admin only)
- [x] `POST /api/v1/users` (admin: create new user)
- [x] `PATCH /api/v1/users/{id}` (admin: update user, e.g. unblock account via `failed_login_attempts: 0` and `locked_until: null`)
- [x] Role-based access control dependency
- [x] Permissions model (RBAC: admin / staff / kiosk)
- [x] `GET /api/v1/roles` (admin: retrieve all available roles)

> **NFC tag registration (chicken-and-egg fix):** The Login Flow only works when `nfc_tag_id` is linked to a user. Added:
>
> - [x] `PATCH /api/v1/users/{id}/nfc  { nfc_tag_id }` (admin only)

## Step 8: CRUD: Kiosks --> Categories --> Lockers --> Assets

**Ticket:** ELP-26 · **Status:** 📋 In Progress · *Requires: step 7 (permissions)*

> **FK order required:** Each entity has an FK to the previous one. Build in this order.

**Kiosks** *(kiosk_id FK in LOCKERS: must come first)*

- [x] `GET /api/v1/kiosks` (admin)
- [x] `POST /api/v1/kiosks` (admin: register a new kiosk device)
- [x] `PATCH /api/v1/kiosks/{id}/status`

**Categories** *(category_id FK in ASSETS: must come first)*

- [x] `GET /api/v1/categories` (all authenticated users)
- [x] `POST /api/v1/categories` (admin)
- [x] `PATCH /api/v1/categories/{id}`

**Lockers** *(requires kiosk_id)*

- [x] `GET /api/v1/lockers` (admin: overview + status)
- [x] `GET /api/v1/lockers/{id}` (admin)
- [x] `POST /api/v1/lockers` (admin: link locker to kiosk)
- [x] `PATCH /api/v1/lockers/{id}/status` (admin: update status, e.g. to MAINTENANCE)

**Assets** *(requires category_id + locker_id)*

- [x] `GET /api/v1/assets` (pagination, filter by status, excludes soft-deleted rows)
- [x] `GET /api/v1/assets/{id}`
- [x] `POST /api/v1/assets` (admin: including `aztec_code`, `category_id`, optional `locker_id`)
- [x] `PATCH /api/v1/assets/{id}` (admin)
- [x] `DELETE /api/v1/assets/{id}` (admin, soft-delete)
  - Implementation: set `is_deleted = true` on the `assets` row (preserve `asset_status` and history). Use DB-level default `FALSE` for `is_deleted`.

**Catalog** *(requires assets + categories: buildable in same ticket)*

- [ ] `GET /api/v1/catalog` (all authenticated users)
  - **Role == staff/student:** categorised pool: number of available assets per category (`asset_status = 'AVAILABLE' AND is_deleted = FALSE GROUP BY category_id`).
  - **Role == Admin:** admin view: all assets with current `loan_status` and borrower info via JOIN on `loans` and `users`.

- [x] CRUD + RBAC implementation is in `backend/api/app/api/v1/endpoints/equipment.py`
- [x] API tests for roles + happy/forbidden paths are in `backend/api/app/tests/test_equipment_api.py`
- [ ] Remaining gap in this step: `GET /api/v1/catalog`

## Step 9: M2M Authentication (Static Device Tokens)

**Ticket:** ELP-90 · **Status:** ✅ Done · *Requires: step 4*

> ⚠️ **Moved up.** The Vision Box needs a Static Device Token to call `POST /api/v1/vision/analyze` (Step 10b). Must be ready before the hardware integration.

**Decision: Static API Keys via `X-Device-Token` header (no OAuth `client_credentials`).**
Hardware clients (Vision Box, Simulation) authenticate with a pre-configured, long-lived key per device, managed via `.env`. This keeps the hardware integration simple and avoids token rotation on embedded hardware.

- New FastAPI dependency: `verify_device_token(x_device_token: str = Header(...))` that compares the value against the configured secrets.
- Scope per device via separate dependency variants (e.g. `verify_vision_box_token`).
- Keys in `.env` as `VISION_BOX_API_KEY` and `SIMULATION_API_KEY`.
- **No** `POST /api/v1/auth/token` endpoint or `client_credentials` grant.

- [x] Device-token dependencies implemented in `backend/api/app/api/deps.py` (`verify_vision_box_token`, `verify_simulation_token`)
- [x] Config keys present in `backend/api/app/core/config.py` (`VISION_BOX_API_KEY`, `SIMULATION_API_KEY`)
- [x] Dependency behavior tested in `backend/api/app/tests/test_deps.py`
- [x] Applied to real hardware endpoints (`POST /api/v1/vision/analyze`)

## Step 10a: Transaction CRUD (checkout / return)

**Ticket:** ELP-28 · **Status:** 📋 In Progress · *Requires: step 8 (assets + lockers)*

Core business logic without hardware coupling: testable via Swagger/Postman.

- [x] `POST /api/v1/loans/checkout`: lend an asset, assign a locker
  - **Concurrency:** Use `SELECT ... FOR UPDATE NOWAIT` to guarantee that 2 users can never be assigned the same asset simultaneously.
  - [ ] **Pro-feature (Idempotency):** Requires an `Idempotency-Key` in the header (e.g. a UUID). The API checks Redis to see if this key has been used recently to prevent a glitchy tablet (double-taps) from accidentally starting two loans.
- [x] `POST /api/v1/loans/return/initiate`: start the return process, search for a free locker.
  - [ ] **Pro-feature (Idempotency):** Requires an `Idempotency-Key` in the header (against double-taps).
- [x] `GET /api/v1/loans/{loan_id}/status`: polling endpoint for the current transaction status.
- [x] `GET /api/v1/loans`: list endpoint (admin sees all, non-admin sees own loans)
- [ ] **Timeout Worker (Hardware-aware):** A background task cancels loans after 3 minutes of inactivity. **Note:** If hardware has already been activated (WSS `open_slot` has been sent), the status must NEVER be rolled back to `AVAILABLE`. On a timeout after physical action, the locker goes directly to `MAINTENANCE` (physical inspection required).
- [x] Validation: asset availability/state, owner checks (`loan.user_id == jwt.sub`), kiosk existence, locker availability
- [ ] Status update asset + locker + audit log entry

- [x] Implemented in `backend/api/app/api/v1/endpoints/loans.py`
- [x] API tests available in `backend/api/app/tests/test_loans_api.py` (including lock-contention and authorization paths)

## Step 10b: Hardware & AI Integration

**Status:** 📋 In Progress · *Requires: step 9 (Static Device Tokens) + step 10a*

By far the most complex part. Couples the transaction logic with physical hardware.

**Decision: Photo storage (`photo_url`):**
We use a **Local Docker Volume** (`/app/uploads`). This fits perfectly within the scope of the prototype and is extremely fast.

- Photos are written to disk and the API serves them via a new endpoint: `GET /api/v1/images/{filename}`.
  - **Security:** implementation must:
    - Enforce a safe filename strategy (UUIDs, no raw user input).
    - Normalise and validate the path to prevent path traversal (`../`).
    - Apply authorisation (only admins or the loan owner may view the photo).

**WebSockets (Vision Box control):**

- [x] Set up a WebSocket manager in FastAPI (`/ws/visionbox/{kiosk_id}`) with static token auth.
- [ ] Send `open_slot {locker_id, loan_id}` after checkout approval
- [ ] Send `set_led {locker_id, color}` based on AI result or error
- [ ] Receive `slot_closed` event from Vision Box and route to appropriate transaction logic
- [ ] **Fallback:** if there is no active WSS session from the Vision Box --> return `503` to the App with message "Vision Box unreachable". Log in audit.

**AI Evaluation endpoint (for Vision Box):**

- [x] `POST /api/v1/vision/analyze`: Proxy endpoint created, receives photo + forwards to VM2 AI safely (ELP-94 completed).
- [ ] Save photo in `/app/uploads` --> generate `photo_url`
- [ ] Process result:
  - **Checkout:** locker empty? --> `ACTIVE` or `FRAUD_SUSPECTED` (on fraud: asset + locker back to `AVAILABLE`)
  - **Return:** damage? --> `COMPLETED` or `PENDING_INSPECTION`
  - **Fallback (AI Timeout/Crash):** if the AI VM does not respond within 10s: mark loan as `PENDING_INSPECTION`, locker to `MAINTENANCE` (requires physical inspection by administrator).
- [ ] Store in `ai_evaluations` table including `photo_url` and `model_version`

## Step 10c: Admin Quarantine Dashboard

**Status:** ❌ Open · *Requires: step 10b*

Endpoints for the admin panel to handle blocked loans (damage or fraud). Used in the Quarantine Flow.

- `GET /api/v1/admin/loans?status=PENDING_INSPECTION` (list of loans in quarantine)
- `GET /api/v1/admin/evaluations/{evaluation_id}` (retrieves the AI report and `photo_url`)
- `PATCH /api/v1/admin/evaluations/{id}` (Administrator approves: status to `DISPUTED`, or rejects: status to `COMPLETED`)

## Step 11: Input Sanitisation

**Ticket:** ELP-30 · **Status:** ❌ Open · *Can be executed in parallel with step 10+*

- Pydantic validators on all request bodies
- Max-length checks, regex on emails / IDs
- SQL injection not applicable (SQLAlchemy ORM): watch for XSS in string fields

## Step 12: Rate Limiting & Abuse Prevention

**Ticket:** ELP-31 · **Status:** ❌ Open · *Requires: step 6 (Redis)*

Rate limiting happens in 3 strategic layers (hybrid approach):

1. **Layer 1: Business Logic (Vertical Brute-force)**
   - The database (`failed_login_attempts`) blocks one specific account after 5 incorrect PINs.
2. **Layer 2: Public Endpoints (DDoS & Horizontal Brute-force)**
   - Endpoints such as `/auth/nfc` are public. Here we use **IP-based** rate limiting via Redis/slowapi.
   - We set the limit generously (e.g. 500 req/min per IP) to avoid issues with campus-NAT (multiple kiosks on 1 network) while still blocking bots.
3. **Layer 3: Authenticated Endpoints (Spam/Glitch prevention)**
   - Once a client has a JWT or M2M token, we rate-limit on **Token ID (`sub` / `kiosk_id`)**.
   - This prevents a compromised account or glitchy app from overloading the server (e.g. 60 req/min per user) without penalising other users on the same network.

> Current state: brute-force lockout at account level is already present in `POST /api/v1/auth/pin`; explicit rate limiting (IP/token) is still open.

## Testing Milestones (when to write tests)

Write tests directly in the same PR as the feature. Use the minimum test set per phase below.

1. **After steps 4-6 (auth + refresh + Redis): done**

   - [x] Unit tests for token helpers (`create/verify` + token type checks)
   - [x] API test: `POST /auth/refresh` is single-use (2nd attempt returns 401)
   - [x] API test: `POST /auth/logout` invalidates the refresh token for subsequent use
   - [x] API test: `POST /auth/pin` lockout after 5 incorrect attempts
   - [x] API tests for `POST /auth/nfc` and Redis failure paths (`503`)

2. **After steps 7-8 (CRUD + RBAC)**

   - [x] Authorisation tests per role (admin/staff/kiosk)
   - [x] Happy-path + forbidden-path per endpoint
   - [ ] `GET /api/v1/catalog` coverage pending (endpoint not implemented yet)

3. **After steps 10a-10c (transactions + hardware + AI)**

   - [x] Concurrency test for checkout (no double assignment)
   - [ ] Idempotency test for checkout/return
   - [ ] Fallback tests (AI timeout, no active Vision Box WebSocket)

4. **After steps 11-13 (sanitisation/rate-limit/audit)**

   - Input validation tests (boundaries/regex)
   - Rate-limit tests (IP and token based)
   - Audit-chain integrity test

## Step 13: Hash-Chaining Audit Logs

**Ticket:** ELP-29 · **Status:** ❌ Open · *Requires: step 10a (transactions)*

- Each audit log entry contains `prev_hash` of the previous entry
- SHA-256 over `(prev_hash + entry_data)` --> `current_hash`
- Tamper-detection: verify the chain is intact on retrieval
- Endpoint: `GET /api/v1/audit` (admin only)

## Step 14: Overdue Worker

- Overdue Worker: Implement a background task (APScheduler or Celery) that runs every hour. It must execute: `UPDATE loans SET loan_status = 'OVERDUE' WHERE loan_status = 'ACTIVE' AND due_date < NOW();` and automatically log this in the audit_logs.

## Scope Note (PXE)

- PXE functionality is moved to V2 (Post-MVP) and is out of the current implementation scope.

## Overview

```text
[1] Password hashing + seed.py  <-- also seed ROLES/CATEGORIES/KIOSKS!
  --> [2] Finish auth research
    --> [3] JWT model
      --> [4] JWT tokens  <-- test with seed data
        --> [5] Refresh token
          --> [6] Redis integration
            --> [7] Users CRUD  <-- incl. PATCH /users/{id}/nfc
              --> [8] Kiosks --> Categories --> Lockers --> Assets CRUD (catalog pending)
                --> [10a] Transaction CRUD (idempotency + timeout worker + audit pending)
                  --> [10b] Hardware & AI  <-- decision: Local Docker Volume
                          WebSockets + fallback + /vision/analyze (PROXY DONE ✅)
                    --> [10c] Admin Quarantine Dashboard
        --> [9] M2M Static Device Tokens (✅ DONE)
[11] Input sanitisation (parallel, from step 10+)
[12] Rate limiting (requires Redis: step 6)
[13] Hash-chaining audit logs (requires step 10a)
```
