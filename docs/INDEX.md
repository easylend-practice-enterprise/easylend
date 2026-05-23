# EasyLend project documentation

Technical documentation for EasyLend: an IoT equipment lending platform. This guide provides a modular overview of system architecture, API design, and hardware integration.

## Documentation map

### 1. System architecture

High-level design and core principles.

- **[Topology](./architecture/01_topology.md):** Physical and logical system layout.
- **[State management](./architecture/02_state_machine.md):** Centralized transition logic and state machine rules.
- **[Concurrency and locking](./architecture/03_concurrency.md):** Multi-user traffic handling and resource protection.
- **[Zero-trust chain](./architecture/04_zero_trust.md):** Trustless interaction across API, IoT, and AI.
- **[Discipline policy](./architecture/05_user_suspension.md):** Automated enforcement for damage and fraud.
- **[Audit trail](./architecture/06_audit_trail.md):** Cryptographic transaction logging.
- **[Security](./architecture/07_security.md):** Hardening, authentication, and rate limiting.
- **[Technical debt](./architecture/08_technical_debt.md):** Current limitations and future roadmap.
- **[Testing en validatie](./architecture/09_testing.md):** Testaanpak, validatie van backend, frontend, AI en hardware.

### 2. API and integration

Communication protocols for kiosks and hardware.

- **[REST principles](./api/01_rest_principles.md):** IoT patterns and business rules.
- **[Return flow](./api/04_return_flow.md):** Detailed sequence for asset returns.
- **[Endpoints](./api/02_endpoints.md):** Core reference for lending and administration.
- **[WebSockets](./api/03_websockets.md):** Real-time IoT hardware communication.

### 3. Data model and workers

Persistence layer and background automation.

- **[Database schema](./database/01_schema.md):** ERD and storage strategy.
- **[Background workers](./database/02_background_workers.md):** Automation for timeouts and overdue loans.

### 4. Hardware and vision

Edge client and computer vision pipeline.

- **[Vision integration](./hardware/01_vision_integration.md):** Dual-phase AI analysis.
- **[Quarantine flow](./hardware/02_quarantine_flow.md):** Administrative resolution for flagged items.

## Suggested reading order

1. **[Technical walkthrough](./WALKTHROUGH.md)**: End-to-end narrative of the system in action.
2. **[Topology](./architecture/01_topology.md)**: Service layout overview.
3. **[Zero-trust chain](./architecture/04_zero_trust.md)**: Foundational security philosophy.
4. **[Audit trail](./architecture/06_audit_trail.md)**: Data integrity mechanics.
5. **[REST principles](./api/01_rest_principles.md)**: Core integration patterns.
6. **[Return flow](./api/04_return_flow.md)**: Dive into the complex return logic.
