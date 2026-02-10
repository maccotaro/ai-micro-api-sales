# ai-micro-api-sales プロジェクト概要

## サービス概要
Sales Support AI Service (ai-micro-api-sales) - 議事録解析、提案書自動生成、シミュレーション、提案チャット、会話履歴を提供するFastAPIサービス。

## サービス詳細
- **ポート**: 8005
- **DB**: PostgreSQL (salesdb)
- **Framework**: FastAPI (Python 3.11+)

## 依存サービス
- api-rag (8010): ハイブリッド検索（V1/V2パイプライン）
- api-admin (8003): マスターデータ、内部API (モデル設定取得)
- api-auth (8002): JWT認証
- Ollama (11434): LLM処理
- Neo4j (7687): グラフ推薦

## 主要API
- /api/sales/meeting-minutes - 議事録CRUD + AI分析
- /api/sales/meeting-minutes/{id}/chat - 議事録チャット (SSE, 会話履歴管理)
- /api/sales/proposals - 提案書生成・フィードバック
- /api/sales/simulation - コスト見積・ROI計算
- /api/sales/graph - Neo4jグラフ推薦
- /api/sales/proposal-chat - 商材提案チャット (SSE streaming)
  - pipeline パラメータ: V1/V2パイプライン選択
  - model パラメータ: チャットモデル動的切替
  - api-ragへhybrid searchリクエスト時にpipeline_versionを付与

## 議事録チャット（会話履歴サポート）
- ChatService: _build_messages() で直近10件の履歴をLLMコンテキストに含める
- DB: chat_conversations + chat_messages テーブル (salesdb)
- context_snapshot: 会話開始時の議事録コンテキストをJSONBで保存
- SSEストリーミング: start/chunk/done イベント
- トークンカウント: 単語分割による概算

## Neo4jグラフスキーマ (Sales固有)
- ノード: Meeting, Problem, Need, Industry, Target, Product, SuccessCase
- リレーション: HAS_PROBLEM, HAS_NEED, IN_INDUSTRY, SOLVED_BY, ADDRESSED_BY

## AIモデル設定
- api-admin内部API (GET /internal/model-settings) から取得 (TTL 5分キャッシュ)
- X-Internal-Secret認証
- フォールバックデフォルト: qwen3:8b (chat_model)

## DB テーブル (salesdb)
- meeting_minutes, proposal_history (CRUD)
- chat_conversations, chat_messages (チャット履歴)
- products, campaigns, simulation_params, wage_data (Read-only)

## 環境変数
- SALESDB_URL, REDIS_URL, RAG_SERVICE_URL, OLLAMA_BASE_URL
- NEO4J_URI, JWKS_URL, ADMIN_INTERNAL_URL, INTERNAL_API_SECRET
