from pathlib import Path

from ultralytics import YOLO

VISION_ROOT = Path(__file__).parent.parent.resolve()


def main():
    model = YOLO("yolov8m-seg.pt")  # Base segmentation checkpoint for YOLO26 config.

    model.train(
        data=str(
            VISION_ROOT
            / "datasets"
            / "laptop_damage_segmentation_YOLO26-seg"
            / "data.yaml"
        ),
        epochs=100,
        imgsz=640,
        device=0,
        name="yolo26m-seg_laptop_damage_detection",
        project=str(VISION_ROOT / "runs" / "laptop-damage-detection"),
    )


if __name__ == "__main__":
    main()
