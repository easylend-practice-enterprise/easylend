# Technical debt

Registered limitations and risks for the V1 release. These items are tracked for resolution in the V2 roadmap.

## 1. Security risks

| Risk | Impact | Severity | V2 plan |
|---|---|---|---|
| **Shared API key** | Fleet-shared key for hardware access. | **Medium** | Migrate to per-device identities. |
| **Static tokens** | No rotation for device secrets. | **Low** | Implement automated rotation. |

## 2. Implementation debt

| Item | Category | Severity | Note |
|---|---|---|---|
| **Interceptors** | Frontend | **Medium** | Missing automatic token refresh. |
| **NFC hardware** | Frontend | **Medium** | Dependency not installed; UI simulation only. |
| **Scaffolding** | Project | **Low** | Empty placeholder files remain in kiosk app. |
| **Observability** | Infrastructure | **Low** | Lacks metrics and tracing integration. |

## 3. Hardware scoping

| Limitation | Impact | Severity | V2 plan |
|---|---|---|---|
| **Closure events** | Hardware | **Low** | Sensor events logged but not automated. |
| **PXE service** | Infrastructure | **None** | Out of scope for MVP. |

## 4. Chain scale

Verification endpoint is optimized for batching. Full log verification for millions of records would require a background worker to prevent timeouts in future production volumes.
