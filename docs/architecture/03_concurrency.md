# Concurrency & Locking Strategy

To ensure database integrity in high-traffic campus environments, EasyLend implements a **Zero-Trust Concurrency Model**. This prevents lock convoys, deadlocks, and race conditions between multiple kiosks.

## Deterministic Lock Order

Multi-entity transactions (such as analyzing a return) always acquire row locks in a strict, deterministic order to prevent deadlocks:

1. **Loan** → 2. **Asset** → 3. **Locker** → 4. **Users**

## Locking Patterns

### 1. Fail-Fast (NOWAIT)

Used during **Checkout** and **Admin Judgments**. We use `SELECT ... FOR UPDATE NOWAIT`.

- **Behavior**: If the required resource (Asset or Locker) is currently locked by another transaction, the API returns an immediate `409 Conflict` instead of waiting.
- **Benefit**: Prevents user sessions from hanging and avoids resource exhaustion on the server.

### 2. Priority Selection (SKIP LOCKED)

Used during **Locker Allocation** for returns. We use `SELECT ... FOR UPDATE SKIP LOCKED`.

- **Behavior**: When assigning a locker for a return, the query skips any currently locked "available" lockers and picks the next free one.
- **Benefit**: Allows multiple users to initiate returns at the same kiosk simultaneously without colliding or blocking.

## Idempotency Guard

Every mutable transaction (`/checkout`, `/return/initiate`) requires a mandatory `Idempotency-Key` provided by the client.

- Keys are stored in Redis with a **24-hour TTL**.
- This ensures that network retries or accidental double-taps in the UI do not result in duplicate loan records or physical door actuations.

## Dead Connection Resilience

The `ConnectionManager` in the Backend API actively monitors the state of WebSocket connections to the kiosks.

- **Fail-Safe Transmissions**: All `send_command` calls are wrapped in exception handlers.
- **Automatic Eviction**: If a WebSocket is found to be dead during a command transmission, the kiosk is immediately removed from the `active_connections` registry.
- **Transaction Safety**: Connection failures during an API call (like `/checkout`) do not rollback the database transaction; the DB remains the source of truth, and the system relies on the "IoT Partial Success" (207) code to inform the Kiosk of the delivery failure.
