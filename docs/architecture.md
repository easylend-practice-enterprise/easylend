# EasyLend Systeemarchitectuur

Dit document bevat de macro-architectuur, infrastructuur-topologie en het databasemodel van het EasyLend platform.

## 1. Topologie

De architectuur is gebouwd rondom een gecentraliseerde **Proxmox Virtual Environment**. We hanteren het *Microservices Pattern* om de zware AI-inferentie te scheiden van de reactieve API. Hardware en simulaties fungeren als "Thin Clients".

### Fysieke topologie

```mermaid
flowchart TD
    %% STIJLEN
    classDef container fill:#bfdbfe,stroke:#3b82f6,stroke-width:2px,color:#000;
    classDef db fill:#fef08a,stroke:#eab308,stroke-width:2px,color:#000;
    classDef edge fill:#bbf7d0,stroke:#22c55e,stroke-width:2px,color:#000;

    subgraph Edge ["Edge Devices & Interfaces"]
        direction TB
        K["Android Kiosk App<br/>(NFC + UI)"]:::edge
        V["Vision Box<br/>(Camera + Slot)"]:::edge
        S["Digital Twin<br/>(Python Simulatie)"]:::edge
    end

    subgraph Proxmox ["Proxmox VE Server (Hypervisor)"]
        direction TB
        
        subgraph VM1 ["VM 1: Core Backend (Ubuntu)"]
            API["FastAPI REST & WSS<br/>(Docker Container)"]:::container
            DB[("PostgreSQL 17")]:::db
            REDIS[("Redis Cache")]:::db
            MONITOR["pgAdmin / UptimeKuma<br/>(Internal Network)"]:::container
        end

        subgraph VM2 ["VM 2: AI Microservice (Ubuntu)"]
            YOLO["YOLOv26 Medium<br/>(Inference Engine)"]:::container
        end
    end

    %% Connections
    K <-->|"HTTPS / REST (JWT)"| API
    V <-->|"HTTP POST (Image) & WSS"| API
    S <-->|"HTTP / WSS"| API
    
    API <-->|"Read / Write"| DB
    API <-->|"Pub / Sub"| REDIS
    API <-->|"POST Image / Get JSON"| YOLO
    API <-->|"Health / Metrics"| MONITOR

```

### Logische topologie

```mermaid
flowchart TD
    %% STIJLEN (Corporate & Clean)
    classDef soft fill:#E1F5FE,stroke:#0277BD,stroke-width:2px,color:#000;
    classDef hard fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#000;
    classDef data fill:#FFF9C4,stroke:#FBC02d,stroke-width:2px,color:#000;
    classDef sim  fill:#F3E5F5,stroke:#7B1FA2,stroke-width:2px,stroke-dasharray: 5 5,color:#000;

    %% --- DOMEIN 1: KIOSK (LINKS) ---
    subgraph Kiosk ["Kiosk (Frontend)"]
        direction TB
        NFC[NFC Reader]:::hard
        CamTab["Tablet camera"]:::hard
        App["Android App (Kotlin)"]:::soft
        
        NFC -->|Badge ID| App
        CamTab -->|Aztec code| App
    end

    %% --- DOMEIN 2: BACKEND (MIDDEN) ---
    subgraph Backend ["Backend (Proxmox Server)"]
        direction TB
        API["FastAPI & WebSockets"]:::soft
        AIService["YOLOv26 AI Service"]:::soft
        PXE["PXE Live Boot Service"]:::soft
        DB[(PostgreSQL 17)]:::data
        Redis[(Redis Cache)]:::data
        
        API <-->|"Query / Log"| DB
        API <-->|"Pub/Sub"| Redis
        API <-->|"Analyze Image"| AIService
        API <-->|"Hardware Status"| PXE
    end

    %% --- DOMEIN 3: VISION BOX (RECHTS) ---
    subgraph Box ["Vision Box (Thin Client)"]
        direction TB
        RPi["Raspberry Pi / ESP32"]:::hard
        CamBox[Camera]:::hard
        Lock["Elektronisch slot"]:::hard
        
        CamBox -->|Photo| RPi
        RPi -->|"Open/Close"| Lock
    end

    %% --- SIMULATIE (ONDER) ---
    Sim["Digital Twin WebUI"]:::sim

    %% --- HOOFD VERBINDINGEN ---
    
    %% Kiosk praat met API
    App <-->|"HTTPS JSON<br/>(JWT Auth)"| API

    %% API praat met Box
    RPi <-->|"WSS & POST Image<br/>(Static API Key)"| API

    %% Simulatie test de API
    Sim -.->|"WSS (Virtuele Lockers)<br/>(Static API Key)"| API
```

## 2. Security & Core Principles

* **Zero-Trust Authenticatie:** Geen enkel endpoint is openbaar. Apparaten (Vision Box, Simulatie) gebruiken Static M2M API Keys (`X-Device-Token`). Kiosk-gebruikers gebruiken NFC-tags (UID) gecombineerd met een PIN (JWT).
* **Cryptografische Audit Trail:** Alle kritieke transacties (`LOGIN`, `DOOR_OPENED`, `PXE_CHECK`, `SELF_DECLARATION`) worden opgeslagen in `AUDIT_LOGS`. Elke rij bevat een `current_hash` gebaseerd op de payload én de `previous_hash` van de vorige rij, wat de database *tamper-proof* maakt.
* **No Hardcoding:** Hardcoded IP-adressen of secrets zijn verboden. Alles loopt via een `.env` bestand, strikt gevalideerd door FastAPI `pydantic-settings`.
* **Database Isolatie:** De database is niet blootgesteld aan het internet (`0.0.0.0` is verboden) en wordt door developers benaderd via een SSH Tunnel naar `127.0.0.1`.

## 3. Database Architectuur & Datamodel (ERD)

Het datamodel (PostgreSQL) is strikt genormaliseerd (3NF) en specifiek ontworpen om naadloos om te gaan met asynchrone hardware-statussen, AI-analyses en fraudepreventie.

### Kernconcepten van het Datamodel

1. **Dynamische Locker Toewijzing:** Assets zijn niet hardcoded gekoppeld aan één fysiek kluisje. De `ASSETS.locker_id` is merely de *huidige* locatie. Tijdens een uitleen-transactie (`LOAN`) registreert de database het `checkout_locker_id`. Bij het inleveren berekent de backend welk kluisje leeg is en wijst deze toe als `return_locker_id`. Dit voorkomt bottlenecks als kluisjes defect zijn.
2. **Geavanceerd State Management (Edge Cases):** Om real-world problemen (zoals verborgen defecten of gebruikers die elkaar beschuldigen) op te vangen, werken de enums nauw samen. Een verdachte inlevering triggert `loan_status = DISPUTED` of `PENDING_INSPECTION`. Het corresponderende kluisje wordt direct hardwarematig geblokkeerd via `locker_status = MAINTENANCE` (De Quarantaine-flow).
3. **JSONB voor Flexibiliteit (NoSQL in SQL):** Omdat hardware checks en AI-modellen onvoorspelbare of wisselende datastructuren genereren, gebruiken we het krachtige `JSONB` datatype van PostgreSQL.
   * `AI_EVALUATIONS.detected_objects` slaat de ruwe bounding-box data op.
   * `AUDIT_LOGS.payload` vangt alles op van PXE-boot hardware tests (`{"ram_ok": true}`) tot self-declarations (`{"has_damage": false}`).

### Entity Relationship Diagram

```mermaid
erDiagram
    %% Lookup Tabellen
    ROLES ||--o{ USERS : has
    CATEGORIES ||--o{ ASSETS : categorizes
    
    %% Infrastructuur
    KIOSKS ||--o{ LOCKERS : contains
    LOCKERS ||--o{ ASSETS : currently_holds
    
    %% Transacties
    USERS ||--o{ LOANS : initiates
    ASSETS ||--o{ LOANS : is_part_of
    LOCKERS ||--o{ LOANS : checkout_location
    LOCKERS ||--o{ LOANS : return_location
    
    %% Analyses & Security
    LOANS ||--o{ AI_EVALUATIONS : evaluated_by
    USERS ||--o{ AUDIT_LOGS : performs
    
    ROLES {
        uuid role_id PK
        varchar role_name UK
    }
    
    CATEGORIES {
        uuid category_id PK
        varchar category_name UK
    }
    
    USERS {
        uuid user_id PK
        uuid role_id FK
        varchar first_name
        varchar last_name
        varchar email UK
        varchar nfc_tag_id UK "Nullable: Voor onboarding"
        varchar pin_hash
        int failed_login_attempts "Anti-brute-force"
        timestamp locked_until "Lockout timer"
        boolean is_active
        varchar ban_reason "Nullable"
    }
    
    KIOSKS {
        uuid kiosk_id PK
        varchar name
        varchar location_description
        enum kiosk_status "ONLINE, OFFLINE, MAINTENANCE"
    }

    LOCKERS {
        uuid locker_id PK
        uuid kiosk_id FK
        int logical_number "Fysiek nummer 1, 2, 3..."
        enum locker_status "AVAILABLE, OCCUPIED, MAINTENANCE, ERROR_OPEN"
    }
    
    ASSETS {
        uuid asset_id PK
        uuid category_id FK
        uuid locker_id FK "Nullable: NULL als uitgeleend"
        varchar name
        varchar aztec_code UK
        enum asset_status "AVAILABLE, BORROWED, RESERVED, MAINTENANCE, LOST"
    }
    
    LOANS {
        uuid loan_id PK
        uuid user_id FK
        uuid asset_id FK
        uuid checkout_locker_id FK
        uuid return_locker_id FK "Nullable: Totdat item geretourneerd is"
        timestamp reserved_at "Nullable"
        timestamp borrowed_at "Nullable"
        timestamp due_date "Nullable"
        timestamp returned_at "Nullable"
        enum loan_status "RESERVED, ACTIVE, OVERDUE, COMPLETED, FRAUD_SUSPECTED, DISPUTED, PENDING_INSPECTION"
    }
    
    AI_EVALUATIONS {
        uuid evaluation_id PK
        uuid loan_id FK
        enum evaluation_type "CHECKOUT, RETURN"
        varchar photo_url
        float ai_confidence
        jsonb detected_objects
        varchar model_version
        boolean is_approved
        varchar rejection_reason "Nullable"
        timestamp analyzed_at
    }
    
    AUDIT_LOGS {
        uuid audit_id PK
        uuid user_id FK "Nullable: Bij anonieme errors"
        enum action_type "LOGIN_SUCCESS, DOOR_FORCED, etc."
        jsonb payload
        varchar previous_hash
        varchar current_hash
        timestamp created_at
    }

```

## 4. Operations & Monitoring (Ops)

Om de gezondheid van het systeem te waarborgen zonder zware overhead, maken we gebruik van lichtgewicht, geïsoleerde tooling:

* **Monitoring:** Uptime Kuma draait intern in de Docker-stack en monitort de FastAPI health-endpoints en de database-verbinding.
* **Backups (Disaster Recovery):** De database wordt dagelijks asynchroon geback-upt via een headless SQLBak container naar een off-site cloudlocatie, volledig buiten de scope van de applicatielogica.
