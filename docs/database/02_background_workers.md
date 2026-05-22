# Background workers

EasyLend runs specialized workers to maintain state without blocking API requests.

## 1. Timeout worker

- **Interval:** 60 seconds.
- **Lock TTL:** 55 seconds.
- **Goal:** Process loans in `RESERVED` or `RETURNING` states that exceed the 3-minute inactivity threshold.
- **Result:** Transitions loan to `PENDING_INSPECTION` and marks the locker as `MAINTENANCE`.

## 2. Overdue worker

- **Interval:** 1 hour.
- **Lock TTL:** 3500 seconds.
- **Goal:** Identify `ACTIVE` loans past their `due_date`.
- **Result:** Transitions loan to `OVERDUE`, blocking the user from new checkouts.

## Reliability

- **Distributed locks:** Redis-backed locks prevent duplicate execution.
- **Isolation:** Loans are processed in individual transactions.
- **Stability:** Poison-pill exclusion ensures one failing record doesn't stall the batch.
