# EasyLend AI Vision Service

AI microservice voor het herkennen van assets via YOLO26. Draait **server-side op een Proxmox VM**: niet op het edge device (Vision Box).

## Overzicht

De Vision Box (Raspberry Pi 4) stuurt een foto door naar deze service via de API. De service analyseert de foto en geeft terug welk asset gedetecteerd is en in welke conditie.

**Ticket:** ELP-56 (In Progress), ELP-72 (AI docs: Open)

## Model

| Eigenschap | Waarde |
| --- | --- |
| Model | YOLO26 Medium (`yolo26m.pt`) |
| Framework | [Ultralytics](https://docs.ultralytics.com/) |
| Training hardware | RTX 3090 (CUDA) |
| Inferentie | Proxmox VM (CPU-only) |
| CPU (host) | Intel Xeon Gold 6426Y (Sapphire Rapids, AVX-512 + AMX) |

**Exportformaat voor productie (ELP-56):**

- **OpenVINO (INT8)** — definitieve keuze. De Xeon Gold 6426Y heeft AVX-512 en Intel AMX waardoor INT8-kwantisatie natively versneld wordt (tot 3× sneller dan PyTorch `.pt`)
- ONNX als noodoplossing als OpenVINO installatieproblemen geeft

**Proxmox VM specs (aanbeveling):**

| Resource | Minimum | Aanbevolen |
| --- | --- | --- |
| vCPUs | 4 | **8** |
| RAM | 4 GB | **8 GB** |

> De host heeft 16 cores (32 threads). 8 vCPUs doorpassen is realistisch zonder andere VMs te raken. 8 GB RAM dekt model + OpenVINO runtime + Python overhead met voldoende buffer.

Benchmarken op de VM zelf:

```bash
yolo benchmark model=yolo26m.pt imgsz=640
```

## Huidige staat

- `yolo26m.pt`: YOLO26 Medium model (gedownload)
- `main.py`: trainingsscript (proof of concept op rock-paper-scissors dataset)
- `utils/webcam.py`: webcam capture utility
- `datasets/`: trainingsdatasets
- `runs/`: trainingsresultaten (Ultralytics output)

> De daadwerkelijke asset-dataset (foto's van ICT-materiaal) en de bijhorende inferentie-API endpoint (`POST /api/v1/vision/analyze`) worden later uitgewerkt zodra het AI-ontwerp vaststaat (ELP-72).

## Lokaal uitvoeren

```bash
uv run python main.py
```

## Testing

```bash
uv run pytest
uv run ruff check . --fix
uv run ruff format .
```

## Export guide: PyTorch → ONNX / OpenVINO

*Voor Injo: uit te voeren op de Proxmox VM of de trainingsmachine met GPU.*

### Stap 1: Model trainen of downloaden

Zorg dat `yolo26m.pt` beschikbaar is (getraind of gedownload via Ultralytics).

### Stap 2: Benchmarken (optioneel maar aanbevolen)

Voor je exporteert, vergelijk de formaten op de **Proxmox VM zelf**:

```bash
yolo benchmark model=yolo26m.pt imgsz=640
```

Dit toont inference-snelheid per formaat (PyTorch, ONNX, OpenVINO, ...).

### Stap 3a: Exporteren naar ONNX

Makkelijkste optie, werkt op elke CPU:

```bash
yolo export model=yolo26m.pt format=onnx imgsz=640
```

Geeft `yolo26m.onnx` terug. Inferentie:

```python
from ultralytics import YOLO

model = YOLO("yolo26m.onnx")
results = model("image.jpg")
```

### Stap 3b: Exporteren naar OpenVINO (INT8): aanbevolen voor Intel CPU

Geeft standaard FP32, voeg `half=True` toe voor INT8 kwantisatie:

```bash
yolo export model=yolo26m.pt format=openvino imgsz=640 half=True
```

Geeft een map `yolo26m_openvino_model/` terug. Inferentie:

```python
from ultralytics import YOLO

model = YOLO("yolo26m_openvino_model/")
results = model("image.jpg")
```

> **Kies OpenVINO** als de Proxmox-CPU Intel is (check met `lscpu | grep "Model name"`).  
> **Kies ONNX** als de CPU AMD is of als OpenVINO installatieproblemen geeft.
