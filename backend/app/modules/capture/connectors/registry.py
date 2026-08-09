from __future__ import annotations

import httpx

from app.modules.capture.connectors.base import PortalConnector, SourceDescriptor
from app.modules.capture.connectors.bridge import BridgeConnector
from app.modules.capture.connectors.chaves_na_mao import ChavesNaMaoConnector
from app.modules.capture.connectors.foxter import FoxterConnector
from app.modules.capture.connectors.guarida import GuaridaConnector
from app.modules.capture.connectors.lello import LelloConnector
from app.modules.capture.connectors.lopes import LopesConnector
from app.modules.capture.connectors.quintoandar import QuintoAndarConnector
from app.modules.capture.connectors.refugios_urbanos import RefugiosUrbanosConnector
from app.modules.leads.domain.entities import LeadDemand


class ConnectorRegistry:
    def __init__(self, connectors: list[PortalConnector]) -> None:
        self._connectors = {connector.descriptor.id: connector for connector in connectors}

    def get(self, source_id: str) -> PortalConnector:
        try:
            return self._connectors[source_id]
        except KeyError as exc:
            raise ValueError(f"Unknown capture source: {source_id}") from exc

    def available_for(self, demand: LeadDemand) -> list[SourceDescriptor]:
        return [
            connector.descriptor
            for connector in self._connectors.values()
            if connector.supports(demand)
        ]

    def descriptors(self) -> list[SourceDescriptor]:
        return [connector.descriptor for connector in self._connectors.values()]


def default_connector_registry(client: httpx.Client) -> ConnectorRegistry:
    return ConnectorRegistry(
        [
            LopesConnector(client),
            LelloConnector(client),
            QuintoAndarConnector(client),
            GuaridaConnector(client),
            FoxterConnector(client),
            BridgeConnector(client),
            ChavesNaMaoConnector(client),
            RefugiosUrbanosConnector(client),
        ]
    )
