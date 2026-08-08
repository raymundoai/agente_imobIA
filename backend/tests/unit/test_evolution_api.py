import httpx
import pytest

from app.modules.conversations.application.use_cases import whatsapp_phones_match
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


def test_receive_message_normalizes_sticker() -> None:
    adapter = EvolutionApiAdapter(httpx.Client())
    message = adapter.receive_message(
        {
            "event": "messages.upsert",
            "data": {
                "key": {
                    "id": "sticker-1",
                    "remoteJid": "5511999999999@s.whatsapp.net",
                    "fromMe": False,
                },
                "message": {
                    "stickerMessage": {
                        "mimetype": "image/webp",
                        "url": "https://cdn.example.com/sticker.webp",
                        "isAnimated": False,
                    }
                },
            },
        }
    )

    assert message.text == ""
    assert message.attachments == [
        {
            "type": "sticker",
            "mimetype": "image/webp",
            "url": "https://cdn.example.com/sticker.webp",
            "isAnimated": False,
        }
    ]


def test_receive_group_message_preserves_group_and_participant_identity() -> None:
    adapter = EvolutionApiAdapter(httpx.Client())
    message = adapter.receive_message(
        {
            "event": "messages.upsert",
            "data": {
                "key": {
                    "id": "group-message-1",
                    "remoteJid": "120363419697103562@g.us",
                    "fromMe": False,
                    "participant": "5551999999999@s.whatsapp.net",
                    "participantAlt": "123456789@lid",
                },
                "pushName": "Corretor João",
                "groupName": "Equipe de vendas",
                "message": {"conversation": "Novo imóvel captado"},
            },
        }
    )

    assert message.is_group
    assert message.external_contact_id == "120363419697103562@g.us"
    assert message.phone == "120363419697103562"
    assert message.conversation_name == "Equipe de vendas"
    assert message.sender_external_id == "5551999999999@s.whatsapp.net"
    assert message.sender_name == "Corretor João"


def test_resolve_group_name_fetches_and_caches_group_catalog() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {"id": "120363424428788822@g.us", "subject": "Grupo de corretores"}
            ],
        )

    adapter = EvolutionApiAdapter(httpx.Client(transport=httpx.MockTransport(handler)))
    credentials = ChannelCredentials(
        base_url="https://evolution.example",
        instance="imobia-demo-whatsapp",
        api_key="test-key",
        webhook_secret="test-secret",
    )

    first = adapter.resolve_group_name(credentials, "120363424428788822@g.us")
    second = adapter.resolve_group_name(credentials, "120363424428788822@g.us")

    assert first == "Grupo de corretores"
    assert second == "Grupo de corretores"
    assert len(requests) == 1


def test_receive_lid_message_prefers_phone_jid_alternative() -> None:
    adapter = EvolutionApiAdapter(httpx.Client())
    message = adapter.receive_message(
        {
            "event": "messages.upsert",
            "data": {
                "key": {
                    "id": "lid-message-1",
                    "remoteJid": "232134862233733@lid",
                    "remoteJidAlt": "5511966662222@s.whatsapp.net",
                    "fromMe": True,
                },
                "message": {"conversation": "Mensagem do celular"},
            },
        }
    )

    assert message.external_contact_id == "5511966662222@s.whatsapp.net"
    assert message.phone == "5511966662222"
    assert message.from_me


def test_brazilian_whatsapp_numbers_match_with_country_and_ninth_digit_variations() -> None:
    assert whatsapp_phones_match("555191129452", "51991129452")
    assert whatsapp_phones_match("551199999999", "11999999999")
    assert not whatsapp_phones_match("555191129452", "51988887777")


def test_send_message_does_not_retry_ambiguous_server_error() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = EvolutionApiAdapter(client, retry_attempts=2, sleeper=lambda _: None)
    credentials = ChannelCredentials(
        base_url="https://evolution.example.com",
        instance="tenant-a",
        api_key="test-api-key",
        webhook_secret="test-webhook-secret",
    )

    with pytest.raises(Exception, match="uncertain"):
        adapter.send_message(
            credentials,
            "5511999999999",
            "Resposta humana",
            idempotency_key="job-123",
        )

    assert len(requests) == 1
    assert requests[-1].url.path == "/message/sendText/tenant-a"
    assert requests[-1].headers["apikey"] == "test-api-key"
    assert requests[-1].headers["idempotency-key"] == "job-123"
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


def test_manager_places_webhook_secret_in_header_not_query() -> None:
    from app.modules.integrations.adapters.evolution_api import EvolutionManagerClient

    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    manager = EvolutionManagerClient(
        client,
        "https://evolution.example.com",
        "api-key",
        "https://api.imobia.example",
    )
    manager.configure_webhook("instance", "tenant-a", "top-secret")

    request = captured[0]
    payload = request.read().decode()
    assert "?token=" not in payload
    assert '"url":"https://api.imobia.example/webhooks/whatsapp/tenant-a"' in payload
    assert '"X-ImobIA-Webhook-Secret":"top-secret"' in payload


def test_manager_fetches_instance_owner_identity() -> None:
    from app.modules.integrations.adapters.evolution_api import EvolutionManagerClient

    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "instance": {
                        "instanceName": "instance",
                        "ownerJid": "5511999999999@s.whatsapp.net",
                    }
                }
            ],
        )

    manager = EvolutionManagerClient(
        httpx.Client(transport=httpx.MockTransport(handler)),
        "https://evolution.example.com",
        "api-key",
    )

    result = manager.instance_info("instance")

    assert result["data"][0]["instance"]["ownerJid"] == "5511999999999@s.whatsapp.net"
    assert captured[0].url.params["instanceName"] == "instance"
