# Quarantine Flow

The "Quarantine" state is an administrative safety net for scenarios where automated logic cannot safely resolve a transaction.

## Triggering Events

A loan enters the `PENDING_INSPECTION` state if:

- **AI Flags Damage**: The segmentation model detects an anomaly during return.
- **Hardware Timeout**: A door is left open, or a sensor fails to report closure.
- **Manual Report**: A user reports damage within the 5-minute checkout grace period.
- **Fraud Detection**: The object detection model finds an empty locker during a return (or a non-empty locker after a checkout).

## System State in Quarantine

When quarantined:

- **Loan Status**: `PENDING_INSPECTION` (or `DISPUTED`).
- **Asset Status**: `PENDING_INSPECTION` (not available for checkout).
- **Locker Status**: `MAINTENANCE` (locked in hardware, ignored by allocation logic).

## Administrative Resolution

Administrators use the **Quarantine Dashboard** to review the captured photo and AI report. They can then "Judge" the evaluation:

- **Approve**: Confirms the AI was correct (e.g., damage is real). Asset stays in maintenance.
- **Reject**: Overrides the AI (e.g., a false positive). Asset is returned to `AVAILABLE` status and the locker is reopened for use.
