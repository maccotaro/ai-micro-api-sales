"""
Chat Service for AI Dialog Feature

Provides streaming chat functionality with context from meeting minutes analysis.
"""
import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any, List, AsyncGenerator
from uuid import UUID, uuid4

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.meeting import MeetingMinute
from app.models.chat import ChatConversation, ChatMessage
from app.schemas.chat import ChatMessageResponse, ChatHistoryResponse

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_TEMPLATE = """あなたは営業支援AIアシスタントです。以下の議事録情報を基に、営業担当者の質問に答えてください。

## 議事録情報
会社名: {company_name}
業種: {industry}
地域: {area}
商談日: {meeting_date}

## 解析結果
{analysis_summary}

## 指示
- 議事録の内容に基づいて具体的に回答してください
- 不明な点は正直に「情報がありません」と答えてください
- 営業活動に役立つ提案や洞察を提供してください
- 日本語で回答してください
"""


class ChatService:
    """Chat service with streaming LLM responses."""

    def __init__(self):
        self.llm = ChatOllama(
            model=settings.default_llm_model,
            base_url=settings.ollama_base_url,
            temperature=0.5,
        )

    def _build_system_prompt(self, meeting: MeetingMinute) -> str:
        """Build system prompt from meeting minute context."""
        analysis = meeting.parsed_json or {}

        # Build analysis summary
        issues = analysis.get("issues", [])
        needs = analysis.get("needs", [])
        keywords = analysis.get("keywords", [])
        summary = analysis.get("summary", "解析結果なし")

        analysis_parts = [f"要約: {summary}"]

        if issues:
            issue_list = "\n".join([f"  - {i.get('issue', '')} ({i.get('priority', 'medium')})" for i in issues[:5]])
            analysis_parts.append(f"課題:\n{issue_list}")

        if needs:
            need_list = "\n".join([f"  - {n.get('need', '')} ({n.get('urgency', 'medium')})" for n in needs[:5]])
            analysis_parts.append(f"ニーズ:\n{need_list}")

        if keywords:
            analysis_parts.append(f"キーワード: {', '.join(keywords[:10])}")

        analysis_summary = "\n\n".join(analysis_parts)

        return SYSTEM_PROMPT_TEMPLATE.format(
            company_name=meeting.company_name,
            industry=meeting.industry or "不明",
            area=meeting.area or "不明",
            meeting_date=meeting.meeting_date.isoformat() if meeting.meeting_date else "不明",
            analysis_summary=analysis_summary,
        )

    def _build_messages(
        self,
        system_prompt: str,
        history: List[ChatMessage],
        user_message: str,
        max_history: int = 10,
    ) -> List:
        """Build message list for LLM from conversation history."""
        messages = [SystemMessage(content=system_prompt)]

        # Add recent history (limit to prevent context overflow)
        recent_history = history[-max_history:] if len(history) > max_history else history

        for msg in recent_history:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                messages.append(AIMessage(content=msg.content))

        # Add current user message
        messages.append(HumanMessage(content=user_message))

        return messages

    async def get_or_create_conversation(
        self,
        meeting_minute_id: UUID,
        user_id: UUID,
        db: Session,
    ) -> ChatConversation:
        """Get existing conversation or create new one for meeting minute."""
        # Find existing active conversation
        conversation = db.query(ChatConversation).filter(
            ChatConversation.meeting_minute_id == meeting_minute_id,
            ChatConversation.created_by == user_id,
        ).order_by(ChatConversation.updated_at.desc()).first()

        if conversation:
            return conversation

        # Get meeting minute for context
        meeting = db.query(MeetingMinute).filter(
            MeetingMinute.id == meeting_minute_id
        ).first()

        if not meeting:
            raise ValueError(f"Meeting minute not found: {meeting_minute_id}")

        # Create new conversation with context snapshot
        conversation = ChatConversation(
            id=uuid4(),
            meeting_minute_id=meeting_minute_id,
            title=f"{meeting.company_name} - 対話",
            context_snapshot={
                "company_name": meeting.company_name,
                "industry": meeting.industry,
                "area": meeting.area,
                "parsed_json": meeting.parsed_json,
            },
            created_by=user_id,
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

        return conversation

    async def stream_chat(
        self,
        meeting_minute_id: UUID,
        user_message: str,
        user_id: UUID,
        db: Session,
        conversation_id: Optional[UUID] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat response for a meeting minute.

        Yields SSE-formatted chunks.
        """
        try:
            # Get or create conversation
            if conversation_id:
                conversation = db.query(ChatConversation).filter(
                    ChatConversation.id == conversation_id,
                    ChatConversation.created_by == user_id,
                ).first()
                if not conversation:
                    raise ValueError(f"Conversation not found: {conversation_id}")
            else:
                conversation = await self.get_or_create_conversation(
                    meeting_minute_id, user_id, db
                )

            # Get meeting minute for context
            meeting = db.query(MeetingMinute).filter(
                MeetingMinute.id == meeting_minute_id
            ).first()

            if not meeting:
                raise ValueError(f"Meeting minute not found: {meeting_minute_id}")

            # Save user message
            user_msg = ChatMessage(
                id=uuid4(),
                conversation_id=conversation.id,
                role="user",
                content=user_message,
            )
            db.add(user_msg)
            db.commit()

            # Build messages for LLM
            system_prompt = self._build_system_prompt(meeting)
            history = list(conversation.messages)
            messages = self._build_messages(system_prompt, history, user_message)

            # Stream response
            full_response = ""
            assistant_msg_id = uuid4()

            # Send conversation_id first
            yield f"data: {json.dumps({'type': 'start', 'conversation_id': str(conversation.id), 'message_id': str(assistant_msg_id)})}\n\n"

            async for chunk in self.llm.astream(messages):
                if chunk.content:
                    full_response += chunk.content
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk.content})}\n\n"

            # Save assistant message
            assistant_msg = ChatMessage(
                id=assistant_msg_id,
                conversation_id=conversation.id,
                role="assistant",
                content=full_response,
                token_count=len(full_response.split()),  # Rough estimate
            )
            db.add(assistant_msg)

            # Update conversation timestamp
            conversation.updated_at = datetime.utcnow()
            db.commit()

            # Send done signal
            yield f"data: {json.dumps({'type': 'done', 'message_id': str(assistant_msg_id)})}\n\n"

        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    async def get_chat_history(
        self,
        meeting_minute_id: UUID,
        user_id: UUID,
        db: Session,
    ) -> ChatHistoryResponse:
        """Get chat history for a meeting minute."""
        # Find conversation
        conversation = db.query(ChatConversation).filter(
            ChatConversation.meeting_minute_id == meeting_minute_id,
            ChatConversation.created_by == user_id,
        ).order_by(ChatConversation.updated_at.desc()).first()

        if not conversation:
            return ChatHistoryResponse(
                conversation_id=None,
                meeting_minute_id=meeting_minute_id,
                messages=[],
                total_messages=0,
            )

        messages = [
            ChatMessageResponse(
                id=msg.id,
                conversation_id=msg.conversation_id,
                role=msg.role,
                content=msg.content,
                token_count=msg.token_count,
                metadata=msg.message_metadata,
                created_at=msg.created_at,
            )
            for msg in conversation.messages
        ]

        return ChatHistoryResponse(
            conversation_id=conversation.id,
            meeting_minute_id=meeting_minute_id,
            messages=messages,
            total_messages=len(messages),
        )

    async def clear_chat_history(
        self,
        meeting_minute_id: UUID,
        user_id: UUID,
        db: Session,
    ) -> bool:
        """Clear all chat history for a meeting minute."""
        # Delete all conversations for this meeting minute
        deleted = db.query(ChatConversation).filter(
            ChatConversation.meeting_minute_id == meeting_minute_id,
            ChatConversation.created_by == user_id,
        ).delete()

        db.commit()

        return deleted > 0


# Singleton instance
chat_service = ChatService()
