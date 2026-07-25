from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.users.adapters.models import UserModel
from app.modules.users.domain.entities import User, UserRole, UserStatus
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

    def list(self, tenant_id: UUID) -> list[User]:
        models = self._session.scalars(
            select(UserModel)
            .where(UserModel.tenant_id == tenant_id)
            .order_by(UserModel.created_at, UserModel.id)
        ).all()
        return [_to_domain(model) for model in models]

    def update(
        self,
        tenant_id: UUID,
        user_id: UUID,
        *,
        name: str | None,
        role: UserRole | None,
        status: UserStatus | None,
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
            model.name = name
        if role is not None:
            model.role = role.value
        if status is not None:
            model.status = status.value
        self._session.commit()
        self._session.refresh(model)
        return _to_domain(model)
