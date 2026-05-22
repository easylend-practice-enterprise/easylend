# Technical walkthrough

This guide follows the lifecycle of an equipment loan: from student authentication to the AI-confirmed return.

## 1. Authentication

A student scans an NFC badge. The kiosk app calls `/auth/nfc` and `/auth/pin`.

- **Mechanism:** The API verifies hashed credentials and issues a JWT pair. Refresh tokens are whitelisted in Redis for revocation capability.
- **Details:** [Security](./architecture/07_security.md)

## 2. Discovery

The student browses available items. The kiosk calls `/catalog`.

- **Mechanism:** The API provides an aggregated view of categories and availability counts.
- **Details:** [Endpoints](./api/02_endpoints.md)

## 3. Checkout

The student selects a laptop and scans its Aztec barcode. The kiosk calls `/loans/checkout`.

- **Logic:** The API acquires fail-fast locks on the asset and locker.
- **Transition:** The state machine moves the loan to `RESERVED`.
- **Response:** The API returns `202 Accepted` after committing to the database. If communication with the vision box fails immediately, it returns `207 Multi-Status`.
- **Hardware:** An `open_slot` command is sent via WebSocket to the Raspberry Pi.
- **Details:** [REST principles](./api/01_rest_principles.md) and [Concurrency](./architecture/03_concurrency.md)

## 4. Pickup and analysis

The student takes the item and closes the door. The vision box sends a `slot_closed` event and uploads a photo to `/vision/analyze`.

- **Analysis:** The API performs dual-phase inference to verify the locker is empty and check for fraud.
- **Confirmation:** Once verified, the API transitions the loan to `ACTIVE`.
- **Polling:** The kiosk polls `/status` to confirm the transition before showing the success screen.
- **Details:** [Vision integration](./hardware/01_vision_integration.md)

## 5. Return

The student initiates a return at a kiosk.

- **Allocation:** The API uses a skip-locked query to find and reserve the first available locker.
- **Interaction:** The door opens, the student places the item inside, and closes the door.
- **Verification:** The vision box captures a photo. The AI verifies the item's presence and inspects for damage.
- **Details:** [State management](./architecture/02_state_machine.md) and [Database schema](./database/01_schema.md)

## 🛑 Exceptions

Logic for non-standard flows:

- **Late return:** Handled by [Background workers](./database/02_background_workers.md).
- **Damage detected:** The loan enters the [Quarantine flow](./hardware/02_quarantine_flow.md).
- **Compliance issues:** Handled via the [Discipline policy](./architecture/05_user_suspension.md).
