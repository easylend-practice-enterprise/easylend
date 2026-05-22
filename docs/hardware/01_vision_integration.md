# Vision AI Integration

The Vision AI service is a standalone FastAPI microservice that performs high-fidelity analysis of locker contents to prevent fraud and detect damage.

## Dual-Phase Analysis

When a Vision Box uploads a photo to `/api/v1/vision/analyze`, the API coordinates two parallel AI requests:

### 1. Object Detection (`/detect`)

- **Model**: YOLO26 Medium (Object Detection).
- **Goal**: Verify if the locker is empty (for checkout) or contains the expected item (for return).
- **Logic**: Returns a `locker_empty` boolean and a list of detected objects.

### 2. Segmentation (`/segment`)

- **Model**: YOLO26 Segmentation (Damage Detection).
- **Goal**: Identify scratches, cracks, or missing components on the asset.
- **Logic**: Returns a `has_damage_detected` boolean.

## Transactional Finalization

To ensure the AI call (which can take ~30s) does not hold database locks, we use a two-phase pattern:

1. **Phase 1**: Pre-flight read of records and AI inference (No DB locks).
2. **Phase 2**: Acquire `NOWAIT` locks on Loan, Asset, and Locker; then apply state machine transitions based on AI results.

## Model Updates

Administrators can trigger an atomic update of the YOLO models via a `PATCH /update-model` request. The API acts as a reverse proxy, forwarding the request to the Vision service, which downloads the new weights and restarts with zero-downtime backup recovery.
