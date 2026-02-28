"""Output formatters for the proposal pipeline SSE streaming.

Extracted from proposal_pipeline_service.py to keep files under 500 lines.
"""
import json


def sse_event(event_type: str, data: dict) -> str:
    """Format SSE event string."""
    data["type"] = event_type
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def format_context_summary(context: dict) -> str:
    """Format Stage 0 context collection as markdown summary."""
    lines = []
    meeting = context.get("meeting", {})
    lines.append("### 商談情報")
    lines.append(f"- **企業名**: {meeting.get('company_name', '不明')}")
    if meeting.get("industry"):
        lines.append(f"- **業種**: {meeting['industry']}")
    if meeting.get("area"):
        lines.append(f"- **地域**: {meeting['area']}")
    if meeting.get("meeting_date"):
        lines.append(f"- **商談日**: {meeting['meeting_date']}")
    lines.append("")

    kb_results = context.get("kb_results", {})
    if kb_results:
        lines.append("### ナレッジベース検索結果")
        for cat_name, results in kb_results.items():
            lines.append(f"- **{cat_name}**: {len(results)}件取得")
        lines.append("")

    products = context.get("product_data", [])
    if products:
        lines.append(f"### 商品データ: {len(products)}件")
        for p in products[:5]:
            lines.append(f"- {p.get('name', '')}")
        if len(products) > 5:
            lines.append(f"- ...他 {len(products) - 5}件")
        lines.append("")

    pub_data = context.get("publication_data", [])
    if pub_data:
        lines.append(f"### 前回掲載実績: {len(pub_data)}件")
        lines.append("")

    campaigns = context.get("campaign_data", [])
    if campaigns:
        lines.append(f"### キャンペーン情報: {len(campaigns)}件")
        lines.append("")

    sim = context.get("simulation_data", [])
    wage = context.get("wage_data", [])
    if sim:
        lines.append(f"### シミュレーションパラメータ: {len(sim)}件")
    if wage:
        lines.append(f"### 地域別時給データ: {len(wage)}件")

    return "\n".join(lines)


def format_stage_output(stage_num: int, output: dict) -> str:
    """Format a stage output as markdown using the appropriate formatter."""
    formatters = {
        1: _format_issues,
        2: _format_proposals,
        3: _format_action_plan,
        4: _format_ad_copy,
        5: _format_checklist_summary,
    }
    formatter = formatters.get(stage_num)
    if formatter:
        result = formatter(output)
        if result.strip():
            return result
    if "raw_response" in output:
        return f"```\n{output['raw_response']}\n```"
    return f"```json\n{json.dumps(output, ensure_ascii=False, indent=2)}\n```"


def format_section_content(section_id: str, stage: int, output: dict) -> str:
    """Format content for a specific output-template section.

    Sections sharing a stage get different sub-content.  Only the
    ``proposal`` section returns JSON (for ShochikubaiComparison).
    All other sections return readable markdown.
    """
    _section_formatters: dict[str, object] = {
        "issues": _format_issues,
        "agenda": _format_agenda_section,
        "proposal": _format_proposal_json,
        "action_plan": _format_action_plan,
        "ad_copy": _format_ad_copy,
        "checklist": _format_checklist_section,
        "summary": _format_summary_section,
    }
    fmt = _section_formatters.get(section_id)
    if fmt:
        result = fmt(output)  # type: ignore[operator]
        if result and result.strip():
            return result
    # Fall back to stage-level markdown formatter
    return format_stage_output(stage, output)


def _format_issues(output: dict) -> str:
    """Format Stage 1 issues as markdown."""
    lines = []
    for issue in output.get("issues", []):
        lines.append(f"### {issue.get('id', '')} {issue.get('title', '')}")
        lines.append(f"**カテゴリ**: {issue.get('category', '')}")
        lines.append(f"\n{issue.get('detail', '')}")
        bant = issue.get("bant_c", {})
        if bant:
            lines.append("\n| BANT-C | ステータス | 詳細 |")
            lines.append("|--------|-----------|------|")
            for key in ["budget", "authority", "need", "timeline", "competitor"]:
                item = bant.get(key, {})
                lines.append(f"| {key.upper()} | {item.get('status', '')} | {item.get('detail', '')} |")
        lines.append("")
    return "\n".join(lines)


def _format_proposals(output: dict) -> str:
    """Format Stage 2 proposals (shochikubai structure) as markdown."""
    lines = []
    tier_labels = {"matsu": "松", "take": "竹", "ume": "梅"}

    for prop in output.get("proposals", []):
        issue_id = prop.get("issue_id", "")
        lines.append(f"### 課題 {issue_id} への提案")

        shochikubai = prop.get("shochikubai", {})
        recommended = prop.get("recommended", "")
        reason = prop.get("recommendation_reason", "")
        if recommended:
            lines.append(f"**推奨**: {tier_labels.get(recommended, recommended)}プラン")
        if reason:
            lines.append(f"*{reason}*")
        lines.append("")

        for tier_key in ["matsu", "take", "ume"]:
            tier = shochikubai.get(tier_key, {})
            if not tier:
                continue
            label = tier_labels.get(tier_key, tier_key)
            star = " **★推奨**" if tier_key == recommended else ""
            total = tier.get("total_price")
            price_str = f" (¥{total:,})" if isinstance(total, (int, float)) and total else ""
            lines.append(f"#### {label}プラン{price_str}{star}")
            for item in tier.get("items", []):
                name = item.get("media_name", "")
                prod = item.get("product_name", "")
                price = item.get("final_price") or item.get("price")
                period = item.get("period", "")
                price_part = f" ¥{price:,}" if isinstance(price, (int, float)) and price else ""
                disc = item.get("campaign_discount")
                disc_part = f" (割引: {disc})" if disc else ""
                lines.append(f"- {name} / {prod}{price_part}{disc_part} ({period})")
            effect = tier.get("expected_effect", "")
            if effect:
                lines.append(f"\n期待効果: {effect}")
            rationale = tier.get("rationale", "")
            if rationale:
                lines.append(f"選定理由: {rationale}")
            lines.append("")

    # Budget summary
    budget = output.get("total_budget_range", {})
    if budget:
        lines.append("### 予算比較")
        for key, label in [("matsu_total", "松"), ("take_total", "竹"), ("ume_total", "梅")]:
            val = budget.get(key)
            if isinstance(val, (int, float)) and val:
                lines.append(f"- {label}: ¥{val:,}")
        lines.append("")

    # Reverse timeline
    timeline = output.get("reverse_timeline", [])
    if timeline:
        lines.append("### 逆算タイムライン")
        for t in timeline:
            lines.append(f"- **{t.get('date', '')}** {t.get('milestone', '')}: {t.get('action', '')}")
        lines.append("")

    # Seasonal context
    seasonal = output.get("seasonal_context", "")
    if seasonal:
        lines.append(f"### 季節考慮: {seasonal}")
        lines.append("")

    # Agenda
    agenda = output.get("agenda_items", [])
    if agenda:
        lines.append("### 次回商談アジェンダ")
        for i, item in enumerate(agenda, 1):
            lines.append(f"{i}. {item}")

    return "\n".join(lines)


def _format_action_plan(output: dict) -> str:
    """Format Stage 3 action plan as markdown (includes coaching & follow-up)."""
    lines: list[str] = []

    # Action plan items
    for action in output.get("action_plan", []):
        lines.append(f"### {action.get('id', '')} {action.get('title', '')}")
        lines.append(f"**優先度**: {action.get('priority', '')}")
        lines.append(f"**対応課題**: {action.get('related_issue_id', '')}")
        lines.append(f"\n{action.get('description', '')}")
        for st in action.get("subtasks", []):
            lines.append(f"- [ ] {st.get('title', '')}: {st.get('detail', '')}")
        lines.append("")

    # Sales coaching
    coaching = output.get("sales_coaching", {})
    if coaching:
        questions = coaching.get("deep_dive_questions", [])
        if questions:
            lines.append("### 深掘り質問")
            for q in questions:
                lines.append(f"- **{q.get('topic', '')}**: {q.get('question', '')}")
                if q.get("follow_up"):
                    lines.append(f"  フォローアップ: {q['follow_up']}")
            lines.append("")

        objections = coaching.get("objection_handling", [])
        if objections:
            lines.append("### 想定反論と対応")
            for o in objections:
                lines.append(f"- **反論**: {o.get('objection', '')}")
                lines.append(f"  **対応**: {o.get('response', '')}")
                if o.get("evidence"):
                    lines.append(f"  根拠: {o['evidence']}")
            lines.append("")

        talk_script = coaching.get("talk_script_outline", [])
        if talk_script:
            lines.append("### トークスクリプト")
            for phase in talk_script:
                dur = phase.get("duration_minutes", "")
                lines.append(f"- **{phase.get('phase', '')} - {phase.get('title', '')}** ({dur}分)")
                for kp in phase.get("key_points", []):
                    lines.append(f"  - {kp}")
            lines.append("")

    # Follow-up actions
    followup = output.get("follow_up_actions", {})
    if followup:
        email = followup.get("email_draft", {})
        if email:
            lines.append("### フォローアップメール案")
            lines.append(f"**件名**: {email.get('subject', '')}")
            lines.append(f"\n{email.get('body', '')}")
            lines.append("")

        events = followup.get("calendar_events", [])
        if events:
            lines.append("### カレンダー登録")
            for ev in events:
                lines.append(
                    f"- **{ev.get('title', '')}** "
                    f"({ev.get('duration_minutes', '')}分, +{ev.get('date_offset_days', '')}日後)"
                )
                lines.append(f"  {ev.get('description', '')}")
            lines.append("")

        tasks = followup.get("tasks", [])
        if tasks:
            lines.append("### フォローアップタスク")
            for t in tasks:
                lines.append(
                    f"- [ ] **{t.get('title', '')}** "
                    f"(優先: {t.get('priority', '')}, 担当: {t.get('assignee', '')}, "
                    f"+{t.get('due_offset_days', '')}日後)"
                )
            lines.append("")

    return "\n".join(lines)


def _format_ad_copy(output: dict) -> str:
    """Format Stage 4 ad copy as markdown."""
    lines = []
    persona = output.get("target_persona", {})
    if persona:
        lines.append("### ターゲットペルソナ")
        lines.append(f"- **年齢層**: {persona.get('age_range', '')}")
        lines.append(f"- **現職**: {persona.get('current_job', '')}")
        lines.append(f"- **動機**: {persona.get('motivation', '')}")
        lines.append("")

    copies = output.get("catchcopy_proposals", [])
    if copies:
        lines.append("### キャッチコピー案")
        for i, c in enumerate(copies, 1):
            lines.append(f"{i}. **{c.get('copy', '')}**")
            lines.append(f"   {c.get('concept', '')}")
        lines.append("")

    draft = output.get("job_description_draft", {})
    if draft:
        lines.append(f"### 求人タイトル案: {draft.get('title', '')}")
        lines.append(f"\n**仕事内容**:\n{draft.get('work_content', '')}")
        lines.append(f"\n**応募資格**:\n{draft.get('qualifications', '')}")

    return "\n".join(lines)


def _format_checklist_summary(output: dict) -> str:
    """Format Stage 5 checklist and summary as markdown."""
    lines: list[str] = []
    checklist = output.get("checklist", [])
    if checklist:
        lines.append("### チェックリスト")
        for item in checklist:
            lines.append(f"- [ ] **{item.get('category', '')}** ({item.get('related_issue_id', '')})")
            lines.append(f"  {item.get('item', '')}")
            q = item.get("question_example", "")
            if q:
                lines.append(f"  *質問例: {q}*")
        lines.append("")

    summary = output.get("summary", {})
    if summary:
        lines.append("### まとめ")
        lines.append(summary.get("overview", ""))
        lines.append("")
        for kp in summary.get("key_points", []):
            lines.append(f"- {kp.get('point', '')} (課題: {', '.join(kp.get('related_issues', []))})")
        ns = summary.get("next_steps", [])
        if ns:
            lines.append("\n### 次のステップ")
            for i, step in enumerate(ns, 1):
                lines.append(f"{i}. {step}")

    return "\n".join(lines)


# ── Section-specific formatters (for output-template sections) ──


def _format_agenda_section(output: dict) -> str:
    """Format 'agenda' section: agenda items + reverse timeline + seasonal."""
    lines: list[str] = []

    agenda = output.get("agenda_items", [])
    if agenda:
        for i, item in enumerate(agenda, 1):
            lines.append(f"{i}. {item}")
        lines.append("")

    timeline = output.get("reverse_timeline", [])
    if timeline:
        lines.append("### 逆算タイムライン")
        for t in timeline:
            lines.append(
                f"- **{t.get('date', '')}** {t.get('milestone', '')}: {t.get('action', '')}"
            )
        lines.append("")

    seasonal = output.get("seasonal_context", "")
    if seasonal:
        lines.append("### 季節考慮")
        lines.append(seasonal)
        lines.append("")

    return "\n".join(lines)


def _format_proposal_json(output: dict) -> str:
    """Format 'proposal' section as JSON for ShochikubaiComparison."""
    subset: dict = {}
    for key in ("proposals", "total_budget_range", "over_budget_justification", "trend_impact"):
        val = output.get(key)
        if val is not None:
            subset[key] = val
    if not subset:
        return ""
    return json.dumps(subset, ensure_ascii=False, indent=2)


def _format_checklist_section(output: dict) -> str:
    """Format 'checklist' section: only checklist items as markdown."""
    lines: list[str] = []
    checklist = output.get("checklist", [])
    if checklist:
        for item in checklist:
            lines.append(f"- [ ] **{item.get('category', '')}** ({item.get('related_issue_id', '')})")
            lines.append(f"  {item.get('item', '')}")
            q = item.get("question_example", "")
            if q:
                lines.append(f"  *質問例: {q}*")
    return "\n".join(lines)


def _format_summary_section(output: dict) -> str:
    """Format 'summary' section: summary + fact check + reference docs."""
    lines: list[str] = []

    summary = output.get("summary", {})
    if summary:
        overview = summary.get("overview", "")
        if overview:
            lines.append(overview)
            lines.append("")
        for kp in summary.get("key_points", []):
            lines.append(f"- {kp.get('point', '')} (課題: {', '.join(kp.get('related_issues', []))})")
        ns = summary.get("next_steps", [])
        if ns:
            lines.append("\n### 次のステップ")
            for i, step in enumerate(ns, 1):
                lines.append(f"{i}. {step}")
        lines.append("")

    fact_check = output.get("fact_check", {})
    if fact_check:
        claims = fact_check.get("claims", [])
        if claims:
            lines.append("### ファクトチェック")
            status_marks = {"verified": "✓", "unverified": "?", "contradicted": "✗"}
            for claim in claims:
                mark = status_marks.get(claim.get("status", ""), "")
                lines.append(f"- {mark} {claim.get('claim', '')} ({claim.get('status', '')})")
                note = claim.get("note", "")
                if note:
                    lines.append(f"  {note}")
            lines.append("")

    ref_docs = output.get("reference_documents", [])
    if ref_docs:
        lines.append("### 参考資料")
        for doc in ref_docs:
            lines.append(f"- **{doc.get('name', '')}** ({doc.get('category', '')}): {doc.get('usage', '')}")
            url = doc.get("url", "")
            if url:
                lines.append(f"  URL: {url}")

    return "\n".join(lines)
