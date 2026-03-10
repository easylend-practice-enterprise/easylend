# EasyLend workflows

> Dit document beschrijft de definitieve systeemworkflows via sequence diagrammen.
> Architectuur: De Kiosk App communiceert via REST (met Polling voor asynchrone hardware-acties). De Vision Box luistert naar commando's via WebSockets (WSS).

De vier kernflows zijn:

1. Login
2. Checkout (Uitlenen)
3. Return (Inleveren)
4. Quarantaine (Schade-afhandeling)

---

## 1. Login Flow (NFC + PIN)

De gebruiker scant zijn NFC-badge en voert zijn PIN in om een JWT-token te ontvangen. Ingebouwd anti-brute-force mechanisme blokkeert het account na 5 mislukte pogingen.

```mermaid
sequenceDiagram
    actor User as Gebruiker
    participant App as Kiosk App (Flutter)
    participant API as FastAPI Backend
    participant DB as PostgreSQL

    User->>App: Houdt NFC-badge voor lezer
    App->>API: POST /api/v1/auth/nfc {nfc_tag_id}
    API->>DB: SELECT user WHERE nfc_tag_id = ?
    DB-->>API: User record

    alt Account geblokkeerd (locked_until > NOW)
        API-->>App: 403 Account geblokkeerd
        App-->>User: "Account tijdelijk geblokkeerd"
    else Account actief
        API-->>App: 200 OK (Vraag PIN)
        App-->>User: Toon PIN-invoer scherm
        User->>App: Voert PIN in
        App->>API: POST /api/v1/auth/pin {nfc_tag_id, pin}
        API->>DB: SELECT pin_hash WHERE nfc_tag_id = ?
        DB-->>API: pin_hash

        alt PIN incorrect
            API->>DB: UPDATE failed_login_attempts + 1
            alt Limiet bereikt (5 pogingen)
                API->>DB: SET locked_until = NOW() + interval
                API->>DB: INSERT audit_log {LOGIN_FAILED, ACCOUNT_LOCKED}
                API-->>App: 403 Account geblokkeerd
            else Nog pogingen over
                API->>DB: INSERT audit_log {LOGIN_FAILED}
                API-->>App: 401 Onjuiste PIN (N pogingen over)
            end
            App-->>User: Foutmelding
        else PIN correct
            API->>DB: UPDATE failed_login_attempts = 0
            API->>DB: INSERT audit_log {LOGIN_SUCCESS}
            API-->>App: 200 OK {access_token: JWT}
            App-->>User: Ingelogd: toon asset catalogus
        end
    end

```

---

## 2. Checkout Flow (Item uitlenen)

De app vraagt een lening aan via REST. De API stuurt de Vision Box aan via WSS. De app "pollt" intussen de API om te weten of de hardware- en AI-acties zijn voltooid.

```mermaid
sequenceDiagram
    actor User as Gebruiker
    participant App as Kiosk App (Flutter)
    participant API as FastAPI Backend
    participant DB as PostgreSQL
    participant VB as Vision Box (RPi 4)
    participant AI as YOLO26 AI Service (VM2)

    User->>App: Kiest asset uit catalogus
    App->>API: POST /api/v1/loans/checkout {asset_id} [JWT]
    API->>DB: SELECT asset WHERE asset_id = ? AND asset_status = AVAILABLE
    DB-->>API: Asset + locker_id

    alt Asset niet beschikbaar
        API-->>App: 409 Conflict
        App-->>User: "Item niet beschikbaar"
    else Asset beschikbaar
        API->>DB: INSERT loan {loan_status: ACTIVE}
        API->>DB: UPDATE asset SET asset_status = BORROWED
        API-->>App: 202 Accepted {loan_id, locker_number}
        App-->>User: Toon lader: "Ga naar locker #N"

        Note over API,VB: API stuurt Vision Box realtime aan
        API->>VB: WSS: open_slot {locker_id}
        VB->>VB: GPIO: slot openen + LED groen

        User->>VB: Neemt item uit locker, sluit deur
        VB->>API: WSS: slot_closed event

        Note over VB,AI: Achtergrondcontrole: kluisje moet leeg zijn
        VB->>API: POST /api/v1/vision/analyze (M2M) {loan_id, image, type: CHECKOUT}
        API->>AI: POST /predict {image}
        AI-->>API: {locker_empty, confidence}

        alt Kluisje niet leeg (Fraude/Fout)
            API->>DB: UPDATE loan SET loan_status = FRAUD_SUSPECTED
            API->>VB: WSS: set_led {color: red}
        else Kluisje leeg (Succes)
            API->>DB: UPDATE locker SET locker_status = AVAILABLE
            API->>DB: UPDATE loan SET loan_status = ACTIVE
            API->>VB: WSS: set_led {color: green}
        end

        Note over App,API: App vraagt de API elke 3 sec om een statusupdate (Polling)
        App->>API: GET /api/v1/loans/{loan_id}/status
        
        alt Status is FRAUD_SUSPECTED
            API-->>App: 200 OK {status: FRAUD_SUSPECTED}
            App-->>User: "Fout gedetecteerd. Item niet meegenomen."
        else Status is COMPLETED
            API-->>App: 200 OK {status: COMPLETED}
            App-->>User: "Veel succes! Breng het item tijdig terug."
        end
    end

```

---

## 3. Return Flow (Item inleveren)

De gebruiker scant de Aztec code via de tablet. De API wijst een leeg kluisje toe. Na het sluiten controleert de AI of het item daadwerkelijk in het kluisje ligt en of er schade is.

```mermaid
sequenceDiagram
    actor User as Gebruiker
    participant App as Kiosk App (Flutter)
    participant API as FastAPI Backend
    participant DB as PostgreSQL
    participant VB as Vision Box (RPi 4)
    participant AI as YOLO26 AI Service (VM2)

    User->>App: Kiest "Item inleveren"
    App-->>User: Toon Aztec code scanner
    User->>App: Scant Aztec code van item
    App->>API: POST /api/v1/loans/return/initiate {aztec_code} [JWT]
    API->>DB: SELECT loan WHERE aztec_code = ? AND loan_status = ACTIVE
    DB-->>API: loan info

    alt Geen actieve uitleen gevonden
        API-->>App: 404 Not Found
        App-->>User: "Geen actieve uitleen voor dit item"
    else Uitleen gevonden
        API->>DB: SELECT locker WHERE locker_status = AVAILABLE LIMIT 1
        DB-->>API: Vrije locker
        API-->>App: 202 Accepted {return_locker_id, locker_number}
        App-->>User: Toon lader: "Breng item naar locker #N"

        API->>VB: WSS: open_slot {return_locker_id}
        VB->>VB: GPIO: slot openen + LED groen
        User->>VB: Plaatst item in locker, sluit deur
        VB->>API: WSS: slot_closed event

        VB->>API: POST /api/v1/vision/analyze (M2M) {loan_id, image, type: RETURN}
        API->>AI: POST /predict {image}
        AI-->>API: {has_damage, damage_details}

        alt Schade gedetecteerd
            API->>DB: UPDATE loan SET loan_status = PENDING_INSPECTION
            API->>DB: UPDATE locker SET locker_status = MAINTENANCE
            API->>VB: WSS: set_led {color: orange}
        else Geen schade
            API->>DB: UPDATE loan SET loan_status = COMPLETED
            API->>DB: UPDATE asset SET asset_status = AVAILABLE
            API->>DB: UPDATE locker SET locker_status = OCCUPIED
            API->>VB: WSS: set_led {color: green}
        end

        Note over App,API: App vraagt de API elke 3 sec om een statusupdate (Polling)
        App->>API: GET /api/v1/loans/{loan_id}/status
        
        alt Status is PENDING_INSPECTION
            API-->>App: 200 OK {status: PENDING_INSPECTION}
            App-->>User: "Schade gedetecteerd. Beheerder is verwittigd."
        else Status is COMPLETED
            API-->>App: 200 OK {status: COMPLETED}
            App-->>User: "Item succesvol ingeleverd!"
        end
    end

```

---

## 4. AI Quarantaine Flow (Schade gedetecteerd)

Wanneer de AI in de Return Flow schade detecteert, moet een menselijke admin dit goedkeuren of verwerpen via het dashboard.

```mermaid
sequenceDiagram
    participant API as FastAPI Backend
    participant DB as PostgreSQL
    participant VB as Vision Box (RPi 4)
    participant Admin as Beheerder

    Note over API,VB: Systeem bevindt zich in PENDING_INSPECTION (oranje LED brandt)

    Admin->>API: GET /api/v1/admin/loans?status=PENDING_INSPECTION [JWT admin]
    API-->>Admin: Lijst van loans in quarantaine

    Admin->>API: GET /api/v1/admin/evaluations/{evaluation_id}
    API-->>Admin: Foto, AI rapport, damage details

    alt Beheerder keurt schade goed (Echte schade)
        Admin->>API: PATCH /api/v1/admin/evaluations/{id} {is_approved: true}
        API->>DB: UPDATE loan SET loan_status = DISPUTED
        API->>DB: INSERT audit_log {DAMAGE_CONFIRMED}
        API-->>Admin: 200 OK (Schade bevestigd, gebruiker gemarkeerd)
    else Beheerder verwerpt AI rapport (Fout-positief)
        Admin->>API: PATCH /api/v1/admin/evaluations/{id} {is_approved: false}
        API->>DB: UPDATE loan SET loan_status = COMPLETED
        API->>DB: UPDATE asset SET asset_status = AVAILABLE
        API->>DB: UPDATE locker SET locker_status = OCCUPIED
        API->>DB: INSERT audit_log {DAMAGE_REJECTED_FALSE_POSITIVE}
        API->>VB: WSS: set_led {color: green}
        API-->>Admin: 200 OK (Quarantaine opgeheven)
    end

```
