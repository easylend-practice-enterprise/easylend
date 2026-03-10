# EasyLend workflows

> Dit document is nog in ontwikkeling en kan nog wijzigen. Momenteel is dit een prototype van de workflow diagrammen.

Dit document beschrijft de voornaamste gebruikers- en systeemworkflows via sequence diagrammen.

De vier kernflows zijn:

1. Login
2. Checkout
3. Return
4. Quarantaine

## 1. Login Flow (NFC + PIN)

De gebruiker scant zijn NFC-badge en voert zijn PIN in om een JWT-token te ontvangen.
Ingebouwd anti-brute-force mechanisme blokkeert het account na meerdere mislukte pogingen.

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

    alt Account geblokkeerd (locked_until in de toekomst)
        API-->>App: 403 Account geblokkeerd
        App-->>User: "Account tijdelijk geblokkeerd"
    else Account actief
        API-->>App: 200 Vraag PIN
        App-->>User: Toon PIN-invoer scherm
        User->>App: Voert PIN in
        App->>API: POST /api/v1/auth/pin {nfc_tag_id, pin}
        API->>DB: SELECT pin_hash WHERE nfc_tag_id = ?
        DB-->>API: pin_hash

        alt PIN incorrect
            API->>DB: UPDATE failed_login_attempts + 1
            alt Limiet bereikt (bijv. 5 pogingen)
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
            API-->>App: 200 JWT access token
            App-->>User: Ingelogd: toon asset catalogus
        end
    end
```

---

## 2. Checkout Flow (Item uitlenen)

De gebruiker kiest een item in de app. De API valideert de aanvraag en opent **zelf** het slot via de Vision Box: de App heeft nooit directe controle over hardware. Na het sluiten van de deur fotografeert de Vision Box het kluisje om te bevestigen dat het **leeg** is.

```mermaid
sequenceDiagram
    actor User as Gebruiker
    participant App as Kiosk App (Flutter)
    participant API as FastAPI Backend
    participant DB as PostgreSQL
    participant VB as Vision Box (RPi 4)
    participant AI as YOLO26 AI Service (VM2)

    User->>App: Kiest asset uit catalogus
    App->>API: POST /loans/checkout {asset_id} [JWT]
    API->>DB: SELECT asset WHERE asset_id = ? AND asset_status = AVAILABLE
    DB-->>API: Asset + locker_id

    alt Asset niet beschikbaar
        API-->>App: 409 Asset niet beschikbaar
        App-->>User: "Item niet beschikbaar"
    else Asset beschikbaar
        API->>DB: INSERT loan {status: ACTIVE, checkout_locker_id}
        API->>DB: UPDATE asset SET asset_status = BORROWED
        API-->>App: 200 {loan_id, locker_number}
        App-->>User: "Ga naar locker #N"

        Note over API,VB: API is de enige die hardware aanstuurt
        API->>VB: WSS: open_slot {locker_id}
        VB->>VB: GPIO: slot openen + LED groen

        User->>VB: Neemt item uit locker, sluit deur
        VB->>API: WSS: slot_closed event

        Note over VB,AI: Foto ná deur-dicht: kluisje hoort leeg te zijn
        VB->>API: POST /api/v1/vision/analyze (M2M) {loan_id, image, type: CHECKOUT}
        API->>AI: POST /predict {image}
        AI-->>API: {locker_empty, objects, confidence}

        alt Kluisje niet leeg (item achtergelaten of verwisseld)
            API->>DB: UPDATE loan SET loan_status = FRAUD_SUSPECTED
            API->>DB: INSERT audit_log {CHECKOUT_INCOMPLETE}
            API->>VB: WSS: set_led {color: red}
            API-->>App: 409 Checkout onvolledig: item niet meegenomen
            App-->>User: "Fout gedetecteerd. Neem contact op met beheerder."
        else Kluisje leeg: checkout geslaagd
            API->>DB: INSERT ai_evaluation {type: CHECKOUT, locker_empty: true}
            API->>DB: UPDATE locker SET locker_status = AVAILABLE
            API->>DB: INSERT audit_log {CHECKOUT_COMPLETED}
            API->>VB: WSS: set_led {color: green}
            API-->>App: WSS: checkout_complete_event
            App-->>User: "Veel succes! Breng het item terug voor [due_date]"
        end
    end
```

---

## 3. Return Flow (Item inleveren)

De gebruiker brengt een item terug. De Vision Box fotografeert voor en na het plaatsen. YOLO26 detecteert eventuele schade.

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
    App->>API: POST /loans/return/initiate {aztec_code} [JWT]
    API->>DB: SELECT loan WHERE asset.aztec_code = ? AND user_id = ? AND status = ACTIVE
    DB-->>API: loan + locker info

    alt Geen actieve uitleen gevonden
        API-->>App: 404 Geen uitleen gevonden
        App-->>User: "Geen actieve uitleen voor dit item"
    else Uitleen gevonden
        API->>DB: SELECT locker WHERE locker_status = AVAILABLE LIMIT 1
        DB-->>API: Vrije locker
        API-->>App: 200 {return_locker_id, locker_number}
        App-->>User: "Breng item naar locker #N"

        API->>VB: WSS: open_slot {return_locker_id}
        VB->>VB: GPIO: slot openen + LED groen
        User->>VB: Plaatst item in locker, sluit deur
        VB->>API: WSS: slot_closed event

        VB->>API: POST /api/v1/vision/analyze (M2M) {loan_id, image, type: RETURN}
        API->>AI: POST /predict {image}
        AI-->>API: {objects, confidence, has_damage, damage_details}

        alt Schade gedetecteerd
            API->>DB: INSERT ai_evaluation {type: RETURN, has_damage: true}
            API->>DB: INSERT damage_reports [...]
            API->>DB: UPDATE loan SET loan_status = PENDING_INSPECTION
            API->>DB: UPDATE locker SET locker_status = MAINTENANCE
            API->>DB: INSERT audit_log {DAMAGE_DETECTED}
            API->>VB: WSS: LED oranje (quarantaine)
            API-->>App: 200 {status: PENDING_INSPECTION}
            App-->>User: "Schade gedetecteerd. Beheerder verwittigd."
        else Geen schade
            API->>DB: INSERT ai_evaluation {type: RETURN, has_damage: false, approved: true}
            API->>DB: UPDATE loan SET loan_status = COMPLETED, return_locker_id, returned_at
            API->>DB: UPDATE asset SET asset_status = AVAILABLE, locker_id = return_locker_id
            API->>DB: UPDATE locker SET locker_status = OCCUPIED
            API->>DB: INSERT audit_log {RETURN_COMPLETED}
            API->>VB: WSS: LED groen bevestiging
            API-->>App: 200 {status: COMPLETED}
            App-->>User: "Item succesvol ingeleverd!"
        end
    end
```

---

## 4. AI Quarantaine Flow (schade gedetecteerd)

Wanneer YOLO26 schade detecteert bij een inlevering, wordt het kluisje automatisch geblokkeerd en wordt een beheerder verwittigd.

```mermaid
sequenceDiagram
    participant API as FastAPI Backend
    participant DB as PostgreSQL
    participant VB as Vision Box (RPi 4)
    participant Admin as Beheerder

    Note over API,VB: Schade gedetecteerd tijdens Return Flow

    API->>DB: UPDATE loan SET loan_status = PENDING_INSPECTION
    API->>DB: INSERT ai_evaluation {has_damage: true, is_approved: false}
    API->>DB: INSERT damage_reports [{damage_type, severity, segmentation_data}]
    API->>DB: UPDATE locker SET locker_status = MAINTENANCE

    API->>VB: WSS: set_led {color: orange}
    VB->>VB: GPIO: LED oranje (quarantaine signaal)

    Note over Admin: Beheerder controleert via dashboard

    Admin->>API: GET /admin/loans?status=PENDING_INSPECTION [JWT admin]
    API-->>Admin: Lijst van loans in quarantaine

    Admin->>API: GET /admin/evaluations/{evaluation_id}
    API-->>Admin: Foto, AI rapport, damage reports

    alt Beheerder keurt schade goed (echte schade)
        Admin->>API: PATCH /admin/evaluations/{id} {is_approved: true}
        API->>DB: UPDATE loan SET loan_status = DISPUTED
        API->>DB: INSERT audit_log {DAMAGE_CONFIRMED}
        API-->>Admin: Schade bevestigd, gebruiker gemarkeerd
    else Beheerder verwerpt AI rapport (fout-positief)
        Admin->>API: PATCH /admin/evaluations/{id} {is_approved: false, rejection_reason}
        API->>DB: UPDATE loan SET loan_status = COMPLETED
        API->>DB: UPDATE asset SET asset_status = AVAILABLE
        API->>DB: UPDATE locker SET locker_status = OCCUPIED
        API->>DB: INSERT audit_log {DAMAGE_REJECTED_FALSE_POSITIVE}
        API->>VB: WSS: set_led {color: green}
        API-->>Admin: Quarantaine opgeheven
    end
```
