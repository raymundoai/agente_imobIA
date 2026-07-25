from uuid import uuid4

from app.modules.properties.application.use_cases import normalize_property


def test_property_normalization_hashes_url_and_coerces_types() -> None:
    tenant_id = uuid4()
    property_ = normalize_property(
        tenant_id,
        {
            "source": "Portal",
            "source_url": " HTTPS://EXAMPLE.COM/Apto-1 ",
            "title": " Apto 1 ",
            "city": " São Paulo ",
            "price": "750000.50",
            "purpose": "buy",
            "bedrooms": "2",
            "area": "80",
        },
    )

    same = normalize_property(
        tenant_id,
        {
            "source": "Portal",
            "source_url": "https://example.com/apto-1",
            "title": "Outro título",
            "city": "São Paulo",
        },
    )

    assert property_.tenant_id == tenant_id
    assert property_.price is not None
    assert str(property_.price) == "750000.50"
    assert property_.bedrooms == 2
    assert property_.area == 80
    assert property_.content_hash == same.content_hash
