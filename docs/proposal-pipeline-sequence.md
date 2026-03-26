# 提案パイプライン 11ステージ シーケンス

## 概要

議事録から11段階のLLMチェーンで構造化提案書を自動生成するパイプライン。

- **Stage 0-5**: 議事録解析・課題構造化・プラン生成（分析フェーズ）
- **Stage 6-10**: 提案書ドキュメント生成（ドキュメントフェーズ）

```
front-sales (ブラウザ)
  │  POST /api/sales/proposal-pipeline/stream
  │  SSE接続
  ▼
api-sales (Port 8005) ── ProposalPipelineService.stream_pipeline()
```

---

## Stage 0: コンテキスト収集（非LLM）

議事録とDBマスタデータ、KB検索結果を収集。以降の全ステージが参照する基盤データ。

```
api-sales
  ├─ salesdb.meeting_minutes から議事録取得
  │   → company_name, industry, area, raw_text, parsed_json
  │
  ├─ api-rag (Port 8010) へ KB 検索（並列）
  │   POST /internal/v1/search/hybrid
  │   → product_info, industry_knowledge 等のチャンク取得
  │
  └─ salesdb からマスタデータ取得
      ├─ products（商品情報）
      ├─ simulation_params（シミュレーション係数）
      ├─ wage_data（地域別時給相場）
      ├─ publication_records（過去の掲載実績）
      └─ campaigns（キャンペーン情報）
```

**出力**: `context` dict（meeting, kb_results, product_data, simulation_data, wage_data, publication_data, campaign_data）

---

## Stage 1: 課題構造化 + BANT-Cチェック（LLM）

議事録テキストのみから顧客の課題を抽出・構造化。BANT-C（Budget, Authority, Need, Timeline, Competition）で分析。

```
api-sales
  ├─ KB検索（product_info, industry_knowledge）→ context に蓄積
  │   ※ Stage 1 プロンプトには含めない（KB情報による課題捏造を防止）
  │
  ├─ LLM呼出し（api-llm → Ollama/vLLM）
  │   入力: 議事録 raw_text + parsed_json
  │   指示: 課題抽出、BANT-C分析、優先度判定
  │
  └─ validate_evidence(): LLM が生成した「根拠」が実際の議事録に含まれるか検証
```

**出力**: `{ issues: [{ id, title, description, bant_c, evidence, priority }] }`

**設計意図**: KB 情報は意図的にプロンプトに含めない。議事録のみから課題を抽出し、LLMが外部知識で課題を捏造するのを防止。

---

## Stage 2: 逆算プランニング（LLM + DB）

Stage 1 の課題に対して、商品・料金データを元に松竹梅3プランを逆算で設計。

```
api-sales
  ├─ KB検索（product_info 追加分）
  │
  └─ LLM呼出し
      入力:
        ├─ Stage 1 の課題一覧（[:2000]文字）
        ├─ KB検索結果（max 5チャンク × 300文字）
        ├─ 商品データ（[:5件][:1500文字]）
        ├─ シミュレーション結果（[:3件][:800文字]）
        ├─ 時給データ（[:3件][:600文字]）
        ├─ 掲載実績（[:3件][:800文字]）
        ├─ キャンペーン（[:3件][:600文字]）
        ├─ 予算レンジ（Stage 1 BANT-Cから抽出）
        └─ 季節コンテキスト（[:500文字]）
      指示: 松竹梅3プランの料金・構成提案
```

**出力**: `{ proposals: [{ issue_id, shochikubai: { matsu, take, ume } }] }`

**トランケーション**: 各データソースに文字数・件数制限を適用（コンテキスト長超過防止）

---

## Stage 3: アクションプラン（LLM）

次回商談までの具体的なタスクと準備事項を生成。

```
api-sales
  ├─ KB検索（sales_framework等）
  │
  └─ LLM呼出し
      入力:
        ├─ Stage 1 課題（[:1500文字]）
        ├─ Stage 2 プラン（[:2000文字]）
        ├─ KB検索結果
        └─ 企業名
      指示: 次回商談までの具体的タスク・準備事項
```

**出力**: `{ action_items: [{ task, deadline, responsible, detail }] }`

---

## Stage 4: 原稿・キャッチコピー提案（LLM）

求人原稿案とキャッチコピー候補を生成。

```
api-sales
  ├─ KB検索（creative_reference等）
  │
  └─ LLM呼出し
      入力:
        ├─ Stage 1 課題（[:1500文字]）
        ├─ Stage 2 プラン（[:2000文字]）
        ├─ KB検索結果
        ├─ 議事録テキスト（[:2000文字]）
        └─ キャッチコピー生成数（設定可能、デフォルト5）
      指示: 求人原稿案、キャッチコピー候補
```

**出力**: `{ ad_copies: [...], catchcopies: [...] }`

---

## Stage 5: チェックリスト + まとめ（LLM）

BANT-C未充足項目の確認と全体の総括。

```
api-sales
  └─ LLM呼出し
      入力:
        ├─ Stage 1-4 の全出力（各[:1500-2000文字]）
        ├─ 議事録テキスト（[:2000文字]）
        └─ 参考ドキュメントリンク（[:1000文字]）
      指示: BANT-C未充足確認、次回アクション総括
```

**出力**: `{ checklist: [...], summary, next_steps }`

---

## Stage 6: 提案書コンテキスト収集（非LLM）

提案書ドキュメント生成に必要な追加データを収集。

```
api-sales
  ├─ KB検索（並列）
  │   ├─ proposal_reference（過去の承認済み提案書テンプレート）
  │   ├─ target_psychology_end_user（求職者心理データ）
  │   └─ target_psychology_decision_maker（決裁者心理データ）
  │
  ├─ 成功事例検索（embedding類似検索）
  │   → 業界・地域でフィルタした類似成功事例
  │
  └─ 掲載実績（高パフォーマンス実績）
      → 業界・地域でフィルタした好実績データ
```

**出力**: KB チャンク + 成功事例 + 掲載実績

---

## Stage 7: 業界・ターゲット分析（LLM）

業界構造とターゲット（求職者・決裁者）の心理を分析。

```
入力:
  ├─ 議事録（企業名、業界、エリア）
  ├─ Stage 1 課題一覧
  ├─ Stage 6 提案書KB（過去の提案テンプレ）
  ├─ Stage 6 求職者心理KBチャンク
  ├─ Stage 6 決裁者心理KBチャンク
  └─ Stage 6 掲載実績
指示: 業界構造分析、ターゲット心理（求職者・決裁者）、採用競合状況
```

**出力**: `{ industry_analysis, end_user_psychology, decision_maker_psychology }`

**補足**: KB に心理データがある場合は `source: "kb_data"`、ない場合は `source: "general_knowledge"` としてLLMの一般知識で推論。

---

## Stage 8: 訴求戦略設計（LLM）

提案書の訴求軸（3つ）を決定し、各軸のキャッチコピーと心理的根拠を設計。

```
入力:
  ├─ Stage 1 課題
  ├─ Stage 7 業界・ターゲット分析
  ├─ Stage 6 決裁者心理チャンク
  ├─ Stage 6 成功事例
  └─ Stage 6 掲載実績
指示: 提案の軸（3つ）、各軸のキャッチコピー、心理的根拠
```

**出力**: `{ appeal_axes: [{ axis, catchcopy, psychology_basis }] }`

---

## Stage 9: ストーリー構成設計（LLM）

提案書全体のストーリーテーマと、5-10ページの構成を設計。

```
入力:
  ├─ Stage 1 課題
  ├─ Stage 7 業界分析
  └─ Stage 8 訴求戦略
指示: 5-10ページの提案書構成（各ページのタイトル・目的・キーポイント・データソース指定）
```

**出力**: `{ story_theme, pages: [{ title, purpose, key_points, data_sources }] }`

**バリデーション**: 5ページ未満→警告、10ページ超→10ページに切り詰め

---

## Stage 10: ページ別Markdown生成（LLM × N回）

Stage 9 の各ページ仕様に基づき、1ページずつ Marp 互換 Markdown を生成。

```
Stage 9 の各ページに対してループ（5-10回のLLM呼出し）:
  ├─ データソース解決
  │   Stage 0-8 の出力から、ページ仕様の data_sources に該当するデータを抽出
  │   （各データソースはトランケーション済み: [:1200], [:1500]等）
  │
  ├─ LLM呼出し（1ページ分）
  │   入力: ストーリーテーマ + ページ仕様 + 該当データ
  │   指示: Marp互換Markdownスライド1ページ生成
  │
  ├─ 行数チェック
  │   16行超過 → LLM で2ページに自動分割
  │
  └─ Markdownテーブル修正（fix_markdown_tables）

全ページ完了後:
  └─ salesdb に保存
      ├─ proposal_documents（ドキュメントメタデータ）
      └─ proposal_document_pages（各ページのMarkdown）
```

**出力**: Marp Markdown ドキュメント

**後続処理**: api-export (Port 8015) で HTML/PDF/PPTX に変換可能

---

## データフロー全体図

```
Stage 0 (DB+KB) ─────────────────────────────────────────────────┐
    │                                                             │
Stage 1 (LLM) ── 課題 ──┬──────────────────────────────────┐     │
    │                    │                                  │     │
Stage 2 (LLM) ── プラン ┼──┐                               │     │
    │                    │  │                               │     │
Stage 3 (LLM) ── アクション │                               │     │
    │                       │                               │     │
Stage 4 (LLM) ── 原稿案    │                               │     │
    │                       │                               │     │
Stage 5 (LLM) ── まとめ    │                               │     │
                            │                               │     │
Stage 6 (KB) ── 提案書素材 ─┤                               │     │
    │                       │                               │     │
Stage 7 (LLM) ── 業界分析 ─┤                               │     │
    │                       │                               │     │
Stage 8 (LLM) ── 訴求戦略 ─┤                               │     │
    │                       │                               │     │
Stage 9 (LLM) ── 構成設計 ─┘                               │     │
    │                                                       │     │
Stage 10 (LLM×N) ── Markdown ← Stage 0-8 全出力を参照 ─────┘─────┘
```

---

## サービス間通信

| 呼出し元 | 呼出し先 | 用途 |
|---------|---------|------|
| api-sales | api-llm (8012) | LLM generate/chat（全LLMステージ） |
| api-sales | api-rag (8010) | KB ハイブリッド検索（Stage 0, 1, 2, 3, 4, 6） |
| api-sales | api-admin (8003) | パイプライン設定取得、モデル設定取得 |
| api-sales | api-export (8015) | Markdown → HTML/PDF/PPTX 変換（後続処理） |
| api-llm | vLLM (8000) / Ollama (11434) | LLM推論（プロバイダー切替可能） |
| api-rag | vLLM (8101) / Ollama (11434) | Embedding 生成（検索用） |

## 設定

| 設定項目 | 場所 | 説明 |
|---------|------|------|
| ステージ有効/無効 | admindb.system_settings `proposal_pipeline_defaults` | 各ステージの enabled フラグ |
| max_tokens | 同上 `stage_config.stage_N.max_tokens` | 各ステージのLLM出力上限 |
| KB マッピング | 同上 `kb_mapping` | カテゴリ → KB ID + 検索クエリテンプレ |
| chat_num_ctx | admindb.system_settings `ai_model_settings` | LLMコンテキストウィンドウサイズ |
| llm_provider | 同上 | vllm / ollama 切替 |

## SSE イベント

| イベント | データ | タイミング |
|---------|--------|----------|
| `pipeline_start` | total_stages, enabled_stages | パイプライン開始時 |
| `stage_start` | stage, name | 各ステージ開始時 |
| `stage_info` | stage, company_name, industry | Stage 0 完了時 |
| `stage_chunk` | stage, content | 各ステージ出力（フォーマット済みテキスト） |
| `stage_complete` | stage, duration_ms | 各ステージ完了時 |
| `stage_sections` | stage, sections[] | 構造化セクション（即時表示用） |
| `pipeline_complete` | total_duration_ms, status | パイプライン完了時 |
| `result` | run_id, sections[], stage_results | 最終結果 |
| `error` | message | エラー発生時 |
