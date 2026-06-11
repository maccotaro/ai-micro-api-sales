"""Tests for the generalized proposal blueprint (Stage 9 blueprint-driven)."""
from app.services.proposal_blueprint import (
    build_story_structure,
    build_blueprint_pages,
    MAX_STRATEGY_DETAIL,
    MAX_SUCCESS_CASES,
)


def _full_inputs():
    meeting = {"company_name": "サンエス警備保障株式会社", "industry": "警備"}
    s1 = {"issues": [{"id": "I-1", "title": "応募数の減少"}]}
    s2 = {"proposals": [{"issue_id": "I-1", "shochikubai": {}}]}
    s6 = {}
    s7 = {
        "industry_analysis": {
            "industry_name": "施設警備",
            "job_types": [{"name": "施設警備"}, {"name": "交通誘導"}],
            "competitive_advantages": ["屋内", "空調"],
        },
        "target_insights": {
            "primary_target": "中高年・シニア層",
            "psychological_axes": [{"axis": "体力"}, {"axis": "人間関係"}],
        },
    }
    s8 = {
        "strategy_axes": [
            {"id": "Ax-1", "title": "差別化", "catchcopies": [{"text": "快適な守衛業務"}]},
            {"id": "Ax-2", "title": "ニーズ訴求", "catchcopies": []},
            {"id": "Ax-3", "title": "キーワード対策", "catchcopies": []},
        ],
        "success_case_references": [{"case_summary": "A"}, {"case_summary": "B"}],
    }
    return s1, s2, s6, s7, s8, meeting


class TestBlueprint:
    def test_reproduces_brand_deck_structure(self):
        st = build_story_structure(*_full_inputs(), max_pages=20)
        assert st["blueprint_driven"] is True
        secs = [p["section"] for p in st["pages"]]
        # Fixed core
        assert secs[0] == "cover" and secs[1] == "agenda"
        assert "principles" in secs and secs[-1] == "next_steps"
        # Variable sections expand per data
        assert secs.count("strategy_detail") == 3
        assert secs.count("success_case") == 2
        # Conditionals present given data
        assert "segment_comparison" in secs  # job_types >= 2
        assert "plan" in secs                # has proposals
        assert "target_psychology" in secs   # psychological_axes present

    def test_page_numbers_sequential(self):
        st = build_story_structure(*_full_inputs(), max_pages=20)
        nums = [p["page_number"] for p in st["pages"]]
        assert nums == list(range(1, len(nums) + 1))

    def test_agenda_lists_content_sections(self):
        st = build_story_structure(*_full_inputs(), max_pages=20)
        agenda = next(p for p in st["pages"] if p["section"] == "agenda")
        assert len(agenda["key_points"]) > 0

    def test_data_sources_present_on_bound_sections(self):
        st = build_story_structure(*_full_inputs(), max_pages=20)
        plan = next(p for p in st["pages"] if p["section"] == "plan")
        assert "stage2_plans" in plan["data_sources"]

    def test_minimal_inputs_skip_conditionals(self):
        st = build_story_structure({"issues": []}, {}, {}, {}, {}, {"company_name": "某社"})
        secs = [p["section"] for p in st["pages"]]
        assert secs == ["cover", "agenda", "principles", "next_steps"]

    def test_strategy_detail_capped(self):
        s8 = {"strategy_axes": [{"id": f"A{i}", "title": f"t{i}", "catchcopies": []} for i in range(10)]}
        pages = build_blueprint_pages({}, {}, {}, {}, s8, {})
        assert sum(1 for p in pages if p["section"] == "strategy_detail") == MAX_STRATEGY_DETAIL

    def test_success_case_capped(self):
        s8 = {"success_case_references": [{"case_summary": str(i)} for i in range(10)]}
        pages = build_blueprint_pages({}, {}, {}, {}, s8, {})
        assert sum(1 for p in pages if p["section"] == "success_case") == MAX_SUCCESS_CASES

    def test_max_pages_cap_records_original(self):
        s8 = {"strategy_axes": [{"id": f"A{i}", "title": f"t{i}", "catchcopies": []} for i in range(10)]}
        st = build_story_structure({}, {}, {}, {"industry_analysis": {}}, s8, {}, max_pages=8)
        assert len(st["pages"]) == 8
        assert st["pages_capped_from"] > 8
