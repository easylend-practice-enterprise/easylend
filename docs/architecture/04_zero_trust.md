# Zero-trust architecture

EasyLend assumes no network segment, device, or account is inherently safe. Trust is verified at every layer of the interaction chain.

## 1. Trustless service communication

Interaction between core services and edge devices does not rely on local network safety.

- **Hardware authentication:** Vision boxes and simulators must provide an `X-Device-Token` for all requests. Comparisons are timing-safe to mitigate side-channel attacks.
- **Microservice authentication:** The vision AI service requires a `VISION_API_KEY`, ensuring only the authorized backend can trigger inference workloads.

## 2. Stateless verification

We implement strict verification for all kiosk interactions, ensuring every request is independently validated.

```mermaid
sequenceDiagram
    actor User as User
    participant App as Kiosk App (Flutter)
    participant API as FastAPI Backend
    participant Redis as Redis Cache
    participant DB as PostgreSQL

    User->>App: Holds NFC badge in front of reader
    App->>API: POST /api/v1/auth/nfc {nfc_tag_id}
    API->>DB: SELECT * FROM users WHERE nfc_tag_id = ?
    DB-->>API: User record

    alt Account locked (locked_until > NOW)
        API-->>App: 401 Unauthorized (Account locked)
        App-->>User: "Account temporarily locked"
    else Account active
        API-->>App: 200 OK (Enter PIN)
        App-->>User: Show PIN entry screen
        User->>App: Enters PIN
        App->>API: POST /api/v1/auth/pin {nfc_tag_id, pin}
        API->>DB: SELECT pin_hash FROM users WHERE nfc_tag_id = ?
        DB-->>API: pin_hash

        alt PIN incorrect
            API->>DB: UPDATE users SET failed_login_attempts = failed_login_attempts + 1 WHERE user_id = <user_id>
            alt Limit reached (5 attempts)
                API->>DB: UPDATE users SET locked_until = NOW() + interval '15 minutes' WHERE user_id = <user_id>
                API->>DB: INSERT INTO audit_logs {action_type: 'LOGIN_FAILED', payload: {reason: 'ACCOUNT_LOCKED'}}
                API-->>App: 401 Unauthorized (Account locked)
            else Attempts remaining
                API->>DB: INSERT INTO audit_logs {action_type: 'LOGIN_FAILED'}
                API-->>App: 401 Incorrect PIN (N attempts remaining)
            end
            App-->>User: Error message
        else PIN correct
            API->>DB: UPDATE users SET failed_login_attempts = 0 WHERE user_id = <user_id>
            API->>DB: INSERT INTO audit_logs {action_type: 'LOGIN_SUCCESS'}
            API->>Redis: SETEX refresh:<user_id>:<jti> (Store Refresh Token)
            API-->>App: 200 OK {access_token, refresh_token}
            App-->>User: Logged in: show asset catalog
        end
    end

    opt Auto-Logout (Inactivity) or Manual Logout
        User-->>App: Stops interacting or clicks Logout
        App-->>User: Show popup / loading screen
        App->>API: POST /api/v1/auth/logout {refresh_token}
        API->>Redis: DEL refresh:<user_id>:<jti> (Revoke Token)
        API-->>App: 200 OK (Successfully logged out)
        App-->>User: Return to NFC start screen
    end

    opt Token Refresh (Access Token expired)
        App->>API: POST /api/v1/auth/refresh {refresh_token}
        API->>Redis: DEL refresh:<user_id>:<old_jti> (Atomically Validate & Revoke)

        alt Refresh token not found in whitelist
            API-->>App: 401 Unauthorized
        else Refresh token was valid
            API->>DB: SELECT user + role WHERE user_id = <sub>
            API->>Redis: SETEX refresh:<user_id>:<new_jti> (Store new refresh token)
            API-->>App: 200 OK {access_token, refresh_token}
        end
    end
```

## 3. Concurrency trust

Database logic follows a trust-no-one approach to mutation.

- **Optimistic inference:** We do not hold database locks during slow AI processing. We perform a pre-flight read, run the AI, and re-verify assumptions during a short, locked finalization phase.
- **Conflict awareness:** Transactions assume concurrent access to the same resources, utilizing fail-fast locking to maintain integrity.

## 4. Hardware verification

The API does not assume a command succeeded just because it was delivered.

- We rely on polling and state transitions to confirm physical outcomes.
- A loan only advances to `ACTIVE` once vision AI confirms the locker is physically empty.
