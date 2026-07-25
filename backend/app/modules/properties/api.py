import json
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.billing_usage.service import CreditLedgerService, image_token_charge
from app.modules.properties.adapters.repositories import SqlAlchemyPropertyRepository
from app.modules.properties.application.use_cases import ListPropertiesUseCase
from app.modules.properties.domain.entities import Property, PropertyPurpose
from app.modules.properties.media import (
    LocalPropertyImageStorage,
    PropertyImageUpload,
    optimization_prompt,
    validate_property_image,
)

router = APIRouter(prefix="/properties", tags=["properties"])


class PropertyResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    source: str
    source_url: str | None
    title: str
    city: str
    neighborhood: str | None
    price: Decimal | None
    sale_price: Decimal | None
    rent_price: Decimal | None
    purpose: str | None
    property_type: str | None
    category: str
    status: str
    listing_code: str | None
    description: str | None
    bedrooms: int | None
    suites: int | None
    bathrooms: int | None
    parking_spaces: int | None
    area: int | None
    land_area: int | None
    address: dict[str, Any]
    details: dict[str, Any]
    images: list[dict[str, Any]]
    advertiser_name: str | None
    advertiser_phone: str | None
    via_extension: bool

    @classmethod
    def from_domain(cls, property_: Property) -> "PropertyResponse":
        return cls(
            id=property_.id,
            tenant_id=property_.tenant_id,
            source=property_.source,
            source_url=property_.source_url,
            title=property_.title,
            city=property_.city,
            neighborhood=property_.neighborhood,
            price=property_.price,
            sale_price=property_.sale_price,
            rent_price=property_.rent_price,
            purpose=property_.purpose.value if property_.purpose else None,
            property_type=property_.property_type,
            category=property_.category,
            status=property_.status,
            listing_code=property_.listing_code,
            description=property_.description,
            bedrooms=property_.bedrooms,
            suites=property_.suites,
            bathrooms=property_.bathrooms,
            parking_spaces=property_.parking_spaces,
            area=property_.area,
            land_area=property_.land_area,
            address=property_.address,
            details=property_.details,
            images=property_.images,
            advertiser_name=property_.advertiser_name,
            advertiser_phone=property_.advertiser_phone,
            via_extension=property_.via_extension,
        )


class PropertyAddressRequest(BaseModel):
    street: str = Field(min_length=1, max_length=255)
    number: str | None = Field(default=None, max_length=40)
    complement: str | None = Field(default=None, max_length=120)
    neighborhood: str = Field(min_length=1, max_length=120)
    city: str = Field(min_length=1, max_length=120)
    state: str = Field(min_length=2, max_length=2)
    postal_code: str | None = Field(default=None, max_length=12)


class PropertyDetailsRequest(BaseModel):
    condo_fee: Decimal | None = Field(default=None, ge=0)
    property_tax: Decimal | None = Field(default=None, ge=0)
    fire_insurance: Decimal | None = Field(default=None, ge=0)
    built_area: Decimal | None = Field(default=None, ge=0)
    usable_area: Decimal | None = Field(default=None, ge=0)
    total_area: Decimal | None = Field(default=None, ge=0)
    furnished: bool = False
    pet_friendly: bool = False
    accepts_financing: bool = False
    accepts_exchange: bool = False
    rental_guarantees: list[str] = Field(default_factory=list, max_length=20)
    minimum_lease_months: int | None = Field(default=None, ge=1, le=120)
    floor: int | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=40)
    year_built: int | None = Field(default=None, ge=1800, le=2200)
    rooms: list[str] = Field(default_factory=list, max_length=80)
    amenities: list[str] = Field(default_factory=list, max_length=120)


class CreatePropertyRequest(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    listing_code: str | None = Field(default=None, max_length=80)
    purpose: str = Field(pattern="^(buy|rent|both)$")
    property_type: str = Field(min_length=2, max_length=80)
    category: str = Field(pattern="^(residential|commercial|mixed)$")
    status: str = Field(default="active", pattern="^(draft|active|inactive)$")
    sale_price: Decimal | None = Field(default=None, ge=0)
    rent_price: Decimal | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=20000)
    bedrooms: int | None = Field(default=None, ge=0, le=100)
    suites: int | None = Field(default=None, ge=0, le=100)
    bathrooms: int | None = Field(default=None, ge=0, le=100)
    parking_spaces: int | None = Field(default=None, ge=0, le=100)
    area: int | None = Field(default=None, ge=0)
    land_area: int | None = Field(default=None, ge=0)
    address: PropertyAddressRequest
    details: PropertyDetailsRequest = Field(default_factory=PropertyDetailsRequest)
    images: list[dict[str, Any]] = Field(default_factory=list)
    owner_name: str | None = Field(default=None, max_length=200)
    owner_phone: str | None = Field(default=None, max_length=40)
    source_url: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_offer_prices(self) -> "CreatePropertyRequest":
        if self.purpose in {"buy", "both"} and self.sale_price is None:
            raise ValueError("sale_price is required for properties offered for sale")
        if self.purpose in {"rent", "both"} and self.rent_price is None:
            raise ValueError("rent_price is required for rental properties")
        if self.suites is not None and self.bedrooms is not None and self.suites > self.bedrooms:
            raise ValueError("suites cannot exceed bedrooms")
        return self


class PropertyImageResponse(BaseModel):
    url: str
    original_name: str
    content_type: str
    size: int
    optimized: bool


@router.post(
    "/images",
    response_model=list[PropertyImageResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_property_images(
    files: Annotated[list[UploadFile], File(description="Imagens JPEG, PNG ou WebP")],
    optimizations: Annotated[str, Form()] = "[]",
    note: Annotated[str | None, Form(max_length=1000)] = None,
    principal: CurrentPrincipal = Depends(get_current_principal),
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
) -> list[PropertyImageResponse]:
    if not files:
        raise HTTPException(status_code=422, detail="Envie pelo menos uma imagem.")
    if len(files) > container.settings.property_image_max_files:
        raise HTTPException(
            status_code=422,
            detail=f"Envie no máximo {container.settings.property_image_max_files} imagens.",
        )
    requested = _parse_optimizations(optimizations)
    should_optimize = bool(requested or (note and note.strip()))
    if should_optimize and container.ai_provider is None:
        raise HTTPException(
            status_code=503,
            detail="O tratamento por OpenAI foi solicitado, mas a integração não está configurada.",
        )
    ledger = CreditLedgerService(session)
    if should_optimize:
        ledger.ensure_available(principal.tenant_id, resource="image_edit")

    prepared: list[PropertyImageUpload] = []
    for file in files:
        content = await file.read(container.settings.property_image_max_bytes + 1)
        upload = PropertyImageUpload(
            original_name=Path(file.filename or "imagem").name,
            content_type=(file.content_type or "").lower(),
            content=content,
        )
        try:
            validate_property_image(upload, max_bytes=container.settings.property_image_max_bytes)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"{upload.original_name}: {exc}") from exc
        prepared.append(upload)

    if should_optimize:
        prompt = optimization_prompt(requested, note)
        processed: list[PropertyImageUpload] = []
        for index, upload in enumerate(prepared):
            try:
                edit_result = container.ai_provider.edit_image(
                    upload.content,
                    filename=upload.original_name,
                    prompt=prompt,
                )
                output = PropertyImageUpload(
                    original_name=upload.original_name,
                    content_type="image/png",
                    content=edit_result.content,
                )
                validate_property_image(
                    output, max_bytes=container.settings.property_image_max_bytes
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"A OpenAI não conseguiu tratar {upload.original_name}; "
                        "nenhuma imagem deste envio foi salva."
                    ),
                ) from exc
            processed.append(output)
            charge = image_token_charge(
                container.settings.openai_image_model,
                input_image_tokens=edit_result.input_image_tokens,
                input_text_tokens=edit_result.input_text_tokens,
                output_image_tokens=edit_result.output_image_tokens,
            )
            ledger.consume(
                principal.tenant_id,
                resource="image_edit",
                model=container.settings.openai_image_model,
                charge=charge,
                idempotency_key=f"image:{principal.tenant_id}:{uuid4()}:{index}",
                reference_id=None,
                extra={
                    "quality": "medium",
                    "size": "1024x1024",
                    "input_image_tokens": edit_result.input_image_tokens,
                    "input_text_tokens": edit_result.input_text_tokens,
                    "output_image_tokens": edit_result.output_image_tokens,
                },
            )
        prepared = processed

    storage = LocalPropertyImageStorage(container.settings.property_media_root)
    response = [
        PropertyImageResponse.model_validate(
            storage.save(principal.tenant_id, upload, optimized=should_optimize),
            from_attributes=True,
        )
        for upload in prepared
    ]
    session.commit()
    return response


def _parse_optimizations(raw: str) -> list[str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=422, detail="optimizations deve ser um JSON válido."
        ) from exc
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise HTTPException(
            status_code=422,
            detail="optimizations deve ser uma lista JSON de textos.",
        )
    if len(value) > 10 or any(len(item) > 120 for item in value):
        raise HTTPException(status_code=422, detail="As otimizações solicitadas excedem o limite.")
    return value


@router.post("", response_model=PropertyResponse, status_code=status.HTTP_201_CREATED)
def create_property(
    payload: CreatePropertyRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> PropertyResponse:
    data = payload.model_dump(mode="python")
    address = data["address"]
    details = data["details"]
    property_ = Property(
        tenant_id=principal.tenant_id,
        source="manual",
        source_url=payload.source_url,
        title=payload.title,
        listing_code=payload.listing_code,
        city=address["city"],
        neighborhood=address["neighborhood"],
        price=payload.sale_price or payload.rent_price,
        sale_price=payload.sale_price,
        rent_price=payload.rent_price,
        purpose=PropertyPurpose(payload.purpose),
        property_type=payload.property_type,
        category=payload.category,
        status=payload.status,
        description=payload.description,
        bedrooms=payload.bedrooms,
        suites=payload.suites,
        bathrooms=payload.bathrooms,
        parking_spaces=payload.parking_spaces,
        area=payload.area,
        land_area=payload.land_area,
        address=address,
        details=details,
        images=payload.images,
        advertiser_name=payload.owner_name,
        advertiser_phone=payload.owner_phone,
    )
    saved = SqlAlchemyPropertyRepository(session).create_manual(principal.tenant_id, property_)
    return PropertyResponse.from_domain(saved)


@router.get("", response_model=list[PropertyResponse])
def list_properties(
    demand_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[PropertyResponse]:
    properties = ListPropertiesUseCase(SqlAlchemyPropertyRepository(session)).execute(
        principal.tenant_id, demand_id=demand_id, limit=limit, offset=offset
    )
    return [PropertyResponse.from_domain(item) for item in properties]
