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
        extension = ALLOWED_IMAGE_TYPES[content_type][0]
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
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise ValueError("Unsupported image type")
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


def optimization_prompt(optimizations: list[str], note: str | None) -> str:
    requested = ", ".join(item.strip() for item in optimizations if item.strip())
    instructions = requested or "melhoria geral de iluminação e nitidez"
    complement = f" Observação do usuário: {note.strip()}." if note and note.strip() else ""
    return (
        "Edite esta fotografia imobiliária preservando fielmente o imóvel, sua arquitetura, "
        "móveis e proporções. Não adicione, remova nem invente elementos. Aplique somente: "
        f"{instructions}.{complement}"
    )
