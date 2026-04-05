"""Tests for pipeline_memory SharedMemory/MessageBus integration.

Group 10: Tests 10.7-10.9
- 10.7: Pipeline SharedMemory integration
- 10.8: Pipeline resume logic
- 10.9: Pipeline progress MessageBus events
"""
import json
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.pipeline_memory import (
    _sm_key,
    extract_stage_summary,
    find_resume_point,
    load_stage_output,
    publish_stage_event,
    save_stage_output,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TENANT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
RUN_ID = "run-test-001"


@pytest.fixture
def mock_shared_memory():
    """SharedMemory mock with .set() and .get() methods."""
    sm = MagicMock()
    sm.set = MagicMock()
    sm.get = MagicMock(return_value=None)
    return sm


@pytest.fixture
def mock_message_bus():
    """MessageBus mock with .publish() method."""
    mb = MagicMock()
    mb.publish = MagicMock()
    return mb


# ===========================================================================
# 10.7  Pipeline SharedMemory integration tests
# ===========================================================================


class TestSaveStageOutput:
    """test_save_stage_output: SharedMemory.set called with correct key."""

    def test_save_stage_output(self, mock_shared_memory):
        output = {"issues": [{"title": "採用コスト削減"}]}
        save_stage_output(mock_shared_memory, TENANT_ID, RUN_ID, 1, output)

        expected_key = f"sm:pipeline:{TENANT_ID}:{RUN_ID}:stage:1"
        mock_shared_memory.set.assert_called_once_with(expected_key, output)

    def test_save_stage_output_key_pattern(self, mock_shared_memory):
        """Verify key format sm:pipeline:{tenant}:{run}:stage:{N}."""
        for stage_num in (0, 5, 10):
            save_stage_output(mock_shared_memory, TENANT_ID, RUN_ID, stage_num, {"ok": True})
            key = mock_shared_memory.set.call_args_list[-1][0][0]
            assert key == _sm_key(TENANT_ID, RUN_ID, stage_num)


class TestLoadStageOutput:
    """test_load_stage_output: mock SharedMemory.get, verify returns."""

    def test_load_stage_output(self, mock_shared_memory):
        expected = {"plans": [{"name": "Plan A"}]}
        mock_shared_memory.get.return_value = expected

        result = load_stage_output(mock_shared_memory, TENANT_ID, RUN_ID, 2)

        expected_key = f"sm:pipeline:{TENANT_ID}:{RUN_ID}:stage:2"
        mock_shared_memory.get.assert_called_once_with(expected_key)
        assert result == expected

    def test_load_stage_output_missing(self, mock_shared_memory):
        mock_shared_memory.get.return_value = None
        result = load_stage_output(mock_shared_memory, TENANT_ID, RUN_ID, 3)
        assert result is None


class TestSaveLoadRoundtrip:
    """test_save_load_roundtrip: save then load, verify data integrity."""

    def test_roundtrip(self, mock_shared_memory):
        data = {"actions": [{"task": "ヒアリング実施", "deadline": "2026-04-10"}]}
        store = {}

        def fake_set(key, value):
            store[key] = value

        def fake_get(key):
            return store.get(key)

        mock_shared_memory.set.side_effect = fake_set
        mock_shared_memory.get.side_effect = fake_get

        save_stage_output(mock_shared_memory, TENANT_ID, RUN_ID, 3, data)
        loaded = load_stage_output(mock_shared_memory, TENANT_ID, RUN_ID, 3)

        assert loaded == data


class TestFallbackWithoutSharedMemory:
    """test_fallback_without_shared_memory: None shared_memory, no errors."""

    def test_save_none_sm(self):
        # Should not raise
        save_stage_output(None, TENANT_ID, RUN_ID, 0, {"ctx": "data"})

    def test_load_none_sm(self):
        result = load_stage_output(None, TENANT_ID, RUN_ID, 0)
        assert result is None

    def test_save_none_run_id(self, mock_shared_memory):
        save_stage_output(mock_shared_memory, TENANT_ID, None, 0, {"ctx": "data"})
        mock_shared_memory.set.assert_not_called()


class TestExtractStageSummary:
    """test_extract_stage_summary: verify summaries are concise."""

    def test_stage1_issues(self):
        output = {
            "issues": [
                {
                    "title": "人材確保の課題",
                    "severity": "high",
                    "bant_c": {
                        "budget": {"score": 3},
                        "authority": {"score": 4},
                    },
                }
            ]
        }
        summary = extract_stage_summary(1, output)
        assert "人材確保の課題" in summary
        assert "high" in summary
        assert len(summary) <= 500

    def test_stage2_plans(self):
        output = {"plans": [{"name": "Plan A", "total_cost": "50万円"}]}
        summary = extract_stage_summary(2, output)
        assert "Plan A" in summary
        assert "50万円" in summary

    def test_stage3_actions(self):
        output = {"action_items": [{"task": "提案書作成", "deadline": "2026-04-15"}]}
        summary = extract_stage_summary(3, output)
        assert "提案書作成" in summary

    def test_stage4_catchcopy(self):
        output = {"catchcopies": ["未来を変える採用"], "draft_summary": "概要テスト"}
        summary = extract_stage_summary(4, output)
        assert "未来を変える採用" in summary

    def test_stage5_summary(self):
        output = {"summary": "BANT-C充足度80%、次回アクション確定"}
        summary = extract_stage_summary(5, output)
        assert "BANT-C" in summary

    def test_stage7_industry(self):
        output = {
            "industry_analysis": {"trends": "DX推進"},
            "target_insights": {"primary_needs": "効率化"},
        }
        summary = extract_stage_summary(7, output)
        assert "DX推進" in summary

    def test_stage8_strategy(self):
        output = {"strategy_axes": [{"axis_name": "コスト削減", "key_message": "30%削減"}]}
        summary = extract_stage_summary(8, output)
        assert "コスト削減" in summary

    def test_stage9_story(self):
        output = {
            "story_theme": "採用革命",
            "pages": [{"title": "表紙"}, {"title": "課題"}],
        }
        summary = extract_stage_summary(9, output)
        assert "採用革命" in summary
        assert "表紙" in summary

    def test_empty_output(self):
        assert extract_stage_summary(1, {}) == ""
        assert extract_stage_summary(1, None) == ""

    def test_fallback_stage(self):
        """Stages without specific handler (0, 6, 10) use JSON fallback."""
        output = {"raw": "data"}
        summary = extract_stage_summary(0, output)
        assert "raw" in summary
        assert len(summary) <= 500

    def test_max_chars_truncation(self):
        output = {"summary": "A" * 1000}
        summary = extract_stage_summary(5, output, max_chars=100)
        assert len(summary) <= 100


# ===========================================================================
# 10.8  Pipeline resume tests
# ===========================================================================


class TestFindResumePointAllCached:
    """test_find_resume_point_all_cached: all stages 0-10 present."""

    def test_all_cached_returns_11(self, mock_shared_memory):
        mock_shared_memory.get.return_value = {"data": "ok"}
        outputs, first_missing = find_resume_point(mock_shared_memory, TENANT_ID, RUN_ID)
        assert first_missing == 11
        assert len(outputs) == 11
        for i in range(11):
            assert i in outputs


class TestFindResumePointPartial:
    """test_find_resume_point_partial: stages 0-5 present, 6 missing."""

    def test_partial_returns_first_missing(self, mock_shared_memory):
        def get_side_effect(key):
            # stages 0-5 exist, 6+ missing
            stage_num = int(key.rsplit(":", 1)[1])
            if stage_num <= 5:
                return {"stage": stage_num}
            return None

        mock_shared_memory.get.side_effect = get_side_effect
        outputs, first_missing = find_resume_point(mock_shared_memory, TENANT_ID, RUN_ID)
        assert first_missing == 6
        assert len(outputs) == 6
        for i in range(6):
            assert i in outputs


class TestFindResumePointEmpty:
    """test_find_resume_point_empty: no stages cached, returns 0."""

    def test_empty_returns_0(self, mock_shared_memory):
        mock_shared_memory.get.return_value = None
        outputs, first_missing = find_resume_point(mock_shared_memory, TENANT_ID, RUN_ID)
        assert first_missing == 0
        assert len(outputs) == 0


class TestResumePopulatesOutputs:
    """test_resume_populates_outputs: outputs dict correctly populated."""

    def test_outputs_populated(self, mock_shared_memory):
        stage_data = {
            0: {"context": "collected"},
            1: {"issues": []},
            2: {"plans": []},
        }

        def get_side_effect(key):
            stage_num = int(key.rsplit(":", 1)[1])
            return stage_data.get(stage_num)

        mock_shared_memory.get.side_effect = get_side_effect
        outputs, first_missing = find_resume_point(mock_shared_memory, TENANT_ID, RUN_ID)

        assert first_missing == 3
        assert outputs[0] == {"context": "collected"}
        assert outputs[1] == {"issues": []}
        assert outputs[2] == {"plans": []}


class TestResumeExpiredTTL:
    """test_resume_expired_ttl: all stages None (TTL expired), starts from 0."""

    def test_expired_ttl_starts_from_0(self, mock_shared_memory):
        mock_shared_memory.get.return_value = None
        outputs, first_missing = find_resume_point(mock_shared_memory, TENANT_ID, RUN_ID)
        assert first_missing == 0
        assert outputs == {}


# ===========================================================================
# 10.9  Pipeline progress MessageBus tests
# ===========================================================================


class TestPublishStageStarted:
    """test_publish_stage_started: correct event format."""

    def test_started_event(self, mock_message_bus):
        publish_stage_event(
            mock_message_bus, RUN_ID,
            stage_num=1, status="started", stage_name="課題構造化",
        )

        mock_message_bus.publish.assert_called_once()
        channel, event = mock_message_bus.publish.call_args[0]
        assert channel == f"mb:pipeline:progress:{RUN_ID}"
        assert event["stage"] == 1
        assert event["status"] == "started"
        assert event["stage_name"] == "課題構造化"
        assert event["total_stages"] == 11

    def test_started_no_duration(self, mock_message_bus):
        publish_stage_event(
            mock_message_bus, RUN_ID,
            stage_num=0, status="started", stage_name="コンテキスト収集",
        )
        _, event = mock_message_bus.publish.call_args[0]
        assert "duration_ms" not in event


class TestPublishStageCompleted:
    """test_publish_stage_completed: duration_ms included."""

    def test_completed_event(self, mock_message_bus):
        publish_stage_event(
            mock_message_bus, RUN_ID,
            stage_num=2, status="completed", duration_ms=1500,
        )

        _, event = mock_message_bus.publish.call_args[0]
        assert event["status"] == "completed"
        assert event["duration_ms"] == 1500
        assert event["total_stages"] == 11


class TestPublishStageFailed:
    """test_publish_stage_failed: error message included."""

    def test_failed_event(self, mock_message_bus):
        publish_stage_event(
            mock_message_bus, RUN_ID,
            stage_num=3, status="failed", error="LLM timeout",
        )

        _, event = mock_message_bus.publish.call_args[0]
        assert event["status"] == "failed"
        assert event["error"] == "LLM timeout"
        assert event["stage"] == 3


class TestPublishWithoutMessageBus:
    """test_publish_without_message_bus: None, no errors."""

    def test_none_message_bus(self):
        # Should not raise
        publish_stage_event(None, RUN_ID, stage_num=0, status="started")

    def test_none_run_id(self, mock_message_bus):
        publish_stage_event(mock_message_bus, None, stage_num=0, status="started")
        mock_message_bus.publish.assert_not_called()
