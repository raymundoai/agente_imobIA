from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select, text
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
from app.modules.messaging.models import MessageJobModel


def _conversation_to_domain(model: ConversationModel) -> Conversation:
    return Conversation(
        id=model.id,
        tenant_id=model.tenant_id,
        contact_id=model.contact_id,
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
        is_group=model.is_group,
        group_name=model.group_name,
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
        sender_external_id=model.sender_external_id,
        sender_name=model.sender_name,
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

        identity_conditions = [
            ConversationModel.external_contact_id == incoming.external_contact_id
        ]
        if not incoming.is_group:
            identity_conditions.append(
                (ConversationModel.phone == incoming.phone)
                & (ConversationModel.is_group.is_(False))
            )
        conversation = self._session.scalar(
            select(ConversationModel).where(
                ConversationModel.tenant_id == tenant_id,
                ConversationModel.channel == incoming.channel.value,
                or_(*identity_conditions),
                ConversationModel.status != ConversationStatus.CLOSED.value,
            )
        )
        conversation_created = conversation is None
        now = datetime.now(UTC)
        if conversation is None:
            conversation = ConversationModel(
                id=uuid4(),
                tenant_id=tenant_id,
                contact_id=incoming.contact_id,
                channel=incoming.channel.value,
                external_contact_id=incoming.external_contact_id,
                phone=incoming.phone,
                customer_name=incoming.customer_name,
                status=(
                    ConversationStatus.WAITING_HUMAN.value
                    if incoming.is_group
                    else ConversationStatus.OPEN.value
                ),
                mode=(
                    ConversationMode.HUMAN.value
                    if incoming.is_group
                    else ConversationMode.AI.value
                ),
                current_agent="leads",
                is_group=incoming.is_group,
                group_name=incoming.group_name,
                started_at=now,
                last_message_at=now,
            )
            self._session.add(conversation)
            self._session.flush()
        else:
            conversation.last_message_at = now
            conversation.contact_id = incoming.contact_id or conversation.contact_id
            conversation.external_contact_id = incoming.external_contact_id
            if incoming.customer_name:
                conversation.customer_name = incoming.customer_name
            if incoming.group_name:
                conversation.group_name = incoming.group_name
            if (
                incoming.direction is MessageDirection.OUTBOUND
                and incoming.author_type is MessageAuthor.HUMAN
                and not incoming.is_group
            ):
                conversation.mode = ConversationMode.HUMAN.value
                conversation.status = ConversationStatus.WAITING_HUMAN.value

        message = Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            direction=incoming.direction,
            author_type=incoming.author_type,
            text=incoming.text,
            attachments=incoming.attachments,
            external_message_id=incoming.external_message_id,
            channel=incoming.channel,
            created_at=now,
            sender_external_id=incoming.sender_external_id,
            sender_name=incoming.sender_name,
        )
        self._session.add(self._message_model(message))
        if incoming.record_usage:
            self._session.add(self._usage_model(tenant_id, message.id))
        job_id = None
        if incoming.enqueue_auto_reply:
            pending_job = self._session.scalar(
                select(MessageJobModel).where(
                    MessageJobModel.tenant_id == tenant_id,
                    MessageJobModel.conversation_id == conversation.id,
                    MessageJobModel.status == "received",
                    MessageJobModel.stage == "generation",
                )
            )
            available_at = now + timedelta(seconds=incoming.debounce_seconds)
            if pending_job is not None:
                pending_job.message_id = message.id
                pending_job.available_at = available_at
                pending_job.max_attempts = incoming.max_attempts
                pending_job.send_to_channel = incoming.send_to_channel
                pending_job.updated_at = now
                job_id = pending_job.id
            else:
                job_id = uuid4()
                self._session.add(MessageJobModel(
                    id=job_id,
                    tenant_id=tenant_id,
                    conversation_id=conversation.id,
                    message_id=message.id,
                    channel=incoming.channel.value,
                    status="received",
                    attempts=0,
                    max_attempts=incoming.max_attempts,
                    send_to_channel=incoming.send_to_channel,
                    available_at=available_at,
                    result={},
                ))
        self._session.commit()
        self._session.refresh(conversation)
        return InboundRecordResult(
            conversation=_conversation_to_domain(conversation),
            message=message,
            created=True,
            conversation_created=conversation_created,
            job_id=job_id,
        )

    def record_outbound(
        self, tenant_id: UUID, message: Message, *, commit: bool = True
    ) -> Message:
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
        if commit:
            self._session.commit()
        else:
            self._session.flush()
        return message

    def list(self, tenant_id: UUID, *, limit: int, offset: int) -> list[Conversation]:
        models = self._session.scalars(
            select(ConversationModel)
            .where(ConversationModel.tenant_id == tenant_id)
            .order_by(ConversationModel.last_message_at.desc(), ConversationModel.id)
            .limit(limit)
            .offset(offset)
        ).all()
        conversations = [_conversation_to_domain(model) for model in models]
        if not conversations:
            return conversations
        latest_messages = self._session.scalars(
            select(MessageModel)
            .where(
                MessageModel.tenant_id == tenant_id,
                MessageModel.conversation_id.in_([item.id for item in conversations]),
            )
            .distinct(MessageModel.conversation_id)
            .order_by(
                MessageModel.conversation_id,
                MessageModel.created_at.desc(),
                MessageModel.id.desc(),
            )
        ).all()
        latest_by_conversation = {
            message.conversation_id: message for message in latest_messages
        }
        for conversation in conversations:
            latest = latest_by_conversation.get(conversation.id)
            if latest is not None:
                conversation.last_message_text = latest.text
                conversation.last_message_attachments = latest.attachments
                conversation.last_message_direction = MessageDirection(latest.direction)
        return conversations

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
        *,
        commit: bool = True,
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
        if commit:
            self._session.commit()
            self._session.refresh(model)
        else:
            self._session.flush()
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
            sender_external_id=message.sender_external_id,
            sender_name=message.sender_name,
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
