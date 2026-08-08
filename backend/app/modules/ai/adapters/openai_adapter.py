import base64
import json
from io import BytesIO
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from app.modules.ai.domain.ports import (
    AiProviderDispatchUncertainError,
    AiProviderPort,
    AiProviderRejectedError,
    AiProviderResponse,
    AiToolCall,
)
from app.modules.properties.media import ImageEditResult


class OpenAiAdapter(AiProviderPort):
    def __init__(
        self,
        *,
        api_key: str,
        chat_model: str,
        embedding_model: str,
        chat_reasoning_effort: str = "none",
        chat_max_output_tokens: int = 4_000,
        embedding_dimensions: int = 1536,
        image_model: str = "gpt-image-2",
        transcription_model: str = "gpt-4o-mini-transcribe",
        vision_model: str | None = None,
        client: OpenAI | None = None,
    ) -> None:
        self._client = client or OpenAI(api_key=api_key, max_retries=0)
        self._chat_model = chat_model
        self._chat_reasoning_effort = chat_reasoning_effort
        self._chat_max_output_tokens = chat_max_output_tokens
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._image_model = image_model
        self._transcription_model = transcription_model
        self._vision_model = vision_model or chat_model

    def transcribe_audio(
        self, content: bytes, *, filename: str, content_type: str
    ) -> str:
        audio = BytesIO(content)
        audio.name = filename
        try:
            response = self._client.audio.transcriptions.create(
                model=self._transcription_model,
                file=audio,
                response_format="text",
            )
        except (APIConnectionError, APITimeoutError) as exc:
            raise AiProviderDispatchUncertainError(
                "OpenAI transcription dispatch is uncertain"
            ) from exc
        except APIStatusError as exc:
            if exc.status_code < 500:
                raise AiProviderRejectedError("OpenAI rejected the transcription") from exc
            raise AiProviderDispatchUncertainError(
                "OpenAI transcription dispatch is uncertain"
            ) from exc
        text = response if isinstance(response, str) else getattr(response, "text", "")
        return str(text or "").strip()

    def describe_image(self, content: bytes, *, content_type: str) -> str:
        encoded = base64.b64encode(content).decode("ascii")
        prompt = (
            "Descreva objetivamente esta imagem para um atendimento imobiliário. "
            "Identifique textos visíveis, tipo de documento e características aparentes "
            "do imóvel, cômodos ou possíveis danos. Não identifique pessoas e não conclua "
            "endereço, propriedade, autenticidade, preço, metragem ou condição jurídica."
        )
        try:
            response = self._client.responses.create(
                model=self._vision_model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt},
                            {
                                "type": "input_image",
                                "image_url": f"data:{content_type};base64,{encoded}",
                            },
                        ],
                    }
                ],
                reasoning={"effort": self._chat_reasoning_effort},
                max_output_tokens=800,
            )
        except (APIConnectionError, APITimeoutError) as exc:
            raise AiProviderDispatchUncertainError(
                "OpenAI vision dispatch is uncertain"
            ) from exc
        except APIStatusError as exc:
            if exc.status_code < 500:
                raise AiProviderRejectedError("OpenAI rejected the image analysis") from exc
            raise AiProviderDispatchUncertainError(
                "OpenAI vision dispatch is uncertain"
            ) from exc
        description = str(
            getattr(response, "output_text", "") or self._extract_text(response)
        ).strip()
        if not description:
            raise RuntimeError("OpenAI did not return an image description")
        return description

    def edit_image(self, content: bytes, *, filename: str, prompt: str) -> ImageEditResult:
        image = BytesIO(content)
        image.name = filename
        try:
            response = self._client.images.edit(
                model=self._image_model,
                image=image,
                prompt=prompt,
                quality="medium",
                size="1024x1024",
            )
        except (APIConnectionError, APITimeoutError) as exc:
            raise AiProviderDispatchUncertainError("OpenAI image dispatch is uncertain") from exc
        except APIStatusError as exc:
            if exc.status_code < 500:
                raise AiProviderRejectedError("OpenAI rejected the image request") from exc
            raise AiProviderDispatchUncertainError("OpenAI image dispatch is uncertain") from exc
        data = response.data[0]
        encoded = getattr(data, "b64_json", None)
        if not encoded:
            raise RuntimeError("OpenAI did not return the processed image content")
        usage = getattr(response, "usage", None)
        input_details = getattr(usage, "input_tokens_details", None)
        input_image_tokens = int(getattr(input_details, "image_tokens", 0) or 0)
        input_text_tokens = int(getattr(input_details, "text_tokens", 0) or 0)
        output_image_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        if input_image_tokens + input_text_tokens + output_image_tokens <= 0:
            raise RuntimeError("OpenAI did not return image token usage")
        return ImageEditResult(
            content=base64.b64decode(encoded),
            input_image_tokens=input_image_tokens,
            input_text_tokens=input_text_tokens,
            output_image_tokens=output_image_tokens,
        )

    def get_embedding(self, text: str) -> list[float]:
        normalized = text.replace("\n", " ").strip()
        if not normalized:
            normalized = " "
        try:
            response = self._client.embeddings.create(
                model=self._embedding_model,
                input=normalized,
                dimensions=self._embedding_dimensions,
                encoding_format="float",
            )
        except (APIConnectionError, APITimeoutError) as exc:
            raise AiProviderDispatchUncertainError(
                "OpenAI embedding dispatch is uncertain"
            ) from exc
        except APIStatusError as exc:
            if exc.status_code < 500:
                raise AiProviderRejectedError("OpenAI rejected the embedding request") from exc
            raise AiProviderDispatchUncertainError(
                "OpenAI embedding dispatch is uncertain"
            ) from exc
        return list(response.data[0].embedding)

    def chat_completion(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
    ) -> AiProviderResponse:
        try:
            response = self._client.responses.create(
                model=self._chat_model,
                instructions=system_prompt,
                input=self._responses_input(messages),
                tools=tools,
                parallel_tool_calls=False,
                reasoning={"effort": self._chat_reasoning_effort},
                max_output_tokens=self._chat_max_output_tokens,
            )
        except (APIConnectionError, APITimeoutError) as exc:
            raise AiProviderDispatchUncertainError("OpenAI chat dispatch is uncertain") from exc
        except APIStatusError as exc:
            if exc.status_code < 500:
                raise AiProviderRejectedError("OpenAI rejected the chat request") from exc
            raise AiProviderDispatchUncertainError("OpenAI chat dispatch is uncertain") from exc
        return AiProviderResponse(
            text=getattr(response, "output_text", "") or self._extract_text(response),
            model=getattr(response, "model", self._chat_model),
            tokens_used=self._tokens_used(response),
            input_tokens=self._usage_value(response, "input_tokens"),
            cached_input_tokens=self._cached_input_tokens(response),
            output_tokens=self._usage_value(response, "output_tokens"),
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

    @staticmethod
    def _usage_value(response: Any, name: str) -> int:
        usage = getattr(response, "usage", None)
        return int(getattr(usage, name, 0) or 0) if usage is not None else 0

    @staticmethod
    def _cached_input_tokens(response: Any) -> int:
        usage = getattr(response, "usage", None)
        details = getattr(usage, "input_tokens_details", None) if usage is not None else None
        return int(getattr(details, "cached_tokens", 0) or 0) if details is not None else 0
