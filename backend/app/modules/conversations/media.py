from __future__ import annotations

import mimetypes
from pathlib import Path
from uuid import UUID, uuid4

from app.shared.errors.exceptions import ApplicationError

ALLOWED_MEDIA_TYPES = {
    "image/jpeg": ("image", ".jpg"),
    "image/png": ("image", ".png"),
    "image/webp": ("image", ".webp"),
    "video/mp4": ("video", ".mp4"),
    "video/webm": ("video", ".webm"),
    "audio/mpeg": ("audio", ".mp3"),
    "audio/mp4": ("audio", ".m4a"),
    "audio/aac": ("audio", ".aac"),
    "audio/wav": ("audio", ".wav"),
    "audio/x-wav": ("audio", ".wav"),
    "audio/ogg": ("audio", ".ogg"),
    "audio/webm": ("audio", ".webm"),
    "application/pdf": ("document", ".pdf"),
    "application/octet-stream": ("document", ".bin"),
    "text/plain": ("document", ".txt"),
    "application/msword": ("document", ".doc"),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        "document",
        ".docx",
    ),
}


def save_conversation_media(
    root: Path,
    tenant_id: UUID,
    conversation_id: UUID,
    *,
    content: bytes,
    content_type: str,
    original_filename: str,
    max_bytes: int,
) -> dict[str, str | int]:
    normalized_type = content_type.split(";", 1)[0].lower().strip()
    definition = ALLOWED_MEDIA_TYPES.get(normalized_type)
    if definition is None:
        raise ApplicationError("Tipo de arquivo não permitido")
    if not content:
        raise ApplicationError("O arquivo está vazio")
    if len(content) > max_bytes:
        raise ApplicationError(f"O arquivo excede o limite de {max_bytes // (1024 * 1024)} MB")
    _validate_signature(content, normalized_type)
    media_type, extension = definition
    safe_name = Path(original_filename or f"arquivo{extension}").name
    if not Path(safe_name).suffix:
        safe_name += extension
    storage_key = f"{tenant_id}/{conversation_id}/{uuid4().hex}{extension}"
    target = (root / storage_key).resolve()
    resolved_root = root.resolve()
    if not target.is_relative_to(resolved_root):
        raise ApplicationError("Caminho de mídia inválido")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return {
        "type": media_type,
        "mimetype": normalized_type,
        "fileName": safe_name,
        "fileLength": len(content),
        "storage_key": storage_key,
    }


def media_path(root: Path, storage_key: str) -> Path:
    target = (root / storage_key).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        raise ApplicationError("Arquivo de mídia não encontrado")
    return target


def media_type_for_filename(filename: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _validate_signature(content: bytes, content_type: str) -> None:
    signatures = {
        "image/jpeg": (b"\xff\xd8\xff",),
        "image/png": (b"\x89PNG\r\n\x1a\n",),
        "image/webp": (b"RIFF",),
        "application/pdf": (b"%PDF-",),
        "audio/ogg": (b"OggS",),
    }
    expected = signatures.get(content_type)
    if expected and not any(content.startswith(signature) for signature in expected):
        raise ApplicationError("O conteúdo do arquivo não corresponde ao tipo informado")
