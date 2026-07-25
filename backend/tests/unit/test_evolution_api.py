import httpx

from app.modules.integrations.adapters.evolution_api import EvolutionApiAdapter
from app.modules.integrations.domain.entities import ChannelCredentials


def test_receive_message_normalizes_evolution_payload() -> None:
    adapter = EvolutionApiAdapter(httpx.Client())
    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "id": "external-1",
                "remoteJid": "5511999999999@s.whatsapp.net",
                "fromMe": False,
            },
            "pushName": "Cliente",
            "message": {"extendedTextMessage": {"text": "Quero comprar"}},
        },
    }

    message = adapter.receive_message(payload)

    assert message.external_message_id == "external-1"
    assert message.phone == "5511999999999"
    assert message.text == "Quero comprar"
    assert message.customer_name == "Cliente"
    assert not message.from_me


def test_send_message_uses_official_endpoint_and_retries_server_error() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(503)
        return httpx.Response(201, json={"key": {"id": "sent-1"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = EvolutionApiAdapter(client, retry_attempts=2, sleeper=lambda _: None)
    credentials = ChannelCredentials(
        base_url="https://evolution.example.com",
        instance="tenant-a",
        api_key="test-api-key",
        webhook_secret="test-webhook-secret",
    )

    sent = adapter.send_message(credentials, "5511999999999", "Resposta humana")

    assert sent.external_message_id == "sent-1"
    assert len(requests) == 2
    assert requests[-1].url.path == "/message/sendText/tenant-a"
    assert requests[-1].headers["apikey"] == "test-api-key"
    assert requests[-1].read() == b'{"number":"5511999999999","text":"Resposta humana"}'


def test_manager_allows_existing_instance_before_connecting() -> None:
    from app.modules.integrations.adapters.evolution_api import EvolutionManagerClient

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/instance/create":
            return httpx.Response(
                403,
                json={
                    "status": 403,
                    "error": "Forbidden",
                    "response": {
                        "message": ['This name "imobia-demo-whatsapp" is already in use.']
                    },
                },
            )
        return httpx.Response(200, json={"base64": "data:image/png;base64,test"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    manager = EvolutionManagerClient(
        client,
        "https://evolution.example.com",
        "test-api-key",
    )

    manager.ensure_instance("imobia-demo-whatsapp", "demo", "secret")
    connected = manager.connect_instance("imobia-demo-whatsapp")

    assert connected["base64"] == "data:image/png;base64,test"
    assert [request.url.path for request in requests] == [
        "/instance/create",
        "/instance/connect/imobia-demo-whatsapp",
    ]
