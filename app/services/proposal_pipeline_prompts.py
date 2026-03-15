"""Prompt templates for proposal document pipeline (Stage 7-10).

Separate from proposal_prompts.py (which handles proposal chat prompts)
and pipeline_prompts.py (which handles Stage 1-5 prompts).
"""
import json


def _summarize_issues(issues: list, max_items: int = 3) -> str:
    """Summarize Stage 1 issues for compact context."""
    lines = []
    for issue in issues[:max_items]:
        lines.append(f"- {issue.get('id', '')}: {issue.get('title', '')} — {issue.get('detail', '')}")
    return "\n".join(lines) if lines else "（課題情報なし）"


def _summarize_publication_records(records: list, max_items: int = 3) -> str:
    """Summarize publication records for compact context."""
    lines = []
    for r in records[:max_items]:
        lines.append(
            f"- {r.get('job_title', '')}: PV={r.get('pv_count', 0)}, "
            f"応募={r.get('application_count', 0)}, 採用={r.get('hire_count', 0)}, "
            f"コピー「{r.get('catchcopy', '')[:40]}」"
        )
    return "\n".join(lines) if lines else "（実績データなし）"


def _format_kb_chunks(chunks: list, label: str, max_items: int = 5) -> str:
    """Format KB chunks for prompt inclusion."""
    if not chunks:
        return f"（{label}なし）"
    lines = [f"【{label}】"]
    for chunk in chunks[:max_items]:
        text = chunk if isinstance(chunk, str) else chunk.get("content", str(chunk))
        lines.append(f"- {text[:200]}")
    return "\n".join(lines)


def build_stage7_prompt(
    meeting: dict,
    stage1_issues: list,
    proposal_kb_chunks: list,
    end_user_chunks: list,
    decision_maker_chunks: list,
    publication_records: list,
) -> str:
    """Build Stage 7 prompt for industry & target analysis."""
    industry = meeting.get("industry", "不明")
    area = meeting.get("area", "不明")

    return f"""あなたは業界分析と求職者心理の専門家です。以下の情報をもとに、業界構造の分析とターゲット心理の構造化を行ってください。

## 基本情報
- 業界: {industry}
- エリア: {area}
- 企業: {meeting.get('company_name', '不明')}

## 顧客の課題（Stage 1分析結果）
{_summarize_issues(stage1_issues)}

## 同業界の実績データ
{_summarize_publication_records(publication_records)}

{_format_kb_chunks(proposal_kb_chunks, '同業界の優秀提案書')}

{_format_kb_chunks(end_user_chunks, 'エンドユーザー心理パターン')}

{_format_kb_chunks(decision_maker_chunks, '担当者心理パターン')}

## 出力形式（JSON）

以下のJSON形式で出力してください:

```json
{{
  "industry_analysis": {{
    "industry_name": "{industry}",
    "job_types": [
      {{
        "name": "職種名",
        "characteristics": ["特徴1", "特徴2"],
        "common_misconceptions": ["求職者が抱く誤解"],
        "actual_reality": "実態の説明"
      }}
    ],
    "competitive_advantages": ["この業界/職種の競合優位性"]
  }},
  "target_insights": {{
    "primary_target": "主要ターゲット層",
    "psychological_axes": [
      {{
        "axis": "心理軸の名称",
        "detail": "詳細説明",
        "appeal_direction": "この心理軸に対する訴求方向"
      }}
    ]
  }},
  "decision_maker_insights": {{
    "role": "意思決定者の役職",
    "judgment_criteria": ["判断基準1", "判断基準2"],
    "common_concerns": ["よくある懸念"],
    "required_evidence": ["必要なエビデンス"]
  }}
}}
```"""


def build_stage8_prompt(
    stage1_issues: list,
    stage7_output: dict,
    decision_maker_chunks: list,
    success_cases: list,
    publication_records: list,
) -> str:
    """Build Stage 8 prompt for appeal strategy planning."""
    industry_analysis = json.dumps(
        stage7_output.get("industry_analysis", {}), ensure_ascii=False,
    )[:800]
    target_insights = json.dumps(
        stage7_output.get("target_insights", {}), ensure_ascii=False,
    )[:600]
    dm_insights = json.dumps(
        stage7_output.get("decision_maker_insights", {}), ensure_ascii=False,
    )[:400]

    success_text = "（成功事例なし）"
    if success_cases:
        cases = []
        for c in success_cases[:3]:
            if isinstance(c, dict):
                cases.append(f"- {c.get('title', '')}: {c.get('achievement', '')}")
            else:
                cases.append(f"- {str(c)[:100]}")
        success_text = "\n".join(cases)

    return f"""あなたは訴求戦略の専門家です。以下の分析結果をもとに、戦略ベースの提案軸を設計してください。

**重要**: 予算や商品パッケージではなく、「どういう切り口でエンドユーザー（求職者等）に訴求するか」という戦略軸で提案を構築してください。同時に、担当者（意思決定者）が納得できるエビデンスを含めてください。

## 業界分析（Stage 7）
{industry_analysis}

## ターゲットインサイト（Stage 7）
{target_insights}

## 担当者インサイト（Stage 7）
{dm_insights}

## 顧客の課題
{_summarize_issues(stage1_issues)}

## 成功事例
{success_text}

## 実績データ
{_summarize_publication_records(publication_records)}

{_format_kb_chunks(decision_maker_chunks, '担当者心理パターン（KB）')}

## 出力形式（JSON）

```json
{{
  "strategy_axes": [
    {{
      "id": "S-1",
      "title": "戦略軸のタイトル",
      "rationale": "この戦略軸を選んだ理由",
      "target_psychology": "対応するターゲット心理",
      "catchcopies": [
        {{
          "text": "キャッチコピーの文言",
          "psychology_link": "なぜこのコピーがターゲットに刺さるかの説明"
        }}
      ]
    }}
  ],
  "success_case_references": [
    {{
      "case_summary": "事例の概要",
      "before": {{"catchcopy": "変更前", "pv": 0, "applications": 0}},
      "after": {{"catchcopy": "変更後", "pv": 0, "applications": 0}},
      "improvement": "改善の概要"
    }}
  ]
}}
```"""


def build_stage9_prompt(
    stage1_issues: list,
    stage7_output: dict,
    stage8_output: dict,
) -> str:
    """Build Stage 9 prompt for story structure design."""
    issues_summary = _summarize_issues(stage1_issues)
    industry = stage7_output.get("industry_analysis", {}).get("industry_name", "不明")
    target = stage7_output.get("target_insights", {}).get("primary_target", "不明")
    axes_summary = json.dumps(
        [{"id": a["id"], "title": a["title"]} for a in stage8_output.get("strategy_axes", [])],
        ensure_ascii=False,
    )
    has_cases = bool(stage8_output.get("success_case_references"))

    return f"""あなたは提案書構成の専門家です。以下の分析・戦略をもとに、顧客担当者を説得するストーリー構成の提案書ページ構成を設計してください。

## 基本情報
- 業界: {industry}
- ターゲット: {target}
- 戦略軸: {axes_summary}
- 成功事例: {"あり" if has_cases else "なし"}

## 顧客の課題
{issues_summary}

## ストーリーフローの原則
提案書は以下の説得フローに従ってください:
1. アジェンダ提示
2. 課題提起・共感（顧客の現状と課題）
3. 業界洞察（エンドユーザーの誤解・実態）
4. ターゲットインサイト（心理軸の構造化）
5. 戦略提案（各戦略軸 × キャッチコピー）
6. **具体的な商品・料金提案**（松竹梅プラン、推奨商品、見積もり）
7. エビデンス（成功事例のBefore/After）※成功事例がある場合のみ
8. 次のステップ（具体的アクション）

## 制約
- ページ数: 5〜10ページ
- 各ページに明確な目的とキーポイントを設定

## 出力形式（JSON）

```json
{{
  "story_theme": "提案書全体のテーマ（1文）",
  "pages": [
    {{
      "page_number": 1,
      "title": "ページタイトル",
      "purpose": "このページの目的",
      "key_points": ["キーポイント1", "キーポイント2"],
      "data_sources": ["stage7_industry_analysis"]
    }}
  ]
}}
```

data_sourcesに使える値:
- stage0_product_data（商品・料金マスタ）, stage0_wage_data（時給相場）, stage0_simulation_data（シミュレーション係数）
- stage1_issues（顧客課題・BANT-C）
- stage2_plans（松竹梅プラン・料金提案・見積もり）
- stage6_publication_data, stage6_success_cases
- stage7_industry_analysis, stage7_target_insights, stage7_decision_maker_insights
- stage8_strategy_axes, stage8_success_case_references

**重要**: 提案書には戦略だけでなく、具体的な商品・料金提案（stage2_plans, stage0_product_data）を含めるページを必ず設計してください。"""


def build_stage10_page_prompt(
    story_theme: str,
    page_title: str,
    page_purpose: str,
    key_points: list,
    page_data: str,
) -> str:
    """Build Stage 10 prompt for individual page Markdown generation."""
    key_points_text = "\n".join(f"- {kp}" for kp in key_points) if key_points else "（なし）"

    return f"""あなたは提案書のライターです。以下の情報をもとに、プレゼンテーション用のMarkdownスライドを1ページ分作成してください。

## 提案書テーマ
{story_theme}

## このページの情報
- タイトル: {page_title}
- 目的: {page_purpose}
- キーポイント:
{key_points_text}

## 使用データ
{page_data}

## 出力ルール（厳守）
- **1スライドに収まる分量にすること**（最大12行程度、絶対に15行を超えないこと）
- 見出しは `#` を1つだけ使用（ページタイトル）、サブ見出しは `##` を使用
- 箇条書きは5項目以内、各項目は1-2行以内
- テーブルは最大5行×4列程度
- 引用（`>`）は2行以内
- スライド区切り `---` は含めない（1ページ分のみ出力）
- データがある場合は具体的な数値を含める
- 長い文章は避け、キーワードと数値で端的に表現する

Markdownのみを出力してください（JSON不要）。"""
