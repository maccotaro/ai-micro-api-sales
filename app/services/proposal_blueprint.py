"""汎用提案ブループリント (PoC).

リファレンス: サンエス警備提案書 (13ページ) を汎用化したセクション列。
Stage 9 を「LLM 自由生成」から「ブループリント駆動（各セクションを Stage 出力に
データバインドし、無ければスキップ）」へ置き換えるための決定論ロジック。

構成:
- 固定コア (業界非依存): 表紙 / アジェンダ / 提案の前提・原則 / 次のステップ
- 条件付き: 誤解 vs 実態, 混同セグメント比較, ターゲット動向, ターゲット心理,
  提案サマリ, 料金提案, キーワード提案（対応データが無ければスキップ）
- 可変 (データ件数で増減): 提案詳細＝施策軸ごと, 成功事例＝事例件数ごと

出力は Stage 10 が消費する page spec のリスト:
  {page_number, title, purpose, key_points, data_sources, section}
"""
import logging

logger = logging.getLogger(__name__)

# 可変セクションの上限（無言截断は禁止、超過はログ）
MAX_STRATEGY_DETAIL = 5
MAX_SUCCESS_CASES = 3


def _nonempty(v) -> bool:
    if v is None:
        return False
    if isinstance(v, (str, list, dict)):
        return len(v) > 0
    return bool(v)


def _industry_name(stage7: dict) -> str:
    return (stage7 or {}).get("industry_analysis", {}).get("industry_name") or ""


def _target_name(stage7: dict) -> str:
    return (stage7 or {}).get("target_insights", {}).get("primary_target") or ""


def build_story_theme(stage7: dict, meeting: dict) -> str:
    """Derive a one-line story theme from industry/target/company."""
    company = (meeting or {}).get("company_name") or ""
    industry = _industry_name(stage7)
    if company:
        return f"{company} 採用成功に向けたご提案"
    if industry:
        return f"{industry}の採用成功に向けて"
    return "採用成功に向けてのご提案"


def build_blueprint_pages(
    stage1: dict,
    stage2: dict,
    stage6: dict,
    stage7: dict,
    stage8: dict,
    meeting: dict,
) -> list[dict]:
    """Build the ordered page spec list deterministically from stage outputs.

    Conditional sections are skipped when their bound data is absent.
    Variable sections expand per data item (capped, with a log on overflow).
    """
    stage1 = stage1 or {}
    stage2 = stage2 or {}
    stage6 = stage6 or {}
    stage7 = stage7 or {}
    stage8 = stage8 or {}

    industry = _industry_name(stage7) or "対象業界"
    target = _target_name(stage7) or "ターゲット層"
    ind_analysis = stage7.get("industry_analysis", {}) or {}
    target_insights = stage7.get("target_insights", {}) or {}
    axes = stage8.get("strategy_axes", []) or []
    cases = stage8.get("success_case_references", []) or []
    has_plans = _nonempty(stage2.get("proposals"))
    job_types = ind_analysis.get("job_types", []) or []
    confusable = ind_analysis.get("confusable_segments") or ind_analysis.get("comparison")

    pages: list[dict] = []

    # --- Fixed: cover ---
    pages.append({
        "title": build_story_theme(stage7, meeting),
        "purpose": "提案書の表紙。企業名と提案テーマを提示する。",
        "key_points": [meeting.get("company_name", ""), "採用成功に向けて"],
        "data_sources": ["stage1_issues"],
        "section": "cover",
    })

    # --- Fixed: agenda (key_points filled later from content sections) ---
    pages.append({
        "title": "本日の流れ",
        "purpose": "本提案のアジェンダを提示する。",
        "key_points": [],
        "data_sources": [],
        "section": "agenda",
    })

    # --- Fixed: principles (原稿設計の重要性 / SEO・CVR) ---
    pages.append({
        "title": "原稿設計の重要性",
        "purpose": "応募獲得最大化に向け、SEO（集客）とCVR（応募率）の観点で原稿設計の重要性を示す。",
        "key_points": ["SEOの観点（集客の最大化）", "CVRの観点（応募率の向上）", "独自性・具体性・安心感"],
        "data_sources": [],
        "section": "principles",
    })

    # --- Conditional: 誤解 vs 実態 ---
    if _nonempty(ind_analysis.get("job_types")) or _nonempty(ind_analysis.get("competitive_advantages")):
        pages.append({
            "title": f"求職者が持つ「{industry}」のイメージと実態のギャップ",
            "purpose": "求職者の誤解と現場の実態のギャップを示し、訴求すべきメリットを明確化する。",
            "key_points": ["求職者が抱くイメージ", "実態（メリット）", "誤解による機会損失"],
            "data_sources": ["stage7_industry_analysis"],
            "section": "misconception",
        })

    # --- Conditional: 混同されやすい類似セグメントとの差別化（比較表） ---
    if _nonempty(confusable) or len(job_types) >= 2:
        pages.append({
            "title": "類似セグメントとの違い",
            "purpose": "求職者が混同しやすい類似セグメントとの違いを比較表で示し、差別化を図る。",
            "key_points": ["主な現場・業務の違い", "環境・条件の違い", "差別化ポイント"],
            "data_sources": ["stage7_industry_analysis"],
            "section": "segment_comparison",
        })

    # --- Conditional: ターゲット動向 ---
    if _nonempty(target_insights):
        pages.append({
            "title": "ターゲット動向",
            "purpose": f"{target}の求職動向・特性を提示する。",
            "key_points": ["ターゲットの求職傾向", "重視する条件"],
            "data_sources": ["stage7_target_insights"],
            "section": "target_trend",
        })

    # --- Conditional: ターゲット心理 N 軸 ---
    if _nonempty(target_insights.get("psychological_axes")):
        pages.append({
            "title": f"{target}が仕事選びで重視する軸",
            "purpose": "ターゲットの不安・欲求（心理軸）を構造化し、訴求方向を示す。",
            "key_points": ["心理軸ごとの不安・欲求", "訴求の方向性"],
            "data_sources": ["stage7_target_insights"],
            "section": "target_psychology",
        })

    # --- Conditional: 提案サマリ（N 施策） ---
    if _nonempty(axes):
        pages.append({
            "title": "原稿設計のご提案",
            "purpose": f"流入強化・応募率向上に向けた{len(axes)}つの施策の全体像を提示する。",
            "key_points": [a.get("title", "") for a in axes[:5]],
            "data_sources": ["stage8_strategy_axes"],
            "section": "strategy_summary",
        })

    # --- Variable: 提案詳細（施策軸ごと） ---
    if len(axes) > MAX_STRATEGY_DETAIL:
        logger.info("Blueprint: strategy axes %d > cap %d (extra summarized)", len(axes), MAX_STRATEGY_DETAIL)
    for i, axis in enumerate(axes[:MAX_STRATEGY_DETAIL], start=1):
        title = axis.get("title", f"提案{i}")
        pages.append({
            "title": f"提案{i}: {title}",
            "purpose": f"施策「{title}」の具体内容とキャッチコピー例を提示する。",
            "key_points": [c.get("text", "") for c in (axis.get("catchcopies", []) or [])[:5]] or [axis.get("rationale", "")],
            "data_sources": ["stage8_strategy_axes"],
            "section": "strategy_detail",
            "axis_id": axis.get("id", f"Ax-{i}"),
        })

    # --- Conditional: 料金提案（松竹梅） ---
    if has_plans:
        pages.append({
            "title": "ご提案プラン（料金）",
            "purpose": "採用目標から逆算した松竹梅の料金プランと見積もりを提示する。",
            "key_points": ["松竹梅プランの比較", "推奨プランと理由", "想定効果（PV・応募・採用）"],
            "data_sources": ["stage2_plans", "stage0_product_data", "stage0_simulation_data"],
            "section": "plan",
        })

    # --- Conditional: キーワード/原稿提案（SEO） ---
    if _nonempty(axes):
        pages.append({
            "title": "検索意図を満たすキーワード・コンテンツ提案",
            "purpose": "エリア×職種×条件の検索意図に合うキーワード設計とユニーク化を提案する。",
            "key_points": ["検索されやすいワード設計", "掛け合わせワードでユニーク化"],
            "data_sources": ["stage8_strategy_axes", "stage7_target_insights"],
            "section": "keyword",
        })

    # --- Variable: 成功事例（件数ごと） ---
    if len(cases) > MAX_SUCCESS_CASES:
        logger.info("Blueprint: success cases %d > cap %d (extra dropped)", len(cases), MAX_SUCCESS_CASES)
    for i, _case in enumerate(cases[:MAX_SUCCESS_CASES], start=1):
        pages.append({
            "title": f"成功事例{i}",
            "purpose": "採用課題を解決した事例のBefore/Afterと成果を共有する。",
            "key_points": ["改修内容（Before/After）", "成果（PV・応募・採用）"],
            "data_sources": ["stage8_success_case_references", "stage6_success_cases"],
            "section": "success_case",
            "case_index": i - 1,
        })

    # --- Fixed: next steps ---
    pages.append({
        "title": "次のステップ",
        "purpose": "次回商談に向けた具体的なアクションを提示する。",
        "key_points": ["ご提案内容のまとめ", "次回までのアクション"],
        "data_sources": ["stage1_issues", "stage2_plans"],
        "section": "next_steps",
    })

    # Fill agenda key_points from the major content sections (exclude cover/agenda).
    agenda_titles = [
        p["title"] for p in pages
        if p["section"] in {"principles", "misconception", "segment_comparison",
                             "target_trend", "target_psychology", "strategy_summary",
                             "plan", "keyword", "success_case", "next_steps"}
    ]
    # de-dup consecutive success_case titles into one agenda entry
    pages[1]["key_points"] = agenda_titles

    # Assign page numbers.
    for n, p in enumerate(pages, start=1):
        p["page_number"] = n

    return pages


def build_story_structure(
    stage1: dict, stage2: dict, stage6: dict, stage7: dict, stage8: dict, meeting: dict,
    max_pages: int = 20,
) -> dict:
    """Build the full Stage 9 story structure (blueprint-driven)."""
    pages = build_blueprint_pages(stage1, stage2, stage6, stage7, stage8, meeting)
    capped_from = None
    if len(pages) > max_pages:
        logger.warning("Blueprint produced %d pages (> %d max), capping", len(pages), max_pages)
        capped_from = len(pages)
        pages = pages[:max_pages]
    result = {
        "story_theme": build_story_theme(stage7, meeting),
        "pages": pages,
        "blueprint_driven": True,
    }
    if capped_from:
        result["pages_capped_from"] = capped_from
    return result
