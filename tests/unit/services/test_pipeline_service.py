# ai-micro-api-sales/tests/unit/services/test_pipeline_service.py
"""
Unit tests for app.services.proposal_pipeline_service module.

Tests:
- SSE event formatting (_sse)
- Output formatters (_format_issues, _format_proposals, etc.)
- ProposalPipelineService._execute_stage routing
- ProposalPipelineService._build_sections
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# =============================================================================
# _sse Tests
# =============================================================================


@pytest.mark.unit
class TestSSEFormatter:
    """Tests for _sse helper."""

    def test_basic_event(self):
        from app.services.proposal_pipeline_service import _sse

        result = _sse("pipeline_start", {"total_stages": 6})
        assert result.startswith("data: ")
        assert result.endswith("\n\n")
        data = json.loads(result[6:].strip())
        assert data["type"] == "pipeline_start"
        assert data["total_stages"] == 6

    def test_error_event(self):
        from app.services.proposal_pipeline_service import _sse

        result = _sse("error", {"message": "エラーメッセージ"})
        data = json.loads(result[6:].strip())
        assert data["type"] == "error"
        assert data["message"] == "エラーメッセージ"

    def test_japanese_content_not_escaped(self):
        from app.services.proposal_pipeline_service import _sse

        result = _sse("stage_info", {"name": "課題構造化"})
        assert "課題構造化" in result  # ensure_ascii=False


# =============================================================================
# Output Formatter Tests
# =============================================================================


@pytest.mark.unit
class TestFormatIssues:
    """Tests for _format_issues Stage 1 formatter."""

    def test_basic_formatting(self):
        from app.services.proposal_pipeline_service import _format_issues

        output = {
            "issues": [
                {
                    "id": "I-1",
                    "title": "採用難",
                    "category": "採用課題",
                    "detail": "人材不足が深刻",
                    "bant_c": {
                        "budget": {"status": "確認済", "detail": "月50万円"},
                        "authority": {"status": "未確認", "detail": ""},
                        "need": {"status": "確認済", "detail": "急募"},
                        "timeline": {"status": "不明", "detail": ""},
                        "competitor": {"status": "未確認", "detail": ""},
                    },
                }
            ]
        }
        result = _format_issues(output)
        assert "### I-1 採用難" in result
        assert "**カテゴリ**: 採用課題" in result
        assert "BUDGET" in result
        assert "確認済" in result

    def test_empty_issues(self):
        from app.services.proposal_pipeline_service import _format_issues

        result = _format_issues({"issues": []})
        assert result == ""

    def test_missing_issues_key(self):
        from app.services.proposal_pipeline_service import _format_issues

        result = _format_issues({})
        assert result == ""


@pytest.mark.unit
class TestFormatProposals:
    """Tests for _format_proposals Stage 2 formatter."""

    def test_basic_formatting(self):
        from app.services.proposal_pipeline_service import _format_proposals

        output = {
            "proposals": [
                {
                    "media_name": "バイトル",
                    "product_name": "プレミアプラン",
                    "issue_id": "I-1",
                    "plan_detail": "4週間掲載",
                    "price": 80000,
                    "reverse_calc": {
                        "hiring_goal": 3,
                        "required_applications": 30,
                        "required_pv": 3000,
                    },
                }
            ],
            "total_budget": 80000,
            "agenda_items": ["予算確認", "掲載時期"],
        }
        result = _format_proposals(output)
        assert "バイトル" in result
        assert "¥80,000" in result
        assert "合計予算" in result
        assert "予算確認" in result

    def test_empty_proposals(self):
        from app.services.proposal_pipeline_service import _format_proposals

        result = _format_proposals({"proposals": []})
        assert "バイトル" not in result


@pytest.mark.unit
class TestFormatActionPlan:
    """Tests for _format_action_plan Stage 3 formatter."""

    def test_basic_formatting(self):
        from app.services.proposal_pipeline_service import _format_action_plan

        output = {
            "action_plan": [
                {
                    "id": "A-1",
                    "title": "見積書作成",
                    "priority": "high",
                    "related_issue_id": "I-1",
                    "description": "プレミアプランの見積書",
                    "subtasks": [
                        {"title": "料金確認", "detail": "最新料金表を参照"},
                    ],
                }
            ]
        }
        result = _format_action_plan(output)
        assert "### A-1 見積書作成" in result
        assert "**優先度**: high" in result
        assert "- [ ] 料金確認" in result


@pytest.mark.unit
class TestFormatAdCopy:
    """Tests for _format_ad_copy Stage 4 formatter."""

    def test_basic_formatting(self):
        from app.services.proposal_pipeline_service import _format_ad_copy

        output = {
            "target_persona": {
                "age_range": "20-30代",
                "current_job": "フリーター",
                "motivation": "安定した収入",
            },
            "catchcopy_proposals": [
                {"copy": "あなたの未来、ここから。", "concept": "将来性訴求"},
            ],
            "job_description_draft": {
                "title": "飲食店スタッフ",
                "work_content": "接客・調理補助",
                "qualifications": "未経験歓迎",
            },
        }
        result = _format_ad_copy(output)
        assert "### ターゲットペルソナ" in result
        assert "20-30代" in result
        assert "あなたの未来、ここから。" in result
        assert "飲食店スタッフ" in result


@pytest.mark.unit
class TestFormatChecklistSummary:
    """Tests for _format_checklist_summary Stage 5 formatter."""

    def test_basic_formatting(self):
        from app.services.proposal_pipeline_service import _format_checklist_summary

        output = {
            "checklist": [
                {
                    "id": "C-1",
                    "category": "Budget",
                    "item": "予算の最終確認",
                    "related_issue_id": "I-1",
                    "question_example": "御社の予算枠は？",
                },
            ],
            "summary": {
                "overview": "採用課題に対するプランを提案",
                "key_points": [
                    {"point": "即戦力採用", "related_issues": ["I-1"], "stage_source": 2},
                ],
                "next_steps": ["見積書提出", "決裁者への提案"],
            },
        }
        result = _format_checklist_summary(output)
        assert "### チェックリスト" in result
        assert "Budget" in result
        assert "御社の予算枠は？" in result
        assert "### まとめ" in result
        assert "見積書提出" in result


# =============================================================================
# ProposalPipelineService._execute_stage Tests
# =============================================================================


@pytest.mark.unit
class TestExecuteStage:
    """Tests for ProposalPipelineService._execute_stage routing."""

    @pytest.mark.asyncio
    async def test_routes_to_stage1(self):
        mock_output = {"issues": []}
        with patch("app.services.proposal_pipeline_service.stage1_issue_structuring",
                    new_callable=AsyncMock, return_value=mock_output) as mock_stage:
            from app.services.proposal_pipeline_service import ProposalPipelineService

            service = ProposalPipelineService.__new__(ProposalPipelineService)
            service.llm_client = MagicMock()

            from app.services.pipeline_config import PipelineConfigData
            config = PipelineConfigData()
            result = await service._execute_stage(
                1, {"meeting": {}}, {}, config, uuid4(), "token",
            )
            assert result == mock_output
            mock_stage.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_to_stage5(self):
        mock_output = {"checklist": [], "summary": {}}
        with patch("app.services.proposal_pipeline_service.stage5_checklist_summary",
                    new_callable=AsyncMock, return_value=mock_output) as mock_stage:
            from app.services.proposal_pipeline_service import ProposalPipelineService

            service = ProposalPipelineService.__new__(ProposalPipelineService)
            service.llm_client = MagicMock()

            from app.services.pipeline_config import PipelineConfigData
            config = PipelineConfigData()
            prev = {1: {}, 2: {}, 3: {}, 4: {}}
            result = await service._execute_stage(
                5, {}, prev, config, uuid4(), "token",
            )
            assert result == mock_output

    @pytest.mark.asyncio
    async def test_passes_pipeline_run_id(self):
        with patch("app.services.proposal_pipeline_service.stage2_reverse_planning",
                    new_callable=AsyncMock, return_value={}) as mock_stage:
            from app.services.proposal_pipeline_service import ProposalPipelineService

            service = ProposalPipelineService.__new__(ProposalPipelineService)
            service.llm_client = MagicMock()

            from app.services.pipeline_config import PipelineConfigData
            config = PipelineConfigData()
            run_id = uuid4()
            await service._execute_stage(
                2, {"meeting": {}}, {1: {}}, config, uuid4(), "token",
                pipeline_run_id=run_id,
            )
            call_kwargs = mock_stage.call_args.kwargs
            assert call_kwargs.get("pipeline_run_id") == str(run_id)

    @pytest.mark.asyncio
    async def test_invalid_stage_raises(self):
        from app.services.proposal_pipeline_service import ProposalPipelineService

        service = ProposalPipelineService.__new__(ProposalPipelineService)
        service.llm_client = MagicMock()

        from app.services.pipeline_config import PipelineConfigData
        config = PipelineConfigData()

        with pytest.raises(ValueError, match="Unknown stage"):
            await service._execute_stage(99, {}, {}, config, uuid4(), "token")


# =============================================================================
# ProposalPipelineService._build_sections Tests
# =============================================================================


@pytest.mark.unit
class TestBuildSections:
    """Tests for _build_sections method."""

    def test_builds_sections_from_template(self):
        from app.services.pipeline_config import (
            OutputSection,
            OutputTemplate,
            PipelineConfigData,
        )
        from app.services.proposal_pipeline_service import ProposalPipelineService

        service = ProposalPipelineService.__new__(ProposalPipelineService)

        config = PipelineConfigData(
            output_template=OutputTemplate(
                sections=[
                    OutputSection(id="sec-1", title="課題分析", stage=1, required=True),
                    OutputSection(id="sec-2", title="提案プラン", stage=2, required=True),
                ]
            )
        )

        outputs = {
            1: {"issues": [{"id": "I-1", "title": "テスト", "category": "採用課題", "detail": "詳細"}]},
        }

        sections = service._build_sections(config, outputs)
        assert len(sections) == 2
        assert sections[0]["id"] == "sec-1"
        assert sections[0]["has_data"] is True
        assert "テスト" in sections[0]["content"]
        assert sections[1]["has_data"] is False
        assert "生成されませんでした" in sections[1]["content"]

    def test_empty_outputs(self):
        from app.services.pipeline_config import (
            OutputSection,
            OutputTemplate,
            PipelineConfigData,
        )
        from app.services.proposal_pipeline_service import ProposalPipelineService

        service = ProposalPipelineService.__new__(ProposalPipelineService)

        config = PipelineConfigData(
            output_template=OutputTemplate(
                sections=[
                    OutputSection(id="sec-1", title="課題", stage=1, required=True),
                    OutputSection(id="sec-2", title="オプション", stage=4, required=False),
                ]
            )
        )

        sections = service._build_sections(config, {})
        assert len(sections) == 2
        assert sections[0]["has_data"] is False
        assert "生成されませんでした" in sections[0]["content"]
        assert sections[1]["content"] == ""  # not required, no data
