# EasyLend AI Vision Service

AI microservice for recognising assets via YOLO26. Runs **server-side on a Proxmox VM**: not on the edge device (Vision Box).

## Overview

The Vision Box (Raspberry Pi 4) forwards a photo to this service via the API. The service analyses the photo and returns which asset was detected and its condition.

**Ticket:** ELP-56 (In Progress), ELP-72 (AI docs: Open)

## Model

| Property | Value |
| --- | --- |
| Model | YOLO26 Medium Segmentation (`yolo26m-seg.pt`) |
| Framework | [Ultralytics](https://docs.ultralytics.com/) |
| Training hardware | RTX 3090 (CUDA) |
| Inference | Proxmox VM (CPU-only) |
| CPU (host) | Intel Xeon Gold 6426Y (Sapphire Rapids, AVX-512 + AMX) |

**Production export format (ELP-56):**

- **OpenVINO (INT8)**: final choice. The Xeon Gold 6426Y includes AVX-512 and Intel AMX, which natively accelerates INT8 quantisation (up to 3× faster than PyTorch `.pt`)
- ONNX as a fallback if OpenVINO installation issues arise

**Proxmox VM specs (recommendation):**

| Resource | Minimum | Recommended |
| --- | --- | --- |
| vCPUs | 4 | **8** |
| RAM | 4 GB | **8 GB** |

> The host has 16 cores (32 threads). Passing through 8 vCPUs is realistic without impacting other VMs. 8 GB RAM covers the model + OpenVINO runtime + Python overhead with ample buffer.

Benchmark on the VM itself:

```bash
uv run yolo benchmark model=yolo26m.pt imgsz=640
```

## Current State

Files in this repo:

- `main.py`: training script (proof of concept on rock-paper-scissors dataset)
- `utils/webcam.py`: webcam capture utility

Locally generated/downloaded artifacts (**not** in Git, listed in `.gitignore`):

- `yolo26m-seg.pt`: YOLO26 Medium Segmentation model
- `datasets/`: training datasets
- `runs/`: training results (Ultralytics output)

> The actual asset dataset (photos of ICT equipment) and the corresponding inference API endpoint (`POST /api/v1/vision/analyze`) will be developed once the AI design is finalised (ELP-72).

## Running Locally

*(Make sure `yolo26m-seg.pt` and the `datasets/` directory are available locally)*

```bash
uv run python main.py
```

## Testing

```bash
uv run pytest
uv run ruff check . --fix
uv run ruff format .
```

## Export Guide: PyTorch → ONNX / OpenVINO

*Run these steps on the Proxmox VM or on a training machine with a GPU.*

### Step 1: Train or download the model

Make sure `yolo26m-seg.pt` is available (trained or downloaded via Ultralytics).

### Step 2: Benchmark (optional but recommended)

Before exporting, compare formats on the **Proxmox VM itself**:

```bash
uv run yolo benchmark model=yolo26m-seg.pt imgsz=640
```

This shows inference speed per format (PyTorch, ONNX, OpenVINO, ...).

### Step 3a: Export to ONNX

Easiest option, works on any CPU:

```bash
yolo export model=yolo26m-seg.pt format=onnx imgsz=640
```

Produces `yolo26m-seg.onnx`. Inference:

```python
from ultralytics import YOLO

model = YOLO("yolo26m.onnx")
results = model("image.jpg")
```

### Step 3b: Export to OpenVINO (INT8): recommended for Intel CPU

> **Note:** To do this you must first install the required packages, as they are not included in `uv.lock` by default to keep the image small:
> `uv pip install openvino onnx onnxruntime`

Defaults to FP32; add `int8=True` for INT8 quantisation:

```bash
yolo export model=yolo26m-seg.pt format=openvino imgsz=640 int8=True
```

Produces a `yolo26m-seg_openvino_model/` directory. Inference:

```python
from ultralytics import YOLO

model = YOLO("yolo26m-seg_openvino_model/")
results = model("image.jpg")
```

> **Choose OpenVINO** if the Proxmox CPU is Intel (check with `lscpu | grep "Model name"`).  
> **Choose ONNX** if the CPU is AMD or if OpenVINO installation issues arise.
