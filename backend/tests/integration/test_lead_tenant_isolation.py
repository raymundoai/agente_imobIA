from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.modules.leads.adapters.repositories import SqlAlchemyLeadDemandRepository
from app.modules.leads.domain.entities import LeadDemand, LeadPurpose
from app.modules.tenants.adapters.models import TenantModel

pytestmark = pytest.mark.integration


def test_lead_demands_are_tenant_isolated(migrated_database: str) -> None:
    tenant_a = uuid4()
    tenant_b = uuid4()
    engine = create_engine(migrated_database)
    with Session(engine) as session:
        session.add_all(
            [
                TenantModel(id=tenant_a, name="A", slug="tenant-a", status="active", settings={}),
                TenantModel(id=tenant_b, name="B", slug="tenant-b", status="active", settings={}),
            ]
        )
        session.commit()
        repo = SqlAlchemyLeadDemandRepository(session)
        lead_a = repo.create(
            tenant_a,
            LeadDemand(
                tenant_id=tenant_a,
                lead_name="Maria A",
                phone="5511999999999",
                purpose=LeadPurpose.BUY,
            ),
        )
        lead_b = repo.create(
            tenant_b,
            LeadDemand(
                tenant_id=tenant_b,
                lead_name="Maria B",
                phone="5511999999999",
                purpose=LeadPurpose.RENT,
            ),
        )

        assert lead_a.id != lead_b.id
        assert repo.get_by_id(tenant_a, lead_a.id) is not None
        assert repo.get_by_id(tenant_b, lead_a.id) is None
        assert repo.get_open_by_phone(tenant_a, "5511999999999").lead_name == "Maria A"
        assert repo.get_open_by_phone(tenant_b, "5511999999999").lead_name == "Maria B"
    engine.dispose()
