# Technical Debt & Risk Assessment

As part of our commitment to engineering transparency, this document registers the known technical debt, security trade-offs, and architectural risks in the **V1 (Alpha)** release of EasyLend. These items are tracked for resolution in the V2 (Post-MVP) roadmap.

## 1. Security Risks

| Risk | Impact | Severity | Mitigation / V2 Plan |
|---|---|---|---|
| **Fleet-Shared API Key** | A compromise of the `VISION_BOX_API_KEY` on one kiosk allows lateral access to other kiosks. | **Medium** | V2 Roadmap: Migrate to per-device JWTs and mTLS-based hardware identities. |
| **Static Device Tokens** | No automated rotation for Vision Box or Simulation tokens. | **Low** | V2 Roadmap: Implement a device registration and token rotation service. |

## 2. Implementation Debt

| Debt Item | Category | Severity | Status / Note |
|---|---|---|---|
| **Dio 401 Interceptor** | Frontend | **Medium** | Missing automatic token refresh. Expired sessions currently require manual re-authentication. |
| **NFC Hardware Integration** | Frontend | **Medium** | The `nfc_manager` dependency is not yet installed; badge scanning is simulated via UI components. |
| **Placeholder Files** | Project | **Low** | ~20 legacy scaffolding files in the Kiosk app remain empty. |
| **Metrics & Tracing** | Observability | **Low** | The system lacks Prometheus/Grafana integration, relying solely on structured logs and Uptime Kuma. |

## 3. Hardware Scoping

| Limitation | Impact | Severity | Mitigation / V2 Plan |
|---|---|---|---|
| **`slot_closed` Event** | Hardware | **Low** | Events are logged in the backend but do not trigger automated state changes (e.g., immediate photo capture). |
| **PXE Boot Service** | Infrastructure | **None** | Referenced in logical topology but explicitly marked as **Out of Scope** for the MVP. |

## 4. Integrity Chain Scale

The `GET /audit/verify` endpoint is currently optimized for batch processing. While it ensures continuity across batches, a full chain verification for millions of records would require a dedicated background worker to prevent API timeouts—this is deferred until the system reaches high-volume production.
