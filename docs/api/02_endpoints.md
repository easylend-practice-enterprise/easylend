# Core endpoint reference

Key endpoints for the lending flow. Full specification available at the interactive `/docs` Swagger UI.

## 1. Authentication

- `POST /auth/nfc`: Validate NFC tag presence.
- `POST /auth/pin`: Verify PIN and issue JWT pair.
- `POST /auth/refresh`: Rotate credentials.
- `POST /auth/logout`: End session.

## 2. Users

- `GET /users/me`: Current user profile and role.

## 3. Transactions

- `POST /loans/checkout`: Initiate borrow. Requires aztec_code.
- `POST /loans/return/initiate`: Start return flow. Requires kiosk_id.
- `POST /loans/{id}/report-damage`: Grace-period report window.

## 4. Catalog

Clients retrieve available assets based on their authenticated role.

```mermaid
sequenceDiagram
    actor Client as Kiosk App
    participant API as FastAPI Backend
    participant DB as PostgreSQL

    Client->>API: GET /api/v1/catalog [With JWT Token]
    Note over API: Validates JWT and checks role

    alt Role == USER
        Note over API,DB: LEFT OUTER JOIN from categories ensures 0-availability rows are returned
        API->>DB: SELECT c.category_id, c.category_name, COUNT(a.asset_id) FROM categories c LEFT JOIN assets a ON a.category_id = c.category_id AND a.asset_status = 'AVAILABLE' AND a.is_deleted = FALSE GROUP BY c.category_id, c.category_name ORDER BY c.category_name
        DB-->>API: Categorised pool (e.g. Laptops: 3, Tablets: 0)
        API-->>Client: 200 OK (Standard view)
    else Role == ADMIN
        Note over API,DB: Admin requires 2 joins for the current status
        API->>DB: SELECT a.*, l.loan_status, u.first_name, u.last_name FROM assets a LEFT JOIN loans l ON a.asset_id = l.asset_id AND l.loan_status IN ('ACTIVE', 'RESERVED') LEFT JOIN users u ON l.user_id = u.user_id WHERE a.is_deleted = FALSE
        DB-->>API: Full list (Asset + Locker info + Current Borrower)
        API-->>Client: 200 OK (Admin view)
    end
```

## 5. Vision

...

## 4. Vision

- `POST /vision/analyze`: AI inference trigger after door closure.
- `PATCH /update-model`: Atomic YOLO weight update.

## 6. Administration

- `GET /admin/quarantine`: List flagged items.
- `PATCH /admin/evaluations/{id}/judge`: Resolve quarantine cases.
- `GET /audit/verify`: Hash-chain integrity check.

Administrators manage system resources and resolve anomalies through the dedicated dashboard.

```mermaid
sequenceDiagram
    actor Admin as Administrator
    participant App as Kiosk App (Virtual or Physical)
    participant API as FastAPI Backend
    participant LoanStateMachine
    participant DB as PostgreSQL
    participant VB as Vision Box (Kiosk A)

    Note over Admin,App: Admin logs in via the app (see sequence_auth.mmd)
    Admin->>App: Logs in and opens Admin Dashboard
    App->>API: GET /api/v1/kiosks [With JWT Admin Token]
    API-->>App: 200 OK (List of kiosks)

    alt 1. Locker Grid UI
        Admin->>App: Selects Kiosk A and opens Locker Grid
        App->>API: GET /api/v1/kiosks/{kiosk_id}/lockers
        API->>DB: SELECT * FROM lockers WHERE kiosk_id = ? ORDER BY logical_number
        DB-->>API: Statuses (AVAILABLE, MAINTENANCE, OCCUPIED)
        API-->>App: 200 OK (Current status per locker)

        opt Force Door Open
            Admin->>App: Taps Locker 1 -> Force Open
            App->>API: POST /api/v1/lockers/{locker_id}/open [JWT Admin]
            Note over API,VB: locker_id in WSS = logical_number (physical slot int), not UUID
            API->>DB: INSERT INTO audit_logs {action_type: 'ADMIN_FORCED_OPEN', payload: {locker_id}}
            API->>DB: COMMIT
            Note over API,VB: Fire-and-forget: audit committed before send, no slot_opened event processed
            API->>VB: WSS: open_slot {locker_id: logical_number}
            alt Vision Box offline
                API-->>App: 503 Service Unavailable
            else Vision Box online
                API-->>App: 200 OK {detail: "Locker opened successfully."}
            end
        end

        opt Mark as Defective / Maintenance
            Admin->>App: Taps Locker 1 -> Mark MAINTENANCE
            App->>API: PATCH /api/v1/lockers/{locker_id}/status {locker_status: 'MAINTENANCE'} [JWT Admin]
            API->>LoanStateMachine: apply_locker_status(locker, MAINTENANCE)
            LoanStateMachine-->>API: locker MAINTENANCE
            API->>DB: COMMIT locker status update + audit log
            API-->>App: 200 OK (Locker marked)
        end

    else 2. Quarantine Inbox
        Admin->>App: Opens Quarantine Inbox
        App->>API: GET /api/v1/admin/quarantine [JWT Admin]
        Note over Admin,API: Paginated: skip/limit query params
        API-->>App: List[QuarantineLoanView] {loan_id, asset_name, user_name, kiosk_name, loan_status, ...}
        App->>API: GET /api/v1/admin/evaluations/{loan_id}
        API-->>App: EvaluationDetailView {evaluation_id, evaluation_type, photo_url, ai_confidence, ...}
        Note over API,DB: /admin/evaluations/{evaluation_id}/judge uses LoanStateMachine under FOR UPDATE NOWAIT locks
        Note right of App: See sequence_quarantine.mmd for full handling flow

    else 3. Asset Catalog
        Admin->>App: Opens Asset Management
        App->>API: GET /api/v1/assets [With JWT Admin Token]
        Note over Admin,API: Optional ?asset_status= filter, always excludes is_deleted=TRUE
        API->>DB: SELECT * FROM assets WHERE is_deleted = FALSE ORDER BY name
        DB-->>API: Full list (Asset + Locker + Category)
        API-->>App: 200 OK (Admin view)

        opt New Asset
            Admin->>App: Adds asset
            App->>API: POST /api/v1/assets [JWT Admin] {name, aztec_code, category_id, locker_id?}
            API->>DB: INSERT INTO assets
            API-->>App: 201 Created (AssetResponse)
        end

        opt Delete Asset (Soft Delete)
            Admin->>App: Deletes asset
            App->>API: DELETE /api/v1/assets/{asset_id} [JWT Admin]
            alt Asset has ACTIVE or RESERVED loan
                API-->>App: 409 Conflict {"Cannot delete an asset that has active or reserved loans."}
            else No active loans
                Note over API,DB: Locker returned to AVAILABLE if asset was assigned
                API->>LoanStateMachine: apply_locker_status(locker, AVAILABLE)
                LoanStateMachine-->>API: locker AVAILABLE
                API->>DB: UPDATE assets SET is_deleted = TRUE, locker_id = NULL WHERE asset_id = ?
                API->>DB: INSERT INTO audit_logs {action_type: 'ASSET_SOFT_DELETED', payload: {asset_id, asset_name}}
                API-->>App: 204 No Content
            end
        end

    else 4. User & NFC Management
        Admin->>App: Opens User Management
        App->>API: GET /api/v1/users [With JWT Admin Token]
        API-->>App: 200 OK (List[UserResponse] with total count)

        opt Unblock User
            Admin->>App: Unblocks account
            App->>API: PATCH /api/v1/users/{user_id} {failed_login_attempts: 0, locked_until: null} [JWT Admin]
            Note over API,DB: Resets failed attempts counter and clears lock timer
            API->>DB: UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE user_id = ?
            API-->>App: 200 OK
        end

        opt Link NFC Tag
            Admin->>App: Links new NFC tag
            App->>API: PATCH /api/v1/users/{user_id}/nfc {nfc_tag_id} [JWT Admin]
            Note over API,DB: Updates nfc_tag_id column, uniqueness enforced at DB level
            API->>DB: UPDATE users SET nfc_tag_id = ? WHERE user_id = ?
            API-->>App: 200 OK
        end
    end
```
