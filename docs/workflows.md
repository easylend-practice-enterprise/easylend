# EasyLend workflows

> Dit document beschrijft de definitieve systeemworkflows via sequence diagrammen.
> Architectuur: De Kiosk App communiceert via REST (met Polling voor asynchrone hardware-acties). De Vision Box luistert naar commando's via WebSockets (WSS).

De zeven kernflows zijn:

1. Login
2. Checkout (Uitlenen)
3. Return (Inleveren)
4. Quarantaine (Schade-afhandeling)
5. Catalogus en Autorisatie Flow (RBAC)
6. Kiosk Boot & Admin Remote Control
7. Admin Dashboard (Beheer)

---

## 1. Login Flow (NFC + PIN)

De gebruiker scant zijn NFC-badge en voert zijn PIN in om een JWT-token te ontvangen. Ingebouwd anti-brute-force mechanisme blokkeert het account na 5 mislukte pogingen.

[Bekijk het sequence diagram: Login Flow](./diagrams/sequence_auth.mmd)

---

## 2. Checkout Flow (Item uitlenen)

De app vraagt een lening aan via REST. De API stuurt de Vision Box aan via WSS. De app "pollt" intussen de API om te weten of de hardware- en AI-acties zijn voltooid.

[Bekijk het sequence diagram: Checkout Flow](./diagrams/sequence_checkout.mmd)

---

## 3. Return Flow (Item inleveren)

De gebruiker scant de Aztec code via de tablet. De API wijst een leeg kluisje toe. Na het sluiten controleert de AI of het item daadwerkelijk in het kluisje ligt en of er schade is.

[Bekijk het sequence diagram: Return Flow](./diagrams/sequence_return.mmd)

---

## 4. AI Quarantaine Flow (Schade gedetecteerd)

Wanneer de AI in de Return Flow schade detecteert, moet een menselijke admin dit goedkeuren of verwerpen via het dashboard.

[Bekijk het sequence diagram: AI Quarantaine Flow](./diagrams/sequence_quarantine.mmd)

---

## 5. Catalogus en Autorisatie Flow (RBAC)

De weergave van de catalogus verschilt op basis van de rol van de ingelogde gebruiker (Student vs. Admin). Studenten zien enkel een geanonimiseerde 'pool' van beschikbare items, Admins zien alle details.

[Bekijk het sequence diagram: Catalogus Flow](./diagrams/sequence_catalog.mmd)

---

## 6. Kiosk Boot & Admin Remote Control

Wanneer een Kiosk opstart, haalt deze zijn eigen hardware-status op via een M2M-token. Een beheerder (met een Admin JWT) kan via de app op afstand kluisjes forceren of beheren.

[Bekijk het sequence diagram: Admin Sync & Boot Flow](./diagrams/sequence_admin_sync.mmd)

---

## 7. Admin Dashboard (Beheer)

Admin gebruikers beheren assets, quarantaine en kiosk-lockers via het Admin Dashboard.

[Bekijk het sequence diagram: Admin App Flow](./diagrams/sequence_admin_app.mmd)
