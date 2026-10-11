"""Generate one consolidated broker charge when each paid cycle expires."""

import logging
import signal
import threading
from datetime import UTC, datetime

from sqlalchemy import select

from app.config import get_settings
from app.container import Container
from app.modules.billing_usage.adapters.models import (
    CommercialPlanModel,
    TenantCommercialSubscriptionModel,
)
from app.modules.billing_usage.asaas import asaas_client_from_settings
from app.modules.billing_usage.broker_billing import BrokerBillingService
from app.modules.billing_usage.commercial import BROKER_BETA_PLAN_CODE

logger = logging.getLogger(__name__)


def run_once(container: Container) -> int:
    with container.database.session_factory() as session:
        tenants = session.scalars(
            select(TenantCommercialSubscriptionModel.tenant_id)
            .join(
                CommercialPlanModel,
                CommercialPlanModel.id == TenantCommercialSubscriptionModel.plan_id,
            )
            .where(
                CommercialPlanModel.code == BROKER_BETA_PLAN_CODE,
                TenantCommercialSubscriptionModel.status.in_(("active", "past_due")),
                TenantCommercialSubscriptionModel.cycle_ends_at <= datetime.now(UTC),
            )
        ).all()
    count = 0
    client = asaas_client_from_settings(container.settings, container.http_client)
    for tenant_id in tenants:
        try:
            with container.database.session_factory() as session:
                invoice = BrokerBillingService(
                    session, client, container.settings
                ).create_renewal_invoice(tenant_id)
                if invoice is not None:
                    count += 1
        except Exception:
            logger.exception("Falha ao gerar fatura mensal da conta %s", tenant_id)
    return count


def main() -> None:
    container = Container.build(get_settings())
    logging.basicConfig(level=container.settings.log_level)
    stopping = threading.Event()

    def stop(_: int, __: object) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not stopping.is_set():
            try:
                run_once(container)
            except Exception:
                logger.exception("Falha no ciclo de faturamento")
            stopping.wait(600)
    finally:
        container.close()


if __name__ == "__main__":
    main()
