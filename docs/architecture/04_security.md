# Traditional Security & Hardening

While our Zero-Trust philosophy and Audit Trail provide advanced protection, EasyLend also adheres to industry-standard security practices to ensure a hardened production environment.

## 1. Authentication Layers

- **Access Tokens**: Short-lived (15 min) JWTs for all kiosk operations.
- **Refresh Tokens**: Long-lived (7 days) tokens stored in a Redis-backed whitelist to support secure session extension and immediate revocation.
- **Password Hashing**: PINs are hashed using **Bcrypt** with a work factor optimized for campus kiosks.

## 2. Network & Infrastructure

- **CORS Protection**: Strict origin validation is enforced for the Kiosk Web/Mobile clients.
- **Security Headers**: Every API response includes a comprehensive suite of headers:
  - `Content-Security-Policy` (CSP)
  - `X-Frame-Options: DENY`
  - `X-Content-Type-Options: nosniff`
  - `Permissions-Policy` (Restricting camera/mic access)

## 3. Threat Mitigation

- **Rate Limiting**: 3-layer protection (Database-level lockout, IP-based limiting, and User-based limiting) to prevent brute-force and DDoS.
- **SSRF Hardening**: The Vision service restricts model downloads to HTTPS-only and validates that target hostnames do not resolve to local or private IP ranges.
- **Database Isolation**: The PostgreSQL instance is bound strictly to `127.0.0.1`. It is not accessible from the public internet, even within the Virtual Machine, requiring an SSH tunnel for administrative access.
