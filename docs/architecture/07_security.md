# Security

Standard practices enforced to harden the production environment.

## 1. Authentication layers

- **Access tokens:** Short-lived JWTs (15 min) for all kiosk operations.
- **Refresh tokens:** Long-lived tokens whitelisted in Redis to support secure session extension and revocation.
- **Hashing:** PINs use Bcrypt, and NFC tags use HMAC-SHA256 with secret salt.

## 2. Network and infrastructure

- **CORS:** Strict origin validation for kiosk and admin clients.
- **Headers:** API responses include CSP, frame protection, and permissions policies.
- **Database isolation:** PostgreSQL is bound to 127.0.0.1, accessible only via SSH tunnel for administration.

## 3. Threat mitigation

- **Rate limiting:** 3-layer protection across database, IP, and user tokens.
- **SSRF hardening:** The vision service validates model download URLs to public IP ranges only.
- **Guard rails:** The application crashes on startup if weak or placeholder secrets are detected in production mode.
