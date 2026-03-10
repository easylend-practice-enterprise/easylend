# EasyLend — Gap Analyse: Documentatie & Tickets

## Wat er veranderd is t.o.v. vorige analyse

| Ticket | Vorige status | Nieuwe status | Actie in gap-analyse |
| --- | --- | --- | --- |
| ELP-83 | Done *(misleidende notitie)* | Done ✅ — beschrijving nu correctief bijgewerkt met Flutter/Dart | ✅ Opgelost |
| ELP-56 | Open | **In Progress** — beschrijving bijgewerkt met YOLO26/OpenVINO/ONNX | ✅ Opgelost |
| ELP-59 | Open *(oud concept)* | **On hold** — hernoemd naar "RPi API-communicatie + GPIO" | ✅ Opgelost |
| ELP-12 | Open | **On hold** — beschrijving bijgewerkt met hardware keuzes | ✅ Opgelost |
| ELP-84 | Open | **On hold** — beschrijving bijgewerkt met hardware/schema's/elektronica | ✅ Opgelost |
| ELP-36 | Open | **In Progress** — Kiosk Android project setup gestart | Nieuw signaal |
| ELP-23 | Open | **In Progress** — Password hashing gestart | Nieuw signaal |

---

## 1. Architectuurwijzigingen

### ✅ AI-service: Edge → Proxmox VM (opgelost)

- **ELP-57** "Model exporteren naar Edge device" → Geannuleerd ✅
- **ELP-59** hernoemd naar "RPi API-communicatie + GPIO" → On hold ✅
- **ELP-56** beschrijving bijgewerkt met YOLO26 + OpenVINO/ONNX → In Progress ✅
- **ELP-83** beschrijving bevat nu Flutter/Dart/VSCode/Android Studio ✅

> [!NOTE]
> `architecture.md` schrijft nog "YOLOv26 Medium" — de officiële naam is **YOLO26** (zonder de `v`). Nog te corrigeren als het opvalt bij evaluatoren.

### ✅ Simulatie: Godot → Python + Web UI (opgelost in vorige sprint)

Tickets ELP-32/33/34 hernoemd. `simulation/README.md` aangemaakt ✅

---

## 2. Resterende gaps per component

### Backend (ELP-10 — Open)

> Zie [Backend Stappenplan](../backend/backend_plan.md) voor de volledige volgorde.

| Gap | Ticket | Status |
| --- | --- | --- |
| Password hashing | ELP-23 | 🔄 **In Progress** |
| Auth research afronden | ELP-82 | 📋 Next up |
| JWT model + tokens + refresh token | ELP-21, ELP-22, ELP-24 | 📋 Queued |
| Redis integratie (refresh tokens) | ELP-25 | 📋 Queued |
| CRUD: users & permissions | ELP-27 | 📋 Queued |
| CRUD: assets | ELP-26 | ❌ Open |
| Transactie logica (lenen/inleveren) | ELP-28 | ❌ Open |
| M2M API tokens | ELP-90 | ❌ Open |
| Input sanitization | ELP-30 | ❌ Open |
| Rate limiting | ELP-31 | ❌ Open |
| Hash-chaining audit logs | ELP-29 | ❌ Open |
| Geen API endpoint-documentatie | ELP-68 | ❌ Open |
| Setup guide | ELP-67 | ❌ Open |

### Kiosk App (ELP-7 — Open)

| Gap | Ticket | Status |
| --- | --- | --- |
| Android project setup | ELP-36 | 🔄 **In Progress** |
| Login scherm | ELP-40 | ❌ Open |
| NFC reader implementatie | ELP-38, ELP-39 | ❌ Open |
| Uitleen/inlever flow | ELP-42 | ❌ Open |
| Asset catalogus | ELP-41 | ❌ Open |
| API calls (login, assets, transactie) | ELP-48 | ❌ Open |
| Kiosk-app docs | ELP-70 | ❌ Open |
| `pubspec.yaml` beschrijving aanpassen | — | ❌ Nog open |

> [!NOTE]
> ELP-83 is nu correct — Flutter als definitieve keuze staat in de ticket-beschrijving. ✅

### Vision Box (ELP-6 — Open)

| Gap | Ticket | Status |
| --- | --- | --- |
| `vision-box/` map is leeg | ELP-71 | ❌ Open |
| Elektronicaschema's ontwerpen | ELP-85 | ❌ Open |
| Elektronica aansluiten | ELP-53 | ❌ Open |
| GPIO scripts (slot, licht) | ELP-58 | ❌ Open |
| Hardware consensus/bestelling | ELP-12, ELP-84 | ⏸ On hold |

> [!IMPORTANT]
> Scope van vision-box software/hardware is **na 3 april** (tussentijdse deadline). On hold is correct.

### AI Service

| Gap | Ticket | Status |
| --- | --- | --- |
| `backend/vision/` map is leeg | — | ❌ Nog leeg |
| AI docs | ELP-72 | ❌ Open |
| AI model trainen/valideren | ELP-56 | 🔄 In Progress |

### Simulatie

| Gap | Ticket | Status |
| --- | --- | --- |
| `simulation/` code ontbreekt | ELP-34 | ❌ Open |
| Simulatie backend | ELP-34 | ❌ Open |
| Simulatie UI | ELP-33 | ❌ Open |
| Simulatie docs | ELP-69 | ❌ Open |

---

## 3. Wat volledig ontbreekt (repo-niveau)

| Ontbrekend | Ticket | Status |
| --- | --- | --- |
| `backend/vision/README.md` | ELP-72 | ❌ Niet aanwezig |
| Setup guide per component | ELP-67 | ❌ Niet begonnen |
| `kiosk-app/pubspec.yaml` beschrijving | — | ❌ Nog standaard Flutter tekst |

> [!NOTE]
> `docs/workflows.md` is aangemaakt ✅. `simulation/README.md` is aangemaakt ✅.

---

## 4. Actielijst (bijgewerkt prioriteiten)

| Prioriteit | Actie | Ticket | Was |
| --- | --- | --- | --- |
| 🔴 Hoog | `backend/vision/README.md` aanmaken | ELP-72 | Nieuw |
| 🔴 Hoog | `kiosk-app/pubspec.yaml` beschrijving aanpassen | — | Nog open |
| 🟡 Medium | AI docs schrijven zodra Injo ontwerp klaar heeft | ELP-72 | Ongewijzigd |
| 🟡 Medium | Backend API endpoint-documenten | ELP-68 | Ongewijzigd |
| 🟡 Medium | Hash-chaining audit logs beschrijven | ELP-29 | Ongewijzigd |
| 🟡 Medium | M2M token flow documenteren | ELP-90 | Ongewijzigd |
| 🟢 Laag | Setup guide schrijven per component | ELP-67 | Ongewijzigd |
