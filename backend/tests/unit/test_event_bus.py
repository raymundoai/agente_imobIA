from uuid import uuid4

from app.shared.events.in_memory import InMemoryEventBus
from app.shared.events.models import DomainEvent


def test_event_bus_dispatches_only_matching_event() -> None:
    bus = InMemoryEventBus()
    received: list[DomainEvent] = []
    bus.subscribe("UserCreated", received.append)

    expected = DomainEvent(name="UserCreated", tenant_id=uuid4())
    bus.publish(DomainEvent(name="TenantCreated", tenant_id=uuid4()))
    bus.publish(expected)

    assert received == [expected]
