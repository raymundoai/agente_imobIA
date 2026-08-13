from __future__ import annotations

import hashlib

import httpx

from app.modules.capture.connectors.auxiliadora_predial import AuxiliadoraPredialConnector
from app.modules.capture.connectors.base import PortalConnector, SourceDescriptor
from app.modules.capture.connectors.bridge import BridgeConnector
from app.modules.capture.connectors.chaves_na_mao import ChavesNaMaoConnector
from app.modules.capture.connectors.dapper import DapperConnector
from app.modules.capture.connectors.delta import DeltaConnector
from app.modules.capture.connectors.foxter import FoxterConnector
from app.modules.capture.connectors.guarida import GuaridaConnector
from app.modules.capture.connectors.imoveis_diferenciados import ImoveisDiferenciadosConnector
from app.modules.capture.connectors.lello import LelloConnector
from app.modules.capture.connectors.lopes import LopesConnector
from app.modules.capture.connectors.nova_sao_paulo import NovaSaoPauloConnector
from app.modules.capture.connectors.ohi import OhiConnector
from app.modules.capture.connectors.quintoandar import QuintoAndarConnector
from app.modules.capture.connectors.rede_gaucha import RedeGauchaConnector
from app.modules.capture.connectors.refugios_urbanos import RefugiosUrbanosConnector
from app.modules.capture.connectors.terramar import TerramarConnector
from app.modules.capture.connectors.urban import UrbanConnector
from app.modules.capture.connectors.vendas_rs import VendasRSConnector
from app.modules.capture.connectors.vila_rica import VilaRicaConnector
from app.modules.capture.connectors.web_discovery import WebDiscoveryConnector
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

    def catalog_version(self, source_ids: list[str]) -> str:
        material = "|".join(
            f"{source_id}:{self.get(source_id).parser_version}"
            for source_id in sorted(source_ids)
        )
        return hashlib.sha256(material.encode()).hexdigest()[:20]


def default_connector_registry(
    client: httpx.Client,
    *,
    web_discovery_enabled: bool = False,
    openai_api_key: str | None = None,
    web_discovery_model: str = "gpt-5.6-luna",
    web_discovery_max_results: int = 6,
    web_discovery_max_output_tokens: int = 4_000,
) -> ConnectorRegistry:
    connectors: list[PortalConnector] = [
        LopesConnector(client),
        LelloConnector(client),
        QuintoAndarConnector(client),
        GuaridaConnector(client),
        FoxterConnector(client),
        BridgeConnector(client),
        ChavesNaMaoConnector(client),
        RefugiosUrbanosConnector(client),
        AuxiliadoraPredialConnector(client),
        NovaSaoPauloConnector(client),
        OhiConnector(client),
        ImoveisDiferenciadosConnector(client),
        UrbanConnector(client),
        DapperConnector(client),
        DeltaConnector(client),
        TerramarConnector(client),
        RedeGauchaConnector(client),
        VendasRSConnector(client),
        VilaRicaConnector(client),
    ]
    if web_discovery_enabled and openai_api_key:
        connectors.append(
            WebDiscoveryConnector(
                client,
                api_key=openai_api_key,
                model=web_discovery_model,
                max_results=web_discovery_max_results,
                max_output_tokens=web_discovery_max_output_tokens,
            )
        )
    return ConnectorRegistry(connectors)
