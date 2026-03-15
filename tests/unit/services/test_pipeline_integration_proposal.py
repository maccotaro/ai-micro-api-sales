# ai-micro-api-sales/tests/unit/services/test_pipeline_integration_proposal.py
"""
Unit tests for Stage 6-10 pipeline integration.

Tests:
- Stage 6-10 routing in _stream_proposal_stages
- Stage 6-10 disabled → Stage 0-5 only
- SSE event emission order
- stage_results storage for Stage 6-10
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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
    MINUTE_ID,
)


@pytest.mark.unit
class TestPipelineIntegrationProposal:
    """Tests for Stage 6-10 integration in ProposalPipelineService."""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock()
        config.enabled = True
        config.pipeline_name = "テスト提案パイプライン"
        config.kb_mapping = {}
        config.output_template = MagicMock(sections=[])

        def get_stage(num):
            cfg = MagicMock()
            cfg.enabled = True
            cfg.name = f"Stage {num}"
            cfg.model = None
            cfg.temperature = 0.3
            cfg.max_tokens = 2000
            cfg.prompt_override = None
            return cfg
        config.get_stage = get_stage
        return config

    @pytest.mark.asyncio
    async def test_stage6_10_routing_called(self, mock_config):
        """Stage 6-10 functions SHALL be called when enabled."""
        from app.services.proposal_pipeline_service import ProposalPipelineService

        service = ProposalPipelineService.__new__(ProposalPipelineService)
        service.llm_client = AsyncMock()

        outputs = {1: make_stage1_output()}
        stage_results = {}
        context = make_stage0_context()

        with patch("app.services.proposal_pipeline_service.stage6_proposal_context",
                   new_callable=AsyncMock, return_value=make_stage6_context()) as mock_s6, \
             patch("app.services.proposal_pipeline_service.stage7_industry_target_analysis",
                   new_callable=AsyncMock, return_value=make_stage7_output()) as mock_s7, \
             patch("app.services.proposal_pipeline_service.stage8_appeal_strategy",
                   new_callable=AsyncMock, return_value=make_stage8_output()) as mock_s8, \
             patch("app.services.proposal_pipeline_service.stage9_story_structure",
                   new_callable=AsyncMock, return_value=make_stage9_output()) as mock_s9, \
             patch("app.services.proposal_pipeline_service.stage10_page_generation",
                   new_callable=AsyncMock, return_value={"document_id": str(uuid4()), "pages": []}) as mock_s10:

            events = []
            async for item in service._stream_proposal_stages(
                context, outputs, mock_config, TENANT_ID, USER_ID,
                uuid4(), MINUTE_ID, MagicMock(), stage_results,
            ):
                if isinstance(item, str):
                    events.append(item)

            mock_s6.assert_called_once()
            mock_s7.assert_called_once()
            mock_s8.assert_called_once()
            mock_s9.assert_called_once()
            mock_s10.assert_called_once()

    @pytest.mark.asyncio
    async def test_stage6_10_disabled_no_execution(self, mock_config):
        """When Stage 6 is disabled, no proposal stages SHALL execute."""
        from app.services.proposal_pipeline_service import ProposalPipelineService

        def get_stage_disabled(num):
            cfg = MagicMock()
            cfg.enabled = num < 6  # Only 0-5 enabled
            cfg.name = f"Stage {num}"
            return cfg
        mock_config.get_stage = get_stage_disabled

        service = ProposalPipelineService.__new__(ProposalPipelineService)
        service.llm_client = AsyncMock()

        outputs = {1: make_stage1_output()}
        stage_results = {}

        with patch("app.services.proposal_pipeline_service.stage6_proposal_context") as mock_s6:
            events = []
            async for item in service._stream_proposal_stages(
                make_stage0_context(), outputs, mock_config,
                TENANT_ID, USER_ID, uuid4(), MINUTE_ID, MagicMock(), stage_results,
            ):
                if isinstance(item, str):
                    events.append(item)

            mock_s6.assert_not_called()
            assert 6 in stage_results
            assert stage_results[6]["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_sse_events_emitted_for_stages(self, mock_config):
        """SSE stage_start and stage_complete SHALL be emitted for each proposal stage."""
        from app.services.proposal_pipeline_service import ProposalPipelineService

        service = ProposalPipelineService.__new__(ProposalPipelineService)
        service.llm_client = AsyncMock()

        outputs = {1: make_stage1_output()}
        stage_results = {}

        with patch("app.services.proposal_pipeline_service.stage6_proposal_context",
                   new_callable=AsyncMock, return_value=make_stage6_context()), \
             patch("app.services.proposal_pipeline_service.stage7_industry_target_analysis",
                   new_callable=AsyncMock, return_value=make_stage7_output()), \
             patch("app.services.proposal_pipeline_service.stage8_appeal_strategy",
                   new_callable=AsyncMock, return_value=make_stage8_output()), \
             patch("app.services.proposal_pipeline_service.stage9_story_structure",
                   new_callable=AsyncMock, return_value=make_stage9_output()), \
             patch("app.services.proposal_pipeline_service.stage10_page_generation",
                   new_callable=AsyncMock, return_value={"document_id": str(uuid4()), "pages": []}):

            sse_events = []
            async for item in service._stream_proposal_stages(
                make_stage0_context(), outputs, mock_config,
                TENANT_ID, USER_ID, uuid4(), MINUTE_ID, MagicMock(), stage_results,
            ):
                if isinstance(item, str) and item.startswith("data:"):
                    try:
                        data = json.loads(item.split("data: ", 1)[1].strip())
                        sse_events.append(data)
                    except (json.JSONDecodeError, IndexError):
                        pass

            # Should have stage_start + stage_complete for each of 5 stages
            start_events = [e for e in sse_events if e.get("type") == "stage_start"]
            complete_events = [e for e in sse_events if e.get("type") == "stage_complete"]
            assert len(start_events) == 5
            assert len(complete_events) == 5

    @pytest.mark.asyncio
    async def test_stage_results_stored(self, mock_config):
        """stage_results SHALL contain entries for Stage 6-10."""
        from app.services.proposal_pipeline_service import ProposalPipelineService

        service = ProposalPipelineService.__new__(ProposalPipelineService)
        service.llm_client = AsyncMock()

        outputs = {1: make_stage1_output()}
        stage_results = {}

        with patch("app.services.proposal_pipeline_service.stage6_proposal_context",
                   new_callable=AsyncMock, return_value=make_stage6_context()), \
             patch("app.services.proposal_pipeline_service.stage7_industry_target_analysis",
                   new_callable=AsyncMock, return_value=make_stage7_output()), \
             patch("app.services.proposal_pipeline_service.stage8_appeal_strategy",
                   new_callable=AsyncMock, return_value=make_stage8_output()), \
             patch("app.services.proposal_pipeline_service.stage9_story_structure",
                   new_callable=AsyncMock, return_value=make_stage9_output()), \
             patch("app.services.proposal_pipeline_service.stage10_page_generation",
                   new_callable=AsyncMock, return_value={"document_id": str(uuid4()), "pages": []}):

            async for _ in service._stream_proposal_stages(
                make_stage0_context(), outputs, mock_config,
                TENANT_ID, USER_ID, uuid4(), MINUTE_ID, MagicMock(), stage_results,
            ):
                pass

            for stage_num in range(6, 11):
                assert stage_num in stage_results
                assert stage_results[stage_num]["status"] == "completed"
                assert "duration_ms" in stage_results[stage_num]
