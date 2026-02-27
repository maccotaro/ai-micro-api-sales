"""Prompt templates for the 6-stage proposal pipeline.

Each stage has a system prompt template with placeholders for:
- Context data (meeting minute, KB content, DB data)
- Previous stage outputs
- Configuration-driven KB content blocks
"""

# ============================================================
# Stage 1: Issue Structuring + BANT-C Check
# ============================================================
STAGE1_SYSTEM_PROMPT = """あなたは求人広告の営業支援AIです。
議事録から企業の課題・ニーズを構造化し、BANT-Cフレームワークで分析してください。

## 入力
### 議事録
{meeting_text}

### 議事録解析結果
{parsed_json}

{kb_context}

## 出力形式（JSON）
以下のJSON形式で出力してください。マークダウンのコードブロックは不要です。
{{
  "issues": [
    {{
      "id": "I-1",
      "category": "採用課題|掲載効果|予算|競合|業界特性",
      "title": "課題の簡潔なタイトル",
      "detail": "詳細な説明",
      "evidence": "議事録からの根拠引用",
      "bant_c": {{
        "budget": {{"status": "確認済|未確認|不明", "detail": "予算に関する情報"}},
        "authority": {{"status": "確認済|未確認|不明", "detail": "決裁者情報"}},
        "need": {{"status": "確認済|未確認|不明", "detail": "ニーズの緊急度"}},
        "timeline": {{"status": "確認済|未確認|不明", "detail": "スケジュール情報"}},
        "competitor": {{"status": "確認済|未確認|不明", "detail": "競合状況"}}
      }}
    }}
  ],
  "company_context": {{
    "industry": "業界",
    "company_size": "企業規模",
    "current_media": ["現在使用中の媒体"],
    "key_decision_maker": "意思決定者"
  }}
}}"""

# ============================================================
# Stage 2: Reverse-Calculation Planning
# ============================================================
STAGE2_SYSTEM_PROMPT = """あなたは求人広告の効果シミュレーション・プランニングAIです。
Stage 1の課題分析と商品・料金データに基づき、逆算プランニングを行ってください。

## 入力
### Stage 1 課題分析
{stage1_output}

{kb_context}

### 商品・料金データ
{product_data}

### シミュレーションデータ
{simulation_data}

### 賃金データ
{wage_data}

### 前回掲載実績
{publication_data}

### 適用可能キャンペーン
{campaign_data}

## 指示
1. 各課題に対して最適な媒体・プランを選定
2. 採用目標から逆算して必要なPV・応募数・掲載期間を計算
3. 根拠付きの料金テーブルを作成
4. 前回掲載実績がある場合は、実績データを根拠に効果予測を強化
5. 適用可能なキャンペーンがあれば、割引適用後の料金も提示
6. 月別の掲載プランテーブルを作成

## 出力形式（JSON）
{{
  "proposals": [
    {{
      "issue_id": "I-1",
      "media_name": "媒体名",
      "product_name": "商品名",
      "plan_detail": "プラン詳細",
      "price": 0,
      "campaign_discount": null,
      "final_price": 0,
      "period": "掲載期間",
      "reverse_calc": {{
        "hiring_goal": 0,
        "required_applications": 0,
        "required_pv": 0,
        "conversion_rate": 0.0,
        "rationale": "逆算根拠の説明",
        "past_performance": "前回実績に基づく補足（あれば）"
      }}
    }}
  ],
  "monthly_plan": [
    {{
      "month": "YYYY-MM",
      "items": ["掲載予定の媒体・プラン"],
      "monthly_cost": 0
    }}
  ],
  "total_budget": 0,
  "agenda_items": [
    "次回商談で話すべきアジェンダ項目"
  ]
}}"""

# ============================================================
# Stage 3: Action Plan Generation
# ============================================================
STAGE3_SYSTEM_PROMPT = """あなたは営業活動の計画策定AIです。
次回商談までに営業担当者が行うべきアクションプランを詳細化してください。

## 入力
### Stage 1 課題分析
{stage1_output}

### Stage 2 提案プラン
{stage2_output}

{kb_context}

## 指示
1. 次回商談までの具体的なタスクを洗い出し
2. 各タスクにサブタスクと期限を設定
3. BANT-C未充足項目の確認方法を具体化

## 出力形式（JSON）
{{
  "action_plan": [
    {{
      "id": "A-1",
      "title": "タスクタイトル",
      "description": "タスクの詳細",
      "related_issue_id": "I-1",
      "priority": "high|medium|low",
      "subtasks": [
        {{
          "title": "サブタスクタイトル",
          "detail": "具体的な内容"
        }}
      ]
    }}
  ]
}}"""

# ============================================================
# Stage 4: Ad Copy / Draft Proposal
# ============================================================
STAGE4_SYSTEM_PROMPT = """あなたは求人原稿の企画・ライティングAIです。
課題分析と提案プランに基づき、求人原稿の内容を提案してください。

## 入力
### Stage 1 課題分析
{stage1_output}

### Stage 2 提案プラン
{stage2_output}

{kb_context}

## 指示
1. ターゲット求職者のペルソナを定義
2. 訴求ポイントを構造化
3. キャッチコピー案を{catchcopy_count}案作成
4. 仕事内容・応募資格のドラフトを作成

## 出力形式（JSON）
{{
  "target_persona": {{
    "age_range": "想定年齢層",
    "current_job": "現在の職種",
    "motivation": "転職動機",
    "concerns": ["懸念事項"]
  }},
  "appeal_points": [
    {{
      "point": "訴求ポイント",
      "rationale": "根拠（課題IDと対応）"
    }}
  ],
  "catchcopy_proposals": [
    {{
      "copy": "キャッチコピー案",
      "concept": "コンセプト説明"
    }}
  ],
  "job_description_draft": {{
    "title": "求人タイトル案",
    "work_content": "仕事内容ドラフト",
    "qualifications": "応募資格",
    "benefits": "待遇・福利厚生のポイント"
  }}
}}"""

# ============================================================
# Stage 5: Checklist + Summary
# ============================================================
STAGE5_SYSTEM_PROMPT = """あなたは営業支援の総括AIです。
全Stageの結果を統合し、チェックリストとまとめを作成してください。

## 入力
### Stage 1 課題分析
{stage1_output}

### Stage 2 提案プラン
{stage2_output}

### Stage 3 アクションプラン
{stage3_output}

### Stage 4 原稿提案（存在する場合）
{stage4_output}

## 指示
1. BANT-C未充足項目から次回商談のチェックリストを作成
2. 全Stageの結果を課題ID参照付きで総合要約

## 出力形式（JSON）
{{
  "checklist": [
    {{
      "id": "C-1",
      "category": "BANT-C項目",
      "item": "確認事項",
      "related_issue_id": "I-1",
      "question_example": "商談で使える質問例"
    }}
  ],
  "summary": {{
    "overview": "全体の総括（200字以内）",
    "key_points": [
      {{
        "point": "要点",
        "related_issues": ["I-1", "I-2"],
        "stage_source": 2
      }}
    ],
    "next_steps": [
      "次回商談への推奨アクション"
    ]
  }}
}}"""


def build_kb_context_block(kb_results: dict[str, list[str]]) -> str:
    """Build KB context block from search results.

    Args:
        kb_results: Dict of category_name -> list of chunk texts.

    Returns:
        Formatted context string for prompt injection.
    """
    if not kb_results:
        return "### ナレッジベース情報\n（該当する情報がありません。一般的な知識で対応してください。）"

    lines = ["### ナレッジベース情報"]
    for category, chunks in kb_results.items():
        if chunks:
            lines.append(f"\n#### {category}")
            for i, chunk in enumerate(chunks, 1):
                lines.append(f"[{i}] {chunk}")

    return "\n".join(lines)
