from types import SimpleNamespace

from app.modules.ai.adapters.openai_adapter import OpenAiAdapter


class _Embeddings:
    def create(self, **kwargs):
        assert kwargs["model"] == "text-embedding-3-small"
        assert kwargs["dimensions"] == 1536
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])])


class _Responses:
    def create(self, **kwargs):
        assert kwargs["model"] == "gpt-5.5"
        assert kwargs["parallel_tool_calls"] is False
        return SimpleNamespace(
            model="gpt-5.5",
            output_text="",
            usage=SimpleNamespace(input_tokens=7, output_tokens=5),
            output=[
                SimpleNamespace(
                    type="function_call",
                    name="search_knowledge_base",
                    arguments='{"query":"boleto"}',
                    call_id="call-1",
                )
            ],
        )


class _Client:
    embeddings = _Embeddings()
    responses = _Responses()


def test_openai_adapter_get_embedding_and_function_calls() -> None:
    adapter = OpenAiAdapter(
        api_key="test",
        chat_model="gpt-5.5",
        embedding_model="text-embedding-3-small",
        client=_Client(),
    )

    assert adapter.get_embedding("abc") == [0.1, 0.2, 0.3]
    response = adapter.chat_completion(
        system_prompt="s", messages=[{"role": "user", "content": "oi"}], tools=[]
    )

    assert response.tokens_used == 12
    assert response.tool_calls is not None
    assert response.tool_calls[0].name == "search_knowledge_base"
    assert response.tool_calls[0].arguments == {"query": "boleto"}
