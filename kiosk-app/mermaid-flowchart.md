# Mermaid

```mermaid
flowchart TD
    Start[App Start] --> Login[Login Screen]

    Login --> NFC{NFC Badge Scan?}
    NFC -->|Yes| BadgeID[Extract Badge ID]
    BadgeID --> PIN[PIN Entry Screen]

    PIN --> ShowError{Error Displayed?}
    ShowError -->|Yes| RateLimit[Rate Limit Screen<br/>5 attempts max]
    ShowError -->|No| Validate[Validate PIN via API]

    Validate -->|Success| AuthSuccess[Store JWT Token]
    Validate -->|Error| ShowError

    RateLimit --> PIN

    AuthSuccess --> Dashboard[Asset Catalog Dashboard]

    %% CHECKOUT FLOW (Uitlenen via REST Polling)
    Dashboard --> SelectAsset{Select Asset to Lend?}
    SelectAsset -->|Yes| ConfirmLend[Confirm Lending in Catalog]
    SelectAsset -->|No| Dashboard

    ConfirmLend --> APIOpenBox[POST /api/v1/loans/checkout]
    APIOpenBox --> PollCheckout["App polls: GET /api/v1/loans/{loan_id}/status"]
    
    PollCheckout --> CheckoutStatus{Status updated?}
    CheckoutStatus -->|No - Still RESERVED| PollCheckout
    CheckoutStatus -->|Yes - ACTIVE| LendSuccess[Transaction Complete]
    CheckoutStatus -->|Yes - FRAUD_SUSPECTED| CheckoutError[Show Checkout Error]
    
    CheckoutError --> Dashboard
    LendSuccess --> Dashboard

    %% RETURN FLOW (Inleveren met Tablet Camera via REST Polling)
    Dashboard --> SelectReturn{Select Asset to Return?}
    SelectReturn -->|Yes| ConfirmReturn[Confirm Return]
    SelectReturn -->|No| Dashboard

    ConfirmReturn --> ScanAztecReturn[Tablet Camera: Scan Aztec Code]
    ScanAztecReturn --> ValidateAztecReturn[POST /api/v1/loans/return/initiate]
    
    ValidateAztecReturn -->|Error| ShowAztecErrorReturn[Show Aztec Error]
    ShowAztecErrorReturn --> ScanAztecReturn

    ValidateAztecReturn -->|Success| ReturnOpenBox[API Opens Vision Box]
    ReturnOpenBox --> PollReturn["App polls: GET /api/v1/loans/{loan_id}/status"]

    PollReturn --> ReturnStatus{Status updated?}
    ReturnStatus -->|No - Still ACTIVE| PollReturn
    ReturnStatus -->|Yes - COMPLETED| ReturnSuccess[Return Complete]
    ReturnStatus -->|Yes - PENDING_INSPECTION| ReturnQuarantine[Show Damage Alert]

    ReturnQuarantine --> Dashboard
    ReturnSuccess --> Dashboard

```
