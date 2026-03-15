# ai-micro-api-sales/tests/unit/services/test_stage9_story_structure.py
"""
TDD unit tests for Stage 9: Story Structure (LLM).

Tests:
- Story structure output validation (story_theme, pages[])
- Page count range (5-10)
- data_sources mapping validation
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from tests.fixtures.proposal_document_fixtures import (
    make_stage1_output,
    make_stage7_output,
    make_stage8_output,
    make_stage9_output,
    TENANT_ID,
)


@pytest.mark.unit
class TestStage9StoryStructure:
    """Tests for stage9_story_structure() function."""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock()
        stage_cfg = MagicMock()
        stage_cfg.enabled = True
        stage_cfg.model = None
        stage_cfg.temperature = 0.3
        stage_cfg.max_tokens = 1500
        stage_cfg.prompt_override = None
        config.get_stage.return_value = stage_cfg
        return config

    @pytest.fixture
    def mock_llm_client(self):
        client = AsyncMock()
        client.chat.return_value = {
            "response": json.dumps(make_stage9_output(), ensure_ascii=False)
        }
        return client

    @pytest.mark.asyncio
    async def test_output_contains_story_theme(self, mock_config, mock_llm_client):
        """Stage 9 output SHALL include story_theme."""
        from app.services.proposal_stages import stage9_story_structure

        result = await stage9_story_structure(
            make_stage1_output(), make_stage7_output(), make_stage8_output(),
            mock_config, mock_llm_client, TENANT_ID
        )

        assert "story_theme" in result
        assert len(result["story_theme"]) > 0

    @pytest.mark.asyncio
    async def test_output_contains_pages_array(self, mock_config, mock_llm_client):
        """Stage 9 output SHALL include pages array with required fields."""
        from app.services.proposal_stages import stage9_story_structure

        result = await stage9_story_structure(
            make_stage1_output(), make_stage7_output(), make_stage8_output(),
            mock_config, mock_llm_client, TENANT_ID
        )

        assert "pages" in result
        assert len(result["pages"]) > 0
        for page in result["pages"]:
            assert "page_number" in page
            assert "title" in page
            assert "purpose" in page
            assert "key_points" in page
            assert "data_sources" in page

    @pytest.mark.asyncio
    async def test_page_count_range(self, mock_config, mock_llm_client):
        """Page count SHALL be between 5 and 10."""
        from app.services.proposal_stages import stage9_story_structure

        result = await stage9_story_structure(
            make_stage1_output(), make_stage7_output(), make_stage8_output(),
            mock_config, mock_llm_client, TENANT_ID
        )

        page_count = len(result["pages"])
        assert 5 <= page_count <= 10, f"Page count {page_count} is outside 5-10 range"

    @pytest.mark.asyncio
    async def test_pages_have_sequential_numbers(self, mock_config, mock_llm_client):
        """Pages SHALL have sequential page_number starting from 1."""
        from app.services.proposal_stages import stage9_story_structure

        result = await stage9_story_structure(
            make_stage1_output(), make_stage7_output(), make_stage8_output(),
            mock_config, mock_llm_client, TENANT_ID
        )

        page_numbers = [p["page_number"] for p in result["pages"]]
        expected = list(range(1, len(page_numbers) + 1))
        assert page_numbers == expected

    @pytest.mark.asyncio
    async def test_data_sources_are_valid(self, mock_config, mock_llm_client):
        """Each page's data_sources SHALL reference valid stage outputs."""
        from app.services.proposal_stages import stage9_story_structure

        valid_sources = {
            "stage1_issues", "stage6_publication_data", "stage6_success_cases",
            "stage7_industry_analysis", "stage7_target_insights", "stage7_decision_maker_insights",
            "stage8_strategy_axes", "stage8_success_case_references",
        }

        result = await stage9_story_structure(
            make_stage1_output(), make_stage7_output(), make_stage8_output(),
            mock_config, mock_llm_client, TENANT_ID
        )

        for page in result["pages"]:
            for source in page["data_sources"]:
                assert source in valid_sources, f"Invalid data_source: {source}"
