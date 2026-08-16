from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import case, func, or_, select, text
from sqlalchemy.orm import Session

from app.modules.billing_usage.adapters.models import (
    AiAttendanceSessionModel,
    CommercialEntitlementGrantModel,
    CommercialPackModel,
    CommercialPlanModel,
    CommercialUsageEventModel,
    CommercialUsageReservationModel,
    TenantCommercialSubscriptionModel,
)
from app.shared.errors.exceptions import PaymentRequiredError

AI_ATTENDANCE = "ai_attendance"
PROPERTY_SEARCH_STANDARD = "property_search_standard"
PROPERTY_SEARCH_AI = "property_search_ai"
IMAGE_OPTIMIZATION = "image_optimization"
COMMERCIAL_RESOURCES = (
    AI_ATTENDANCE,
    PROPERTY_SEARCH_STANDARD,
    PROPERTY_SEARCH_AI,
    IMAGE_OPTIMIZATION,
)
PILOT_PLAN_CODE = "piloto_mvp"

RESOURCE_LABELS = {
    AI_ATTENDANCE: "atendimentos da IA",
    PROPERTY_SEARCH_STANDARD: "buscas de imóveis",
    PROPERTY_SEARCH_AI: "buscas estendidas com IA",
    IMAGE_OPTIMIZATION: "otimizações de fotos",
}


class CommercialAllowanceExhausted(PaymentRequiredError):
    code = "commercial_allowance_exhausted"

    def __init__(self, resource: str, detail: str | None = None) -> None:
        self.resource = resource
        super().__init__(
            detail
            or f"A franquia de {RESOURCE_LABELS.get(resource, resource)} deste ciclo terminou."
        )


@dataclass(frozen=True, slots=True)
class AttendancePreparation:
    session_id: UUID
    is_new_attendance: bool
    expires_at: datetime | None


def _calendar_cycle(now: datetime) -> tuple[datetime, datetime]:
    start = now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


class CommercialEntitlementService:
    """Commercial allowances, separate from the provider-cost credit ledger."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def subscription(
        self, tenant_id: UUID, *, lock: bool = False
    ) -> TenantCommercialSubscriptionModel:
        self._advisory_lock(f"commercial-subscription:{tenant_id}")
        statement = select(TenantCommercialSubscriptionModel).where(
            TenantCommercialSubscriptionModel.tenant_id == tenant_id
        )
        if lock:
            statement = statement.with_for_update()
        subscription = self._session.scalar(statement)
        now = datetime.now(UTC)
        if subscription is None:
            plan = self._session.scalar(
                select(CommercialPlanModel).where(
                    CommercialPlanModel.code == PILOT_PLAN_CODE,
                    CommercialPlanModel.is_current.is_(True),
                )
            )
            if plan is None:
                raise RuntimeError("Commercial pilot plan is not configured")
            cycle_start, cycle_end = _calendar_cycle(now)
            subscription = TenantCommercialSubscriptionModel(
                tenant_id=tenant_id,
                plan_id=plan.id,
                status="pilot",
                enforcement_mode="meter_only",
                cycle_started_at=cycle_start,
                cycle_ends_at=cycle_end,
            )
            self._session.add(subscription)
            self._session.flush()
        self._roll_cycle(subscription, now)
        return subscription

    def reserve(
        self,
        tenant_id: UUID,
        *,
        resource: str,
        idempotency_key: str,
        reference_id: UUID | None,
        units: int = 1,
        ttl_seconds: int = 900,
        extra: dict | None = None,
        commit: bool = True,
    ) -> CommercialUsageReservationModel:
        if resource not in COMMERCIAL_RESOURCES:
            raise ValueError(f"Unknown commercial resource: {resource}")
        if units <= 0:
            raise ValueError("units must be positive")
        self._advisory_lock(f"commercial-allowance:{tenant_id}:{resource}")
        subscription = self.subscription(tenant_id, lock=True)
        existing = self._session.scalar(
            select(CommercialUsageReservationModel)
            .where(
                CommercialUsageReservationModel.tenant_id == tenant_id,
                CommercialUsageReservationModel.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        if existing is not None and existing.status in {"reserved", "settled"}:
            if commit:
                self._session.commit()
            return existing

        now = datetime.now(UTC)
        grant = self._session.scalar(
            select(CommercialEntitlementGrantModel)
            .where(
                CommercialEntitlementGrantModel.tenant_id == tenant_id,
                CommercialEntitlementGrantModel.resource == resource,
                CommercialEntitlementGrantModel.valid_from <= now,
                or_(
                    CommercialEntitlementGrantModel.expires_at.is_(None),
                    CommercialEntitlementGrantModel.expires_at > now,
                ),
                CommercialEntitlementGrantModel.quantity
                - CommercialEntitlementGrantModel.consumed_units
                - CommercialEntitlementGrantModel.reserved_units
                >= units,
            )
            .order_by(
                CommercialEntitlementGrantModel.expires_at.asc().nullslast(),
                CommercialEntitlementGrantModel.created_at,
            )
            .with_for_update()
            .limit(1)
        )
        if grant is None and subscription.enforcement_mode == "enforce":
            raise CommercialAllowanceExhausted(resource)
        if grant is not None:
            grant.reserved_units += units
        snapshot = {
            **(extra or {}),
            "enforcement_mode_snapshot": subscription.enforcement_mode,
            "subscription_status_snapshot": subscription.status,
            "plan_id_snapshot": str(subscription.plan_id),
        }
        if existing is None:
            existing = CommercialUsageReservationModel(
                id=uuid4(),
                tenant_id=tenant_id,
                grant_id=grant.id if grant else None,
                resource=resource,
                units=units,
                status="reserved",
                idempotency_key=idempotency_key,
                reference_id=reference_id,
                extra=snapshot,
                expires_at=now + timedelta(seconds=ttl_seconds),
            )
            self._session.add(existing)
        else:
            existing.grant_id = grant.id if grant else None
            existing.resource = resource
            existing.units = units
            existing.status = "reserved"
            existing.reference_id = reference_id
            existing.extra = snapshot
            existing.expires_at = now + timedelta(seconds=ttl_seconds)
            existing.settled_at = None
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return existing

    def settle(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        *,
        reference_id: UUID | None = None,
        extra: dict | None = None,
        commit: bool = True,
    ) -> CommercialUsageEventModel:
        event_key = f"settle:{idempotency_key}"
        existing_event = self._session.scalar(
            select(CommercialUsageEventModel).where(
                CommercialUsageEventModel.tenant_id == tenant_id,
                CommercialUsageEventModel.idempotency_key == event_key,
            )
        )
        if existing_event is not None:
            return existing_event
        reservation = self._session.scalar(
            select(CommercialUsageReservationModel)
            .where(
                CommercialUsageReservationModel.tenant_id == tenant_id,
                CommercialUsageReservationModel.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        if reservation is None:
            raise RuntimeError("Commercial reservation not found")
        if reservation.status == "released":
            raise RuntimeError("Commercial reservation was already released")
        if reservation.status == "settled":
            raise RuntimeError("Settled commercial reservation has no usage event")
        grant = None
        if reservation.grant_id is not None:
            grant = self._session.scalar(
                select(CommercialEntitlementGrantModel)
                .where(CommercialEntitlementGrantModel.id == reservation.grant_id)
                .with_for_update()
            )
            if grant is None:
                raise RuntimeError("Commercial grant not found")
            grant.reserved_units = max(grant.reserved_units - reservation.units, 0)
            grant.consumed_units += reservation.units
        reservation.status = "settled"
        reservation.settled_at = datetime.now(UTC)
        reservation.reference_id = reference_id or reservation.reference_id
        reservation.extra = {**reservation.extra, **(extra or {})}
        event = CommercialUsageEventModel(
            id=uuid4(),
            tenant_id=tenant_id,
            grant_id=grant.id if grant else None,
            reservation_id=reservation.id,
            resource=reservation.resource,
            units=reservation.units,
            within_allowance=grant is not None,
            mode_snapshot=str(reservation.extra.get("enforcement_mode_snapshot", "meter_only")),
            idempotency_key=event_key,
            reference_id=reservation.reference_id,
            extra=reservation.extra,
        )
        self._session.add(event)
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return event

    def release(self, tenant_id: UUID, idempotency_key: str, *, commit: bool = True) -> bool:
        reservation = self._session.scalar(
            select(CommercialUsageReservationModel)
            .where(
                CommercialUsageReservationModel.tenant_id == tenant_id,
                CommercialUsageReservationModel.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        if reservation is None or reservation.status != "reserved":
            return False
        if reservation.grant_id is not None:
            grant = self._session.scalar(
                select(CommercialEntitlementGrantModel)
                .where(CommercialEntitlementGrantModel.id == reservation.grant_id)
                .with_for_update()
            )
            if grant is not None:
                grant.reserved_units = max(grant.reserved_units - reservation.units, 0)
        reservation.status = "released"
        reservation.settled_at = datetime.now(UTC)
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return True

    def touch(self, tenant_id: UUID, idempotency_key: str, ttl_seconds: int = 900) -> bool:
        reservation = self._session.scalar(
            select(CommercialUsageReservationModel)
            .where(
                CommercialUsageReservationModel.tenant_id == tenant_id,
                CommercialUsageReservationModel.idempotency_key == idempotency_key,
                CommercialUsageReservationModel.status == "reserved",
            )
            .with_for_update()
        )
        if reservation is None:
            return False
        reservation.expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        self._session.commit()
        return True

    def reservation_status(self, tenant_id: UUID, idempotency_key: str) -> str | None:
        return self._session.scalar(
            select(CommercialUsageReservationModel.status).where(
                CommercialUsageReservationModel.tenant_id == tenant_id,
                CommercialUsageReservationModel.idempotency_key == idempotency_key,
            )
        )

    def reconcile_expired(self) -> int:
        expired = self._session.scalars(
            select(CommercialUsageReservationModel)
            .where(
                CommercialUsageReservationModel.status == "reserved",
                CommercialUsageReservationModel.expires_at < datetime.now(UTC),
            )
            .with_for_update(skip_locked=True)
        ).all()
        for reservation in expired:
            self.release(reservation.tenant_id, reservation.idempotency_key, commit=False)
        self._session.commit()
        return len(expired)

    def assign_plan(
        self,
        tenant_id: UUID,
        *,
        plan_code: str,
        enforcement_mode: str,
        status: str | None = None,
    ) -> TenantCommercialSubscriptionModel:
        if enforcement_mode not in {"meter_only", "enforce"}:
            raise ValueError("Invalid commercial enforcement mode")
        plan = self._session.scalar(
            select(CommercialPlanModel).where(
                CommercialPlanModel.code == plan_code,
                CommercialPlanModel.is_current.is_(True),
            )
        )
        if plan is None:
            raise ValueError("Commercial plan not found")
        now = datetime.now(UTC)
        cycle_start, cycle_end = _calendar_cycle(now)
        subscription = self.subscription(tenant_id, lock=True)
        next_status = status or ("pilot" if plan.code == PILOT_PLAN_CODE else "active")
        if subscription.plan_id != plan.id or next_status not in {"pilot", "active"}:
            old_plan_grants = self._session.scalars(
                select(CommercialEntitlementGrantModel).where(
                    CommercialEntitlementGrantModel.tenant_id == tenant_id,
                    CommercialEntitlementGrantModel.source == "plan",
                    or_(
                        CommercialEntitlementGrantModel.expires_at.is_(None),
                        CommercialEntitlementGrantModel.expires_at > now,
                    ),
                )
            ).all()
            for grant in old_plan_grants:
                grant.expires_at = now
        subscription.plan_id = plan.id
        subscription.status = next_status
        subscription.enforcement_mode = enforcement_mode
        subscription.cycle_started_at = cycle_start
        subscription.cycle_ends_at = cycle_end
        if subscription.status in {"pilot", "active"}:
            self._provision_plan_grants(subscription, plan)
        self._session.commit()
        return subscription

    def grant(
        self,
        tenant_id: UUID,
        *,
        resource: str,
        quantity: int,
        source: str,
        idempotency_key: str,
        reference: str | None,
        expires_at: datetime | None,
        created_by: UUID | None,
        extra: dict | None = None,
    ) -> CommercialEntitlementGrantModel:
        if resource not in COMMERCIAL_RESOURCES:
            raise ValueError("Invalid commercial resource")
        if source not in {"pack", "manual", "promotion"}:
            raise ValueError("Invalid commercial grant source")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        existing = self._session.scalar(
            select(CommercialEntitlementGrantModel).where(
                CommercialEntitlementGrantModel.tenant_id == tenant_id,
                CommercialEntitlementGrantModel.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return existing
        item = CommercialEntitlementGrantModel(
            id=uuid4(),
            tenant_id=tenant_id,
            resource=resource,
            source=source,
            quantity=quantity,
            idempotency_key=idempotency_key,
            reference=reference,
            valid_from=datetime.now(UTC),
            expires_at=expires_at,
            created_by=created_by,
            extra=extra or {},
        )
        self._session.add(item)
        self._session.commit()
        return item

    def grant_pack(
        self,
        tenant_id: UUID,
        *,
        pack_code: str,
        idempotency_key: str,
        created_by: UUID | None,
        expires_at: datetime | None = None,
    ) -> CommercialEntitlementGrantModel:
        pack = self._session.scalar(
            select(CommercialPackModel).where(CommercialPackModel.code == pack_code)
        )
        if pack is None:
            raise ValueError("Commercial pack not found")
        return self.grant(
            tenant_id,
            resource=pack.resource,
            quantity=pack.units,
            source="pack",
            idempotency_key=idempotency_key,
            reference=pack.code,
            expires_at=expires_at,
            created_by=created_by,
            extra={"pack_id": str(pack.id), "pack_code": pack.code},
        )

    def resource_summary(self, tenant_id: UUID) -> dict[str, dict[str, int]]:
        subscription = self.subscription(tenant_id)
        self._session.commit()
        now = datetime.now(UTC)
        summaries: dict[str, dict[str, int]] = {}
        for resource in COMMERCIAL_RESOURCES:
            grants = self._session.scalars(
                select(CommercialEntitlementGrantModel).where(
                    CommercialEntitlementGrantModel.tenant_id == tenant_id,
                    CommercialEntitlementGrantModel.resource == resource,
                    CommercialEntitlementGrantModel.valid_from <= now,
                    or_(
                        CommercialEntitlementGrantModel.expires_at.is_(None),
                        CommercialEntitlementGrantModel.expires_at > now,
                    ),
                )
            ).all()
            cycle_events = self._session.execute(
                select(
                    func.coalesce(func.sum(CommercialUsageEventModel.units), 0),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    CommercialUsageEventModel.within_allowance.is_(False),
                                    CommercialUsageEventModel.units,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                ).where(
                    CommercialUsageEventModel.tenant_id == tenant_id,
                    CommercialUsageEventModel.resource == resource,
                    CommercialUsageEventModel.created_at >= subscription.cycle_started_at,
                    CommercialUsageEventModel.created_at < subscription.cycle_ends_at,
                )
            ).one()
            summaries[resource] = {
                "granted": sum(item.quantity for item in grants),
                "consumed": sum(item.consumed_units for item in grants),
                "reserved": sum(item.reserved_units for item in grants),
                "available": sum(
                    item.quantity - item.consumed_units - item.reserved_units for item in grants
                ),
                "measured": int(cycle_events[0] or 0),
                "overage": int(cycle_events[1] or 0),
            }
        return summaries

    def _roll_cycle(self, subscription: TenantCommercialSubscriptionModel, now: datetime) -> None:
        if now < subscription.cycle_ends_at:
            if subscription.status in {"pilot", "active"}:
                plan = self._session.get(CommercialPlanModel, subscription.plan_id)
                if plan is not None:
                    self._provision_plan_grants(subscription, plan)
            return
        cycle_start, cycle_end = _calendar_cycle(now)
        subscription.cycle_started_at = cycle_start
        subscription.cycle_ends_at = cycle_end
        if subscription.status in {"pilot", "active"}:
            plan = self._session.get(CommercialPlanModel, subscription.plan_id)
            if plan is not None:
                self._provision_plan_grants(subscription, plan)

    def _provision_plan_grants(
        self,
        subscription: TenantCommercialSubscriptionModel,
        plan: CommercialPlanModel,
    ) -> None:
        quantities = {
            AI_ATTENDANCE: plan.ai_attendances,
            PROPERTY_SEARCH_STANDARD: plan.property_searches,
            IMAGE_OPTIMIZATION: plan.image_optimizations,
        }
        for resource, quantity in quantities.items():
            if quantity <= 0:
                continue
            key = f"plan:{plan.id}:{subscription.cycle_started_at.isoformat()}:{resource}"
            existing = self._session.scalar(
                select(CommercialEntitlementGrantModel).where(
                    CommercialEntitlementGrantModel.tenant_id == subscription.tenant_id,
                    CommercialEntitlementGrantModel.resource == resource,
                    CommercialEntitlementGrantModel.source == "plan",
                    CommercialEntitlementGrantModel.reference == plan.code,
                    CommercialEntitlementGrantModel.valid_from == subscription.cycle_started_at,
                    CommercialEntitlementGrantModel.expires_at == subscription.cycle_ends_at,
                )
            )
            if existing is not None:
                continue
            if self._session.scalar(
                select(CommercialEntitlementGrantModel.id).where(
                    CommercialEntitlementGrantModel.tenant_id == subscription.tenant_id,
                    CommercialEntitlementGrantModel.idempotency_key == key,
                )
            ):
                key = f"{key}:{uuid4()}"
            self._session.add(
                CommercialEntitlementGrantModel(
                    id=uuid4(),
                    tenant_id=subscription.tenant_id,
                    resource=resource,
                    source="plan",
                    quantity=quantity,
                    idempotency_key=key,
                    reference=plan.code,
                    valid_from=subscription.cycle_started_at,
                    expires_at=subscription.cycle_ends_at,
                    extra={
                        "plan_id": str(plan.id),
                        "plan_code": plan.code,
                        "cycle_start": subscription.cycle_started_at.isoformat(),
                    },
                )
            )
        self._session.flush()

    def _advisory_lock(self, key: str) -> None:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": key},
        )


class AiAttendanceService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._allowances = CommercialEntitlementService(session)

    def prepare(
        self,
        tenant_id: UUID,
        *,
        conversation_id: UUID,
        contact_id: UUID | None,
        phone: str,
        channel: str,
        opening_job_id: UUID | None,
        max_responses: int,
        ttl_seconds: int = 1800,
    ) -> AttendancePreparation:
        contact_key = f"contact:{contact_id}" if contact_id else f"{channel}:{phone}"
        self._allowances._advisory_lock(f"ai-attendance:{tenant_id}:{contact_key}")
        now = datetime.now(UTC)
        current = self._session.scalar(
            select(AiAttendanceSessionModel)
            .where(
                AiAttendanceSessionModel.tenant_id == tenant_id,
                AiAttendanceSessionModel.contact_key == contact_key,
                AiAttendanceSessionModel.status.in_(("pending", "active")),
            )
            .with_for_update()
        )
        if current is not None and current.status == "active":
            if current.expires_at is not None and current.expires_at > now:
                if current.response_count >= max_responses:
                    raise CommercialAllowanceExhausted(
                        AI_ATTENDANCE,
                        "Este atendimento atingiu o limite operacional de segurança "
                        "e foi encaminhado para a equipe.",
                    )
                current.conversation_id = conversation_id
                self._session.commit()
                return AttendancePreparation(current.id, False, current.expires_at)
            current.status = "closed"
            current.close_reason = "window_expired"
        if current is not None and current.status == "pending":
            if current.created_at > now - timedelta(seconds=ttl_seconds):
                self._session.commit()
                return AttendancePreparation(current.id, False, None)
            self._allowances.release(tenant_id, current.reservation_key, commit=False)
            current.status = "released"
            current.close_reason = "opening_expired"

        session_id = uuid4()
        reservation_key = f"ai-attendance:{session_id}"
        self._allowances.reserve(
            tenant_id,
            resource=AI_ATTENDANCE,
            idempotency_key=reservation_key,
            reference_id=conversation_id,
            ttl_seconds=ttl_seconds,
            extra={
                "attendance_session_id": str(session_id),
                "opening_job_id": str(opening_job_id) if opening_job_id else None,
                "contact_key": contact_key,
            },
            commit=False,
        )
        attendance = AiAttendanceSessionModel(
            id=session_id,
            tenant_id=tenant_id,
            contact_id=contact_id,
            conversation_id=conversation_id,
            contact_key=contact_key,
            channel=channel,
            status="pending",
            reservation_key=reservation_key,
            opening_job_id=opening_job_id,
            delivered_job_ids=[],
        )
        self._session.add(attendance)
        self._session.commit()
        return AttendancePreparation(attendance.id, True, None)

    def settle_delivery(
        self,
        tenant_id: UUID,
        attendance_id: UUID,
        *,
        delivery_id: UUID,
        window_hours: int,
    ) -> AiAttendanceSessionModel:
        attendance = self._session.scalar(
            select(AiAttendanceSessionModel)
            .where(
                AiAttendanceSessionModel.tenant_id == tenant_id,
                AiAttendanceSessionModel.id == attendance_id,
            )
            .with_for_update()
        )
        if attendance is None:
            raise RuntimeError("AI attendance session not found")
        delivery_key = str(delivery_id)
        delivered = list(attendance.delivered_job_ids or [])
        if delivery_key in delivered:
            return attendance
        now = datetime.now(UTC)
        if attendance.status == "pending":
            self._allowances.settle(
                tenant_id,
                attendance.reservation_key,
                reference_id=attendance.conversation_id,
                extra={"first_delivery_id": delivery_key},
                commit=False,
            )
            attendance.status = "active"
            attendance.started_at = now
            attendance.expires_at = now + timedelta(hours=window_hours)
        elif attendance.status != "active":
            raise RuntimeError("AI attendance session is not open")
        delivered.append(delivery_key)
        attendance.delivered_job_ids = delivered
        attendance.response_count += 1
        self._session.commit()
        return attendance

    def release_for_job(self, tenant_id: UUID, opening_job_id: UUID) -> bool:
        attendance = self._session.scalar(
            select(AiAttendanceSessionModel)
            .where(
                AiAttendanceSessionModel.tenant_id == tenant_id,
                AiAttendanceSessionModel.opening_job_id == opening_job_id,
                AiAttendanceSessionModel.status == "pending",
            )
            .with_for_update()
        )
        if attendance is None:
            return False
        self._allowances.release(tenant_id, attendance.reservation_key, commit=False)
        attendance.status = "released"
        attendance.close_reason = "generation_failed"
        self._session.commit()
        return True

    def touch_for_job(self, tenant_id: UUID, opening_job_id: UUID) -> bool:
        attendance = self._session.scalar(
            select(AiAttendanceSessionModel).where(
                AiAttendanceSessionModel.tenant_id == tenant_id,
                AiAttendanceSessionModel.opening_job_id == opening_job_id,
                AiAttendanceSessionModel.status == "pending",
            )
        )
        if attendance is None:
            return False
        return self._allowances.touch(tenant_id, attendance.reservation_key, 1800)

    def find_for_job(self, tenant_id: UUID, opening_job_id: UUID) -> UUID | None:
        return self._session.scalar(
            select(AiAttendanceSessionModel.id).where(
                AiAttendanceSessionModel.tenant_id == tenant_id,
                AiAttendanceSessionModel.opening_job_id == opening_job_id,
                AiAttendanceSessionModel.status.in_(("pending", "active")),
            )
        )

    def close_expired(self) -> int:
        now = datetime.now(UTC)
        items = self._session.scalars(
            select(AiAttendanceSessionModel)
            .where(
                AiAttendanceSessionModel.status == "active",
                AiAttendanceSessionModel.expires_at <= now,
            )
            .with_for_update(skip_locked=True)
        ).all()
        for item in items:
            item.status = "closed"
            item.close_reason = "window_expired"
        self._session.commit()
        return len(items)
