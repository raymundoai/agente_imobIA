from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.container import get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.conversations.adapters.models import ConversationModel
from app.modules.leads.adapters.models import LeadDemandModel
from app.modules.maintenance.adapters.models import MaintenanceTicketModel
from app.modules.properties.adapters.models import PropertyModel

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class DashboardStats(BaseModel):
    conversations: int
    leads: int
    handoffs: int
    maintenance_tickets: int
    properties: int


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> DashboardStats:
    tenant_id = principal.tenant_id
    conversations = session.scalar(
        select(func.count())
        .select_from(ConversationModel)
        .where(ConversationModel.tenant_id == tenant_id)
    )
    leads = session.scalar(
        select(func.count())
        .select_from(LeadDemandModel)
        .where(LeadDemandModel.tenant_id == tenant_id)
    )
    handoffs = session.scalar(
        select(func.count())
        .select_from(ConversationModel)
        .where(
            ConversationModel.tenant_id == tenant_id,
            ConversationModel.mode == "human",
        )
    )
    maintenance_tickets = session.scalar(
        select(func.count())
        .select_from(MaintenanceTicketModel)
        .where(MaintenanceTicketModel.tenant_id == tenant_id)
    )
    properties = session.scalar(
        select(func.count())
        .select_from(PropertyModel)
        .where(
            PropertyModel.tenant_id == tenant_id,
            PropertyModel.source == "manual",
        )
    )
    return DashboardStats(
        conversations=int(conversations or 0),
        leads=int(leads or 0),
        handoffs=int(handoffs or 0),
        maintenance_tickets=int(maintenance_tickets or 0),
        properties=int(properties or 0),
    )
