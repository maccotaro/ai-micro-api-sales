"""Formatters for Stage 6-10 output display in SSE streaming."""


def format_stage6(out: dict) -> str:
    """Format Stage 6 (Proposal Context Collection) for display."""
    parts = []
    if out.get("proposal_kb_chunks"):
        parts.append(f"提案書KB: {len(out['proposal_kb_chunks'])}件")
    if out.get("end_user_psychology_chunks"):
        parts.append(f"エンドユーザー心理: {len(out['end_user_psychology_chunks'])}件")
    if out.get("decision_maker_psychology_chunks"):
        parts.append(f"担当者心理: {len(out['decision_maker_psychology_chunks'])}件")
    if out.get("success_cases"):
        parts.append(f"成功事例: {len(out['success_cases'])}件")
    if out.get("publication_records"):
        parts.append(f"実績データ: {len(out['publication_records'])}件")
    if parts:
        return "## 提案コンテキスト収集\n\n" + "\n".join(f"- {p}" for p in parts)
    return "## 提案コンテキスト収集\n\n（データなし）"


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
