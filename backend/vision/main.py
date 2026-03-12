import os

from ultralytics import YOLO

current_dir = os.path.dirname(os.path.abspath(__file__))


def main():
    model = YOLO("yolo26m-seg.pt")
    model.train(
        data="datasets/Laptop.v2-laptop.yolo26/data.yaml",
        epochs=10,
        imgsz=640,
        device=0,
        name="yolo26m-seg_laptop_detection",
        project=os.path.join(current_dir, "runs", "laptop-detection"),
    )


if __name__ == "__main__":
    main()
