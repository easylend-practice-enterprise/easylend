# API Principles & IoT Patterns

EasyLend uses a specific set of architectural patterns to handle the inherent unreliability of IoT hardware while maintaining a fast, reactive mobile experience.

## 1. The "Snoepautomaat" Pattern
Lending transactions follow a **Commit-First, Hardware-Second** architecture. This prevents "split-brain" scenarios where a physical locker opens but the database record fails to persist (or vice versa).

1. **Client** sends request (e.g., `/checkout`).
2. **API** validates logic and commits the loan record to the database.
3. **API** returns a success code immediately after commit.
4. **Hardware Command** is sent asynchronously via WebSockets.
5. **Client** polls for the physical outcome (e.g., transition to `ACTIVE`).

## 2. The "IoT Partial Success" Pattern (202 vs 207)
We use two different success codes to manage hardware synchronization:
- **`202 Accepted`**: The transaction is committed and the hardware command was successfully dispatched to the local proxy.
- **`207 Multi-Status`**: The transaction is committed, but the backend **immediately knows** the hardware command failed (e.g., the Vision Box is offline).
  - *UX Benefit*: The Kiosk can show an immediate "Hardware Error" instead of waiting for a 10-second polling timeout.

## 3. Lending Quotas & Blocks
We enforce two primary compliance rules at the API level:
- **Concurrent Quota**: A user is limited to a configurable number of active loans (Default: 2).
- **Overdue Block**: If a user has any item in the `OVERDUE` state, they are prohibited from starting new checkouts until the item is returned.

## 4. Status Polling Rules
Clients must poll the `/status` endpoint every **2 seconds** after a `202` or `207` response until a terminal state is reached or a 10-second hardware timeout occurs.
