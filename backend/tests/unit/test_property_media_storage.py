import io
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.properties.media import LocalPropertyImageStorage, S3PropertyImageStorage


def test_local_storage_is_tenant_scoped_and_round_trips(tmp_path) -> None:
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    property_id = uuid4()
    image_id = uuid4()
    storage = LocalPropertyImageStorage(tmp_path)
    key = storage.build_key(tenant_id, property_id, image_id, "original", "image/png")

    storage.put(tenant_id, key, b"\x89PNG\r\n\x1a\ncontent", "image/png")

    with storage.open(tenant_id, key) as stream:
        assert stream.read() == b"\x89PNG\r\n\x1a\ncontent"
    with pytest.raises(ValueError, match="tenant scope"):
        storage.open(other_tenant_id, key)
    with pytest.raises(ValueError):
        storage.open(tenant_id, f"{tenant_id}/../secret")


def test_s3_storage_uses_private_object_and_presigned_url(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    class FakeClient:
        def put_object(self, **kwargs):
            calls.append(("put", kwargs))

        def get_object(self, **kwargs):
            return {"Body": io.BytesIO(b"stored")}

        def delete_object(self, **kwargs):
            calls.append(("delete", kwargs))

        def head_object(self, **kwargs):
            calls.append(("head", kwargs))

        def generate_presigned_url(self, operation, *, Params, ExpiresIn):
            calls.append((operation, {"Params": Params, "ExpiresIn": ExpiresIn}))
            return "https://storage.example/signed"

    monkeypatch.setitem(
        sys.modules, "boto3", SimpleNamespace(client=lambda *args, **kwargs: FakeClient())
    )
    tenant_id = uuid4()
    key = f"{tenant_id}/property/image/original.png"
    storage = S3PropertyImageStorage(
        bucket="private-media",
        endpoint_url="https://s3.example",
        region="us-east-1",
        access_key="key",
        secret_key="secret",
    )

    storage.put(tenant_id, key, b"image", "image/png")
    assert storage.exists(tenant_id, key)
    assert storage.signed_url(tenant_id, key) == "https://storage.example/signed"
    assert calls[0][1]["Bucket"] == "private-media"
    assert "ACL" not in calls[0][1]
    with pytest.raises(ValueError, match="tenant scope"):
        storage.signed_url(uuid4(), key)
