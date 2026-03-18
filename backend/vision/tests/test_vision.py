def test_environment_setup():
    """Simple check that Pytest is successfully configured in the Vision module."""
    assert True


def test_ultralytics_import():
    """Verify that Ultralytics (YOLO) can be successfully imported."""
    from ultralytics import YOLO

    # We do not instantiate a model here to keep the CI pipeline fast,
    # but we verify that the class is available in the virtual environment.
    assert YOLO is not None
