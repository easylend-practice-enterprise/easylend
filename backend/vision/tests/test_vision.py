def test_environment_setup():
    """Simpele check of Pytest succesvol is geconfigureerd in de Vision map."""
    assert True


def test_ultralytics_import():
    """Controleer of Ultralytics (YOLO) succesvol geladen kan worden."""
    from ultralytics import YOLO

    # We instantiëren nog geen model om de CI-pipeline snel te houden,
    # maar we checken of de class beschikbaar is in de virtuele omgeving.
    assert YOLO is not None
