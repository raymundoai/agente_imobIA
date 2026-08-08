from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.properties.media import (
    LocalPropertyImageStorage,
    PropertyImageUpload,
    optimization_prompt,
    validate_property_image,
    validate_property_media,
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


def test_property_media_validation_accepts_video_and_rejects_spoofed_content() -> None:
    mp4 = PropertyImageUpload(
        "tour.mp4",
        "video/mp4",
        b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isom",
    )
    validate_property_media(mp4, max_image_bytes=100, max_video_bytes=100)

    with pytest.raises(ValueError, match="formato de vídeo"):
        validate_property_media(
            PropertyImageUpload("tour.mp4", "video/mp4", b"not-video"),
            max_image_bytes=100,
            max_video_bytes=100,
        )
def test_optimization_prompt_forbids_inventing_property_elements() -> None:
    prompt = optimization_prompt(["corrigir iluminação"], "manter cores naturais")
    assert "Não adicione, remova nem invente elementos" in prompt
    assert "corrigir iluminação" in prompt
    assert "manter cores naturais" in prompt


def test_optimization_prompt_honors_furniture_removal_option() -> None:
    prompt = optimization_prompt(["remove_furniture"], None)
    assert "remover a mobília e deixar o ambiente vazio" in prompt
    assert "A alteração de mobília foi solicitada" in prompt
    assert "preserve a mobília existente" not in prompt


def test_optimization_prompt_prioritizes_custom_furniture_request() -> None:
    prompt = optimization_prompt([], "Remover todos os móveis")
    assert "execute-o como parte obrigatória" in prompt
    assert "Remover todos os móveis" in prompt
    assert "A alteração de mobília foi solicitada" in prompt
