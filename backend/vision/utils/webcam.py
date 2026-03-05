import logging
from pathlib import Path

import cv2
from ultralytics import YOLO

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class YOLOModelTester:
    """
    Een robuuste utility class om YOLO modellen lokaal te testen via de webcam.
    Perfect voor MLOps debugging voordat het model aan FastAPI gekoppeld wordt.
    """

    def __init__(
        self, model_name: str, conf_threshold: float = 0.5, camera_id: int = 0
    ):
        self.conf_threshold = conf_threshold
        self.camera_id = camera_id

        current_dir = Path(__file__).resolve().parent.parent
        self.model_path = (
            current_dir
            / "runs"
            / "detect"
            / "runs"
            / "rock-paper-scissors"
            / model_name
            / "weights"
            / "best.pt"
        )

        if not self.model_path.exists():
            logger.error(f"Model niet gevonden op: {self.model_path}")
            raise FileNotFoundError("Train eerst het model of check het pad!")

        logger.info(f"Model succesvol geladen: {self.model_path.name}")
        self.model = YOLO(str(self.model_path))

    def run(self) -> None:
        """Start de webcam loop met error handling en nette afsluiting."""
        cap = cv2.VideoCapture(self.camera_id)

        if not cap.isOpened():
            logger.error("Kon de webcam niet initialiseren. Wordt deze al gebruikt?")
            return

        logger.info(
            "Webcam actief. Klik op de video en druk op 'q' of gebruik het kruisje om te stoppen."
        )

        window_name = "EasyLend AI Debugger"

        max_consecutive_failures = 10
        consecutive_failures = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    consecutive_failures += 1
                    logger.warning(
                        f"Frame overgeslagen of webcam verbinding verloren. ({consecutive_failures}/{max_consecutive_failures})"
                    )
                    if consecutive_failures >= max_consecutive_failures:
                        logger.error(
                            "Te veel opeenvolgende mislukte frames. Webcam verbinding verbroken."
                        )
                        break
                    continue
                consecutive_failures = 0

                results = self.model.predict(
                    frame, conf=self.conf_threshold, verbose=False
                )
                annotated_frame = results[0].plot()

                cv2.imshow(window_name, annotated_frame)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    logger.info("Afsluit-commando ontvangen (q).")
                    break

                if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                    logger.info("Venster gesloten via kruisje (X).")
                    break

        except KeyboardInterrupt:
            logger.info("Script handmatig gestopt (Ctrl+C in terminal).")
        except Exception as e:
            logger.exception(f"Er is een onverwachte fout opgetreden: {e}")
        finally:
            logger.info("Webcam en vensters netjes afsluiten...")
            cap.release()
            cv2.destroyAllWindows()


if __name__ == "__main__":
    tester = YOLOModelTester(
        model_name="yolo26n_rock-paper-scissors", conf_threshold=0.6
    )
    tester.run()
