import httpx

from app.modules.integrations.adapters.telegram import TelegramApiAdapter
from app.modules.integrations.domain.entities import ChannelCredentials


def test_telegram_adapter_normalizes_private_message_and_sends_reply() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/sendMessage")
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 91}})

    adapter = TelegramApiAdapter(httpx.Client(transport=httpx.MockTransport(handler)))
    inbound = adapter.receive_message(
        {
            "update_id": 10,
            "message": {
                "message_id": 90,
                "from": {"id": 123, "first_name": "Maria", "username": "maria"},
                "chat": {"id": 123, "type": "private"},
                "text": "Procuro apartamento em São Paulo",
            },
        }
    )
    assert inbound.external_message_id == "123:90"
    assert inbound.phone == "telegram:123"
    assert inbound.customer_name == "Maria"

    sent = adapter.send_message(
        ChannelCredentials(
            base_url="https://api.telegram.org",
            instance="bot",
            api_key="token",
            webhook_secret="secret",
        ),
        inbound.phone,
        "Olá, Maria!",
    )
    assert sent.external_message_id == "123:91"
