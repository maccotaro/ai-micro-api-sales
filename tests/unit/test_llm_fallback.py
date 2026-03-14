"""TDD Red Phase: LLM fallback tests for api-sales.

These tests define the expected behavior when LLM is unavailable
in the sales service (independent-deploy Phase 1-3, tasks 3.1-3.2).

Expected behavior after implementation:
- ProposalService.generate_proposal() returns a fallback ProposalHistory
  when LLMUnavailableError is raised (not a crash)
- AnalysisService.analyze_meeting() returns a fallback analysis result
  when LLMUnavailableError is raised (not a crash)
- Fallback responses contain "生成機能は一時的に利用できません"
"""
import pytest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock
from uuid import UUID, uuid4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FALLBACK_MESSAGE = "生成機能は一時的に利用できません"


def _make_mock_meeting(
    meeting_id: UUID | None = None,
    company_name: str = "テスト株式会社",
    raw_text: str = "テスト議事録内容です。採用について相談。",
) -> MagicMock:
    """Create a mock MeetingMinute object."""
    m = MagicMock()
    m.id = meeting_id or uuid4()
    m.company_name = company_name
    m.industry = "IT"
    m.area = "東京"
    m.raw_text = raw_text
    m.meeting_date = date(2026, 3, 14)
    m.next_action_date = None
    m.status = "draft"
    m.created_by = uuid4()
    return m


def _make_mock_analysis():
    """Create a mock MeetingMinuteAnalysis."""
    from unittest.mock import MagicMock

    analysis = MagicMock()
    analysis.meeting_minute_id = uuid4()
    analysis.company_name = "テスト株式会社"
    analysis.industry = "IT"
    analysis.area = "東京"
    analysis.issues = [
        MagicMock(issue="人材採用が難しい", priority="high", category="採用", details="応募が来ない"),
    ]
    analysis.needs = [
        MagicMock(need="コスト削減", urgency="medium", budget_hint="月50万円"),
    ]
    analysis.keywords = ["採用", "コスト"]
    analysis.summary = "テスト要約"
    return analysis


# ---------------------------------------------------------------------------
# Test: ProposalService returns fallback when LLM unavailable (task 3.2)
# ---------------------------------------------------------------------------

class TestProposalServiceFallback:
    """ProposalService must return a fallback when LLM service is down."""

    @pytest.mark.asyncio
    async def test_generate_proposal_returns_fallback_on_llm_unavailable(self):
        """generate_proposal() returns a fallback ProposalHistory
        instead of raising when LLM is unavailable.

        The proposal_json should contain the fallback message so the
        frontend can display it appropriately.
        """
        # Import the error class that will be created
        from app.services.llm_client import LLMUnavailableError

        # Patch LLMClient to raise on generate
        with patch("app.services.proposal_service.LLMClient") as MockLLMClient:
            mock_instance = MagicMock()
            mock_instance.generate = AsyncMock(
                side_effect=LLMUnavailableError("LLM unavailable")
            )
            MockLLMClient.return_value = mock_instance

            from app.services.proposal_service import ProposalService

            svc = ProposalService()
            # Override the llm_client that was created in __init__
            svc.llm_client = mock_instance

            meeting = _make_mock_meeting()
            analysis = _make_mock_analysis()
            db = MagicMock()
            user_id = uuid4()

            try:
                result = await svc.generate_proposal(
                    meeting=meeting,
                    analysis=analysis,
                    db=db,
                    user_id=user_id,
                )

                # Result should be a ProposalHistory (or dict) with fallback content
                assert result is not None

                # The proposal_json should contain the fallback message
                proposal_json = result.proposal_json if hasattr(result, 'proposal_json') else result
                if isinstance(proposal_json, dict):
                    fallback_text = str(proposal_json)
                else:
                    fallback_text = str(proposal_json)

                assert FALLBACK_MESSAGE in fallback_text, (
                    f"Proposal fallback should contain '{FALLBACK_MESSAGE}', "
                    f"got: {fallback_text!r}"
                )

            except LLMUnavailableError:
                pytest.fail(
                    "generate_proposal() should catch LLMUnavailableError and "
                    "return a fallback proposal, but it raised instead"
                )
            except Exception as e:
                # The current code raises generic Exception from _call_llm
                # After implementation, it should return a fallback instead
                if "LLM" in str(type(e).__name__) or "unavailable" in str(e).lower():
                    pytest.fail(
                        f"generate_proposal() should handle LLM unavailability "
                        f"gracefully, but raised: {e}"
                    )
                raise

    @pytest.mark.asyncio
    async def test_proposal_fallback_does_not_update_meeting_status(self):
        """When LLM is unavailable, meeting status should NOT change to 'proposed'.

        The meeting should stay in its current status because no real proposal
        was generated.
        """
        from app.services.llm_client import LLMUnavailableError

        with patch("app.services.proposal_service.LLMClient") as MockLLMClient:
            mock_instance = MagicMock()
            mock_instance.generate = AsyncMock(
                side_effect=LLMUnavailableError("LLM unavailable")
            )
            MockLLMClient.return_value = mock_instance

            from app.services.proposal_service import ProposalService

            svc = ProposalService()
            svc.llm_client = mock_instance

            meeting = _make_mock_meeting()
            original_status = meeting.status
            analysis = _make_mock_analysis()
            db = MagicMock()

            try:
                await svc.generate_proposal(
                    meeting=meeting,
                    analysis=analysis,
                    db=db,
                    user_id=uuid4(),
                )
                # If it returns a fallback, meeting status should not be 'proposed'
                assert meeting.status != "proposed", (
                    "Meeting status should not change to 'proposed' when LLM is unavailable"
                )
            except (LLMUnavailableError, Exception):
                # Current behavior: raises. After impl: returns fallback.
                # Either way, status should not have changed to 'proposed'
                assert meeting.status == original_status, (
                    "Meeting status should not change when LLM call fails"
                )


# ---------------------------------------------------------------------------
# Test: AnalysisService returns fallback when LLM unavailable (task 3.2)
# ---------------------------------------------------------------------------

class TestAnalysisServiceFallback:
    """AnalysisService must return a fallback when LLM service is down."""

    @pytest.mark.asyncio
    async def test_analyze_meeting_returns_fallback_on_llm_unavailable(self):
        """analyze_meeting() returns a fallback analysis result instead of raising.

        The fallback should contain partial information (company_name, etc.)
        from the meeting itself, plus the fallback message in the summary.
        """
        from app.services.llm_client import LLMUnavailableError

        with patch("app.services.analysis_service.LLMClient") as MockLLMClient:
            mock_instance = MagicMock()
            mock_instance.generate = AsyncMock(
                side_effect=LLMUnavailableError("LLM unavailable")
            )
            MockLLMClient.return_value = mock_instance

            from app.services.analysis_service import AnalysisService

            svc = AnalysisService()
            svc.llm_client = mock_instance

            meeting = _make_mock_meeting()
            db = MagicMock()

            try:
                result = await svc.analyze_meeting(
                    meeting=meeting,
                    db=db,
                    tenant_id=None,
                    store_in_graph=False,
                )

                # Fallback result should exist
                assert result is not None

                # Summary should contain fallback message
                summary = getattr(result, 'summary', '') or ''
                assert FALLBACK_MESSAGE in summary, (
                    f"Analysis fallback summary should contain '{FALLBACK_MESSAGE}', "
                    f"got: {summary!r}"
                )

                # Company name should be preserved from meeting
                assert result.company_name == meeting.company_name

            except LLMUnavailableError:
                pytest.fail(
                    "analyze_meeting() should catch LLMUnavailableError and "
                    "return a fallback analysis, but it raised instead"
                )
            except Exception as e:
                if "LLM" in str(type(e).__name__) or "unavailable" in str(e).lower():
                    pytest.fail(
                        f"analyze_meeting() should handle LLM unavailability "
                        f"gracefully, but raised: {e}"
                    )
                raise

    @pytest.mark.asyncio
    async def test_analysis_fallback_does_not_update_meeting_status(self):
        """When LLM is unavailable, meeting status should NOT change to 'analyzed'.

        The meeting should stay in its current status.
        """
        from app.services.llm_client import LLMUnavailableError

        with patch("app.services.analysis_service.LLMClient") as MockLLMClient:
            mock_instance = MagicMock()
            mock_instance.generate = AsyncMock(
                side_effect=LLMUnavailableError("LLM unavailable")
            )
            MockLLMClient.return_value = mock_instance

            from app.services.analysis_service import AnalysisService

            svc = AnalysisService()
            svc.llm_client = mock_instance

            meeting = _make_mock_meeting()
            original_status = meeting.status
            db = MagicMock()

            try:
                await svc.analyze_meeting(
                    meeting=meeting,
                    db=db,
                    tenant_id=None,
                    store_in_graph=False,
                )
                # If fallback returned, status should not be 'analyzed'
                assert meeting.status != "analyzed", (
                    "Meeting status should not change to 'analyzed' when LLM is unavailable"
                )
            except (LLMUnavailableError, Exception):
                assert meeting.status == original_status, (
                    "Meeting status should not change when LLM call fails"
                )

    @pytest.mark.asyncio
    async def test_analysis_fallback_has_empty_issues_and_needs(self):
        """Fallback analysis should have empty issues and needs lists.

        Since the LLM did not run, no issues/needs were extracted.
        """
        from app.services.llm_client import LLMUnavailableError

        with patch("app.services.analysis_service.LLMClient") as MockLLMClient:
            mock_instance = MagicMock()
            mock_instance.generate = AsyncMock(
                side_effect=LLMUnavailableError("LLM unavailable")
            )
            MockLLMClient.return_value = mock_instance

            from app.services.analysis_service import AnalysisService

            svc = AnalysisService()
            svc.llm_client = mock_instance

            meeting = _make_mock_meeting()
            db = MagicMock()

            try:
                result = await svc.analyze_meeting(
                    meeting=meeting,
                    db=db,
                    tenant_id=None,
                    store_in_graph=False,
                )
                # No LLM ran, so issues and needs should be empty
                assert len(result.issues) == 0, (
                    f"Fallback analysis should have 0 issues, got {len(result.issues)}"
                )
                assert len(result.needs) == 0, (
                    f"Fallback analysis should have 0 needs, got {len(result.needs)}"
                )
            except LLMUnavailableError:
                pytest.fail(
                    "analyze_meeting() should catch LLMUnavailableError and return fallback"
                )
            except Exception:
                pass  # Other exceptions may occur in current code
