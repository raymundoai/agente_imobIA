import logging
import signal
import threading

from app.config import get_settings
from app.container import Container
from app.modules.messaging.processor import MessageJobProcessor


def main() -> None:
    container = Container.build(get_settings())
    processor = MessageJobProcessor(container)
    logging.basicConfig(level=container.settings.log_level)
    stopping = threading.Event()

    def stop(_: int, __: object) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not stopping.is_set():
            if processor.process_next() is None:
                stopping.wait(1)
    finally:
        container.close()


if __name__ == "__main__":
    main()
