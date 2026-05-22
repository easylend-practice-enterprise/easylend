# Concurrency and locking

EasyLend implements a zero-trust concurrency model to ensure database integrity in high-traffic environments. This prevents lock convoys, deadlocks, and race conditions between kiosks.

## Deterministic lock order

Transactions targeting multiple entities always acquire row locks in a strict order:

1. **Loan**
2. **Asset**
3. **Locker**
4. **Users**

## Locking patterns

### 1. Fail-fast

Used during checkout and admin judgments via `SELECT ... FOR UPDATE NOWAIT`.

- **Behavior:** If a resource is locked by another transaction, the API returns an immediate `409 Conflict`.
- **Benefit:** Prevents hanging sessions and resource exhaustion.

### 2. Priority selection

Used for locker allocation during return initiation via `SELECT ... FOR UPDATE SKIP LOCKED`.

- **Behavior:** The query skips locked available lockers and selects the next free slot.
- **Benefit:** Supports simultaneous returns at the same kiosk without contention.

## Idempotency guard

Mutable transactions require a mandatory `Idempotency-Key` header.

- Keys are persisted in Redis with a 24-hour TTL.
- This ensures network retries do not result in duplicate records or physical actions.

## Dead connection resilience

The backend actively monitors WebSocket connection state.

- **Fail-safe transmission:** Command calls are wrapped in exception handlers.
- **Automatic eviction:** Dead sockets are removed from the active connection registry immediately.
- **Transaction safety:** Connection failures do not trigger database rollbacks: the database remains the source of truth, and the system relies on the 207 status code for kiosk-side error handling.
