"""Service for proposal document chat (page-level and document-level).

Handles question answering, page rewriting, and story structure regeneration.
Separate from proposal_chat_service.py which handles the media RAG chat.
"""
import json
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.model_settings_client import get_chat_num_ctx
from app.utils.markdown_table_fixer import fix_markdown_tables
from app.models.proposal_document import (
    ProposalDocument, ProposalDocumentPage, ProposalDocumentChat,
)
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

_llm_client = None


def _get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient(
            base_url=settings.llm_service_url,
            secret=settings.internal_api_secret,
            timeout=120.0,
        )
    return _llm_client


async def process_document_chat(
    doc: ProposalDocument,
    page: Optional[ProposalDocumentPage],
    user_message: str,
    action_type: str,
    db: Session,
) -> tuple[str, bool]:
    """Process a chat message and return (response_text, was_updated)."""
    llm = _get_llm_client()

    if action_type == "question" and page:
        return await _handle_page_question(doc, page, user_message, llm, db)
    elif action_type == "rewrite" and page:
        return await _handle_page_rewrite(doc, page, user_message, llm, db)
    elif action_type == "question" and not page:
        return await _handle_global_question(doc, user_message, llm, db)
    elif action_type == "regenerate_all" and not page:
        return await _handle_global_regenerate(doc, user_message, llm, db)
    else:
        return "不正なリクエストです。", False


async def _handle_page_question(
    doc: ProposalDocument,
    page: ProposalDocumentPage,
    question: str,
    llm: LLMClient,
    db: Session,
) -> tuple[str, bool]:
    """Answer a question about a specific page."""
    context = page.generation_context or {}
    prompt = f"""以下の提案書ページについて質問に回答してください。

## ページ情報
- タイトル: {page.title}
- 目的: {page.purpose}

## ページ内容
{page.markdown_content}

## 使用データソース
{json.dumps(context.get('page_data', ''), ensure_ascii=False)[:800]}

## 質問
{question}

根拠データに基づいて、なぜこの内容にしたかを説明してください。"""

    history = _get_recent_history(db, doc.id, page.id, limit=5)
    messages = _build_messages(prompt, history)

    result = await llm.chat(
        messages=messages,
        service_name="api-sales",
        temperature=0.3,
        tenant_id=str(doc.tenant_id),
        provider_options={"num_ctx": get_chat_num_ctx()},
    )
    return result.get("response", "回答を生成できませんでした。"), False


async def _handle_page_rewrite(
    doc: ProposalDocument,
    page: ProposalDocumentPage,
    instruction: str,
    llm: LLMClient,
    db: Session,
) -> tuple[str, bool]:
    """Rewrite a page based on user instruction."""
    context = page.generation_context or {}
    story_theme = doc.story_structure.get("story_theme", "")

    prompt = f"""以下の提案書ページを、ユーザーの指示に従って書き直してください。

## 提案書テーマ
{story_theme}

## 現在のページ
- タイトル: {page.title}
- 目的: {page.purpose}

## 現在の内容
{page.markdown_content}

## 使用データ
{json.dumps(context.get('page_data', ''), ensure_ascii=False)[:800]}

## ユーザーの指示
{instruction}

書き直したMarkdownのみを出力してください。"""

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "指示に従ってページを書き直してください。Markdownのみ出力。"},
    ]

    result = await llm.chat(
        messages=messages,
        service_name="api-sales",
        temperature=0.3,
        tenant_id=str(doc.tenant_id),
        provider_options={"num_ctx": get_chat_num_ctx()},
    )

    new_markdown = result.get("response", "")
    if new_markdown:
        page.markdown_content = fix_markdown_tables(new_markdown)
        db.commit()
        return f"ページを更新しました。\n\n{new_markdown}", True
    return "ページの書き直しに失敗しました。", False


async def _handle_global_question(
    doc: ProposalDocument,
    question: str,
    llm: LLMClient,
    db: Session,
) -> tuple[str, bool]:
    """Answer a question about the overall proposal."""
    story = doc.story_structure or {}
    pages_summary = "\n".join(
        f"- ページ{p.get('page_number', '?')}: {p.get('title', '')} ({p.get('purpose', '')})"
        for p in story.get("pages", [])
    )

    prompt = f"""以下の提案書全体について質問に回答してください。

## テーマ
{story.get('story_theme', '')}

## ページ構成
{pages_summary}

## 質問
{question}"""

    history = _get_recent_history(db, doc.id, None, limit=5)
    messages = _build_messages(prompt, history)

    result = await llm.chat(
        messages=messages,
        service_name="api-sales",
        temperature=0.3,
        tenant_id=str(doc.tenant_id),
        provider_options={"num_ctx": get_chat_num_ctx()},
    )
    return result.get("response", "回答を生成できませんでした。"), False


async def _handle_global_regenerate(
    doc: ProposalDocument,
    instruction: str,
    llm: LLMClient,
    db: Session,
) -> tuple[str, bool]:
    """Regenerate story structure based on instruction."""
    story = doc.story_structure or {}

    prompt = f"""以下の提案書のストーリー構成を、ユーザーの指示に従って変更してください。

## 現在のテーマ
{story.get('story_theme', '')}

## 現在のページ構成
{json.dumps(story.get('pages', []), ensure_ascii=False)}

## ユーザーの指示
{instruction}

変更後のストーリー構成をJSON形式で出力してください。
変更が必要なページには "changed": true を付けてください。"""

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "指示に従って構成を変更。JSON形式で出力。"},
    ]

    result = await llm.chat(
        messages=messages,
        service_name="api-sales",
        temperature=0.3,
        tenant_id=str(doc.tenant_id),
        provider_options={"num_ctx": get_chat_num_ctx()},
    )

    response_text = result.get("response", "")
    try:
        from app.services.pipeline_helpers import parse_json_response
        new_structure = parse_json_response(response_text)
        if "pages" in new_structure:
            doc.story_structure = new_structure
            db.commit()
            changed = sum(1 for p in new_structure["pages"] if p.get("changed"))
            return f"構成を更新しました。{changed}ページが変更対象です。", True
    except Exception as e:
        logger.warning("Failed to parse regenerated structure: %s", e)

    return "構成の変更に失敗しました。", False


def _get_recent_history(
    db: Session, document_id: UUID, page_id: Optional[UUID], limit: int = 5,
) -> list[dict]:
    """Get recent chat messages for context."""
    query = db.query(ProposalDocumentChat).filter(
        ProposalDocumentChat.document_id == document_id,
    )
    if page_id:
        query = query.filter(ProposalDocumentChat.page_id == page_id)
    else:
        query = query.filter(ProposalDocumentChat.page_id.is_(None))

    messages = query.order_by(
        ProposalDocumentChat.created_at.desc()
    ).limit(limit * 2).all()

    return [{"role": m.role, "content": m.content} for m in reversed(messages)]


def _build_messages(system_prompt: str, history: list[dict]) -> list[dict]:
    """Build message list with system prompt and trimmed history."""
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-10:])
    return messages
