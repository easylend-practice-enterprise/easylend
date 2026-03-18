# EasyLend Workflows

> This document describes the definitive system workflows through sequence diagrams.
> Architecture: The Kiosk App communicates via REST (with Polling for asynchronous hardware actions). The Vision Box listens to commands via WebSockets (WSS).

The seven core flows are:

1. Login
2. Checkout (Lending)
3. Return
4. Quarantine (Damage handling)
5. Catalog & Authorisation Flow (RBAC)
6. Kiosk Boot & Admin Remote Control
7. Admin Dashboard (Management)

---

## 1. Login Flow (NFC + PIN)

The user scans their NFC badge and enters their PIN to receive an access token and a refresh token. The refresh token is stored in Redis as a token whitelist entry and deleted on logout/revocation. A built-in anti-brute-force mechanism locks the account after 5 failed attempts.

[View the sequence diagram: Login Flow](./diagrams/sequence_auth.mmd)

---

## 2. Checkout Flow (Lending an item)

The app requests a loan via REST. The API controls the Vision Box via WSS. In the meantime the app polls the API to find out whether the hardware and AI actions have completed.

[View the sequence diagram: Checkout Flow](./diagrams/sequence_checkout.mmd)

---

## 3. Return Flow (Returning an item)

The user scans the Aztec code via the tablet. The API assigns an available locker. After closing, the AI verifies that the item is actually inside the locker and checks for damage.

[View the sequence diagram: Return Flow](./diagrams/sequence_return.mmd)

---

## 4. AI Quarantine Flow (Damage detected)

When the AI detects damage during the Return Flow, a human admin must approve or reject the assessment via the dashboard.

[View the sequence diagram: AI Quarantine Flow](./diagrams/sequence_quarantine.mmd)

---

## 5. Catalog & Authorisation Flow (RBAC)

The catalog view differs based on the role of the logged-in user (Student vs. Admin). Students only see an anonymised "pool" of available items; admins see all details.

[View the sequence diagram: Catalog Flow](./diagrams/sequence_catalog.mmd)

---

## 6. Kiosk Boot & Admin Remote Control

When a Kiosk starts up, it fetches its own hardware status via an M2M token. An administrator (with an Admin JWT) can remotely force open or manage lockers via the app.

[View the sequence diagram: Admin Sync & Boot Flow](./diagrams/sequence_admin_sync.mmd)

---

## 7. Admin Dashboard (Management)

Admin users manage assets, quarantine cases, and kiosk lockers via the Admin Dashboard.

[View the sequence diagram: Admin App Flow](./diagrams/sequence_admin_app.mmd)
