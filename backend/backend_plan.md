# EasyLend Backend: Stappenplan

> Volgorde gebaseerd op technische afhankelijkheden. Auth moet volledig klaar zijn voor CRUD, CRUD voor business logic.

---

## Stap 1: Password Hashing (afgerond)

**Ticket:** ELP-23 · **Status:** ✅ Done

- `passlib` of `bcrypt` integreren in de FastAPI app
- Hash wachtwoord bij registratie / update
- Verify bij login
- **Done-criteria:** unit test die hash + verify valideert

> **Seed script (chore, geen ticket):** `seed.py` is beschikbaar onder `backend/api/scripts/seed.py`. Let op de **FK-volgorde**, de DB enforceert referentiële integriteit:
>
> ```text
> Stap 1: ROLES (role_id wordt FK in USERS)
> Stap 2: CATEGORIES (category_id wordt FK in ASSETS)
> Stap 3: KIOSKS (kiosk_id wordt FK in LOCKERS)
> Stap 4: LOCKERS (locker_id wordt FK in ASSETS)
> Stap 5: USERS met role_id --> ASSETS met category_id + locker_id
> ```
>
> Uitvoeren in lokale testomgeving: `uv run python scripts/seed.py`

---

## Stap 2: Auth Research afronden

**Ticket:** ELP-82 · **Status:** ✅ Done

ELP-82 is research: niet implementatie. Vink dit af zodra je een beslissing hebt over:

- [x] JWT algoritme (HS256 vs RS256)
- [x] Access token TTL (bijv. 15 min)
- [x] Refresh token TTL (bijv. 7 dagen)
- [x] Refresh token opslag: Redis key-structuur (`refresh_token:{user_id}`)

---

## Stap 3: JWT Model opstellen

**Ticket:** ELP-21 · **Status:** 📋 Queued · *Requires: stap 2*

- Pydantic model voor JWT payload:

  ```python
  class TokenPayload(BaseModel):
      sub: UUID  # user_id
      role: str
      exp: datetime
      jti: UUID  # token ID (voor revocation)
  ```

- Aparte `schemas/token.py`

---

## Stap 4: JWT Tokens maken

**Ticket:** ELP-22 · **Status:** 📋 Queued · *Requires: stap 3*

- `create_access_token()` en `verify_access_token()` functies
- FastAPI dependency `get_current_user` via `Authorization: Bearer`
- Endpoints:
  - `POST /api/v1/auth/nfc` --> start login via NFC (geeft tijdelijke context)
  - `POST /api/v1/auth/pin` --> verifieert PIN en geeft access + refresh token
  - `POST /api/v1/auth/logout`

> **Test met seed data (stap 1)**: geen User CRUD nodig om dit te testen.

---

## Stap 5: Refresh Token Mechanisme

**Ticket:** ELP-24 · **Status:** 📋 Queued · *Requires: stap 4*

- `POST /api/v1/auth/refresh` endpoint
- Refresh token valideren --> nieuw access token uitschrijven
- Refresh token na gebruik invalideren (rotation)

---

## Stap 6: Redis Integratie (refresh tokens)

**Ticket:** ELP-25 · **Status:** 📋 Queued · *Requires: stap 5*

- Redis config is al klaar (ELP-17 ✅ Done)
- Refresh tokens opslaan in Redis met TTL:

  ```text
  SET refresh_token:{user_id} {token} EX 604800
  ```

- Revocation check bij elke refresh aanvraag
- Bij logout: DEL key

---

## Stap 7: CRUD: Users & Permissions

**Ticket:** ELP-27 · **Status:** 📋 Queued · *Requires: stap 4 (auth middleware)*

- `GET /api/v1/users/me`
- `GET /api/v1/users/{id}` (admin only)
- `POST /api/v1/users` (admin: nieuw gebruiker aanmaken)
- Role-based access control dependency
- Permissions model (RBAC: admin / medewerker / kiosk)

> **NFC tag registratie (kip-en-ei fix):** De Login Flow werkt enkel als `nfc_tag_id` gekoppeld is aan een user. Voeg toe:
>
> `PATCH /api/v1/users/{id}/nfc  { nfc_tag_id }` (admin only)
>
> Zonder dit endpoint kan je NFC-login nooit testen buiten de seed data om.

---

## Stap 8: CRUD: Kiosks --> Categories --> Lockers --> Assets

**Ticket:** ELP-26 · **Status:** ❌ Open · *Requires: stap 7 (permissions)*

> **FK-volgorde verplicht:** Elke entiteit heeft een FK naar de vorige. Bouw in deze volgorde.

**Kiosks** *(kiosk_id FK in LOCKERS: moet eerst)*

- `GET /api/v1/kiosks` (admin)
- `POST /api/v1/kiosks` (admin: nieuw kioskapparaat registreren)
- `PUT /api/v1/kiosks/{id}/status`

**Categories** *(category_id FK in ASSETS: moet eerst)*

- `GET /api/v1/categories`
- `POST /api/v1/categories` (admin)
- `PUT /api/v1/categories/{id}`

**Lockers** *(requires kiosk_id)*

- `GET /api/v1/lockers` (admin: overzicht + status)
- `GET /api/v1/lockers/{id}`
- `POST /api/v1/lockers` (admin: kluisje aan kiosk koppelen)
- `PUT /api/v1/lockers/{id}/status` (admin: bijv. naar MAINTENANCE)

**Assets** *(requires category_id + locker_id)*

- `GET /api/v1/assets` (paginatie, filter op status)
- `GET /api/v1/assets/{id}`
- `POST /api/v1/assets` (admin: inclusief `aztec_code` en `category_id`)
- `PUT /api/v1/assets/{id}` (admin)
- `DELETE /api/v1/assets/{id}` (admin, soft-delete)

---

## Stap 9: M2M API Tokens

**Ticket:** ELP-90 · **Status:** ❌ Open · *Requires: stap 4*

> ⚠️ **Omhoog geschoven.** De Vision Box heeft een M2M token nodig om `POST /api/v1/vision/analyze` (Stap 10b) te mogen aanroepen. Klaar zijn vóór de hardware-integratie.

- Aparte token flow voor machine-clients (Vision Box, Kiosk)
- `POST /api/v1/auth/token` met `client_credentials` grant
- Statische API-key of signed JWT zonder refresh
- Scope beperken (bijv. kiosk mag enkel checkout/return, vision-box enkel analyze)

---

## Stap 10a: Transactie CRUD (lenen / inleveren)

**Ticket:** ELP-28 · **Status:** ❌ Open · *Requires: stap 8 (assets + lockers)*

De basis business-logica zonder hardware-koppeling: testbaar via Swagger/Postman.

- `POST /api/v1/loans/checkout`: asset uitlenen, locker toewijzen
  - **Concurrency:** Gebruik `SELECT ... FOR UPDATE NOWAIT` om te garanderen dat 2 users nooit tegelijkertijd hetzelfde asset krijgen toegewezen.
  - **Pro-feature (Idempotentie):** Vereist een `Idempotency-Key` in de header (bijv. een UUID). De API checkt in Redis of deze key recent gebruikt is om te voorkomen dat een haperende tablet (double-taps) per ongeluk twee leningen start.
- `POST /api/v1/loans/return/initiate`: inleverproces starten, vrije locker zoeken.
  - **Pro-feature (Idempotentie):** Vereist een `Idempotency-Key` in de header (tegen double-taps).
- `GET /api/v1/loans/{loan_id}/status`: polling endpoint voor de actuele transactiestatus.
- **Timeout Worker (Hardware-bewust):** Een achtergrondtaak annuleert leningen na 3 minuten inactiviteit. **Let op:** Als de hardware al is geactiveerd (WSS `open_slot` is verstuurd) mag de status NOOIT gerollbacked worden naar `AVAILABLE`. Bij een timeout ná fysieke actie gaat de locker direct naar `MAINTENANCE` (fysieke controle vereist).
- Validatie: asset beschikbaar/actief? gebruiker actief? locker vrij? **Is deze lening van de ingelogde gebruiker (`loan.user_id == jwt.sub`)?**
- Status-update asset + locker + audit log entry

---

## Stap 10b: Hardware & AI Integratie

**Status:** ❌ Open · *Requires: stap 9 (M2M tokens) + stap 10a*

Veruit het complexste deel. Koppelt de transactielogica met de fysieke hardware.

**Beslissing: Foto-opslag (`photo_url`):**
We gebruiken een **Lokaal Docker Volume** (`/app/uploads`). Dit past perfect in de scope van het prototype en is bloedsnel.

- Foto's worden weggeschreven naar schijf en de API serveert ze via een nieuw endpoint: `GET /api/v1/images/{filename}`.
  - **Security:** implementatie moet:
    - Een veilige bestandsnaam-strategie afdwingen (UUID's, geen ruwe user input).
    - Het pad normaliseren en valideren om path traversal (`../`) tegen te gaan.
    - Authorisatie toepassen (enkel admins of de eigenaar van de lening mogen de foto zien).

**WebSockets (Vision Box aansturing):**

- WebSocket manager opzetten in FastAPI (`/ws/visionbox`)
- `open_slot {locker_id, loan_id}` sturen na checkout-goedkeuring
- `set_led {locker_id, color}` sturen op basis van AI-resultaat of fout
- `slot_closed` event ontvangen van Vision Box
- **Fallback:** als er geen actieve WSS-sessie is van de Vision Box --> stuur `503` terug naar de App met melding "Vision Box niet bereikbaar". Log in audit.

**AI Evaluatie-endpoint (voor Vision Box):**

- `POST /api/v1/vision/analyze`: ontvangt foto + loan_id van Vision Box (M2M auth)
- Sla foto op in `/app/uploads` --> genereer `photo_url`
- Stuurt foto door naar YOLO26 AI Service (VM2)
- Verwerkt resultaat:
  - **Checkout:** kluisje leeg? --> `ACTIVE` of `FRAUD_SUSPECTED` (bij fraude: asset + locker terug naar `AVAILABLE`)
  - **Return:** schade? --> `COMPLETED` of `PENDING_INSPECTION`
  - **Fallback (AI Timeout/Crash):** Als de AI VM niet antwoordt binnen 10s: markeer loan als `PENDING_INSPECTION`, locker naar `MAINTENANCE` (vereist fysieke controle door beheerder).
- Slaat op in `ai_evaluations` tabel inclusief `photo_url` en `model_version`

---

## Stap 10c: Admin Quarantaine Dashboard

**Status:** ❌ Open · *Requires: stap 10b*

Endpoints voor het beheerpaneel om geblokkeerde leningen (schade of fraude) af te handelen. Deze worden gebruikt in de Quarantaine Flow.

- `GET /api/v1/admin/loans?status=PENDING_INSPECTION` (lijst van leningen in quarantaine)
- `GET /api/v1/admin/evaluations/{evaluation_id}` (haalt het AI rapport en de `photo_url` op)
- `PATCH /api/v1/admin/evaluations/{id}` (Beheerder keurt goed: status naar `DISPUTED`, of keurt af: status naar `COMPLETED`)

---

## Stap 11: Input Sanitization

**Ticket:** ELP-30 · **Status:** ❌ Open · *Parallel uitvoerbaar met stap 10+*

- Pydantic validators op alle request bodies
- Max-length checks, regex op e-mails / IDs
- SQL injection niet van toepassing (SQLAlchemy ORM): wel XSS in string velden

---

## Stap 12: Rate Limiting & Abuse Prevention

**Ticket:** ELP-31 · **Status:** ❌ Open · *Requires: stap 6 (Redis)*

Rate limiting gebeurt in 3 strategische lagen (hybride aanpak):

1. **Laag 1: Business Logic (Vertical Brute-force)**
   - De database (`failed_login_attempts`) blokkeert één specifiek account na 5 foute PINs.
2. **Laag 2: Public Endpoints (DDoS & Horizontal Brute-force)**
   - Endpoints zoals `/auth/nfc` zijn publiek. Hier gebruiken we **IP-based** rate limiting via Redis/slowapi.
   - We zetten de limiet ruim (bijv. 500 req/min per IP) om problemen met campus-NAT (meerdere kiosken op 1 netwerk) te voorkomen, maar bots te blokkeren.
3. **Laag 3: Authenticated Endpoints (Spam/Glitch preventie)**
   - Zodra een client een JWT of M2M token heeft, rate-limiten we op **Token ID (`sub` / `kiosk_id`)**.
   - Dit voorkomt dat een gecompromitteerd account of haperende app de server overbelast (bijv. 60 req/min per user), zonder andere gebruikers op hetzelfde netwerk te straffen.

---

## Stap 13: Hash-Chaining Audit Logs

**Ticket:** ELP-29 · **Status:** ❌ Open · *Requires: stap 10a (transacties)*

- Elke auditlog-entry bevat `prev_hash` van de vorige entry
- SHA-256 over `(prev_hash + entry_data)` --> `current_hash`
- Tamper-detection: check of chain intact is bij opvragen
- Endpoint: `GET /api/v1/audit` (admin only)

---

## Overzicht

```text
[1] Password hashing + seed.py  <-- ROLES/CATEGORIES/KIOSKS ook seeden!
  --> [2] Auth research afronden
    --> [3] JWT model
      --> [4] JWT tokens  <-- test met seed data
        --> [5] Refresh token
          --> [6] Redis integratie
            --> [7] Users CRUD  <-- incl. PATCH /users/{id}/nfc
              --> [8] Kiosks --> Categories --> Lockers --> Assets CRUD
                --> [10a] Transactie CRUD
                  --> [10b] Hardware & AI  <-- beslissing: Lokaal Docker Volume
                          WebSockets + fallback + /vision/analyze
                    --> [10c] Admin Quarantaine Dashboard
        --> [9] M2M tokens  <-- vóór 10b, Vision Box auth
[11] Input sanitization (parallel, vanaf stap 10+)
[12] Rate limiting (requires Redis: stap 6)
[13] Hash-chaining audit logs (requires stap 10a)
```
