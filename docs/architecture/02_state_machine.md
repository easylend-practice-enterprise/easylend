# State Management (LoanStateMachine)

EasyLend uses a Redux-style centralized transition model. The `LoanStateMachine` is the **single source of truth** for all legal loan lifecycle transitions and the resulting statuses of assets and lockers.

## The State Authority

Controllers are restricted to **orchestration only**: they validate input, acquire locks, and coordinate side effects. They do **not** directly author business state transitions. Instead, they call `LoanStateMachine.apply_transition()`, which enforces the canonical state rules.

## Primary Transitions

| Initial State | Target State | Asset Outcome | Locker Outcome | Context |
|---|---|---|---|---|
| `None` | `RESERVED` | `BORROWED` | `OCCUPIED` | Post-checkout (Waiting for pickup) |
| `RESERVED` | `ACTIVE` | `BORROWED` | `AVAILABLE` | Vision confirms item taken |
| `ACTIVE` | `RETURNING` | `BORROWED` | `OCCUPIED` | Return initiated (Locker reserved) |
| `RETURNING` | `COMPLETED` | `AVAILABLE` | `OCCUPIED` | Vision confirms item returned |
| `ACTIVE` | `OVERDUE` | `BORROWED` | `None` | Due date passed |
| `OVERDUE` | `RETURNING` | `BORROWED` | `OCCUPIED` | Late return initiated |

## Exceptional Transitions (Quarantine)

Detections of fraud, damage, or hardware timeouts trigger transitions to quarantine states:

- **`FRAUD_SUSPECTED`**: Triggered if a locker is still NOT empty after a checkout.
- **`PENDING_INSPECTION`**: Triggered by hardware timeouts or AI-detected damage.
- **`DISPUTED`**: Triggered by user damage reports or admin verification.

## Overdue Blocking Rule

We enforce a strict **Overdue Block** policy. If a user has any loan in the `OVERDUE` state, they are prohibited from starting new checkouts until the overdue item is successfully returned.
