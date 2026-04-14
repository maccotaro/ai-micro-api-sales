"""Tests for KB correction service."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.kb_correction import (
    search_kb_terms,
    correct_with_llm,
    run_kb_correction,
)


@pytest.fixture
def mock_minute():
    minute = MagicMock()
    minute.id = uuid.uuid4()
    minute.tenant_id = uuid.uuid4()
    minute.raw_text = "テスト会議のテキスト。ラピニクスの新製品について。"
    minute.minutes_status = "raw"
    minute.version = 1
    minute.created_by = uuid.uuid4()
    minute.parsed_json = None
    minute.status = "draft"
    return minute


class TestSearchKbTerms:
    @pytest.mark.asyncio
    @patch("app.services.kb_correction.httpx.AsyncClient")
    async def test_returns_terms_on_success(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"content": "ラピニクス株式会社\n会社概要"},
                {"content": "TalentHive\nAI採用ツール"},
            ]
        }
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        terms = await search_kb_terms("tenant-1", "test text")
        assert len(terms) == 2
        assert "ラピニクス株式会社" in terms[0]

    @pytest.mark.asyncio
    @patch("app.services.kb_correction.httpx.AsyncClient")
    async def test_returns_empty_on_error(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        terms = await search_kb_terms("tenant-1", "test text")
        assert terms == []


class TestCorrectWithLlm:
    @pytest.mark.asyncio
    @patch("app.services.kb_correction.httpx.AsyncClient")
    async def test_returns_corrected_text(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "修正後のテキスト"}
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await correct_with_llm("元のテキスト", ["用語1", "用語2"])
        assert result == "修正後のテキスト"

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_terms(self):
        result = await correct_with_llm("テキスト", [])
        assert result is None


class TestRunKbCorrection:
    @pytest.mark.asyncio
    @patch("app.services.kb_correction.correct_with_llm", new_callable=AsyncMock)
    @patch("app.services.kb_correction.search_kb_terms", new_callable=AsyncMock)
    async def test_applies_correction(self, mock_search, mock_llm, mock_minute):
        mock_search.return_value = ["ラピニクス"]
        mock_llm.return_value = "補正済みテキスト"

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_minute

        result = await run_kb_correction(mock_minute.id, db)

        assert result is True
        assert mock_minute.corrected_text == "補正済みテキスト"
        assert mock_minute.minutes_status == "corrected"
        assert mock_minute.version == 2
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.kb_correction.search_kb_terms", new_callable=AsyncMock)
    async def test_graceful_degradation_no_kb(self, mock_search, mock_minute):
        """When KB returns no terms, raw_text is copied to corrected_text."""
        mock_search.return_value = []

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_minute

        result = await run_kb_correction(mock_minute.id, db)

        assert result is True
        assert mock_minute.corrected_text == mock_minute.raw_text
        assert mock_minute.minutes_status == "corrected"

    @pytest.mark.asyncio
    @patch("app.services.kb_correction.correct_with_llm", new_callable=AsyncMock)
    @patch("app.services.kb_correction.search_kb_terms", new_callable=AsyncMock)
    async def test_graceful_degradation_llm_failed(self, mock_search, mock_llm, mock_minute):
        """When LLM fails, raw_text is copied to corrected_text."""
        mock_search.return_value = ["term1"]
        mock_llm.return_value = None

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_minute

        result = await run_kb_correction(mock_minute.id, db)

        assert result is True
        assert mock_minute.corrected_text == mock_minute.raw_text
        assert mock_minute.minutes_status == "corrected"

    @pytest.mark.asyncio
    async def test_skips_non_raw_status(self, mock_minute):
        """Records not in 'raw' status are skipped."""
        mock_minute.minutes_status = "corrected"

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_minute

        result = await run_kb_correction(mock_minute.id, db)
        assert result is False
        db.commit.assert_not_called()
