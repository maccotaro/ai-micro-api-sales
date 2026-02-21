"""
Chat Router

API endpoints for AI chat functionality on meeting minutes.
Provides streaming chat with Server-Sent Events (SSE).
Tenant isolation: verifies access to parent meeting minute.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import require_sales_access, check_tenant_access
from app.models.meeting import MeetingMinute
from app.schemas.chat import (
    ChatStreamRequest,
    ChatHistoryResponse,
)
from app.services.chat_service import chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meeting-minutes", tags=["chat"])


def _get_minute_for_chat(
    db: Session, minute_id: UUID, current_user: dict
) -> MeetingMinute:
    """Get a meeting minute with tenant access check for chat operations."""
    minute = db.query(MeetingMinute).filter(MeetingMinute.id == minute_id).first()

    if not minute:
        raise HTTPException(status_code=404, detail="Meeting minute not found")

    if not check_tenant_access(
        str(minute.tenant_id) if minute.tenant_id else None,
        current_user,
        allow_none=False,
    ):
        user_id = UUID(current_user["user_id"])
        if minute.tenant_id is None and minute.created_by == user_id:
            return minute
        raise HTTPException(status_code=403, detail="Access denied: resource belongs to different tenant")

    return minute


@router.post("/{minute_id}/chat")
async def stream_chat(
    minute_id: UUID,
    request: ChatStreamRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """
    Stream AI chat response for a meeting minute.

    Returns Server-Sent Events (SSE) stream with the following event types:
    - `start`: Contains conversation_id and message_id
    - `chunk`: Contains content chunk
    - `done`: Indicates completion with final message_id
    - `error`: Contains error message if something went wrong
    """
    minute = _get_minute_for_chat(db, minute_id, current_user)
    user_id = UUID(current_user["user_id"])

    # Check if meeting is analyzed
    if minute.status == "draft":
        raise HTTPException(
            status_code=400,
            detail="Meeting minute must be analyzed before chatting. Run analysis first."
        )

    return StreamingResponse(
        chat_service.stream_chat(
            meeting_minute_id=minute_id,
            user_message=request.content,
            user_id=user_id,
            db=db,
            conversation_id=request.conversation_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/{minute_id}/chat/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    minute_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """Get chat history for a meeting minute."""
    minute = _get_minute_for_chat(db, minute_id, current_user)
    user_id = UUID(current_user["user_id"])

    history = await chat_service.get_chat_history(
        meeting_minute_id=minute_id,
        user_id=user_id,
        db=db,
    )

    return history


@router.delete("/{minute_id}/chat")
async def clear_chat_history(
    minute_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sales_access),
):
    """Clear all chat history for a meeting minute."""
    minute = _get_minute_for_chat(db, minute_id, current_user)
    user_id = UUID(current_user["user_id"])

    deleted = await chat_service.clear_chat_history(
        meeting_minute_id=minute_id,
        user_id=user_id,
        db=db,
    )

    if deleted:
        return {"message": "Chat history cleared successfully"}
    else:
        return {"message": "No chat history to clear"}
