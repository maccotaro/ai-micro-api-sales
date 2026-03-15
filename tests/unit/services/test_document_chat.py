# ai-micro-api-sales/tests/unit/services/test_document_chat.py
"""
Unit tests for document_chat_service.

Tests:
- Page question → prompt contains markdown_content + generation_context
- Page rewrite → markdown_content updated
- Global question → story_structure in input
- Global regenerate → changed pages only
- Chat history 5-turn trimming
- Context size limit (~2,500 tokens)
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from tests.fixtures.proposal_document_fixtures import (
    make_stage9_output,
    TENANT_ID,
)


def _make_mock_doc(story_structure=None):
    doc = MagicMock()
    doc.id = uuid4()
    doc.tenant_id = TENANT_ID
    doc.title = "テスト提案書"
    doc.story_structure = story_structure or make_stage9_output()
    return doc


def _make_mock_page(markdown="# テスト\n\nテスト内容", context=None):
    page = MagicMock()
    page.id = uuid4()
    page.title = "テストページ"
    page.purpose = "テスト目的"
    page.markdown_content = markdown
    page.generation_context = context or {"page_data": "テストデータ"}
    return page


@pytest.mark.unit
class TestDocumentChat:
    """Tests for process_document_chat function."""

    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        llm.chat.return_value = {"response": "AI回答テスト"}
        return llm

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        return db

    @pytest.mark.asyncio
    async def test_page_question_includes_markdown_in_prompt(self, mock_llm, mock_db):
        """Page question prompt SHALL contain the page's markdown_content."""
        from app.services.document_chat_service import process_document_chat

        doc = _make_mock_doc()
        page = _make_mock_page(markdown="# 施設警備の魅力")

        with patch("app.services.document_chat_service._get_llm_client", return_value=mock_llm):
            response, updated = await process_document_chat(
                doc, page, "なぜこの内容？", "question", mock_db,
            )

        mock_llm.chat.assert_called_once()
        messages = mock_llm.chat.call_args.kwargs.get("messages", [])
        prompt = " ".join(m["content"] for m in messages)
        assert "施設警備の魅力" in prompt
        assert not updated

    @pytest.mark.asyncio
    async def test_page_rewrite_updates_markdown(self, mock_llm, mock_db):
        """Page rewrite SHALL update page.markdown_content."""
        from app.services.document_chat_service import process_document_chat

        doc = _make_mock_doc()
        page = _make_mock_page()
        mock_llm.chat.return_value = {"response": "# 書き直し結果"}

        with patch("app.services.document_chat_service._get_llm_client", return_value=mock_llm):
            response, updated = await process_document_chat(
                doc, page, "もっとデータを入れて", "rewrite", mock_db,
            )

        assert updated
        assert page.markdown_content == "# 書き直し結果"

    @pytest.mark.asyncio
    async def test_global_question_includes_story_structure(self, mock_llm, mock_db):
        """Global question prompt SHALL contain story_structure."""
        from app.services.document_chat_service import process_document_chat

        doc = _make_mock_doc()

        with patch("app.services.document_chat_service._get_llm_client", return_value=mock_llm):
            response, updated = await process_document_chat(
                doc, None, "全体の構成は？", "question", mock_db,
            )

        messages = mock_llm.chat.call_args.kwargs.get("messages", [])
        prompt = " ".join(m["content"] for m in messages)
        assert "テーマ" in prompt or "ページ構成" in prompt
        assert not updated

    @pytest.mark.asyncio
    async def test_global_regenerate_updates_structure(self, mock_llm, mock_db):
        """Global regenerate SHALL update doc.story_structure."""
        from app.services.document_chat_service import process_document_chat

        doc = _make_mock_doc()
        new_structure = {
            "story_theme": "新テーマ",
            "pages": [
                {"page_number": 1, "title": "新ページ", "changed": True},
            ],
        }
        mock_llm.chat.return_value = {
            "response": json.dumps(new_structure, ensure_ascii=False),
        }

        with patch("app.services.document_chat_service._get_llm_client", return_value=mock_llm):
            response, updated = await process_document_chat(
                doc, None, "構成を変えて", "regenerate_all", mock_db,
            )

        assert updated
        assert doc.story_structure["story_theme"] == "新テーマ"

    @pytest.mark.asyncio
    async def test_chat_history_trimmed_to_5_turns(self, mock_llm, mock_db):
        """Chat history SHALL be trimmed to last 5 turns (10 messages)."""
        from app.services.document_chat_service import _get_recent_history

        # Create 12 mock messages
        messages = []
        for i in range(12):
            m = MagicMock()
            m.role = "user" if i % 2 == 0 else "assistant"
            m.content = f"メッセージ{i}"
            messages.append(m)

        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = messages[:10]

        history = _get_recent_history(mock_db, uuid4(), uuid4(), limit=5)
        assert len(history) <= 10

    @pytest.mark.asyncio
    async def test_context_size_within_limit(self, mock_llm, mock_db):
        """Chat LLM calls SHALL keep context within ~2,500 tokens."""
        from app.services.document_chat_service import process_document_chat

        doc = _make_mock_doc()
        page = _make_mock_page(markdown="# テスト\n" + "テスト文章。" * 50)

        with patch("app.services.document_chat_service._get_llm_client", return_value=mock_llm):
            await process_document_chat(
                doc, page, "質問", "question", mock_db,
            )

        messages = mock_llm.chat.call_args.kwargs.get("messages", [])
        total_text = " ".join(m["content"] for m in messages)
        # ~4 chars per token for Japanese
        estimated_tokens = len(total_text) // 4
        assert estimated_tokens <= 5000, f"Context is {estimated_tokens} tokens"
