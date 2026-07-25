from collections import defaultdict

from app.shared.events.models import DomainEvent
from app.shared.events.ports import EventBusPort, EventHandler


class InMemoryEventBus(EventBusPort):
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def publish(self, event: DomainEvent) -> None:
        for handler in tuple(self._handlers[event.name]):
            handler(event)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        self._handlers[event_name].append(handler)
