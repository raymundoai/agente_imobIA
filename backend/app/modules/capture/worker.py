import logging
import signal
import threading

from app.config import get_settings
from app.container import Container
from app.modules.capture.processor import CaptureJobProcessor


def main() -> None:
    container = Container.build(get_settings())
    processor = CaptureJobProcessor(container)
    logging.basicConfig(level=container.settings.log_level)
    stopping = threading.Event()
    logger = logging.getLogger(__name__)

    def stop(_: int, __: object) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not stopping.is_set():
            try:
                result = processor.process_next()
            except Exception:
                logger.exception("Capture worker survived an unexpected processor error")
                stopping.wait(1)
                continue
            if result is None:
                stopping.wait(1)
            else:
                logger.info("Capture job processed: %s", result)
    finally:
        container.close()


if __name__ == "__main__":
    main()
