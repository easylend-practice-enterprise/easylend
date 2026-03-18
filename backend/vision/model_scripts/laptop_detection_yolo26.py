import os

from ultralytics import YOLO

current_dir = os.path.dirname(os.path.abspath(__file__))


def main():
    model = YOLO("yolo26m.pt")
    model.train(
        data="datasets/laptop_detection_YOLO26/data.yaml",
        epochs=100,
        imgsz=640,
        device=0,
        name="yolo26m-laptop_detection",
        project=os.path.join(current_dir, "runs", "laptop-detection"),
    )


if __name__ == "__main__":
    main()
