# User Suspension & Discipline Policy

EasyLend implements automated disciplinary actions to protect equipment and ensure accountability during damage disputes.

## 1. Automatic Suspension (7-Day Lock)

A user's account is automatically locked for **7 days** under the following conditions:

- **Grace-Period Damage Report**: If a user reports that an item they just picked up is damaged.
- **AI-Detected Damage**: If the Vision AI flags damage during a return and an administrator approves the finding.

## 2. Suspension Scope

When a suspension is triggered:

1. The **current borrower** is locked.
2. If it is a damage report, the **previous borrower** is also locked (pending administrative investigation to determine who caused the damage).
3. `User.locked_until` is updated in the database using a `FOR UPDATE NOWAIT` lock to ensure atomicity.

## 3. Administrative Resolution

Only a system administrator can lift a suspension early by resetting the `locked_until` timestamp and `failed_login_attempts` via the User Management dashboard.
