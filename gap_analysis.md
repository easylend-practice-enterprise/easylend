# EasyLend Gap Analysis

> This document is the single source of truth for all missing components (gaps) between the current completed backend and a working physical MVP.

## 1. Documentation & Setup (Backend)

The backend logic is 100% completed, but we need to formalize the contracts for the rest of the team.

| Gap | Ticket | Status | Priority |
| :--- | :--- | :--- | :--- |
| **API Contract (Swagger/Docs)**: Documenting JWT, Idempotency, WSS payloads, and the 202/503 polling fallback. | ELP-68 | ❌ Open | 🔥 High (Blocks Frontend) |
| **Setup Guide**: How to spin up the backend, Postgres, and Redis locally via Docker? | ELP-67 | ❌ Open | Normal |

## 2. Simulation (Digital Twin)

Before connecting real hardware, we will build a Python/Web simulation of the Kiosk to test the backend end-to-end.

| Gap | Ticket | Status | Priority |
| :--- | :--- | :--- | :--- |
| **Simulation Framework Setup**: Framework choice (Streamlit/FastAPI/Flask) and scaffolding in `/simulation`. | ELP-32 | ❌ Open | 🔥 High |
| **Mocking Hardware IO**: Simulating the WSS connection (`X-Device-Token`), WSS events (`slot_closed`), and NFC scans. | ELP-33 | ❌ Open | High |

## 3. Kiosk App (Frontend - Flutter/Android)

The tablet interface for students. Communicates via REST API.

| Gap | Ticket | Status | Priority |
| :--- | :--- | :--- | :--- |
| **Android Project Setup**: Scaffolding and dependencies (including NFC libs). | ELP-36 | 🔄 In Progress | High |
| **NFC Reader Implementation**: Physically reading the tag and forwarding it to the API. | ELP-38 | ❌ Open | High |
| **Login Flow & UI**: Handling the PIN screen and JWT storage (incl. 403 lockouts). | ELP-40 | ❌ Open | Normal |
| **Asset Catalog**: Fetching and displaying available items (`GET /catalog`). | ELP-41 | ❌ Open | Normal |
| **Transaction Flows (Checkout/Return)**: Building the UI for Checkout and Return, including the 3-second Polling mechanic and Aztec scanning. | ELP-42 | ❌ Open | Normal |
| **API Integration**: Connecting all generated UI to the actual backend endpoints. | ELP-92 | ❌ Open | Normal |

## 4. Vision Box (Physical Hardware - Raspberry Pi)

The edge client that controls the lockers and captures photos.

| Gap | Ticket | Status | Priority |
| :--- | :--- | :--- | :--- |
| **Hardware Setup**: Configuring the Raspberry Pi, drawing electronic schematics. | ELP-85 | ❌ Open | ⏸ On hold (Waiting for parts) |
| **GPIO Scripts**: Python scripts for switching the lock and the LED (green/orange/red). | ELP-58 | ❌ Open | ⏸ On hold |
| **WebSocket Client**: Script that receives WSS commands and triggers the GPIO scripts. | ELP-51 | ❌ Open | ⏸ On hold |

## 5. AI Service (YOLO26 VM)

The service that analyzes the photos sent by the Vision Box.

| Gap | Ticket | Status | Priority |
| :--- | :--- | :--- | :--- |
| **API Wrapper for YOLO**: FastAPI service around the YOLO26 model that accepts `POST /predict`. | ELP-62 | ❌ Open | Normal |
| **AI Model Training/Quantization**: Converting the model to OpenVINO (INT8) for the Xeon CPU. | ELP-56 | 🔄 In Progress | Normal |
| **AI Documentation**: Documenting the architecture and thresholds. | ELP-72 | ❌ Open | Low |

---
*Execution order: Section 1 first, then Section 2, then Sections 3 and 5 in parallel.*
