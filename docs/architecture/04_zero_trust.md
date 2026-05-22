# Zero-Trust Architecture

EasyLend is designed with a **Zero-Trust Philosophy**. We assume that any network segment, device, or user account can be compromised. Therefore, trust is never assumed—it is continuously verified at every layer of the chain.

## 1. Trustless Inter-Service Communication (M2M)

Communication between our core services and edge devices does not rely on local network "safety."

- **Hardware Auth**: The Vision Box and Simulator must provide a static `X-Device-Token` for every request and WebSocket handshake. This is verified using timing-safe comparisons to prevent side-channel attacks.
- **Microservice Auth**: The Vision AI service is protected by a dedicated `VISION_API_KEY`, ensuring that only our authorized Backend API can trigger inference workloads.

## 2. Stateless User Verification

We implement strict, stateless authentication for all kiosk interactions:

- **NFC + PIN MFA**: Scanned credentials are never stored in plain text. PINs use **Bcrypt**, and NFC tags are protected by a **HMAC-SHA256** secret-salted digest.
- **JWT Whitelisting**: While the API is stateless, we maintain a Redis-backed "token whitelist" for refresh tokens. This allows for immediate, global revocation of a session if an account is flagged for fraud.

## 3. Zero-Trust Concurrency

Our database logic follows a "Trust-No-One" approach to data mutation:

- **Optimistic AI Inference**: We never hold database locks during slow AI processing. We perform a pre-flight read, run the AI, and then re-verify all assumptions during a short, locked "Finalization" phase.
- **Fail-Fast Locking**: Every transaction assumes other users might be targeting the same asset. We use `NOWAIT` and `SKIP LOCKED` to fail gracefully rather than letting sessions hang.

## 4. Hardware Failure as a First-Class Citizen

The API does not "trust" that a hardware command was executed successfully just because it was sent.

- We rely on **Polling and State Transitions** to confirm physical reality.
- A loan only advances to `ACTIVE` once the Vision AI physically confirms the locker is empty, regardless of the WebSocket transmission status.
