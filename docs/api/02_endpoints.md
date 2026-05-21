# Core Endpoint Reference

This section highlights the most critical endpoints for the EasyLend lending flow. For a full interactive specification, please refer to the auto-generated Swagger UI at `/docs`.

## 1. Authentication
- `POST /auth/nfc`: Step 1 — Validate NFC tag presence.
- `POST /auth/pin`: Step 2 — Verify PIN and issue JWT token pair.
- `POST /auth/refresh`: Rotate refresh tokens (consumes old token in Redis).

## 2. Lending Transactions
- `POST /loans/checkout`: Initiate a borrow. Requires `Idempotency-Key` and `aztec_code`.
- `POST /loans/return/initiate`: Start the return flow. Requires `Idempotency-Key`, `aztec_code`, and `kiosk_id`.
- `POST /loans/{loan_id}/report-damage`: Grace-period damage reporting (5-minute window).

## 3. Vision & Edge
- `POST /vision/analyze`: Triggered by Vision Box after a door is closed. Performs dual-phase AI detection.
- `PATCH /update-model`: Reverse proxy to Vision microservice to update YOLO models.

## 4. Administration
- `GET /admin/quarantine`: List loans flagged for manual inspection.
- `PATCH /admin/evaluations/{id}/judge`: Resolve a quarantine case (Approve/Reject).
- `GET /audit/verify`: Verify the integrity of the cryptographic audit chain.
