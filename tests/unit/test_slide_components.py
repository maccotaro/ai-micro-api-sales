"""Tests for deterministic brand-slide layout components."""
from app.services.slide_components import render_section
from app.services.brand_theme import brand_marp_frontmatter


def _stages():
    s7 = {
        "industry_analysis": {
            "job_types": [{"common_misconceptions": ["屋外で過酷"], "actual_reality": "屋内で空調完備"}],
            "competitive_advantages": ["座り作業あり"],
        },
        "target_insights": {
            "psychological_axes": [
                {"axis": "体力が不安", "detail": "立ちっぱなしは辛い", "appeal_direction": "座り仕事を訴求"}
            ]
        },
    }
    s8 = {
        "strategy_axes": [
            {"id": "Ax-1", "title": "差別化", "rationale": "誤解を解く",
             "catchcopies": [{"text": "快適な守衛業務", "psychology_link": "体力不安"}]},
            {"id": "Ax-2", "title": "ニーズ訴求", "rationale": "安心感"},
            {"id": "Ax-3", "title": "キーワード対策", "rationale": "検索意図"},
        ],
        "success_case_references": [
            {"case_summary": "飲食A社", "before": {"catchcopy": "旧", "pv": 1000, "applications": 50},
             "after": {"catchcopy": "新", "pv": 2000, "applications": 150}, "improvement": "コピー刷新"}
        ],
    }
    return {"story_theme": "採用成功に向けて", "stage7": s7, "stage8": s8}


class TestRenderSection:
    def test_deterministic_sections_render(self):
        stages = _stages()
        for spec in [
            {"section": "cover", "title": "某社 ご提案"},
            {"section": "agenda", "title": "本日の流れ", "key_points": ["A", "B"]},
            {"section": "principles", "title": "原稿設計の重要性"},
            {"section": "misconception", "title": "ギャップ"},
            {"section": "target_psychology", "title": "重視する軸"},
            {"section": "strategy_summary", "title": "ご提案"},
            {"section": "strategy_detail", "title": "提案1", "axis_id": "Ax-1"},
            {"section": "success_case", "title": "成功事例1", "case_index": 0},
        ]:
            out = render_section(spec, stages)
            assert out and spec["title"] in out

    def test_non_deterministic_falls_back(self):
        for section in ["plan", "keyword", "target_trend", "next_steps", "unknown"]:
            assert render_section({"section": section, "title": "X"}, _stages()) is None

    def test_misconception_content(self):
        out = render_section({"section": "misconception", "title": "X"}, _stages())
        assert "屋外で過酷" in out and "屋内で空調完備" in out and 'class="cmp"' in out

    def test_psychology_table(self):
        out = render_section({"section": "target_psychology", "title": "X"}, _stages())
        assert "体力が不安" in out and "座り仕事を訴求" in out and "|" in out

    def test_success_case_before_after(self):
        out = render_section({"section": "success_case", "title": "X", "case_index": 0}, _stages())
        assert "Before" in out and "After" in out and "2000" in out

    def test_strategy_detail_picks_axis_by_id(self):
        out = render_section({"section": "strategy_detail", "title": "T", "axis_id": "Ax-1"}, _stages())
        assert "快適な守衛業務" in out

    def test_empty_data_returns_none_for_conditional(self):
        empty = {"story_theme": "", "stage7": {}, "stage8": {}}
        assert render_section({"section": "misconception", "title": "X"}, empty) is None
        assert render_section({"section": "target_psychology", "title": "X"}, empty) is None


class TestBrandTheme:
    def test_frontmatter_braces_balanced(self):
        fm = brand_marp_frontmatter("テスト")
        assert fm.count("{") == fm.count("}")
        assert "style: |" in fm and "marp: true" in fm
