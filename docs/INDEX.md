# EasyLend Project Documentation

Welcome to the technical documentation for **EasyLend**, an IoT-enabled equipment lending platform. This documentation is structured to provide reviewers and developers with a clear, modular understanding of our system architecture, API design, and hardware integration.

---

## 📖 Suggested Reading Order (Reviewer's Path)
1. **[Technical Walkthrough](./WALKTHROUGH.md)**: Start here for a narrative overview of how the system works end-to-end.
2. **[System Topology](./architecture/01_topology.md)**: Understand the "Physical vs Logical" split of our services.
3. **[Zero-Trust Chain](./architecture/04_zero_trust.md)**: Explore our core security philosophy across API, IoT, and AI.
4. **[Audit Trail](./architecture/06_audit_trail.md)**: Deep-dive into our blockchain-inspired cryptographic logging.
5. **[REST Principles](./api/01_rest_principles.md)**: Review our unique "IoT Partial Success" and "Snoepautomaat" patterns.

---

## 🗺️ Documentation Map

### [1. System Architecture](./architecture/01_topology.md)
*The high-level design of EasyLend.*
- **[Topology](./architecture/01_topology.md):** Physical and Logical system layout.
- **[State Management](./architecture/02_state_machine.md):** The Redux-style `LoanStateMachine` and transition logic.
- **[Concurrency & Locking](./architecture/03_concurrency.md):** Our Zero-Trust approach and dead connection resilience.
- **[Zero-Trust Chain](./architecture/04_zero_trust.md):** Security philosophy across the whole system.
- **[Audit Trail](./architecture/06_audit_trail.md):** Blockchain-inspired cryptographic transaction logging.
- [Traditional Security](./architecture/04_security.md): Authentication, Hardening, and Rate Limiting.
- [Discipline Policy](./architecture/05_user_suspension.md): Compliance rules for user locking and damage disputes.
- [Technical Debt & Risk](./architecture/07_technical_debt.md): Registration of known V1 limitations and V2 roadmap.

### [2. API & Integration](./api/01_rest_principles.md)
*How the Kiosk app and hardware interact with the backend.*
- **[REST Principles](./api/01_rest_principles.md):** The "IoT Partial Success" pattern and business rules.
- **[Endpoint Reference](./api/02_endpoints.md):** Key REST endpoints for lending and administration.
- **[WebSocket Protocol](./api/03_websockets.md):** The real-time IoT hardware communication spec.

### [3. Data Model & Workers](./database/01_schema.md)
*How we persist state and handle background tasks.*
- **[Database Schema](./database/01_schema.md):** The Entity Relationship Diagram (ERD) and JSONB usage.
- **[Background Workers](./database/02_background_workers.md):** Logic for loan timeouts and overdue detection.

### [4. Hardware & Vision AI](./hardware/01_vision_integration.md)
*The edge client and computer vision pipeline.*
- **[Vision Integration](./hardware/01_vision_integration.md):** Dual-phase AI analysis and model updates.
- **[Quarantine Flow](./hardware/02_quarantine_flow.md):** Administrative handling of damage and fraud detections.

---

## 🚀 Quick Start
If you are looking for installation and setup instructions, please refer to the [Root README](../README.md).
