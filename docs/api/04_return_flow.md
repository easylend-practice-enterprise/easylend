# Return flow

Logic for returning borrowed assets and verifying their condition.

## Return initiation

The student scans the asset's Aztec code. The API assigns an available locker and moves the loan to a pre-vision mutex state (`RETURNING`).

```mermaid
sequenceDiagram
    actor User as User
    participant App as Kiosk App (Flutter)
    participant API as FastAPI Backend
    participant FSM as LoanStateMachine
    participant Redis as Redis Cache
    participant DB as PostgreSQL
    participant VB as Vision Box (RPi 4)
    participant AI as Vision AI Service (yolo26-dual-model)

    User->>App: Selects "Return item" and picks their active loan
    App->>API: POST /api/v1/loans/return/initiate {loan_id, kiosk_id} [JWT, Idempotency-Key]

    API->>Redis: EXISTS idempotency:{key}
    alt Duplicate Idempotency-Key
        API-->>App: 409 Conflict {"Request already processing"}
    else Key not seen
        API->>Redis: SETEX idempotency:{key} 86400 "processing"

        API->>DB: SELECT kiosk WHERE kiosk_id = ?
        alt Kiosk not found
            API-->>App: 404 Not Found
        else Kiosk found
            alt Vision Box offline (WSS not connected)
                API-->>App: 503 Service Unavailable
                App-->>User: "Lockers currently out of service"
            else Vision Box online
                API->>DB: SELECT loan WHERE loan_id = ?
                alt Loan not found
                    API-->>App: 404 Not Found
                else Loan belongs to another user (loan.user_id != jwt.sub)
                    API-->>App: 403 Forbidden
                    App-->>User: "This loan does not belong to you"
                else Loan not in ACTIVE or OVERDUE status
                    API-->>App: 400 Bad Request ("Loan is not returnable")
                else Loan found & Owner matches
                    API->>DB: BEGIN TRANSACTION

                    %% Atomic state-transition guard on the active/overdue loan row
                    API->>DB: SELECT loan WHERE loan_id = ? AND loan_status IN ('ACTIVE', 'OVERDUE') AND return_locker_id IS NULL FOR UPDATE
                    alt Loan lock contention
                        API-->>App: 409 Conflict {"A return is already in progress"}
                    else Loan state changed concurrently
                        API-->>App: 409 Conflict {"Loan no longer returnable"}
                    else Lock acquired

                        %% Find and lock first available locker (SKIP LOCKED prevents duplicate assignment)
                        API->>DB: SELECT locker WHERE kiosk_id = ? AND locker_status = 'AVAILABLE' ORDER BY logical_number FOR UPDATE SKIP LOCKED LIMIT 1
                        alt No available locker
                            API-->>App: 503 Service Unavailable {"No available lockers at this kiosk"}
                        else Locker found
                            API->>FSM: apply_transition(loan, none, locker, RETURNING)
                            FSM-->>API: loan_status='RETURNING', locker_status='OCCUPIED'
                            API->>DB: UPDATE loans SET return_locker_id = locker_id WHERE loan_id = ?
                            API->>DB: INSERT INTO audit_logs {action_type: 'LOAN_RETURN_INITIATED', payload: {loan_id, asset_id, return_locker_id}}

                            %% Hardware command sent AFTER DB commit
                            Note over API,VB: DB committed BEFORE send; command outcome does not change endpoint response
                            API->>DB: COMMIT

                            Note over API,VB: locker_id in WSS = logical_number (physical slot int), not UUID
                            API->>VB: WSS: open_slot {locker_id: logical_number, loan_id, evaluation_type: RETURN}

                            alt Hardware command failed immediately (disconnection)
                                Note over API,App: API returns 207 to indicate DB success but HW delivery failure
                                API-->>App: 207 Multi-Status {loan_id, return_locker_id, loan_status: RETURNING}
                                App-->>User: Show error: "Hardware communication failed"
                            else Hardware command accepted/dispatched
                                API-->>App: 202 Accepted {loan_id, return_locker_id, loan_status: RETURNING}
                                App-->>User: Show loader: "Bring item to locker #N"
                            end
                        end
                    end
                end
            end
        end
    end

    VB->>VB: GPIO: open slot + LED green
    User->>VB: Places item in locker, closes door
    VB->>API: WSS: slot_closed {event: "slot_closed", locker_id: "<logical_number>"}
    Note over API: slot_closed is logged only (no transactional state change)

    %% Vision Box triggers AI analysis (M2M, no JWT)
    VB->>API: POST /api/v1/vision/analyze (X-Device-Token) {loan_id, image, evaluation_type: RETURN}

    %% Vision AI analysis with parallel Phase 1 (no row locks held during AI call)
    par Object Detection (Phase 1 of 2)
        API->>AI: POST /detect {image}
        AI-->>API: {locker_empty, detections}
    and Segmentation (Phase 2 of 2)
        API->>AI: POST /segment {image}
        AI-->>API: {has_damage_detected}
    end

    Note over API,DB: After AI: deterministic Loan --> Asset --> Locker lock order during finalization
    Note over API,DB: Reduces contention window: locks held only during ~100ms DB write, not the ~30s AI call

    alt Locker empty OR Damage detected
        API->>FSM: apply_transition(loan, asset, locker, PENDING_INSPECTION)
        FSM-->>API: loan_status='PENDING_INSPECTION', asset_status='PENDING_INSPECTION', locker_status='MAINTENANCE'
        API->>DB: UPDATE assets SET locker_id = <return_locker_id> WHERE asset_id = ?
        API->>DB: INSERT INTO audit_logs {action_type: 'VISION_EVALUATION_PROCESSED'}
        Note over API,VB: locker_id in WSS = logical_number (physical slot int)
        API->>VB: WSS: set_led {locker_id: logical_number, color: orange}
    else AI service error / model crash
        Note over API,DB: Failure fallback transition is applied only after Loan/Asset/Locker locks are held
        API->>FSM: apply_transition(loan, asset, locker, PENDING_INSPECTION)
        FSM-->>API: loan_status='PENDING_INSPECTION', asset_status='PENDING_INSPECTION', locker_status='MAINTENANCE'
        API->>DB: UPDATE assets SET locker_id = <return_locker_id> WHERE asset_id = ?
        API->>DB: INSERT INTO audit_logs {action_type: 'VISION_EVALUATION_FAILED'}
        Note over API,VB: locker_id in WSS = logical number (physical slot int)
        API->>VB: WSS: set_led {locker_id: logical_number, color: orange}
        Note over API,DB: Loan stays PENDING_INSPECTION until admin review and timeout worker monitors RESERVED loans separately
    else Item present AND No damage (success)
        API->>FSM: apply_transition(loan, asset, locker, COMPLETED)
        FSM-->>API: loan_status='COMPLETED', asset_status='AVAILABLE', locker_status='OCCUPIED'
        API->>DB: UPDATE loans SET returned_at = NOW() WHERE loan_id = ?
        API->>DB: UPDATE assets SET locker_id = <return_locker_id> WHERE asset_id = ?
        API->>DB: INSERT INTO audit_logs {action_type: 'LOAN_RETURN_CONFIRMED', payload: {loan_id, asset_id, locker_id}}
        API->>DB: INSERT INTO audit_logs {action_type: 'VISION_EVALUATION_PROCESSED'}
        Note over API,VB: locker_id in WSS = logical_number (physical slot int)
        API->>VB: WSS: set_led {locker_id: logical_number, color: green}
    end

    Note over App,API: Polling GET /api/v1/loans/{loan_id}/status is the only authoritative client signal for hardware/AI outcomes
    App->>API: GET /api/v1/loans/{loan_id}/status [JWT]
    alt loan_status is RETURNING
        API-->>App: 200 OK {loan_status: RETURNING}
        App->>API: GET /api/v1/loans/{loan_id}/status [JWT]
    else loan_status is PENDING_INSPECTION
        API-->>App: 200 OK {loan_status: PENDING_INSPECTION}
        App-->>User: "Damage detected. Administrator has been notified."
    else loan_status is COMPLETED
        API-->>App: 200 OK {loan_status: COMPLETED}
        App-->>User: "Item successfully returned!"
    end
```
