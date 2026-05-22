# Discipline policy

EasyLend implements automated disciplinary actions to protect equipment and ensure accountability during damage disputes.

## 1. Automatic suspension

A user's account is automatically locked for 7 days under these conditions:

- **Grace-period report:** User reports an item is damaged immediately after pickup.
- **AI-detected damage:** Vision AI flags damage during return and an admin approves the finding.

## 2. Suspension scope

When a suspension is triggered:

1. The **current borrower** is locked.
2. For damage reports, the **previous borrower** is also locked pending investigation to determine liability.
3. `User.locked_until` is updated atomically using a `FOR UPDATE NOWAIT` lock.

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant Redis
    participant DB as PostgreSQL
    participant LoanStateMachine
    participant HardwareManager

    Client->>API: POST /api/v1/loans/{loan_id}/report-damage (Idempotency-Key)
    API->>Redis: _guard_idempotency(idempotency_key)

    alt Duplicate idempotency key
        API-->>Client: 409 Conflict
    else Idempotency key accepted
        API->>DB: SELECT loan FOR UPDATE NOWAIT
        API->>DB: SELECT asset FOR UPDATE NOWAIT
        API->>DB: SELECT locker FOR UPDATE NOWAIT
        Note over API,DB: Lock order: Loan → Asset → Locker → Users (FOR UPDATE NOWAIT)

        API->>API: Validate grace period using borrowed_at OR created_at (max 5 minutes)
        Note over API: If created_at is unavailable, the implementation falls back to reserved_at.

        API->>LoanStateMachine: apply_transition(loan, asset, locker, DISPUTED)
        LoanStateMachine-->>API: loan DISPUTED, asset MAINTENANCE, locker MAINTENANCE, suspend_users true

        API->>DB: SELECT current_user FOR UPDATE NOWAIT
        API->>DB: UPDATE current_user.locked_until = now + 7 days
        API->>DB: SELECT previous completed loan ORDER BY returned_at DESC LIMIT 1

        opt Previous loan exists
            API->>DB: SELECT previous_user FOR UPDATE NOWAIT
            API->>DB: UPDATE previous_user.locked_until = now + 7 days
        end

        API->>DB: INSERT audit GRACE_PERIOD_DAMAGE_REPORTED (loan_id, asset_id, previous_loan_id)
        API->>DB: COMMIT

        API->>HardwareManager: set_led(color="orange")
        alt Hardware sync fails
            HardwareManager-->>API: error
            API->>API: Log error and return success
            API-->>Client: 200 OK
        else Hardware sync succeeds
            HardwareManager-->>API: ack
            API-->>Client: 200 OK
        end
    end
```

## 3. Resolution

Only a system administrator can lift a suspension early by resetting the `locked_until` timestamp and the failed login attempts counter.
