# Background Workers

To maintain system state without blocking the main API thread, EasyLend runs two specialized background workers as separate containers.

## 1. Loan Timeout Worker

- **Interval**: Runs every 60 seconds.
- **Purpose**: Scans for `RESERVED` or `RETURNING` loans that have not progressed within 3 minutes.
- **Action**: Transitions the loan to `PENDING_INSPECTION` and marks the associated locker as `MAINTENANCE`. This handles scenarios where a user walks away without closing a door or a hardware sensor fails to report.

## 2. Overdue Worker

- **Interval**: Runs every 1 hour.
- **Purpose**: Identifies `ACTIVE` loans that have passed their `due_date`.
- **Action**: Transitions the loan to `OVERDUE`.
- **Impact**: Once a loan is marked `OVERDUE`, the user is immediately blocked from starting any new checkouts until the item is returned.

## Reliable Execution

Both workers utilize:

- **Distributed Redis Locks**: Ensures only one instance of a worker runs across multiple API replicas.
- **Per-Row NOWAIT Locking**: Prevents the worker from blocking concurrent API requests.
- **Poison-Pill Exclusion**: Failing records are isolated so a single problematic loan does not stall the entire batch.
