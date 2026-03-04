from ultralytics import YOLO


def main():
    model = YOLO("yolo26n.pt")  # Load a pretrained YOLO model
    model.train(
        data="datasets/test_object_detection/data.yaml",  # Path to the dataset configuration file
        epochs=5,  # Number of training epochs
        imgsz=640,  # Image size for training
        name="yolo26n_test_object_detection",  # Name of the training run
        project="runs/test_object_detection",  # Directory to save training results
    )


if __name__ == "__main__":
    main()
