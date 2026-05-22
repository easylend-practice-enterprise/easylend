# Audit trail

EasyLend implements a blockchain-inspired cryptographic audit trail to ensure critical transactions are immutable and tampering is detectable.

## 1. Hashing chain

Every record in the `audit_logs` table is part of a continuous chain using SHA-256.

### Log entry structure

- **Payload:** JSON data for the event.
- **Action type:** Standardized event identifier.
- **Previous hash:** Fingerprint of the preceding record.
- **Current hash:** SHA256 sum of the previous hash, action type, and payload.

### Genesis block

The chain starts with a foundation of 64 zeros. Every subsequent record links back to this block.

## 2. Immutability

Each record embeds the hash of its predecessor, creating an append-only chain.

- **Modification detection:** Changing an old record's payload invalidates its hash and every subsequent link.
- **Deletion detection:** Removing a record creates a gap that breaks the chain's cryptographic continuity.

## 3. Verification

The `GET /audit/verify` endpoint re-computes hashes across the chain. It identifies the exact record where integrity was first broken, supporting batch processing for large logs.

## 4. Efficiency

Logging does not block row-level transactions. We use a fetch-latest-then-compute pattern to keep the audit trail off the critical lock-contention path.
