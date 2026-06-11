"""Deterministic brand-slide layout components (PoC).

Renders Marp-compatible HTML for specific blueprint sections directly from the
already-structured upstream stage outputs (Stage 7/8). No extra LLM call is
needed — this is more reliable and reproduces the reference brand deck layout
(comparison boxes, numbered cards, Before/After, psychology table).

`render_section(page_spec, stages)` returns the page Markdown/HTML for sections
it can render deterministically, or None to signal "fall back to the LLM path".
The brand CSS classes used here are defined in app.services.brand_theme.
"""
import html
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


def _header(title: str) -> str:
    """Markdown H1 → rendered as the cyan header bar by the brand CSS."""
    return f"# {title}\n\n"


def render_cover(title: str, theme: str) -> str:
    # First page gets `_class: lead` applied by marp_export; keep it heading-based.
    return f"# {title}\n\n## 採用成功に向けて\n\n{theme}\n"


def render_agenda(title: str, items: list[str]) -> str:
    lis = "\n".join(
        f'<li><span class="num">{i:02d}</span> {_esc(t)}</li>'
        for i, t in enumerate(items, start=1)
    )
    return _header(title) + f'<ol class="agenda">\n{lis}\n</ol>\n'


def render_principles(title: str) -> str:
    return _header(title) + (
        '<div class="principle">\n'
        '  <div class="col"><div class="head">SEOの観点（集客の最大化）</div>'
        '検索意図に最適な答えを示し、独自性・具体性で上位表示を狙う。</div>\n'
        '  <div class="col"><div class="head">CVRの観点（応募率の向上）</div>'
        '検索条件と原稿内容を一致させ、透明性と安心感で応募に導く。</div>\n'
        '</div>\n'
    )


def render_misconception(title: str, industry_analysis: dict) -> Optional[str]:
    jts = (industry_analysis or {}).get("job_types") or []
    advantages = (industry_analysis or {}).get("competitive_advantages") or []
    misconceptions: list[str] = []
    reality: list[str] = list(advantages)
    for jt in jts:
        misconceptions += (jt.get("common_misconceptions") or [])
        if jt.get("actual_reality"):
            reality.append(jt["actual_reality"])
    if not misconceptions and not reality:
        return None
    left = "".join(f"<li>{_esc(m)}</li>" for m in misconceptions[:4]) or "<li>—</li>"
    right = "".join(f"<li>{_esc(r)}</li>" for r in reality[:4]) or "<li>—</li>"
    return _header(title) + (
        '<div class="cmp">\n'
        f'  <div class="col left"><div class="head">求職者が抱くイメージ</div><ul>{left}</ul></div>\n'
        f'  <div class="col right"><div class="head">現場の実態</div><ul>{right}</ul></div>\n'
        '</div>\n'
    )


def render_target_psychology(title: str, target_insights: dict) -> Optional[str]:
    axes = (target_insights or {}).get("psychological_axes") or []
    if not axes:
        return None
    rows = "\n".join(
        f"| {_esc(a.get('axis'))} | {_esc(a.get('detail'))} | {_esc(a.get('appeal_direction'))} |"
        for a in axes
    )
    return _header(title) + (
        "| 重視する軸 | 具体的な不安・欲求 | 訴求の方向性 |\n"
        "|---|---|---|\n" + rows + "\n"
    )


def render_strategy_summary(title: str, axes: list) -> Optional[str]:
    if not axes:
        return None
    cards = "\n".join(
        f'  <div class="card"><div class="num">{i:02d}</div>'
        f'<div class="ttl">{_esc(a.get("title"))}</div>'
        f'<div class="body">{_esc(a.get("rationale") or a.get("target_psychology") or "")}</div></div>'
        for i, a in enumerate(axes[:3], start=1)
    )
    return _header(title) + f'<div class="cards">\n{cards}\n</div>\n'


def render_strategy_detail(title: str, axis: dict) -> Optional[str]:
    if not axis:
        return None
    copies = (axis.get("catchcopies") or [])
    body = ""
    if axis.get("rationale"):
        body += f"{_esc(axis['rationale'])}\n\n"
    if copies:
        body += "**キャッチコピー例**\n\n"
        body += "\n".join(
            f"- {_esc(c.get('text'))}" + (f"（{_esc(c.get('psychology_link'))}）" if c.get("psychology_link") else "")
            for c in copies[:6]
        ) + "\n"
    return _header(title) + (body or "—\n")


def render_segment_comparison(title: str, industry_analysis: dict) -> Optional[str]:
    """比較表: 募集職種 vs 混同されやすい類似職種（reference: 施設警備 vs 交通誘導）."""
    seg = (industry_analysis or {}).get("confusable_segments") or {}
    rows = seg.get("comparison_rows") or []
    confused = seg.get("confused_with")
    if not rows or not confused:
        return None  # no structured comparison data → LLM fallback
    target_h = _esc(seg.get("target_segment") or "募集職種")
    other_h = _esc(confused)
    body_rows = "\n".join(
        f"| {_esc(r.get('aspect'))} | {_esc(r.get('target'))} | {_esc(r.get('other'))} |"
        for r in rows
    )
    return _header(title) + (
        f"| 観点 | {target_h} | {other_h} |\n"
        "|---|---|---|\n" + body_rows + "\n"
    )


def render_success_case(title: str, case: dict) -> Optional[str]:
    if not case:
        return None
    before = case.get("before") or {}
    after = case.get("after") or {}

    def _metrics(d: dict) -> str:
        parts = []
        if d.get("catchcopy"):
            parts.append(f'<div class="metric">コピー: {_esc(d["catchcopy"])}</div>')
        if d.get("pv") is not None:
            parts.append(f'<div class="metric">PV: {_esc(d.get("pv"))}</div>')
        if d.get("applications") is not None:
            parts.append(f'<div class="metric">応募: {_esc(d.get("applications"))}</div>')
        return "".join(parts) or '<div class="metric">—</div>'

    summary = _esc(case.get("case_summary") or "")
    improvement = _esc(case.get("improvement") or "")
    body = _header(title)
    if summary:
        body += f"{summary}\n\n"
    body += (
        '<div class="ba">\n'
        f'  <div class="col before"><div class="head">Before</div>{_metrics(before)}</div>\n'
        f'  <div class="col after"><div class="head">After</div>{_metrics(after)}</div>\n'
        '</div>\n'
    )
    if improvement:
        body += f"\n**改善ポイント**: {improvement}\n"
    return body


# Sections rendered deterministically; everything else falls back to the LLM.
_DETERMINISTIC = {
    "cover", "agenda", "principles", "misconception", "segment_comparison",
    "target_psychology", "strategy_summary", "strategy_detail", "success_case",
}


def render_section(page_spec: dict, stages: dict) -> Optional[str]:
    """Render a page deterministically if its section is supported, else None.

    `stages` carries: story_theme, stage7, stage8.
    """
    section = page_spec.get("section")
    if section not in _DETERMINISTIC:
        return None
    title = page_spec.get("title", "")
    s7 = stages.get("stage7") or {}
    s8 = stages.get("stage8") or {}
    ind = s7.get("industry_analysis") or {}
    ti = s7.get("target_insights") or {}
    axes = s8.get("strategy_axes") or []
    cases = s8.get("success_case_references") or []

    try:
        if section == "cover":
            return render_cover(title, stages.get("story_theme", ""))
        if section == "agenda":
            return render_agenda(title, page_spec.get("key_points") or [])
        if section == "principles":
            return render_principles(title)
        if section == "misconception":
            return render_misconception(title, ind)
        if section == "segment_comparison":
            return render_segment_comparison(title, ind)
        if section == "target_psychology":
            return render_target_psychology(title, ti)
        if section == "strategy_summary":
            return render_strategy_summary(title, axes)
        if section == "strategy_detail":
            # index 優先（LLM の axis id は重複し得るため）。範囲外は id で後方互換。
            idx = page_spec.get("axis_index")
            if isinstance(idx, int) and 0 <= idx < len(axes):
                axis = axes[idx]
            else:
                axis = _find_axis(axes, page_spec.get("axis_id"))
            return render_strategy_detail(title, axis)
        if section == "success_case":
            idx = page_spec.get("case_index", 0)
            case = cases[idx] if 0 <= idx < len(cases) else None
            return render_success_case(title, case)
    except Exception as e:  # never break the pipeline on a render error
        logger.warning("Component render failed for section %s: %s", section, e)
        return None
    return None


def _find_axis(axes: list, axis_id) -> dict:
    for a in axes:
        if a.get("id") == axis_id:
            return a
    return axes[0] if axes else {}
