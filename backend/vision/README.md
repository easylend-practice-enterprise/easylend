# EasyLend AI Vision Service

AI microservice (FastAPI) for recognizing assets and laptop damage via YOLO26. Runs **server-side on a Proxmox VM** (not on the edge device / Vision Box).

## Overview

The Vision Box (Raspberry Pi 4) forwards a photo to the Main API, which proxies it to this Vision service. The service analyzes the photo and returns the detected assets and their condition.

**Tickets:** ELP-56 (AI Model), ELP-72 (AI Docs), ELP-93 (Vision Microservice)

## Infrastructure & Hardware

| Property | Value |
| --- | --- |
| Model | YOLO26 (`best.pt` → OpenVINO for inference) |
| Dual-model system | Object detection (`/detect`) + damage segmentation (`/segment`) |
| Framework | [Ultralytics](https://docs.ultralytics.com/) |
| Training hardware | RTX 3090 (CUDA) |
| Inference | Proxmox VM (CPU-only) |
| CPU (host) | Intel Xeon Gold 6426Y (Sapphire Rapids, AVX-512 + AMX) |

**Proxmox VM specs (Recommendation):**

| Resource | Minimum | Recommended |
| --- | --- | --- |
| vCPUs | 4 | **8** |
| RAM | 4 GB | **8 GB** |

> The host has 16 cores (32 threads). Passing through 8 vCPUs is realistic without impacting other VMs. 8 GB RAM covers the model, OpenVINO runtime, and FastAPI overhead with ample buffer.

## Automatic OpenVINO Acceleration

Because the Intel Xeon Gold CPU supports AVX-512 and Intel AMX, we use **OpenVINO** for inference.
You **do not** need to manually export the model anymore. The FastAPI service (`main.py`) handles this automatically:

1. On startup, it checks for a `.pt` model.
2. If the OpenVINO cache is missing, it compiles it on-the-fly.
3. It loads the highly optimized OpenVINO model into memory.

## Running the Service

The service is fully Dockerized.

### Local Development

To run the service locally (without Watchtower and with a local volume mount for rapid development):

```bash
docker compose -f docker-compose.local.yml up -d
```

### Production (Proxmox VM2)

The production environment uses Watchtower to automatically pull the latest image from the GitHub Container Registry.

```bash
docker compose -f docker-compose.prod.yml up -d
```

## Dual-Model System

The Vision service uses a **dual-model approach**:
1. **Detection model** (`POST /detect`): Counts objects in the locker image to determine if it is empty or occupied.
2. **Segmentation model** (`POST /segment`): Detects physical damage on assets.

Both models are called in parallel by the Main API during checkout and return evaluations. The Main API evaluates the combined result and transitions the loan accordingly.

## Model Management & Webhook

To keep the Docker image small, the `models/` directory is excluded from the build.
When the container starts fresh, it boots in **degraded mode** (The `/health` endpoint will show `model_loaded: false`).

To download the latest model weights, send a POST request to the management webhook. The service will safely download the weights, compile the OpenVINO cache, and restart automatically.

```bash
curl -X POST http://localhost:8000/update-model \
     -H "Authorization: Bearer <VISION_API_KEY>" \
     -H "Content-Type: application/json" \
     -d '{"download_url": "[https://your-secure-url.com/best.pt](https://your-secure-url.com/best.pt)"}'
```

## API Endpoints

- `GET /health` - Check service status and model availability. Returns `model_loaded: true/false`.
- `POST /detect` - Upload an image (multipart/form-data) for object detection. Returns `status`, `count`, `detections[]`, `locker_empty`. Requires `Authorization: Bearer <VISION_API_KEY>`.
- `POST /segment` - Upload an image (multipart/form-data) for damage segmentation. Returns `status`, `has_damage_detected`. Requires `Authorization: Bearer <VISION_API_KEY>`.
- `POST /update-model` - Webhook to download new model weights from a safe HTTPS URL. Triggers a service restart. Requires auth.

## Testing & Linting

Tests run automatically in CI. OpenVINO compilation is skipped during tests (`SKIP_MODEL_LOADING=1`) for speed.

```bash
uv run pytest
uv run ruff check . --fix
uv run ruff format .
```
