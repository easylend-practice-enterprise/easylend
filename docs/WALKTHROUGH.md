# Technical Walkthrough: The Loan Lifecycle

This walkthrough follows the "Happy Path" journey of an equipment loan—from the moment a student approaches the kiosk to the final AI-confirmed return. It connects our high-level architecture with implementational details.

---

## 1. Authentication & Entry
A student scans their NFC badge. The Kiosk app calls `POST /auth/nfc` and then `POST /auth/pin`.
- **Under the hood**: The API verifies the hashed tag and PIN, issuing a JWT pair. The refresh token is whitelisted in Redis for session safety.
- **Deep Dive**: [Security & Audit](./architecture/04_security.md)

## 2. Asset Discovery
The student browses the catalog. The Kiosk calls `GET /api/v1/catalog`.
- **Under the hood**: The API returns an aggregated view of available items by category (e.g., "Laptops: 5 available").
- **Deep Dive**: [Core Endpoints](./api/02_endpoints.md)

## 3. The "Snoepautomaat" Checkout
The student selects a laptop and scans its Aztec barcode. The Kiosk calls `POST /api/v1/loans/checkout`.
- **Step A**: The API acquires `NOWAIT` locks on the Asset and Locker.
- **Step B**: The `LoanStateMachine` transitions the loan to `RESERVED`.
- **Step C**: The DB commits. The API returns `202 Accepted` (or `207` if the door is stuck).
- **Step D**: An `open_slot` command is sent via WebSocket to the Raspberry Pi.
- **Deep Dive**: [REST Principles](./api/01_rest_principles.md) & [Concurrency](./architecture/03_concurrency.md)

## 4. Physical Interaction & Vision Analysis
The student takes the laptop and closes the door. The Vision Box sends a `slot_closed` event and then uploads a photo to `POST /api/v1/vision/analyze`.
- **Phase 1 (Optimistic)**: The API performs AI inference (`/detect` and `/segment`) without DB locks.
- **Phase 2 (Atomic)**: If the AI confirms the locker is empty, the API locks the rows and transitions the loan to `ACTIVE`.
- **Polling**: During this time, the Kiosk has been polling `/status`. It now sees `ACTIVE` and shows the "Success" screen.
- **Deep Dive**: [Vision Integration](./hardware/01_vision_integration.md)

## 5. The Return Journey
The student returns to the kiosk later and selects "Return."
- **Locker Allocation**: The API uses `SKIP LOCKED` to find the first truly available locker at that kiosk, reserving it by transitioning the loan to `RETURNING`.
- **Final AI Check**: After the student places the item inside and closes the door, the Vision Box uploads a new photo. The AI verifies the item is present and checks for damage.
- **Deep Dive**: [State Management](./architecture/02_state_machine.md) & [Database Schema](./database/01_schema.md)

---

## 🛑 Exceptional Scenarios
What if something goes wrong?
- **Late Return**: Covered by the [Overdue Workers](./database/02_background_workers.md).
- **Damage Detected**: The loan enters the [Quarantine Flow](./hardware/02_quarantine_flow.md).
- **Dispute**: Handled via the [User Suspension Policy](./architecture/05_user_suspension.md).
