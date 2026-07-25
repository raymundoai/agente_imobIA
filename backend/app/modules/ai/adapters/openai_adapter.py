import base64
import json
from io import BytesIO
from typing import Any

from openai import OpenAI

from app.modules.ai.domain.ports import AiProviderPort, AiProviderResponse, AiToolCall


class OpenAiAdapter(AiProviderPort):
    def __init__(
        self,
        *,
        api_key: str,
        chat_model: str,
        embedding_model: str,
        embedding_dimensions: int = 1536,
        image_model: str = "gpt-image-1",
        client: OpenAI | None = None,
    ) -> None:
        self._client = client or OpenAI(api_key=api_key)
        self._chat_model = chat_model
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._image_model = image_model

    def edit_image(self, content: bytes, *, filename: str, prompt: str) -> bytes:
        image = BytesIO(content)
        image.name = filename
        response = self._client.images.edit(
            model=self._image_model,
            image=image,
            prompt=prompt,
        )
        data = response.data[0]
        encoded = getattr(data, "b64_json", None)
        if not encoded:
            raise RuntimeError("OpenAI did not return the processed image content")
        return base64.b64decode(encoded)

    def get_embedding(self, text: str) -> list[float]:
        normalized = text.replace("\n", " ").strip()
        if not normalized:
            normalized = " "
        response = self._client.embeddings.create(
            model=self._embedding_model,
            input=normalized,
            dimensions=self._embedding_dimensions,
            encoding_format="float",
        )
        return list(response.data[0].embedding)

    def chat_completion(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
    ) -> AiProviderResponse:
        response = self._client.responses.create(
            model=self._chat_model,
            instructions=system_prompt,
            input=self._responses_input(messages),
            tools=tools,
            parallel_tool_calls=False,
        )
        return AiProviderResponse(
            text=getattr(response, "output_text", "") or self._extract_text(response),
            model=getattr(response, "model", self._chat_model),
            tokens_used=self._tokens_used(response),
            tool_calls=self._tool_calls(response),
        )

    @staticmethod
    def _responses_input(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role", "user")
            if role == "tool":
                converted.append(
                    {
                        "role": "user",
                        "content": (
                            f"Resultado da ferramenta {message.get('name', 'tool')}: "
                            f"{message.get('content', '')}"
                        ),
                    }
                )
            else:
                converted.append({"role": role, "content": message.get("content", "")})
        return converted

    @staticmethod
    def _tool_calls(response: Any) -> list[AiToolCall]:
        calls: list[AiToolCall] = []
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) != "function_call":
                continue
            raw_arguments = getattr(item, "arguments", "{}") or "{}"
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                arguments = {}
            calls.append(
                AiToolCall(
                    name=getattr(item, "name", ""),
                    arguments=arguments,
                    call_id=getattr(item, "call_id", None),
                )
            )
        return calls

    @staticmethod
    def _extract_text(response: Any) -> str:
        parts: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    parts.append(text)
        return "\n".join(parts)

    @staticmethod
    def _tokens_used(response: Any) -> int:
        usage = getattr(response, "usage", None)
        if usage is None:
            return 0
        return int(
            getattr(usage, "total_tokens", 0)
            or (getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0))
        )
