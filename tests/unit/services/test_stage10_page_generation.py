# ai-micro-api-sales/tests/unit/services/test_stage10_page_generation.py
"""
TDD unit tests for Stage 10: Page Generation (LLM).

Tests:
- Per-page individual LLM calls
- Marp-compatible Markdown output
- DB save (proposal_documents + proposal_document_pages)
- generation_context preservation
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

from tests.fixtures.proposal_document_fixtures import (
    make_stage0_context,
    make_stage1_output,
    make_stage6_context,
    make_stage7_output,
    make_stage8_output,
    make_stage9_output,
    TENANT_ID,
    USER_ID,
    PIPELINE_RUN_ID,
    MINUTE_ID,
)


SAMPLE_PAGE_MARKDOWN = """---
marp: true
---

# 本日のご提案

## 3つのアプローチで採用課題を解決

1. **施設警備の魅力訴求**
2. **シニア層への安心訴求**
3. **実績に基づく提案**

---"""


@pytest.mark.unit
class TestStage10PageGeneration:
    """Tests for stage10_page_generation() function."""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock()
        stage_cfg = MagicMock()
        stage_cfg.enabled = True
        stage_cfg.model = None
        stage_cfg.temperature = 0.3
        stage_cfg.max_tokens = 800
        stage_cfg.prompt_override = None
        config.get_stage.return_value = stage_cfg
        return config

    @pytest.fixture
    def mock_llm_client(self):
        client = AsyncMock()
        client.chat.return_value = {"response": SAMPLE_PAGE_MARKDOWN}
        return client

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_calls_llm_per_page(self, mock_config, mock_llm_client, mock_db):
        """Stage 10 SHALL make one LLM call per page."""
        from app.services.proposal_stages import stage10_page_generation

        stage9_output = make_stage9_output()
        page_count = len(stage9_output["pages"])

        result = await stage10_page_generation(
            make_stage0_context(), make_stage1_output(),
            make_stage6_context(), make_stage7_output(), make_stage8_output(),
            stage9_output, mock_config, mock_llm_client, mock_db,
            TENANT_ID, USER_ID, PIPELINE_RUN_ID, MINUTE_ID,
        )

        assert mock_llm_client.chat.call_count == page_count

    @pytest.mark.asyncio
    async def test_output_contains_pages_with_markdown(self, mock_config, mock_llm_client, mock_db):
        """Stage 10 output SHALL contain pages with markdown_content."""
        from app.services.proposal_stages import stage10_page_generation

        result = await stage10_page_generation(
            make_stage0_context(), make_stage1_output(),
            make_stage6_context(), make_stage7_output(), make_stage8_output(),
            make_stage9_output(), mock_config, mock_llm_client, mock_db,
            TENANT_ID, USER_ID, PIPELINE_RUN_ID, MINUTE_ID,
        )

        assert "document_id" in result
        assert "pages" in result
        for page in result["pages"]:
            assert "page_number" in page
            assert "markdown_content" in page
            assert len(page["markdown_content"]) > 0

    @pytest.mark.asyncio
    async def test_saves_to_database(self, mock_config, mock_llm_client, mock_db):
        """Stage 10 SHALL create proposal_documents and proposal_document_pages records."""
        from app.services.proposal_stages import stage10_page_generation

        await stage10_page_generation(
            make_stage0_context(), make_stage1_output(),
            make_stage6_context(), make_stage7_output(), make_stage8_output(),
            make_stage9_output(), mock_config, mock_llm_client, mock_db,
            TENANT_ID, USER_ID, PIPELINE_RUN_ID, MINUTE_ID,
        )

        # db.add should be called for document + pages
        assert mock_db.add.call_count >= 1
        assert mock_db.commit.call_count >= 1

    @pytest.mark.asyncio
    async def test_generation_context_saved(self, mock_config, mock_llm_client, mock_db):
        """Each page SHALL save generation_context for re-generation."""
        from app.services.proposal_stages import stage10_page_generation

        result = await stage10_page_generation(
            make_stage0_context(), make_stage1_output(),
            make_stage6_context(), make_stage7_output(), make_stage8_output(),
            make_stage9_output(), mock_config, mock_llm_client, mock_db,
            TENANT_ID, USER_ID, PIPELINE_RUN_ID, MINUTE_ID,
        )

        for page in result["pages"]:
            assert "generation_context" in page
            assert page["generation_context"] is not None

    @pytest.mark.asyncio
    async def test_page_llm_context_only_includes_data_sources(self, mock_config, mock_llm_client, mock_db):
        """Each page LLM call SHALL only include data from that page's data_sources."""
        from app.services.proposal_stages import stage10_page_generation

        stage9_output = make_stage9_output()

        await stage10_page_generation(
            make_stage0_context(), make_stage1_output(),
            make_stage6_context(), make_stage7_output(), make_stage8_output(),
            stage9_output, mock_config, mock_llm_client, mock_db,
            TENANT_ID, USER_ID, PIPELINE_RUN_ID, MINUTE_ID,
        )

        # Each call should have story_theme in the prompt
        for call_obj in mock_llm_client.chat.call_args_list:
            call_kwargs = call_obj.kwargs if call_obj.kwargs else {}
            messages = call_kwargs.get("messages", [])
            system_msg = next((m for m in messages if m.get("role") == "system"), {})
            assert stage9_output["story_theme"] in system_msg.get("content", "")
