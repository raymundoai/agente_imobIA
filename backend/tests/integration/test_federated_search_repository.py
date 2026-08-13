from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.modules.capture.connectors.base import ExternalListingRecord
from app.modules.capture.federated import FederatedSearchRepository
from app.modules.capture.models import CaptureJobModel, SearchRunSourceModel
from app.modules.leads.adapters.repositories import SqlAlchemyLeadDemandRepository
from app.modules.leads.domain.entities import LeadDemand, LeadPurpose
from app.modules.tenants.adapters.models import TenantModel

pytestmark = pytest.mark.integration


def test_federated_run_persists_parent_before_jobs_and_aggregates_results(
    migrated_database: str,
) -> None:
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    engine = create_engine(migrated_database)
    with Session(engine, autoflush=False, expire_on_commit=False) as session:
        session.add_all(
            [
                TenantModel(
                    id=tenant_id,
                    name="Imobiliária A",
                    slug="federated-a",
                    status="active",
                    settings={},
                ),
                TenantModel(
                    id=other_tenant_id,
                    name="Imobiliária B",
                    slug="federated-b",
                    status="active",
                    settings={},
                ),
            ]
        )
        session.commit()
        demand = SqlAlchemyLeadDemandRepository(session).create(
            tenant_id,
            LeadDemand(
                tenant_id=tenant_id,
                lead_name="Bruna",
                phone="5551999999999",
                purpose=LeadPurpose.BUY,
                property_type="apartamento",
                city="São Paulo",
                neighborhoods=["Pinheiros"],
                price_max=Decimal("1000000"),
                bedrooms=2,
            ),
        )
        repository = FederatedSearchRepository(session)
        run = repository.create_run(tenant_id, demand, ["test_source"])

        assert repository.get_run(tenant_id, run.id) is not None
        assert repository.get_run(other_tenant_id, run.id) is None
        assert (
            session.scalar(
                select(func.count(SearchRunSourceModel.id)).where(
                    SearchRunSourceModel.search_run_id == run.id
                )
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count(CaptureJobModel.id)).where(
                    CaptureJobModel.search_run_id == run.id
                )
            )
            == 1
        )

        job = repository.claim_next(lease_seconds=60, worker_id="integration-test")
        assert job is not None
        record = ExternalListingRecord(
            source_id="test_source",
            source_listing_id="listing-1",
            canonical_url="https://example.test/imovel/listing-1",
            title="Apartamento com 2 quartos em Pinheiros",
            purpose="buy",
            property_type="apartamento",
            state="SP",
            city="São Paulo",
            neighborhood="Pinheiros",
            price=Decimal("850000"),
            sale_price=Decimal("850000"),
            bedrooms=2,
            bathrooms=2,
            area=80,
            primary_image_url="https://example.test/imovel/listing-1.jpg",
            extraction_confidence=95,
        )
        _, matched = repository.upsert_and_match(job, demand, record)
        assert matched
        repository.complete(
            job,
            discovered_count=1,
            imported_count=1,
            parser_version="test-v1",
        )

        reusable = repository.find_reusable_run(tenant_id, demand, ["test_source"])
        assert reusable is not None
        assert reusable.id == run.id
        latest = repository.latest_compatible_run(
            tenant_id, demand, ["test_source"]
        )
        assert latest is not None
        assert latest.id == run.id
        assert repository.find_reusable_run(tenant_id, demand, ["other_source"]) is None
        demand.price_max = Decimal("900000")
        assert repository.find_reusable_run(tenant_id, demand, ["test_source"]) is None
        assert repository.latest_compatible_run(
            tenant_id, demand, ["test_source"]
        ) is None
        demand.price_max = Decimal("1000000")

        persisted = repository.get_run(tenant_id, run.id)
        assert persisted is not None
        assert persisted.status == "completed"
        assert persisted.completed_source_count == 1
        assert persisted.result_count == 1
        results = repository.list_results(tenant_id, run.id)
        assert len(results) == 1
        assert results[0]["sale_price"] == "850000"
        assert results[0]["rent_price"] is None
        assert repository.list_results(other_tenant_id, run.id) == []
        listing_id = UUID(results[0]["id"])
        capture = repository.get_result_for_capture(tenant_id, run.id, listing_id)
        assert capture is not None
        capture_demand_id, capture_data = capture
        assert capture_demand_id == demand.id
        assert capture_data["source"] == "test_source"
        assert capture_data["price"] == Decimal("850000")
        assert capture_data["listing_code"] == "test_source:listing-1"
        assert capture_data["images"] == [
            {"url": "https://example.test/imovel/listing-1.jpg", "is_primary": True}
        ]
        assert repository.get_result_for_capture(other_tenant_id, run.id, listing_id) is None
        assert not repository.mark_result_saved(other_tenant_id, run.id, listing_id)
        assert repository.mark_result_saved(tenant_id, run.id, listing_id)
        assert repository.list_results(tenant_id, run.id)[0]["review_status"] == "saved"

        second_run = repository.create_run(
            tenant_id,
            demand,
            ["test_source"],
            force_refresh=True,
        )
        second_job = repository.claim_next(lease_seconds=60, worker_id="integration-test")
        assert second_job is not None
        changed_record = ExternalListingRecord(
            source_id="test_source",
            source_listing_id="listing-1",
            canonical_url="https://example.test/imovel/listing-1",
            title="Apartamento atualizado em Pinheiros",
            purpose="buy",
            property_type="apartamento",
            state="SP",
            city="São Paulo",
            neighborhood="Pinheiros",
            price=Decimal("900000"),
            sale_price=Decimal("900000"),
            bedrooms=2,
        )
        repository.upsert_and_match(second_job, demand, changed_record)
        repository.complete(
            second_job,
            discovered_count=1,
            imported_count=1,
            parser_version="test-v2",
        )

        assert repository.list_results(tenant_id, run.id)[0]["sale_price"] == "850000"
        assert repository.list_results(tenant_id, second_run.id)[0]["sale_price"] == "900000"
        assert repository.get_run(tenant_id, run.id).result_count == 1
        assert repository.get_run(tenant_id, second_run.id).result_count == 1

        second_run.cache_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        run.cache_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
        assert repository.find_reusable_run(tenant_id, demand, ["test_source"]) is None
    engine.dispose()
