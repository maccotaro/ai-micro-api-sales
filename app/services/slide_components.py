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


def ensure_page_title(md: str, title: str) -> str:
    """Prepend `# title` when the page Markdown lacks an H1.

    LLM-generated pages sometimes omit the heading, which drops the brand
    header bar entirely. The H1 is required by the brand layout.
    """
    if not title or md.lstrip().startswith("# "):
        return md
    return f"# {title}\n\n{md}"


def render_cover(title: str, theme: str) -> str:
    # First page gets `_class: lead` applied by marp_export; keep it heading-based.
    # title と theme が同一になりがちなので重複表示を避ける。
    sub = "採用成功に向けたご提案"
    body = f"# {title}\n\n## {sub}\n"
    if theme and theme.strip() and theme.strip() not in title:
        body += f"\n{theme}\n"
    return body


def render_agenda(title: str, items: list[str]) -> str:
    lis = "\n".join(
        f'<li><span class="num">{i:02d}</span> {_esc(t)}</li>'
        for i, t in enumerate(items, start=1)
    )
    return _header(title) + f'<ol class="agenda">\n{lis}\n</ol>\n'


def _step(t: str, d: str) -> str:
    return f'<div class="step"><div class="t">{t}</div><div class="d">{d}</div></div>'


def render_principles(title: str) -> str:
    """固定テンプレ: 応募獲得最大化のSEO/CVR 3ステップフロー（業界非依存の方法論）。"""
    seo = (_step("Googleの理念", "検索意図に「最適な答え」を出す") + '<div class="arrow">↓</div>'
           + _step("E-E-A-Tの重視", "経験・専門性・権威性・信頼性が順位を決める") + '<div class="arrow">↓</div>'
           + _step("重複コンテンツはリスク", "似た原稿は検索結果から除外される可能性")
           + '<div class="concl">独自性と具体性が必要</div>')
    cvr = (_step("入口と出口の整合性", "「検索条件」と「原稿内容」の一致を求める") + '<div class="arrow">↓</div>'
           + _step("NG例：情報の不一致", "「主婦歓迎」なのに男性写真ばかり→離脱増") + '<div class="arrow">↓</div>'
           + _step("可視化による安心感", "写真・具体的な言葉で応募の不安を払拭")
           + '<div class="concl">透明性と安心感が必要</div>')
    return _header(title) + (
        '<h2>応募獲得の最大化には、ユーザー体験の向上と有益で正しい情報が必要です</h2>\n'
        '<div class="cols">\n'
        f'  <div class="col"><div class="colhead">SEOの観点（集客の最大化）</div>{seo}</div>\n'
        f'  <div class="col"><div class="colhead">CVRの観点（応募率の向上）</div>{cvr}</div>\n'
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
    """心理軸ごとの横帯カード(軸名→不安・欲求→訴求方向)。表より密度が高い。"""
    ti = target_insights or {}
    axes = ti.get("psychological_axes") or []
    if not axes:
        return None
    body = _header(title)
    if ti.get("primary_target"):
        body += (
            '<div class="lead-psy"><span class="lbl">主要ターゲット</span>'
            f'{_esc(ti["primary_target"])}</div>\n'
        )
    rows = ""
    for a in axes[:4]:
        rows += (
            '<div class="axisrow">'
            f'<div class="axname">{_esc(a.get("axis"))}</div>'
            f'<div class="axdetail"><div class="cap">具体的な不安・欲求</div>{_esc(a.get("detail"))}</div>'
            '<div class="axar">▶</div>'
            f'<div class="axappeal"><div class="cap">訴求の方向性</div>{_esc(a.get("appeal_direction"))}</div>'
            '</div>'
        )
    body += f'<div class="axisrows">{rows}</div>\n'
    body += '<div class="concl">この心理軸に沿って原稿・キャッチコピーを設計します</div>\n'
    return body


def render_strategy_summary(title: str, axes: list) -> Optional[str]:
    """3カード(タイトル+狙う心理+パラダイム+メリットチップ+コピー例)＋結論帯。"""
    if not axes:
        return None
    cards = ""
    for i, a in enumerate(axes[:3], start=1):
        para = a.get("paradigm") or {}
        pd = ""
        if para.get("old") or para.get("new"):
            pd = (
                f'<div class="pd"><span class="pold">{_esc(para.get("old"))}</span>'
                f' <span class="par">▶</span> '
                f'<span class="pnew">{_esc(para.get("new"))}</span></div>'
            )
        chips = "".join(
            f'<span class="chip">{_esc(m)}</span>'
            for m in (a.get("merits") or [])[:5] if m
        )
        chips = f'<div class="chips">{chips}</div>' if chips else ""
        copies = [c for c in (a.get("catchcopies") or []) if c.get("text")]
        copy_line = (
            f'<div class="copyline">例:「{_esc(copies[0]["text"])}」</div>' if copies else ""
        )
        cards += (
            f'<div class="card"><div class="num">{i:02d}</div>'
            f'<div class="ttl">{_esc(a.get("title"))}</div>'
            f'<div class="body">{_esc(a.get("target_psychology") or a.get("rationale") or "")}</div>'
            f'{pd}{chips}{copy_line}</div>\n'
        )
    return _header(title) + (
        f'<div class="cards">\n{cards}</div>\n'
        '<div class="concl">この3つの戦略軸で原稿を再設計し、応募獲得を最大化します</div>\n'
    )


def render_strategy_detail(title: str, axis: dict) -> Optional[str]:
    """狙う心理 + paradigm(旧→新) + merits(5カード) + キャッチコピー(刺さる理由付)。

    上流 stage8 の各軸データ(target_psychology/paradigm/merits/catchcopies)を
    余すところなく描画し、サンエス参照デッキ並みの密度でページを埋める。
    """
    if not axis:
        return None
    html = _header(title)
    # 狙うターゲット心理(リード): ページ冒頭に文脈を与え、余白を抑える。
    psy = axis.get("target_psychology") or axis.get("rationale") or ""
    if psy:
        html += (
            '<div class="lead-psy">'
            '<span class="lbl">狙うターゲット心理</span>'
            f'{_esc(psy)}</div>\n'
        )
    para = axis.get("paradigm") or {}
    if para.get("old") or para.get("new"):
        html += (
            '<div class="para">'
            f'<div class="old">従来「{_esc(para.get("old"))}」</div>'
            '<div class="ar">パラダイムシフト ▶</div>'
            f'<div class="new">新定義「{_esc(para.get("new"))}」</div>'
            '</div>\n'
        )
    merits = [m for m in (axis.get("merits") or []) if m][:5]
    if merits:
        cards = "".join(f'<div class="merit">{_esc(m)}</div>' for m in merits)
        html += f'<div class="merits">{cards}</div>\n'
    copies = [c for c in (axis.get("catchcopies") or []) if c.get("text")][:3]
    if copies:
        lis = ""
        for c in copies:
            reason = c.get("psychology_link") or ""
            rs = f'<span class="rs">→ {_esc(reason)}</span>' if reason else ""
            lis += f'<li><span class="ct">{_esc(c.get("text"))}</span>{rs}</li>'
        html += f'<div class="cc"><div class="h">キャッチコピー例</div><ul>{lis}</ul></div>\n'
    if not (psy or para or merits or copies):
        html += f"{_esc(axis.get('rationale') or '')}\n"
    return html


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
    """Before/After を大型数値＋矢印＋改善バナーで描画(サンエス参照デッキ準拠)。"""
    if not case:
        return None
    before = case.get("before") or {}
    after = case.get("after") or {}

    def _metrics(d: dict, big: bool) -> str:
        parts = []
        if d.get("catchcopy"):
            parts.append(f'<div class="metric">コピー:「{_esc(d["catchcopy"])}」</div>')
        nums = ""
        if d.get("pv") is not None:
            nums += f'<div class="kpi"><div class="kv">{_esc(d.get("pv"))}</div><div class="kl">PV</div></div>'
        if d.get("applications") is not None:
            cls = "kv big" if big else "kv"
            nums += f'<div class="kpi"><div class="{cls}">{_esc(d.get("applications"))}</div><div class="kl">応募</div></div>'
        if nums:
            parts.append(f'<div class="kpis">{nums}</div>')
        return "".join(parts) or '<div class="metric">—</div>'

    summary = _esc(case.get("case_summary") or "")
    improvement = _esc(case.get("improvement") or "")
    body = _header(title)
    if summary:
        body += (
            '<div class="lead-psy"><span class="lbl">事例概要</span>'
            f'{summary}</div>\n'
        )
    body += (
        '<div class="ba">\n'
        f'  <div class="col before"><div class="head">Before</div>{_metrics(before, False)}</div>\n'
        '  <div class="ba-ar">▶</div>\n'
        f'  <div class="col after"><div class="head">After</div>{_metrics(after, True)}</div>\n'
        '</div>\n'
    )
    if improvement:
        body += f'<div class="improve"><span class="lbl">改善ポイント</span>{improvement}</div>\n'
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
