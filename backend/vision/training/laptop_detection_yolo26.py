from pathlib import Path

from ultralytics import YOLO

# Dit wijst altijd naar de 'backend/vision' root map
VISION_ROOT = Path(__file__).parent.parent.resolve()


def main():
    model = YOLO(
        "yolo26m.pt"
    )  # Base checkpoint used by our YOLO26 training configuration.

    model.train(
        data=str(VISION_ROOT / "datasets" / "laptop_detection_YOLO26" / "data.yaml"),
        epochs=100,
        imgsz=640,
        device=0,
        name="yolo26m-laptop_detection",
        project=str(VISION_ROOT / "runs" / "laptop-detection"),
    )


if __name__ == "__main__":
    main()
