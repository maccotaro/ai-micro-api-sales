"""Formatters for Stage 6-10 output display in SSE streaming."""


def render_missing_alerts(output: dict) -> str:
    """Render Stage 5 抜け漏れアラート (missing required-slot) as markdown."""
    alerts = output.get("missing_alerts", [])
    if not alerts:
        return ""
    out = ["\n### ⚠️ 抜け漏れアラート（提案に必要な情報）",
           "**要対応（未充足）**" if output.get("missing_alerts_blocking")
           else f"確認事項 {len(alerts)} 件"]
    for a in alerts:
        out.append(f"- **{a.get('label', '')}**: {a.get('reason', '')}")
        if a.get("question_example"):
            out.append(f"  - 質問例: {a['question_example']}")
    return "\n".join(out)


def _ctx_excerpt(item, n: int = 90) -> str:
    """One-line excerpt of a context item (string chunk or dict)."""
    if isinstance(item, dict):
        item = (item.get("title") or item.get("achievement") or item.get("company_name")
                or item.get("content") or item.get("store_name") or str(item))
    return " ".join(str(item).split())[:n] + ("…" if len(" ".join(str(item).split())) > n else "")


def format_stage6(out: dict) -> str:
    """Format Stage 6 (Proposal Context Collection): list collected items with excerpts."""
    lines = ["## 提案コンテキスト収集"]
    sections = [
        ("提案書KB（戦略・事例）", out.get("proposal_kb_chunks")),
        ("エンドユーザー心理", out.get("end_user_psychology_chunks")),
        ("担当者心理", out.get("decision_maker_psychology_chunks")),
        ("成功事例", out.get("success_cases")),
        ("掲載実績データ", out.get("publication_records")),
    ]
    for title, items in sections:
        if not items:
            continue
        lines.append(f"\n### {title}（{len(items)}件）")
        for it in items[:5]:
            lines.append(f"- {_ctx_excerpt(it)}")
        if len(items) > 5:
            lines.append(f"- …他 {len(items) - 5} 件")
    if len(lines) == 1:
        return "## 提案コンテキスト収集\n\n（データなし）"
    return "\n".join(lines)


def format_stage7(out: dict) -> str:
    """Format Stage 7 (Industry & Target Analysis) for display."""
    lines = ["## 業界・ターゲット分析"]
    ia = out.get("industry_analysis", {})
    if ia:
        lines.append(f"\n### 業界: {ia.get('industry_name', '不明')}")
        for jt in ia.get("job_types", []):
            lines.append(f"\n**{jt.get('name', '')}**")
            if jt.get("characteristics"):
                lines.append("- 特徴: " + "、".join(jt["characteristics"]))
            if jt.get("common_misconceptions"):
                lines.append("- 誤解: " + "、".join(jt["common_misconceptions"]))
            if jt.get("actual_reality"):
                lines.append(f"- 実態: {jt['actual_reality']}")
        if ia.get("competitive_advantages"):
            lines.append("\n**競合優位性**: " + "、".join(ia["competitive_advantages"]))

    ti = out.get("target_insights", {})
    if ti:
        lines.append(f"\n### ターゲット: {ti.get('primary_target', '不明')}")
        for axis in ti.get("psychological_axes", []):
            lines.append(f"- **{axis.get('axis', '')}**: {axis.get('detail', '')} → {axis.get('appeal_direction', '')}")

    dm = out.get("decision_maker_insights", {})
    if dm:
        lines.append(f"\n### 担当者: {dm.get('role', '不明')}")
        if dm.get("judgment_criteria"):
            lines.append("- 判断基準: " + "、".join(dm["judgment_criteria"]))
        if dm.get("common_concerns"):
            lines.append("- 懸念: " + "、".join(dm["common_concerns"]))

    source = out.get("source", "")
    if source == "general_knowledge":
        lines.append("\n> ※ 一般知識に基づく分析です。心理パターンKBにデータを追加すると精度が向上します。")

    return "\n".join(lines)


def format_stage8(out: dict) -> str:
    """Format Stage 8 (Appeal Strategy) for display."""
    lines = ["## 訴求戦略"]
    for axis in out.get("strategy_axes", []):
        lines.append(f"\n### {axis.get('id', '')}: {axis.get('title', '')}")
        lines.append(f"- 根拠: {axis.get('rationale', '')}")
        lines.append(f"- 対象心理: {axis.get('target_psychology', '')}")
        for copy in axis.get("catchcopies", []):
            lines.append(f"- 「{copy.get('text', '')}」")
            lines.append(f"  - 心理紐づけ: {copy.get('psychology_link', '')}")

    cases = out.get("success_case_references", [])
    if cases:
        lines.append("\n### 成功事例 Before/After")
        for case in cases:
            lines.append(f"\n**{case.get('case_summary', '')}**")
            before = case.get("before", {})
            after = case.get("after", {})
            lines.append(f"- Before: 「{before.get('catchcopy', '')}」 PV:{before.get('pv', 0)} 応募:{before.get('applications', 0)}")
            lines.append(f"- After: 「{after.get('catchcopy', '')}」 PV:{after.get('pv', 0)} 応募:{after.get('applications', 0)}")
            lines.append(f"- 改善: {case.get('improvement', '')}")

    return "\n".join(lines)


def format_stage9(out: dict) -> str:
    """Format Stage 9 (Story Structure) for display."""
    lines = [f"## ストーリー構成\n\n**テーマ**: {out.get('story_theme', '')}"]
    lines.append(f"\n| # | タイトル | 目的 | データソース |")
    lines.append("|---|---------|------|-------------|")
    for page in out.get("pages", []):
        sources = ", ".join(page.get("data_sources", []))
        lines.append(f"| {page.get('page_number', '')} | {page.get('title', '')} | {page.get('purpose', '')} | {sources} |")
    return "\n".join(lines)
