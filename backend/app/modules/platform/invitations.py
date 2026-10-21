"""One-use invitation codes for closed beta registration."""

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.shared.database.base import Base
from app.shared.errors.exceptions import ForbiddenError


class SignupInvitationModel(Base):
    __tablename__ = "signup_invitations"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    code_suffix: Mapped[str] = mapped_column(String(4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redeemed_tenant_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def normalize_invitation(code: str) -> str:
    return re.sub(r"[\s-]", "", code).upper()


def invitation_hash(code: str) -> str:
    return hashlib.sha256(normalize_invitation(code).encode("ascii", errors="ignore")).hexdigest()


def create_invitation(
    session: Session, *, valid_days: int = 30
) -> tuple[SignupInvitationModel, str]:
    raw = secrets.token_hex(12).upper()
    code = "IMB-" + "-".join(raw[index : index + 6] for index in range(0, 24, 6))
    now = datetime.now(UTC)
    invitation = SignupInvitationModel(
        id=uuid4(),
        code_hash=invitation_hash(code),
        code_suffix=raw[-4:],
        created_at=now,
        expires_at=now + timedelta(days=valid_days),
    )
    session.add(invitation)
    session.commit()
    return invitation, code


def lock_valid_invitation(session: Session, code: str) -> SignupInvitationModel:
    normalized = normalize_invitation(code)
    if not re.fullmatch(r"IMB[0-9A-F]{24}", normalized):
        raise ForbiddenError("Código de convite inválido ou indisponível")
    invitation = session.scalar(
        select(SignupInvitationModel)
        .where(SignupInvitationModel.code_hash == invitation_hash(normalized))
        .with_for_update()
    )
    if (
        invitation is None
        or invitation.revoked_at is not None
        or invitation.redeemed_at is not None
        or invitation.expires_at <= datetime.now(UTC)
    ):
        raise ForbiddenError("Código de convite inválido ou indisponível")
    return invitation
