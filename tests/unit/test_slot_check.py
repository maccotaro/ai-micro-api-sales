"""Tests for the required-slot 抜け漏れチェッカー."""
from app.services.slot_check import compute_missing_alerts, attach_missing_alerts


class TestComputeMissingAlerts:
    def test_all_slots_missing(self):
        s1 = {"issues": [{"id": "I-1", "title": "応募数の減少", "bant_c": {}}]}
        s2 = {"proposals": [{"issue_id": "I-1"}]}
        alerts = compute_missing_alerts({}, s1, s2)
        slots = {a["slot"] for a in alerts}
        assert "recruitment_target" in slots
        assert "budget_conditions" in slots
        assert "decision_process" in slots

    def test_filled_sections_no_alerts(self):
        parsed = {"section_3": "シニア層", "section_9": "予算50万", "section_10": "部長決裁"}
        s1 = {"issues": [{"id": "I-1", "title": "x", "bant_c": {}}]}
        s2 = {"proposals": [{"issue_id": "I-1"}]}
        assert compute_missing_alerts(parsed, s1, s2) == []

    def test_bant_c_fallback_fills_budget_and_authority(self):
        parsed = {"section_3": "学生"}
        s1 = {"issues": [{"id": "I-1", "title": "x", "bant_c": {"budget": "30万", "authority": "店長"}}]}
        s2 = {"proposals": [{"issue_id": "I-1"}]}
        assert compute_missing_alerts(parsed, s1, s2) == []

    def test_uncovered_issue_flagged(self):
        parsed = {"section_3": "x", "section_9": "x", "section_10": "x"}
        s1 = {"issues": [{"id": "I-1", "title": "応募数"}, {"id": "I-2", "title": "定着率"}]}
        s2 = {"proposals": [{"issue_id": "I-1"}]}
        alerts = compute_missing_alerts(parsed, s1, s2)
        uncovered = [a for a in alerts if a["slot"] == "issue_uncovered"]
        assert len(uncovered) == 1
        assert uncovered[0]["issue_id"] == "I-2"

    def test_cross_sell_counts_as_coverage(self):
        parsed = {"section_3": "x", "section_9": "x", "section_10": "x"}
        s1 = {"issues": [{"id": "I-2", "title": "定着率"}]}
        s2 = {"proposals": [], "cross_sell": [{"issue_id": "I-2", "product_name": "速払い"}]}
        assert compute_missing_alerts(parsed, s1, s2) == []


class TestAttach:
    def test_blocking_flag(self):
        out = attach_missing_alerts({"checklist": []}, {}, {"issues": []}, {}, blocking=True)
        assert out["missing_alerts_blocking"] is True
        assert len(out["missing_alerts"]) == 3  # all 3 slots missing

    def test_non_blocking_default(self):
        out = attach_missing_alerts({}, {"section_3": "x", "section_9": "x", "section_10": "x"},
                                    {"issues": []}, {}, blocking=False)
        assert out["missing_alerts"] == []
        assert out["missing_alerts_blocking"] is False
