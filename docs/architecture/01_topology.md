# System topology

EasyLend uses a microservices-inspired architecture to isolate heavy AI inference from reactive API traffic. Infrastructure is centralized on Proxmox, with edge hardware acting as thin clients.

## Physical topology

Workloads are split across two virtual machines to prevent resource starvation during inference.

```mermaid
flowchart TD
    %% STYLES
    classDef container fill:#bfdbfe,stroke:#3b82f6,stroke-width:2px,color:#000;
    classDef db fill:#fef08a,stroke:#eab308,stroke-width:2px,color:#000;
    classDef edge fill:#bbf7d0,stroke:#22c55e,stroke-width:2px,color:#000;

    subgraph Edge [Edge devices]
        direction TB
        K["Kiosk app: 10.0.2.x"]:::edge
        V["Vision box: 10.0.2.x"]:::edge
    end

    subgraph Proxmox [Proxmox server]
        direction TB

        subgraph VM1 [VM 1: Core backend - 10.0.2.147]
            API["FastAPI REST and WSS: Port 8000"]:::container
            DB[("PostgreSQL 17")]:::db
            REDIS[("Redis cache")]:::db
        end

        subgraph VM2 [VM 2: AI service - 10.0.2.146]
            YOLO["YOLO26 inference: Port 8001"]:::container
        end
    end

    %% Connections
    K <-->|"HTTPS and WSS: Port 8000"| API
    V <-->|"WSS and POST image"| API
    API <-->|"Read and write"| DB
    API <-->|"Pub and sub"| REDIS
    API <-->|"POST image: Port 8001"| YOLO
```

## Logical topology

The system is divided into three functional domains.

```mermaid
flowchart TD
    %% STYLES
    classDef soft fill:#E1F5FE,stroke:#0277BD,stroke-width:2px,color:#000;
    classDef hard fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#000;
    classDef data fill:#FFF9C4,stroke:#FBC02d,stroke-width:2px,color:#000;

    subgraph Kiosk [Kiosk]
        direction TB
        NFC[NFC reader]:::hard
        CamTab["Tablet camera: scanner"]:::hard
        App["Kiosk app: Flutter"]:::soft

        NFC -->|Badge ID| App
        CamTab -->|Aztec code| App
    end

    subgraph Backend [Backend]
        direction TB
        API["FastAPI and WebSockets"]:::soft
        AIService["YOLO26 AI service"]:::soft
        DB[(PostgreSQL 17)]:::data
        Redis[(Redis cache)]:::data

        API <-->|"Query and log"| DB
        API <-->|"Pub and sub"| Redis
        API <-->|"Analyze image"| AIService
    end

    subgraph Box [Vision box]
        direction TB
        RPi["Raspberry Pi 4"]:::hard
        CamBox[Camera]:::hard
        Lock[Electronic lock]:::hard
        CamBox -->|Photo| RPi
        RPi -->|"Open and close"| Lock
    end

    %% CONNECTIONS
    App <-->|"HTTPS REST and polling"| API
    RPi <-->|"WSS and POST image"| API
```
