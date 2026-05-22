# System Topology

EasyLend uses a microservices-inspired architecture designed to isolate heavy AI inference workloads from reactive API traffic. Our infrastructure is centralized on a Proxmox Virtual Environment, with physical hardware and simulations acting as "Thin Clients."

## Physical Topology
We split our workloads across two Virtual Machines (Ubuntu) to ensure that YOLO inference does not starve the main API of CPU or Memory resources.

```mermaid
flowchart TD
    %% STYLES
    classDef container fill:#bfdbfe,stroke:#3b82f6,stroke-width:2px,color:#000;
    classDef db fill:#fef08a,stroke:#eab308,stroke-width:2px,color:#000;
    classDef edge fill:#bbf7d0,stroke:#22c55e,stroke-width:2px,color:#000;

    subgraph Edge ["Edge Devices & Interfaces"]
        direction TB
        K["Android Kiosk App<br/>(NFC + UI)"]:::edge
        V["Vision Box<br/>(Camera + Slot)"]:::edge
        S["Digital Twin<br/>(Python Simulation)"]:::edge
    end

    subgraph Proxmox ["Proxmox VE Server (Hypervisor)"]
        direction TB

        subgraph VM1 ["VM 1: Core Backend (10.0.2.147)"]
            API["FastAPI REST & WSS (Port 8000)"]:::container
            DB[("PostgreSQL 17")]:::db
            REDIS[("Redis Cache")]:::db
        end

        subgraph VM2 ["VM 2: AI Microservice (10.0.2.146)"]
            YOLO["YOLO26 Medium (Port 8001)"]:::container
        end
    end

    %% Connections
    K <-->|"HTTPS / WSS (Port 8000)"| API
    V <-->|"WSS (Port 8000) & POST Image"| API
    S <-->|"HTTP / WSS (Port 8000)"| API

    API <-->|"Read / Write"| DB
    API <-->|"Pub / Sub"| REDIS
    API <-->|"POST Image (Port 8001)"| YOLO
```

## Logical Topology
Our logical structure is divided into three primary domains: the **Kiosk (Frontend)**, the **Backend (API & AI)**, and the **Vision Box (Hardware Orchestrator)**.

```mermaid
flowchart TD
    %% STYLES
    classDef soft fill:#E1F5FE,stroke:#0277BD,stroke-width:2px,color:#000;
    classDef hard fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#000;
    classDef data fill:#FFF9C4,stroke:#FBC02d,stroke-width:2px,color:#000;

    %% DOMAIN 1: KIOSK
    subgraph Kiosk ["Kiosk (Frontend)"]
        direction TB
        NFC[NFC Reader]:::hard
        App["Android App (Flutter)"]:::soft
        NFC -->|Badge ID| App
    end

    %% DOMAIN 2: BACKEND
    subgraph Backend ["Backend"]
        direction TB
        API["FastAPI & WebSockets"]:::soft
        AIService["YOLO26 AI Service"]:::soft
        DB[(PostgreSQL 17)]:::data
        Redis[(Redis Cache)]:::data

        API <-->|"Query / Log"| DB
        API <-->|"Pub/Sub + Token Whitelist"| Redis
        API <-->|"Analyze Image"| AIService
    end

    %% DOMAIN 3: VISION BOX
    subgraph Box ["Vision Box (Thin Client)"]
        direction TB
        RPi["Raspberry Pi 4"]:::hard
        CamBox[Camera]:::hard
        Lock["Electronic lock"]:::hard
        CamBox -->|Photo| RPi
        RPi -->|"Open/Close"| Lock
    end

    %% CONNECTIONS
    App <-->|"HTTPS REST + Polling"| API
    RPi <-->|"WSS & POST Image"| API
```
