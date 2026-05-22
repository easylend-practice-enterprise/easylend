import os
from pathlib import Path

from ultralytics import YOLO

os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

VISION_ROOT = Path(__file__).parent.parent.resolve()


def main():
    model = YOLO("yolo26l-seg.pt")

    model.train(
        data=str(
            VISION_ROOT
            / "datasets"
            / "laptop_damage_detection_YOLO26-seg"
            / "data.yaml"
        ),
        imgsz=960,
        batch=4,
        nbs=16,
        mask_ratio=2,
        overlap_mask=False,
        amp=False,
        epochs=300,
        patience=40,
        dropout=0.15,
        weight_decay=0.0005,
        copy_paste=0.3,
        mosaic=1.0,
        mixup=0.0,
        scale=0.3,
        close_mosaic=15,
        optimizer="AdamW",
        lr0=0.0005,
        cos_lr=True,
        warmup_epochs=5.0,
        device=0,
        name="yolo26l-seg",
        project=str(VISION_ROOT / "runs" / "laptop-damage-detection"),
    )


if __name__ == "__main__":
    main()
