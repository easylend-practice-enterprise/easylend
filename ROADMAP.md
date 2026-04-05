# EasyLend Roadmap

## V2 Architecture

### Fleet-Shared Hardware Auth Boundary (Technical Debt)

Current state:

- All hardware clients currently authenticate with a fleet-shared secret (`VISION_BOX_API_KEY`).
- Trust is established at the fleet level, not at an individual device identity level.

Architectural risk:

- A single device token leak enables lateral movement across kiosks.
- A compromised client can potentially impersonate another kiosk identity and submit events under a different path parameter.
- Incident response is coarse-grained because rotating one shared key impacts all hardware clients at once.

### V2 Target State

Introduce device-bound authentication for all hardware clients using one of these approved patterns:

1. Device-bound JWTs

- Each hardware unit receives a unique device identity.
- Short-lived access JWTs are minted per device with strict claims (`device_id`, `kiosk_id`, `aud`, `exp`, `jti`).
- API and WebSocket gateways validate claim-to-route binding (for example, token `kiosk_id` must equal route `kiosk_id`).
- Support token rotation and revocation without disrupting unaffected devices.

1. Mutual TLS (mTLS)

- Each hardware unit receives a unique client certificate issued by an internal CA.
- TLS termination enforces client cert validation and maps cert identity to registered kiosk/device records.
- Compromise containment is per certificate via targeted revocation.

### Migration Plan (V2)

Phase 1: Identity model

- Add device registry entities and lifecycle states (provisioned, active, revoked).
- Bind each device identity to one kiosk in the control plane.

Phase 2: Dual-stack auth rollout

- Keep legacy shared-key flow temporarily for backward compatibility.
- Add device-bound JWT or mTLS validation in parallel and gate by feature flag.

Phase 3: Enforcement

- Require route-to-identity binding for all hardware endpoints and WebSocket channels.
- Reject fleet-shared credentials on privileged hardware paths.

Phase 4: Decommission legacy

- Remove fleet-shared `VISION_BOX_API_KEY` from runtime authentication.
- Rotate and retire all old credentials and update operational runbooks.
