import os

from ultralytics import YOLO

current_dir = os.path.dirname(os.path.abspath(__file__))


def main():
    model = YOLO("yolo26n.pt")
    model.train(
        data="datasets/rock-paper-scissors/data.yaml",
        epochs=5,
        imgsz=640,
        name="yolo26n_rock-paper-scissors",
        project=os.path.join(current_dir, "runs", "rock-paper-scissors"),
    )


if __name__ == "__main__":
    main()
