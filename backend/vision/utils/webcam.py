import argparse
import logging
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue

import cv2
from ultralytics import YOLO

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def discover_models(current_dir: Path) -> list:
    """Discover models by locating `weights/best.pt` under common run folders.

    Returns list of tuples (display, path-to-best.pt).
    """
    bases = [
        current_dir / "runs" / "detect" / "runs",
        current_dir / "runs",
    ]
    results = []
    seen = set()
    for base in bases:
        if not base.exists():
            continue
        for cand in base.rglob("weights/best.pt"):
            model_dir = cand.parent.parent
            try:
                display = str(model_dir.relative_to(base))
            except Exception:
                display = str(model_dir)
            if str(cand) not in seen:
                results.append((display, cand))
                seen.add(str(cand))
    return results


class YOLOModelTester:
    """
    A robust utility class for testing YOLO models locally via webcam.
    Ideal for MLOps debugging before coupling the model to FastAPI.
    """

    def __init__(
        self, model_name: str, conf_threshold: float = 0.5, camera_id: int = 0
    ):
        self.conf_threshold = conf_threshold
        self.camera_id = camera_id
        current_dir = Path(__file__).resolve().parent.parent
        self._available_models = discover_models(current_dir)

        # Allow model_name to be an index (int) into discovered models
        selected_path = None
        if model_name is None:
            if self._available_models:
                selected_path = self._available_models[0][1]
        else:
            # numeric index
            try:
                idx = int(model_name)
                if 0 <= idx < len(self._available_models):
                    selected_path = self._available_models[idx][1]
            except (ValueError, TypeError, IndexError) as e:
                logger.debug("Model index parse/lookup failed: %s", e)

            # exact match by display
            if selected_path is None:
                for display, cand in self._available_models:
                    if display == model_name or model_name in display:
                        selected_path = cand
                        break

            # direct path fallback (supports subpaths like 'laptop-detection/...')
            if selected_path is None:
                for base in [
                    current_dir / "runs" / "detect" / "runs",
                    current_dir / "runs",
                ]:
                    direct = base / model_name / "weights" / "best.pt"
                    if direct.exists():
                        selected_path = direct
                        break

        if selected_path is None:
            logger.error("No model selected or model not found. Available models:")
            for i, (display, cand) in enumerate(self._available_models):
                logger.error(f"  [{i}] {display} -> {cand}")
            raise FileNotFoundError("Train the model first or verify the path!")

        self.model_path = selected_path
        logger.info(f"Model selected: {self.model_path}")
        self.model = YOLO(str(self.model_path))

        # state for threaded inference
        self._frame_q: Queue = Queue(maxsize=1)
        self._annotated_frame = None
        self._annot_lock = threading.Lock()
        self._stop_event = threading.Event()

    def run(self) -> None:
        """Start the webcam loop with error handling and clean shutdown."""
        cap = cv2.VideoCapture(self.camera_id)

        if not cap.isOpened():
            logger.error("Could not open webcam. Is it already in use?")
            return

        logger.info("Webcam active. Press 'q' in the window to stop.")

        window_name = "EasyLend AI Debugger"

        # inference thread
        def infer_loop():
            while not self._stop_event.is_set():
                try:
                    frame = self._frame_q.get(timeout=0.2)
                except Empty:
                    continue
                try:
                    results = self.model.predict(
                        frame, conf=self.conf_threshold, verbose=False
                    )
                    annotated = results[0].plot()
                    with self._annot_lock:
                        self._annotated_frame = annotated
                except Exception:
                    logger.exception("Error during inference")

        th = threading.Thread(target=infer_loop, daemon=True)
        th.start()

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    logger.warning("Empty frame received; waiting...")
                    time.sleep(0.05)
                    continue

                # keep only the latest frame for inference
                try:
                    if self._frame_q.full():
                        _ = self._frame_q.get_nowait()
                    self._frame_q.put_nowait(frame)
                except Exception as e:
                    logger.debug("Frame queue operation failed: %s", e)

                # display latest annotated frame if available
                with self._annot_lock:
                    out = self._annotated_frame
                if out is not None:
                    cv2.imshow(window_name, out)
                else:
                    cv2.imshow(window_name, frame)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    logger.info("Shutdown command received (q).")
                    break

        except KeyboardInterrupt:
            logger.info("Script stopped manually (Ctrl+C in terminal).")
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
        finally:
            logger.info("Releasing webcam and closing windows...")
            self._stop_event.set()
            th.join(timeout=1.0)
            cap.release()
            cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="YOLO webcam tester with model discovery"
    )
    parser.add_argument(
        "--model",
        "-m",
        help="Model name, index, or relative path under runs",
        default=None,
    )
    parser.add_argument(
        "--list", "-l", action="store_true", help="List discovered models and exit"
    )
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="Interactive model selector"
    )
    parser.add_argument("--conf", type=float, default=0.6, help="Confidence threshold")
    parser.add_argument("--camera", type=int, default=0, help="Camera device id")
    args = parser.parse_args()
    # discover models first so we can interactively select
    current_dir = Path(__file__).resolve().parent.parent
    available = discover_models(current_dir)

    if args.list:
        print("Discovered models:")
        for i, (display, cand) in enumerate(available):
            print(f"[{i}] {display} -> {cand}")
        sys.exit(0)

    chosen = args.model
    if args.interactive or (chosen is None and sys.stdin.isatty()):
        if not available:
            print("No models discovered to select from.")
            sys.exit(1)
        print("Select model:")
        for i, (display, cand) in enumerate(available):
            print(f"[{i}] {display}")
        while True:
            sel = input("Enter index or partial name (q to quit): ")
            if sel.lower() in ("q", "quit", "exit"):
                sys.exit(0)
            # try index
            try:
                idx = int(sel)
                if 0 <= idx < len(available):
                    chosen = str(available[idx][0])
                    break
            except (ValueError, TypeError) as e:
                logger.debug("Selection not an index: %s", e)
            # try name match
            matches = [d for d, p in available if sel in d]
            if len(matches) == 1:
                chosen = matches[0]
                break
            elif len(matches) > 1:
                print("Multiple matches:", matches)
            else:
                print("No match, try again")

    tester = YOLOModelTester(
        model_name=chosen, conf_threshold=args.conf, camera_id=args.camera
    )
    tester.run()
