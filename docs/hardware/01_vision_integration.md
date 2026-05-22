# Vision integration

Standalone microservice for high-fidelity analysis of locker contents.

## Dual-phase analysis

API coordinates parallel requests after a photo upload:

1. **Object detection:** Verifies locker occupancy state (YOLO26 Medium).
2. **Segmentation:** Identifies scratches or cracks (YOLO26 Segmentation).

## Finalization logic

Ensures slow AI calls do not hold database locks:

1. **Inference phase:** Pre-flight read and AI processing (unlocked).
2. **Commit phase:** Acquire fail-fast locks and apply state transitions.

## Model updates

Administrators can trigger atomic updates of the YOLO weights using a reverse-proxied request.

- **Required format:** The endpoint strictly expects standard PyTorch (`.pt`) files via secure HTTPS URLs.
- **OpenVINO pipeline:** Direct uploads of pre-compiled OpenVINO directories via the API are not supported. Instead, upon receiving a new `.pt` file, the service automatically exports it to the optimized OpenVINO format before loading it into memory. This ensures maximum CPU acceleration on the host hardware without requiring administrators to manually compile models.

## Advanced workflow: pre-converted models

For faster deployments, models can be pre-converted to OpenVINO format on a high-performance machine (e.g., with a GPU) and delivered manually to the Vision service.

1. **Export:** On the source machine, run `model.export(format="openvino")`.
2. **Delivery:** Copy the resulting directory (e.g., `best_openvino_model/`) into the Vision Docker's persistent volume (`/app/models/`).
3. **Naming:** The directory must follow the naming convention `<model_name>_openvino_model`. For example, if the target is `detection.pt`, the folder must be `detection_openvino_model`.
4. **Loading:** Upon restart, the service will detect the existing directory and skip the internal conversion process.

```mermaid
sequenceDiagram
    actor Admin as Admin/System
    participant API as Main API
    participant Vision as Vision API

    Admin->>API: PATCH /api/v1/update-model {JSON Payload}
    API->>API: Verify verify_vision_box_token dependency

    alt Invalid Token
        API-->>Admin: 403 Forbidden
    else Valid Token
        Note over API: Acts as reverse proxy<br/>Translates to POST request<br/>Attaches Authorization: Bearer <VISION_API_KEY>
        API->>Vision: POST /update-model
        Vision->>Vision: Verify Bearer token
        Vision->>Vision: Download model(s) (Fail-Fast behavior)
        Vision->>Vision: Schedule BackgroundTask to restart server
        Vision-->>API: 200 OK
        API-->>Admin: 200 OK
    end
```
