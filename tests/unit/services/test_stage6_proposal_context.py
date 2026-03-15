# ai-micro-api-sales/tests/unit/services/test_stage6_proposal_context.py
"""
TDD unit tests for Stage 6: Proposal Context Collection (non-LLM).

Tests:
- KB search invocations (proposal_reference, end_user psychology, decision_maker psychology)
- Success case embedding search
- Publication records aggregation
- Fallback messages when KB returns no results
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from tests.fixtures.proposal_document_fixtures import (
    make_stage0_context,
    make_stage1_output,
    make_proposal_kb_chunks,
    make_end_user_psychology_chunks,
    make_decision_maker_psychology_chunks,
    make_success_case_results,
    make_publication_records,
    TENANT_ID,
)


@pytest.mark.unit
class TestStage6ProposalContext:
    """Tests for stage6_proposal_context() function."""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock()
        config.kb_mapping = {
            "proposal_reference": MagicMock(
                knowledge_base_ids=["kb-proposal-1"],
                search_query_template="{industry} {area} 提案書 成功事例 戦略",
                max_chunks=15,
                used_in_stages=[6],
            ),
            "target_psychology_end_user": MagicMock(
                knowledge_base_ids=["kb-psychology-1"],
                search_query_template="{industry} {job_type} エンドユーザー 心理 不安 動機",
                max_chunks=5,
                used_in_stages=[7],
            ),
            "target_psychology_decision_maker": MagicMock(
                knowledge_base_ids=["kb-psychology-1"],
                search_query_template="{industry} 担当者 意思決定 懸念 判断軸",
                max_chunks=5,
                used_in_stages=[7, 8],
            ),
        }
        return config

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_searches_proposal_kb(self, mock_config, mock_db):
        """Stage 6 SHALL search proposal_reference KB category."""
        from app.services.proposal_stages import stage6_proposal_context

        context = make_stage0_context()
        stage1_output = make_stage1_output()

        with patch(
            "app.services.proposal_stages._search_kbs",
            new_callable=AsyncMock,
            return_value={"proposal_reference": make_proposal_kb_chunks()},
        ) as mock_search, patch(
            "app.services.proposal_stages.load_success_cases",
            new_callable=AsyncMock,
            return_value=make_success_case_results(),
        ), patch(
            "app.services.proposal_stages.load_publication_records_for_proposal",
            return_value=make_publication_records(),
        ):
            result = await stage6_proposal_context(
                context, stage1_output, mock_config, mock_db, TENANT_ID
            )

            # Verify KB search was called
            mock_search.assert_called_once()
            assert "proposal_kb_chunks" in result

    @pytest.mark.asyncio
    async def test_searches_psychology_kbs(self, mock_config, mock_db):
        """Stage 6 SHALL search both end_user and decision_maker psychology KBs."""
        from app.services.proposal_stages import stage6_proposal_context

        context = make_stage0_context()
        stage1_output = make_stage1_output()

        with patch(
            "app.services.proposal_stages._search_kbs",
            new_callable=AsyncMock,
            return_value={
                "proposal_reference": make_proposal_kb_chunks(),
                "target_psychology_end_user": make_end_user_psychology_chunks(),
                "target_psychology_decision_maker": make_decision_maker_psychology_chunks(),
            },
        ), patch(
            "app.services.proposal_stages.load_success_cases",
            new_callable=AsyncMock,
            return_value=make_success_case_results(),
        ), patch(
            "app.services.proposal_stages.load_publication_records_for_proposal",
            return_value=make_publication_records(),
        ):
            result = await stage6_proposal_context(
                context, stage1_output, mock_config, mock_db, TENANT_ID
            )

            assert "end_user_psychology_chunks" in result
            assert "decision_maker_psychology_chunks" in result
            assert len(result["end_user_psychology_chunks"]) > 0
            assert len(result["decision_maker_psychology_chunks"]) > 0

    @pytest.mark.asyncio
    async def test_loads_success_cases(self, mock_config, mock_db):
        """Stage 6 SHALL search success_case_embeddings by industry and area."""
        from app.services.proposal_stages import stage6_proposal_context

        context = make_stage0_context()
        stage1_output = make_stage1_output()

        with patch(
            "app.services.proposal_stages._search_kbs",
            new_callable=AsyncMock,
            return_value={},
        ), patch(
            "app.services.proposal_stages.load_success_cases",
            new_callable=AsyncMock,
            return_value=make_success_case_results(),
        ) as mock_cases, patch(
            "app.services.proposal_stages.load_publication_records_for_proposal",
            return_value=make_publication_records(),
        ):
            result = await stage6_proposal_context(
                context, stage1_output, mock_config, mock_db, TENANT_ID
            )

            mock_cases.assert_called_once()
            assert "success_cases" in result
            assert len(result["success_cases"]) > 0

    @pytest.mark.asyncio
    async def test_loads_publication_records(self, mock_config, mock_db):
        """Stage 6 SHALL query publication_records for high-performing entries."""
        from app.services.proposal_stages import stage6_proposal_context

        context = make_stage0_context()
        stage1_output = make_stage1_output()

        with patch(
            "app.services.proposal_stages._search_kbs",
            new_callable=AsyncMock,
            return_value={},
        ), patch(
            "app.services.proposal_stages.load_success_cases",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.services.proposal_stages.load_publication_records_for_proposal",
            return_value=make_publication_records(),
        ) as mock_pub:
            result = await stage6_proposal_context(
                context, stage1_output, mock_config, mock_db, TENANT_ID
            )

            mock_pub.assert_called_once()
            assert "publication_records" in result

    @pytest.mark.asyncio
    async def test_fallback_when_no_kb_results(self, mock_config, mock_db):
        """When KB returns no results, Stage 6 SHALL include fallback messages."""
        from app.services.proposal_stages import stage6_proposal_context

        context = make_stage0_context()
        stage1_output = make_stage1_output()

        with patch(
            "app.services.proposal_stages._search_kbs",
            new_callable=AsyncMock,
            return_value={},
        ), patch(
            "app.services.proposal_stages.load_success_cases",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.services.proposal_stages.load_publication_records_for_proposal",
            return_value=[],
        ):
            result = await stage6_proposal_context(
                context, stage1_output, mock_config, mock_db, TENANT_ID
            )

            # Empty results should still produce a valid output
            assert "proposal_kb_chunks" in result
            assert "end_user_psychology_chunks" in result
            assert "decision_maker_psychology_chunks" in result
            assert "success_cases" in result
            assert "publication_records" in result
