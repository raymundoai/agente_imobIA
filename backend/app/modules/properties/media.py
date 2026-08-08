from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol
from uuid import UUID, uuid4

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": (".jpg", (b"\xff\xd8\xff",)),
    "image/png": (".png", (b"\x89PNG\r\n\x1a\n",)),
    "image/webp": (".webp", (b"RIFF",)),
}

ALLOWED_VIDEO_TYPES = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
}

ALLOWED_MEDIA_TYPES = {
    **{content_type: extension for content_type, (extension, _) in ALLOWED_IMAGE_TYPES.items()},
    **ALLOWED_VIDEO_TYPES,
}


class PropertyImageProcessor(Protocol):
    def edit_image(self, content: bytes, *, filename: str, prompt: str) -> ImageEditResult: ...


@dataclass(frozen=True, slots=True)
class ImageEditResult:
    content: bytes
    input_image_tokens: int
    input_text_tokens: int
    output_image_tokens: int


@dataclass(frozen=True, slots=True)
class PropertyImageUpload:
    original_name: str
    content_type: str
    content: bytes


class PropertyImageStorage(Protocol):
    def put(self, tenant_id: UUID, key: str, content: bytes, content_type: str) -> None: ...

    def open(self, tenant_id: UUID, key: str) -> BinaryIO: ...

    def delete(self, tenant_id: UUID, key: str) -> None: ...

    def exists(self, tenant_id: UUID, key: str) -> bool: ...

    def signed_url(
        self, tenant_id: UUID, key: str, *, expires_seconds: int = 300
    ) -> str | None: ...


class LocalPropertyImageStorage:
    def __init__(self, root: Path) -> None:
        self._root = root

    @staticmethod
    def build_key(
        tenant_id: UUID,
        property_id: UUID,
        image_id: UUID,
        variant: str,
        content_type: str,
    ) -> str:
        extension = ALLOWED_MEDIA_TYPES[content_type]
        return f"{tenant_id}/{property_id}/{image_id}/{variant}{extension}"

    def _path(self, tenant_id: UUID, key: str) -> Path:
        expected = f"{tenant_id}/"
        if not key.startswith(expected) or ".." in Path(key).parts:
            raise ValueError("Storage key outside tenant scope")
        root = self._root.resolve()
        target = (root / key).resolve()
        if root not in target.parents:
            raise ValueError("Invalid storage key")
        return target

    def put(self, tenant_id: UUID, key: str, content: bytes, content_type: str) -> None:
        if content_type not in ALLOWED_MEDIA_TYPES:
            raise ValueError("Unsupported property media type")
        target = self._path(tenant_id, key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(f"{target.suffix}.{uuid4().hex}.tmp")
        temporary.write_bytes(content)
        os.replace(temporary, target)

    def open(self, tenant_id: UUID, key: str) -> BinaryIO:
        return self._path(tenant_id, key).open("rb")

    def delete(self, tenant_id: UUID, key: str) -> None:
        self._path(tenant_id, key).unlink(missing_ok=True)

    def exists(self, tenant_id: UUID, key: str) -> bool:
        return self._path(tenant_id, key).is_file()

    def signed_url(self, tenant_id: UUID, key: str, *, expires_seconds: int = 300) -> None:
        self._path(tenant_id, key)
        return None

class S3PropertyImageStorage:
    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        region: str | None,
        access_key: str | None,
        secret_key: str | None,
    ) -> None:
        import boto3

        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    @staticmethod
    def _scoped(tenant_id: UUID, key: str) -> str:
        if not key.startswith(f"{tenant_id}/") or ".." in Path(key).parts:
            raise ValueError("Storage key outside tenant scope")
        return key

    def put(self, tenant_id: UUID, key: str, content: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=self._scoped(tenant_id, key),
            Body=content,
            ContentType=content_type,
        )

    def open(self, tenant_id: UUID, key: str) -> BinaryIO:
        return self._client.get_object(
            Bucket=self._bucket, Key=self._scoped(tenant_id, key)
        )["Body"]

    def delete(self, tenant_id: UUID, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=self._scoped(tenant_id, key))

    def exists(self, tenant_id: UUID, key: str) -> bool:
        try:
            self._client.head_object(
                Bucket=self._bucket, Key=self._scoped(tenant_id, key)
            )
        except Exception as exc:
            response = getattr(exc, "response", {})
            if response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return False
            raise
        return True

    def signed_url(self, tenant_id: UUID, key: str, *, expires_seconds: int = 300) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": self._scoped(tenant_id, key)},
            ExpiresIn=expires_seconds,
        )


def validate_property_image(upload: PropertyImageUpload, *, max_bytes: int) -> None:
    if upload.content_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError("Formato não permitido. Envie imagens JPEG, PNG ou WebP.")
    if not upload.content:
        raise ValueError("A imagem enviada está vazia.")
    if len(upload.content) > max_bytes:
        raise ValueError(f"A imagem excede o limite de {max_bytes} bytes.")
    signatures = ALLOWED_IMAGE_TYPES[upload.content_type][1]
    if not any(upload.content.startswith(signature) for signature in signatures):
        raise ValueError("O conteúdo do arquivo não corresponde ao formato informado.")
    if upload.content_type == "image/webp" and upload.content[8:12] != b"WEBP":
        raise ValueError("O conteúdo do arquivo não é uma imagem WebP válida.")


def validate_property_media(
    upload: PropertyImageUpload,
    *,
    max_image_bytes: int,
    max_video_bytes: int,
) -> None:
    if upload.content_type in ALLOWED_IMAGE_TYPES:
        validate_property_image(upload, max_bytes=max_image_bytes)
        return
    if upload.content_type not in ALLOWED_VIDEO_TYPES:
        raise ValueError(
            "Formato não permitido. Envie imagens JPEG, PNG ou WebP, ou vídeos MP4, MOV ou WebM."
        )
    if not upload.content:
        raise ValueError("O vídeo enviado está vazio.")
    if len(upload.content) > max_video_bytes:
        raise ValueError(f"O vídeo excede o limite de {max_video_bytes} bytes.")
    if upload.content_type == "video/webm":
        valid = upload.content.startswith(b"\x1aE\xdf\xa3")
    else:
        valid = len(upload.content) >= 12 and upload.content[4:8] == b"ftyp"
    if not valid:
        raise ValueError("O conteúdo do arquivo não corresponde ao formato de vídeo informado.")


OPTIMIZATION_INSTRUCTIONS = {
    "lighting": "melhorar a iluminação de forma natural",
    "straighten": "corrigir o enquadramento e a perspectiva",
    "visual_organization": "organizar visualmente o ambiente sem remover elementos",
    "walls": "suavizar marcas e pequenas imperfeições nas paredes",
    "windows": "realçar a vista e as janelas sem substituir a paisagem",
    "sharpen": "aumentar a nitidez com aparência natural",
    "remove_furniture": "remover a mobília e deixar o ambiente vazio",
    "add_furniture": "adicionar mobília virtual coerente com o ambiente",
}


def optimization_prompt(optimizations: list[str], note: str | None) -> str:
    requested = ", ".join(
        OPTIMIZATION_INSTRUCTIONS.get(item.strip(), item.strip())
        for item in optimizations
        if item.strip()
    )
    instructions = requested or "melhoria geral de iluminação e nitidez"
    user_request = note.strip() if note and note.strip() else ""
    complement = (
        f" Pedido adicional do usuário (execute-o como parte obrigatória da edição): {user_request}."
        if user_request
        else ""
    )
    normalized_request = user_request.casefold()
    mentions_furniture = any(
        term in normalized_request for term in ("móvel", "móveis", "mobilia", "mobília")
    )
    requests_furniture_change = mentions_furniture and any(
        action in normalized_request
        for action in ("remov", "retir", "elimin", "adicion", "inclu", "coloc")
    )
    furniture_change_requested = bool(
        {"remove_furniture", "add_furniture"}.intersection(optimizations)
        or requests_furniture_change
    )
    element_constraint = (
        "A alteração de mobília foi solicitada; altere somente a mobília, sem modificar elementos estruturais."
        if furniture_change_requested
        else "Não adicione, remova nem invente elementos e preserve a mobília existente."
    )
    return (
        "Edite esta fotografia imobiliária preservando fielmente o imóvel, sua arquitetura, "
        f"materiais fixos e proporções. {element_constraint} Aplique somente: "
        f"{instructions}.{complement}"
    )
