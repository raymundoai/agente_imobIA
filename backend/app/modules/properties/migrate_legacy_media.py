from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import UUID

from sqlalchemy import select

from app.config import get_settings
from app.container import Container
from app.modules.properties.adapters.models import PropertyImageModel
from app.modules.properties.media import PropertyImageUpload, validate_property_image


def _safe_legacy_path(root: Path, tenant_id: UUID, key: str) -> Path:
    if not key.startswith(f"{tenant_id}/") or ".." in Path(key).parts:
        raise ValueError("legacy key outside tenant scope")
    resolved_root = root.resolve()
    target = (resolved_root / key).resolve()
    if resolved_root not in target.parents:
        raise ValueError("legacy path outside configured root")
    return target


def _legacy_key(image: PropertyImageModel) -> str | None:
    if image.original_storage_key:
        return image.original_storage_key
    parsed = urlparse(image.legacy_url or "")
    prefix = "/media/properties/"
    if parsed.scheme or parsed.netloc or not parsed.path.startswith(prefix):
        return None
    return unquote(parsed.path[len(prefix) :])


def migrate(container: Container) -> dict[str, int]:
    root = container.settings.property_media_legacy_root
    if root is None:
        raise RuntimeError("PROPERTY_MEDIA_LEGACY_ROOT must be configured")
    migrated = skipped = missing = invalid = 0
    with container.database.session_factory() as session:
        images = session.scalars(
            select(PropertyImageModel).where(
                PropertyImageModel.legacy_url.is_not(None),
                PropertyImageModel.derived_storage_key.is_(None),
            )
        ).all()
        for image in images:
            key = _legacy_key(image)
            if key is None:
                invalid += 1
                continue
            try:
                source = _safe_legacy_path(root, image.tenant_id, key)
            except ValueError:
                invalid += 1
                continue
            if not source.is_file():
                missing += 1
                continue
            if container.property_image_storage.exists(image.tenant_id, key):
                skipped += 1
            else:
                content_type = (
                    image.original_content_type
                    if image.original_content_type.startswith("image/")
                    else mimetypes.guess_type(source.name)[0] or "application/octet-stream"
                )
                if not content_type.startswith("image/"):
                    invalid += 1
                    continue
                content = source.read_bytes()
                try:
                    validate_property_image(
                        PropertyImageUpload(source.name, content_type, content),
                        max_bytes=container.settings.property_image_max_bytes,
                    )
                except ValueError:
                    invalid += 1
                    continue
                container.property_image_storage.put(
                    image.tenant_id, key, content, content_type
                )
                image.original_content_type = content_type
                image.original_size = len(content)
                migrated += 1
            image.original_storage_key = key
        session.commit()
    return {
        "migrated": migrated,
        "skipped": skipped,
        "missing": missing,
        "invalid": invalid,
    }


def main() -> None:
    container = Container.build(get_settings())
    try:
        print(migrate(container))
    finally:
        container.close()


if __name__ == "__main__":
    main()
