# Cryptographic Audit Trail

EasyLend implements a **Blockchain-inspired Cryptographic Audit Trail**. This ensures that every critical transaction in the system is immutable and that any tampering with the database can be mathematically detected.

## 1. The Hashing Chain
Every record in our `AUDIT_LOGS` table is part of a continuous cryptographic chain. We use **SHA-256** to compute a unique fingerprint for every event.

### Structure of a Log Entry
1. **Payload**: The JSON data of the event (e.g., who logged in, which locker opened).
2. **Action Type**: A standardized identifier for the event.
3. **Previous Hash**: The `current_hash` of the immediately preceding record in the database.
4. **Current Hash**: `SHA256(previous_hash + action_type + json_string(payload))`

### The Genesis Block
The first record in the system points to a "Genesis Hash" (a string of 64 zeros). Every subsequent record builds upon this foundation.

## 2. Immutability Properties
Because each record embeds the fingerprint of the previous one, the chain is **append-only**:
- **Tamper Detection**: If an attacker modifies the payload of an old record, its `current_hash` will no longer match. This breaks the link to the *next* record, and every subsequent link in the chain becomes invalid.
- **Deletion Detection**: Deleting a record entirely creates a "gap" where the `previous_hash` of the following record no longer points to a valid predecessor.

## 3. Automated Chain Verification
We provide a dedicated administrative endpoint: `GET /api/v1/audit/verify`.
- This service traverses the entire chain (or a specific batch) and re-computes every hash.
- It returns an `is_valid` boolean. If tampering is detected, it identifies the exact `tampered_record_id` where the chain first broke.

## 4. Operational Efficiency
To prevent logging from becoming a bottleneck, we do not lock the previous row during a write. We use a **Fetch-Latest-then-Compute** pattern, keeping the high-fidelity audit trail off the critical lock-contention path while maintaining strict cryptographic continuity.
