from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError, BadRequestError

from app.modules.ai.adapters.openai_adapter import OpenAiAdapter
from app.modules.ai.domain.ports import (
    AiProviderDispatchUncertainError,
    AiProviderRejectedError,
)


def _adapter(error: Exception) -> OpenAiAdapter:
    def fail(**kwargs):
        raise error

    client = SimpleNamespace(
        responses=SimpleNamespace(create=fail),
        embeddings=SimpleNamespace(create=fail),
        images=SimpleNamespace(edit=fail),
    )
    return OpenAiAdapter(
        api_key="unused",
        chat_model="gpt-5.4-mini",
        embedding_model="text-embedding-3-small",
        client=client,
    )


def test_openai_4xx_is_definitively_rejected() -> None:
    response = httpx.Response(
        400,
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
    )
    error = BadRequestError("invalid", response=response, body={})
    with pytest.raises(AiProviderRejectedError):
        _adapter(error).chat_completion(system_prompt="x", messages=[], tools=[])


def test_openai_transport_failure_is_dispatch_uncertain() -> None:
    error = APIConnectionError(
        request=httpx.Request("POST", "https://api.openai.com/v1/responses")
    )
    with pytest.raises(AiProviderDispatchUncertainError):
        _adapter(error).chat_completion(system_prompt="x", messages=[], tools=[])


def test_openai_sdk_is_created_with_retries_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(
        "app.modules.ai.adapters.openai_adapter.OpenAI",
        fake_openai,
    )
    OpenAiAdapter(
        api_key="key",
        chat_model="gpt-5.4-mini",
        embedding_model="text-embedding-3-small",
    )
    assert captured["max_retries"] == 0
