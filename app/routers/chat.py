"""
Chat Router

API endpoints for AI chat functionality on meeting minutes.
Provides streaming chat with Server-Sent Events (SSE).
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import require_sales_access
from app.models.meeting import MeetingMinute
from app.schemas.chat import (
    ChatStreamRequest,
    ChatHistoryResponse,
)
from app.services.chat_service import chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meeting-minutes", tags=["chat"])


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

    Example usage with JavaScript:
    ```javascript
    const response = await fetch('/api/sales/meeting-minutes/{id}/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: 'この顧客の課題は？' })
    });
    const reader = response.body.getReader();
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        // Parse SSE data
    }
    ```
    """
    user_id = UUID(current_user["user_id"])

    # Verify access to meeting minute
    minute = db.query(MeetingMinute).filter(
        MeetingMinute.id == minute_id,
        MeetingMinute.created_by == user_id,
    ).first()

    if not minute:
        raise HTTPException(status_code=404, detail="Meeting minute not found")

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
    """
    Get chat history for a meeting minute.

    Returns all messages in the current conversation for this meeting minute.
    """
    user_id = UUID(current_user["user_id"])

    # Verify access to meeting minute
    minute = db.query(MeetingMinute).filter(
        MeetingMinute.id == minute_id,
        MeetingMinute.created_by == user_id,
    ).first()

    if not minute:
        raise HTTPException(status_code=404, detail="Meeting minute not found")

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
    """
    Clear all chat history for a meeting minute.

    This will delete all conversations and messages associated with this meeting minute.
    """
    user_id = UUID(current_user["user_id"])

    # Verify access to meeting minute
    minute = db.query(MeetingMinute).filter(
        MeetingMinute.id == minute_id,
        MeetingMinute.created_by == user_id,
    ).first()

    if not minute:
        raise HTTPException(status_code=404, detail="Meeting minute not found")

    deleted = await chat_service.clear_chat_history(
        meeting_minute_id=minute_id,
        user_id=user_id,
        db=db,
    )

    if deleted:
        return {"message": "Chat history cleared successfully"}
    else:
        return {"message": "No chat history to clear"}
