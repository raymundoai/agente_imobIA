import logging
import signal
import threading

from app.config import get_settings
from app.container import Container
from app.modules.capture.processor import CaptureJobProcessor
from app.modules.contacts import models as contact_models  # noqa: F401
from app.modules.conversations.adapters import models as conversation_models  # noqa: F401
from app.modules.properties.adapters import models as property_models  # noqa: F401
from app.modules.users.adapters import models as user_models  # noqa: F401


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
