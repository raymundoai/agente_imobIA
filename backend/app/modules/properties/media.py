from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": (".jpg", (b"\xff\xd8\xff",)),
    "image/png": (".png", (b"\x89PNG\r\n\x1a\n",)),
    "image/webp": (".webp", (b"RIFF",)),
}


class PropertyImageProcessor(Protocol):
    def edit_image(self, content: bytes, *, filename: str, prompt: str) -> bytes: ...


@dataclass(frozen=True, slots=True)
class PropertyImageUpload:
    original_name: str
    content_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class StoredPropertyImage:
    url: str
    original_name: str
    content_type: str
    size: int
    optimized: bool


class LocalPropertyImageStorage:
    def __init__(self, root: Path, *, url_prefix: str = "/media/properties") -> None:
        self._root = root
        self._url_prefix = url_prefix.rstrip("/")

    def save(
        self,
        tenant_id: UUID,
        upload: PropertyImageUpload,
        *,
        optimized: bool,
    ) -> StoredPropertyImage:
        extension = ALLOWED_IMAGE_TYPES[upload.content_type][0]
        filename = f"{uuid4().hex}{extension}"
        tenant_directory = self._root / str(tenant_id)
        tenant_directory.mkdir(parents=True, exist_ok=True)
        target = tenant_directory / filename
        temporary = target.with_suffix(f"{target.suffix}.tmp")
        temporary.write_bytes(upload.content)
        os.replace(temporary, target)
        return StoredPropertyImage(
            url=f"{self._url_prefix}/{tenant_id}/{filename}",
            original_name=upload.original_name,
            content_type=upload.content_type,
            size=len(upload.content),
            optimized=optimized,
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
