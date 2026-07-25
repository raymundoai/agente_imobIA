from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.properties.media import (
    LocalPropertyImageStorage,
    PropertyImageUpload,
    optimization_prompt,
    validate_property_image,
)


def test_local_property_image_storage_scopes_file_by_tenant(tmp_path: Path) -> None:
    tenant_id = uuid4()
    property_id = uuid4()
    image_id = uuid4()
    upload = PropertyImageUpload(
        original_name="../../fachada.png",
        content_type="image/png",
        content=b"\x89PNG\r\n\x1a\ncontent",
    )
    storage = LocalPropertyImageStorage(tmp_path)
    key = storage.build_key(
        tenant_id, property_id, image_id, "original", upload.content_type
    )
    storage.put(tenant_id, key, upload.content, upload.content_type)

    with storage.open(tenant_id, key) as stored:
        assert stored.read() == upload.content


def test_property_image_validation_rejects_spoofed_mime_and_size() -> None:
    with pytest.raises(ValueError, match="não corresponde"):
        validate_property_image(
            PropertyImageUpload("fake.png", "image/png", b"not-png"), max_bytes=100
        )
    with pytest.raises(ValueError, match="excede"):
        validate_property_image(
            PropertyImageUpload("large.png", "image/png", b"\x89PNG\r\n\x1a\n" + b"x" * 20),
            max_bytes=10,
        )


def test_optimization_prompt_forbids_inventing_property_elements() -> None:
    prompt = optimization_prompt(["corrigir iluminação"], "manter cores naturais")
    assert "Não adicione, remova nem invente elementos" in prompt
    assert "corrigir iluminação" in prompt
    assert "manter cores naturais" in prompt
