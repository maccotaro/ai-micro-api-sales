"""
Chat Conversation and Message Models for AI Dialog Feature
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Column, String, Text, Integer,
    TIMESTAMP, ForeignKey, Index, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.db.session import SalesDBBase


class ChatConversation(SalesDBBase):
    """チャット会話セッション"""
    __tablename__ = "chat_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    meeting_minute_id = Column(
        UUID(as_uuid=True),
        ForeignKey("meeting_minutes.id", ondelete="CASCADE"),
        nullable=False
    )
    title = Column(String(255))
    context_snapshot = Column(JSONB)  # 会話開始時の解析結果スナップショット
    tenant_id = Column(UUID(as_uuid=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    meeting_minute = relationship("MeetingMinute", backref="chat_conversations")
    messages = relationship("ChatMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="ChatMessage.created_at")

    __table_args__ = (
        Index("idx_chat_conversations_minute_id", "meeting_minute_id"),
        Index("idx_chat_conversations_created_by", "created_by"),
        Index("idx_chat_conversations_updated_at", "updated_at"),
    )


class ChatMessage(SalesDBBase):
    """チャットメッセージ"""
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        nullable=False
    )
    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    token_count = Column(Integer)
    message_metadata = Column(JSONB)  # 'metadata' is reserved in SQLAlchemy
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    conversation = relationship("ChatConversation", back_populates="messages")

    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="ck_chat_messages_role"
        ),
        Index("idx_chat_messages_conversation_id", "conversation_id"),
        Index("idx_chat_messages_created_at", "created_at"),
    )
