from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.users.adapters.models import UserAuditLogModel, UserModel
from app.modules.users.domain.entities import User, UserAuditLog, UserRole, UserStatus
from app.modules.users.ports.repositories import UserRepositoryPort
from app.shared.errors.exceptions import ConflictError


def _to_domain(model: UserModel) -> User:
    return User(
        id=model.id,
        tenant_id=model.tenant_id,
        name=model.name,
        email=model.email,
        hashed_password=model.hashed_password,
        role=UserRole(model.role),
        status=UserStatus(model.status),
        created_at=model.created_at,
        session_version=model.session_version,
        is_master=model.is_master,
        must_change_password=model.must_change_password,
        invitation_expires_at=model.invitation_expires_at,
        invited_at=model.invited_at,
        last_login_at=model.last_login_at,
        updated_at=model.updated_at,
    )


def _audit_to_domain(model: UserAuditLogModel) -> UserAuditLog:
    return UserAuditLog(
        id=model.id,
        tenant_id=model.tenant_id,
        actor_user_id=model.actor_user_id,
        target_user_id=model.target_user_id,
        action=model.action,
        changes=model.changes,
        created_at=model.created_at,
    )


class SqlAlchemyUserRepository(UserRepositoryPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, tenant_id: UUID, user: User) -> User:
        if user.tenant_id != tenant_id:
            raise ValueError("User tenant does not match repository tenant scope")
        model = UserModel.from_domain(user)
        self._session.add(model)
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConflictError("User email already exists in this tenant") from exc
        return user

    def get_by_id(self, tenant_id: UUID, user_id: UUID) -> User | None:
        model = self._session.scalar(
            select(UserModel).where(
                UserModel.tenant_id == tenant_id,
                UserModel.id == user_id,
            )
        )
        return _to_domain(model) if model else None

    def get_by_email(self, tenant_id: UUID, email: str) -> User | None:
        model = self._session.scalar(
            select(UserModel).where(
                UserModel.tenant_id == tenant_id,
                UserModel.email == email.strip().lower(),
            )
        )
        return _to_domain(model) if model else None

    def get_by_invitation_hash(self, token_hash: str) -> User | None:
        model = self._session.scalar(
            select(UserModel).where(UserModel.invitation_token_hash == token_hash)
        )
        return _to_domain(model) if model else None

    def list(self, tenant_id: UUID) -> list[User]:
        models = self._session.scalars(
            select(UserModel)
            .where(UserModel.tenant_id == tenant_id)
            .order_by(UserModel.created_at, UserModel.id)
        ).all()
        return [_to_domain(model) for model in models]

    def count_active_admins_for_update(self, tenant_id: UUID) -> int:
        models = self._session.scalars(
            select(UserModel)
            .where(
                UserModel.tenant_id == tenant_id,
                UserModel.role == UserRole.ADMIN.value,
                UserModel.status == UserStatus.ACTIVE.value,
            )
            .with_for_update()
        ).all()
        return len(models)

    def update(
        self,
        tenant_id: UUID,
        user_id: UUID,
        *,
        name: str | None,
        email: str | None,
        role: UserRole | None,
        status: UserStatus | None,
        revoke_sessions: bool = False,
    ) -> User | None:
        model = self._session.scalar(
            select(UserModel).where(
                UserModel.tenant_id == tenant_id,
                UserModel.id == user_id,
            )
        )
        if model is None:
            return None
        if name is not None:
            model.name = name.strip()
        if email is not None:
            model.email = email.strip().lower()
        if role is not None:
            model.role = role.value
        if status is not None:
            model.status = status.value
            if status is UserStatus.INACTIVE:
                model.invitation_token_hash = None
                model.invitation_expires_at = None
        if revoke_sessions:
            model.session_version += 1
        model.updated_at = datetime.now(UTC)
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConflictError("User email already exists in this tenant") from exc
        self._session.refresh(model)
        return _to_domain(model)

    def set_invitation(
        self,
        tenant_id: UUID,
        user_id: UUID,
        *,
        token_hash: str,
        expires_at: datetime,
        invited: bool,
    ) -> User | None:
        model = self._session.scalar(
            select(UserModel).where(
                UserModel.tenant_id == tenant_id,
                UserModel.id == user_id,
            )
        )
        if model is None:
            return None
        now = datetime.now(UTC)
        model.invitation_token_hash = token_hash
        model.invitation_expires_at = expires_at
        model.invited_at = now
        model.must_change_password = True
        if invited:
            model.status = UserStatus.INVITED.value
        else:
            model.session_version += 1
        model.updated_at = now
        self._session.commit()
        self._session.refresh(model)
        return _to_domain(model)

    def accept_invitation(self, user_id: UUID, *, hashed_password: str) -> User | None:
        model = self._session.scalar(
            select(UserModel).where(UserModel.id == user_id).with_for_update()
        )
        if model is None or model.status not in {
            UserStatus.ACTIVE.value,
            UserStatus.INVITED.value,
        }:
            return None
        model.hashed_password = hashed_password
        model.status = UserStatus.ACTIVE.value
        model.must_change_password = False
        model.invitation_token_hash = None
        model.invitation_expires_at = None
        model.session_version += 1
        model.updated_at = datetime.now(UTC)
        self._session.commit()
        self._session.refresh(model)
        return _to_domain(model)

    def revoke_sessions(self, tenant_id: UUID, user_id: UUID) -> User | None:
        model = self._session.scalar(
            select(UserModel).where(
                UserModel.tenant_id == tenant_id,
                UserModel.id == user_id,
            )
        )
        if model is None:
            return None
        model.session_version += 1
        model.updated_at = datetime.now(UTC)
        self._session.commit()
        self._session.refresh(model)
        return _to_domain(model)

    def delete(self, tenant_id: UUID, user_id: UUID) -> bool:
        from app.modules.conversations.adapters.models import ConversationModel
        from app.modules.leads.adapters.models import LeadDemandModel
        from app.modules.maintenance.adapters.models import MaintenanceTicketModel

        model = self._session.scalar(
            select(UserModel).where(
                UserModel.tenant_id == tenant_id,
                UserModel.id == user_id,
            )
        )
        if model is None:
            return False
        self._session.execute(
            update(ConversationModel)
            .where(
                ConversationModel.tenant_id == tenant_id,
                ConversationModel.assigned_user_id == user_id,
            )
            .values(assigned_user_id=None)
        )
        self._session.execute(
            update(LeadDemandModel)
            .where(
                LeadDemandModel.tenant_id == tenant_id,
                LeadDemandModel.responsible_user_id == user_id,
            )
            .values(responsible_user_id=None)
        )
        self._session.execute(
            update(MaintenanceTicketModel)
            .where(
                MaintenanceTicketModel.tenant_id == tenant_id,
                MaintenanceTicketModel.assigned_user_id == user_id,
            )
            .values(assigned_user_id=None)
        )
        self._session.delete(model)
        self._session.commit()
        return True

    def change_password(
        self, tenant_id: UUID, user_id: UUID, *, hashed_password: str
    ) -> User | None:
        model = self._session.scalar(
            select(UserModel).where(
                UserModel.tenant_id == tenant_id,
                UserModel.id == user_id,
            )
        )
        if model is None:
            return None
        model.hashed_password = hashed_password
        model.must_change_password = False
        model.invitation_token_hash = None
        model.invitation_expires_at = None
        model.session_version += 1
        model.updated_at = datetime.now(UTC)
        self._session.commit()
        self._session.refresh(model)
        return _to_domain(model)

    def record_login(self, tenant_id: UUID, user_id: UUID) -> User | None:
        model = self._session.scalar(
            select(UserModel).where(
                UserModel.tenant_id == tenant_id,
                UserModel.id == user_id,
            )
        )
        if model is None:
            return None
        model.last_login_at = datetime.now(UTC)
        self._session.commit()
        self._session.refresh(model)
        return _to_domain(model)

    def add_audit(self, audit: UserAuditLog) -> UserAuditLog:
        model = UserAuditLogModel.from_domain(audit)
        self._session.add(model)
        self._session.commit()
        return audit

    def list_audit(self, tenant_id: UUID, limit: int = 100) -> list[UserAuditLog]:
        models = self._session.scalars(
            select(UserAuditLogModel)
            .where(UserAuditLogModel.tenant_id == tenant_id)
            .order_by(UserAuditLogModel.created_at.desc(), UserAuditLogModel.id.desc())
            .limit(limit)
        ).all()
        return [_audit_to_domain(model) for model in models]
