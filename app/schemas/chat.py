"""
Chat Conversation and Message Schemas
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


# =====================================================
# Chat Message Schemas
# =====================================================

class ChatMessageCreate(BaseModel):
    """メッセージ作成用スキーマ"""
    content: str = Field(..., min_length=1, max_length=10000)


class ChatMessageResponse(BaseModel):
    """メッセージレスポンス"""
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    token_count: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


# =====================================================
# Chat Conversation Schemas
# =====================================================

class ChatConversationCreate(BaseModel):
    """会話作成用スキーマ"""
    title: Optional[str] = Field(None, max_length=255)


class ChatConversationResponse(BaseModel):
    """会話レスポンス"""
    id: UUID
    meeting_minute_id: UUID
    title: Optional[str] = None
    context_snapshot: Optional[Dict[str, Any]] = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    messages: List[ChatMessageResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class ChatHistoryResponse(BaseModel):
    """チャット履歴レスポンス"""
    conversation_id: Optional[UUID] = None
    meeting_minute_id: UUID
    messages: List[ChatMessageResponse] = Field(default_factory=list)
    total_messages: int = 0


# =====================================================
# Streaming Schemas
# =====================================================

class StreamChunk(BaseModel):
    """ストリーミングチャンクレスポンス"""
    type: str = "chunk"  # chunk, error, done
    content: Optional[str] = None
    message_id: Optional[UUID] = None
    error: Optional[str] = None


class ChatStreamRequest(BaseModel):
    """ストリーミングチャットリクエスト"""
    content: str = Field(..., min_length=1, max_length=10000)
    conversation_id: Optional[UUID] = None  # Noneの場合は新規会話を作成
