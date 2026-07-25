from abc import ABC, abstractmethod
from collections.abc import Callable

from app.shared.events.models import DomainEvent

EventHandler = Callable[[DomainEvent], None]


class EventBusPort(ABC):
    @abstractmethod
    def publish(self, event: DomainEvent) -> None: ...

    @abstractmethod
    def subscribe(self, event_name: str, handler: EventHandler) -> None: ...
