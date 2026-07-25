import httpx

from app.modules.integrations.adapters.tecimob import TecimobAdapter
from app.modules.integrations.ports.real_estate_platform import (
    PlatformCredentials,
    PlatformLeadData,
)


def test_list_properties_uses_bearer_auth_and_filters() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [{"id": "property-1"}],
                "meta": {"current_page": 2, "per_page": 10, "total": 1},
            },
        )

    adapter = TecimobAdapter(httpx.Client(transport=httpx.MockTransport(handler)))
    credentials = PlatformCredentials(
        base_url="https://api.tecimob.com.br/v1",
        access_token="test-token",
    )

    page = adapter.list_properties(
        credentials,
        page=2,
        per_page=10,
        filters={"filter[transaction]": "venda"},
    )

    assert page.items == [{"id": "property-1"}]
    assert page.page == 2
    assert page.per_page == 10
    assert page.total == 1
    assert requests[0].url.path == "/v1/api/properties"
    assert requests[0].url.params["filter[transaction]"] == "venda"
    assert requests[0].headers["authorization"] == "Bearer test-token"


def test_create_lead_posts_expected_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"data": {"id": "lead-1"}})

    adapter = TecimobAdapter(httpx.Client(transport=httpx.MockTransport(handler)))
    credentials = PlatformCredentials(
        base_url="https://api.tecimob.com.br/v1",
        access_token="test-token",
    )

    lead = adapter.create_lead(
        credentials,
        PlatformLeadData(
            name="Maria Lead",
            phone="5551999999999",
            email="maria@example.com",
            property_ids=["property-1"],
            note="Interesse em apartamento.",
        ),
    )

    assert lead == {"id": "lead-1"}
    assert requests[0].url.path == "/v1/api/leads/store-person"
    assert requests[0].read() == (
        b'{"name":"Maria Lead","email":"maria@example.com",'
        b'"phone_number":"5551999999999","properties_id":["property-1"],'
        b'"note":"Interesse em apartamento."}'
    )
