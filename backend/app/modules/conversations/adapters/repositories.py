from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.billing_usage.adapters.models import UsageRecordModel
from app.modules.conversations.adapters.models import ConversationModel, MessageModel
from app.modules.conversations.domain.entities import (
    Conversation,
    ConversationChannel,
    ConversationMode,
    ConversationStatus,
    Message,
    MessageAuthor,
    MessageDirection,
)
from app.modules.conversations.ports.repositories import (
    ConversationRepositoryPort,
    InboundRecordResult,
    IncomingMessageData,
)


def _conversation_to_domain(model: ConversationModel) -> Conversation:
    return Conversation(
        id=model.id,
        tenant_id=model.tenant_id,
        channel=ConversationChannel(model.channel),
        external_contact_id=model.external_contact_id,
        phone=model.phone,
        customer_name=model.customer_name,
        status=ConversationStatus(model.status),
        mode=ConversationMode(model.mode),
        current_intent=model.current_intent,
        current_agent=model.current_agent,
        assigned_user_id=model.assigned_user_id,
        started_at=model.started_at,
        last_message_at=model.last_message_at,
        closed_at=model.closed_at,
    )


def _message_to_domain(model: MessageModel) -> Message:
    return Message(
        id=model.id,
        tenant_id=model.tenant_id,
        conversation_id=model.conversation_id,
        channel=ConversationChannel(model.channel),
        direction=MessageDirection(model.direction),
        author_type=MessageAuthor(model.author_type),
        text=model.text,
        attachments=model.attachments,
        external_message_id=model.external_message_id,
        created_at=model.created_at,
    )


class SqlAlchemyConversationRepository(ConversationRepositoryPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def record_inbound(self, tenant_id: UUID, incoming: IncomingMessageData) -> InboundRecordResult:
        self._advisory_lock(f"message:{tenant_id}:{incoming.external_message_id}")
        self._advisory_lock(f"conversation:{tenant_id}:{incoming.channel.value}:{incoming.phone}")
        existing = self._session.scalar(
            select(MessageModel).where(
                MessageModel.tenant_id == tenant_id,
                MessageModel.channel == incoming.channel.value,
                MessageModel.external_message_id == incoming.external_message_id,
            )
        )
        if existing is not None:
            conversation = self._session.scalar(
                select(ConversationModel).where(
                    ConversationModel.tenant_id == tenant_id,
                    ConversationModel.id == existing.conversation_id,
                )
            )
            if conversation is None:  # Protected by the composite foreign key.
                raise RuntimeError("Message conversation is missing")
            self._session.commit()
            return InboundRecordResult(
                conversation=_conversation_to_domain(conversation),
                message=_message_to_domain(existing),
                created=False,
            )

        conversation = self._session.scalar(
            select(ConversationModel).where(
                ConversationModel.tenant_id == tenant_id,
                ConversationModel.channel == incoming.channel.value,
                ConversationModel.phone == incoming.phone,
                ConversationModel.status != ConversationStatus.CLOSED.value,
            )
        )
        conversation_created = conversation is None
        now = datetime.now(UTC)
        if conversation is None:
            conversation = ConversationModel(
                id=uuid4(),
                tenant_id=tenant_id,
                channel=incoming.channel.value,
                external_contact_id=incoming.external_contact_id,
                phone=incoming.phone,
                customer_name=incoming.customer_name,
                status=ConversationStatus.OPEN.value,
                mode=ConversationMode.AI.value,
                current_agent="leads",
                started_at=now,
                last_message_at=now,
            )
            self._session.add(conversation)
            self._session.flush()
        else:
            conversation.last_message_at = now
            conversation.external_contact_id = incoming.external_contact_id
            if incoming.customer_name:
                conversation.customer_name = incoming.customer_name

        message = Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            direction=MessageDirection.INBOUND,
            author_type=MessageAuthor.CUSTOMER,
            text=incoming.text,
            attachments=incoming.attachments,
            external_message_id=incoming.external_message_id,
            channel=incoming.channel,
            created_at=now,
        )
        self._session.add(self._message_model(message))
        self._session.add(self._usage_model(tenant_id, message.id))
        self._session.commit()
        self._session.refresh(conversation)
        return InboundRecordResult(
            conversation=_conversation_to_domain(conversation),
            message=message,
            created=True,
            conversation_created=conversation_created,
        )

    def record_outbound(self, tenant_id: UUID, message: Message) -> Message:
        if message.tenant_id != tenant_id:
            raise ValueError("Message tenant does not match repository scope")
        conversation = self._session.scalar(
            select(ConversationModel).where(
                ConversationModel.tenant_id == tenant_id,
                ConversationModel.id == message.conversation_id,
            )
        )
        if conversation is None:
            raise ValueError("Conversation does not exist in tenant scope")
        conversation.last_message_at = message.created_at
        self._session.add(self._message_model(message))
        self._session.add(self._usage_model(tenant_id, message.id))
        self._session.commit()
        return message

    def list(self, tenant_id: UUID, *, limit: int, offset: int) -> list[Conversation]:
        models = self._session.scalars(
            select(ConversationModel)
            .where(ConversationModel.tenant_id == tenant_id)
            .order_by(ConversationModel.last_message_at.desc(), ConversationModel.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return [_conversation_to_domain(model) for model in models]

    def get_by_id(self, tenant_id: UUID, conversation_id: UUID) -> Conversation | None:
        model = self._session.scalar(
            select(ConversationModel).where(
                ConversationModel.tenant_id == tenant_id,
                ConversationModel.id == conversation_id,
            )
        )
        return _conversation_to_domain(model) if model else None

    def list_messages(self, tenant_id: UUID, conversation_id: UUID) -> list[Message]:
        models = self._session.scalars(
            select(MessageModel)
            .where(
                MessageModel.tenant_id == tenant_id,
                MessageModel.conversation_id == conversation_id,
            )
            .order_by(MessageModel.created_at, MessageModel.id)
        ).all()
        return [_message_to_domain(model) for model in models]

    def update_mode(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        mode: ConversationMode,
        assigned_user_id: UUID | None,
    ) -> Conversation | None:
        model = self._session.scalar(
            select(ConversationModel).where(
                ConversationModel.tenant_id == tenant_id,
                ConversationModel.id == conversation_id,
            )
        )
        if model is None:
            return None
        model.mode = mode.value
        if mode is ConversationMode.HUMAN:
            model.status = ConversationStatus.WAITING_HUMAN.value
            model.assigned_user_id = assigned_user_id
        else:
            model.status = ConversationStatus.OPEN.value
            model.assigned_user_id = None
        self._session.commit()
        self._session.refresh(model)
        return _conversation_to_domain(model)

    def _advisory_lock(self, key: str) -> None:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": key},
        )

    @staticmethod
    def _message_model(message: Message) -> MessageModel:
        return MessageModel(
            id=message.id,
            tenant_id=message.tenant_id,
            conversation_id=message.conversation_id,
            channel=message.channel.value,
            direction=message.direction.value,
            author_type=message.author_type.value,
            text=message.text,
            attachments=message.attachments,
            external_message_id=message.external_message_id,
            created_at=message.created_at,
        )

    @staticmethod
    def _usage_model(tenant_id: UUID, message_id: UUID) -> UsageRecordModel:
        return UsageRecordModel(
            id=uuid4(),
            tenant_id=tenant_id,
            type="message",
            quantity=1,
            module="conversations",
            related_entity_id=message_id,
        )
