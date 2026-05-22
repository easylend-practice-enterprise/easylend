# State management

EasyLend uses a centralized transition model. The `LoanStateMachine` is the single source of truth for all loan lifecycle changes and correlated status updates for assets and lockers.

## State authority

Controllers are restricted to orchestration: they validate input, acquire row locks, and coordinate side effects. They do not author business state transitions directly. Instead, they call `LoanStateMachine.apply_transition()`, which enforces the transition rules.

## Primary transitions

| Initial state | Target state | Asset outcome | Locker outcome | Context |
|---|---|---|---|---|
| `None` | `RESERVED` | `BORROWED` | `OCCUPIED` | Post-checkout: waiting for pickup. |
| `RESERVED` | `ACTIVE` | `BORROWED` | `AVAILABLE` | Vision confirms item taken. |
| `ACTIVE` | `RETURNING` | `BORROWED` | `OCCUPIED` | Return initiated: locker reserved. |
| `RETURNING` | `COMPLETED` | `AVAILABLE` | `OCCUPIED` | Vision confirms item returned. |
| `ACTIVE` | `OVERDUE` | `BORROWED` | `None` | Due date passed. |
| `OVERDUE` | `RETURNING` | `BORROWED` | `OCCUPIED` | Late return initiated. |

## Exceptional transitions

Scenarios where automated logic detects anomalies:

- **FRAUD_SUSPECTED:** Triggered if a locker remains occupied after a checkout pickup.
- **PENDING_INSPECTION:** Triggered by hardware timeouts or AI-detected damage.
- **DISPUTED:** Triggered by manual damage reports or admin verification.

## Overdue blocking

We enforce a strict block policy. If a user has any loan in the `OVERDUE` state, they are prohibited from starting new checkouts until the overdue item is returned.
