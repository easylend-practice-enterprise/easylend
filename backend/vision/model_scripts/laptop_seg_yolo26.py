import os

from ultralytics import YOLO

current_dir = os.path.dirname(os.path.abspath(__file__))


def main():
    model = YOLO("yolo26m-seg.pt")
    model.train(
        data="datasets/laptop_damage_segmentation_YOLO26-seg/data.yaml",
        epochs=100,
        imgsz=640,
        device=0,
        name="yolo26m-seg_laptop_damage_detection",
        project=os.path.join(current_dir, "runs", "laptop-damage-detection"),
    )


if __name__ == "__main__":
    main()
