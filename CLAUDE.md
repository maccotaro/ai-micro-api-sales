# CLAUDE.md

このファイルは、このリポジトリでコードを扱う際のClaude Code (claude.ai/code) へのガイダンスを提供します。

## プロジェクト概要

**ai-micro-api-sales** - 営業支援AIサービス

議事録解析と提案書自動生成を行うFastAPIベースのマイクロサービスです。LLMを活用して商談議事録から顧客課題を抽出し、最適な商品提案を自動生成します。

## アーキテクチャ

### サービス構成

```
ai-micro-api-sales (Port 8005)
    │
    ├── salesdb (PostgreSQL) ← 共有データベース
    │
    ├── api-rag (Port 8010) ← 9段階ハイブリッド検索パイプライン
    │   └── GraphRAG, BM25, Cross-Encoder統合
    │
    ├── api-admin (Port 8003) ← マスタデータ管理（フォールバック用）
    │
    ├── api-auth (Port 8002) ← JWT認証
    │
    ├── Ollama (Port 11434) ← LLM処理
    │
    └── Neo4j (Port 7687) ← グラフデータベース
```

### 主要機能

1. **議事録管理** (`/api/sales/meeting-minutes`)
   - 議事録のCRUD操作
   - AIによる議事録解析（課題・ニーズ抽出）

2. **提案書生成** (`/api/sales/proposals`)
   - 解析結果に基づく自動提案生成
   - 商品マッチング
   - フィードバック管理

3. **シミュレーション** (`/api/sales/simulation`)
   - 地域・業界パラメータに基づくコスト試算
   - キャンペーン適用
   - ROI計算

4. **グラフベース推薦** (`/api/sales/graph`)
   - Neo4jによる関係性ベース推薦
   - 類似議事録検索（問題・ニーズ共有）
   - 成功事例マッチング

5. **商材提案チャット** (`/api/sales/proposal-chat`) ★重要
   - **9段階ハイブリッド検索パイプライン**（api-rag連携）
   - GraphRAG Query Expansion
   - BM25 + Cross-Encoder Re-ranking
   - 料金情報連携
   - LLMによる提案生成

## ディレクトリ構造

```
ai-micro-api-sales/
├── app/
│   ├── core/
│   │   ├── config.py       # 環境設定
│   │   └── security.py     # JWT認証
│   ├── db/
│   │   └── session.py      # DB接続
│   ├── models/
│   │   ├── meeting.py      # MeetingMinute, ProposalHistory
│   │   └── master.py       # Product, Campaign等（読み取り専用）
│   ├── schemas/
│   │   ├── meeting.py      # 議事録・提案スキーマ
│   │   └── simulation.py   # シミュレーションスキーマ
│   ├── services/
│   │   ├── analysis_service.py   # 議事録解析
│   │   ├── proposal_service.py   # 提案生成
│   │   ├── simulation_service.py # シミュレーション
│   │   ├── embedding_service.py  # ベクトル検索
│   │   └── graph/
│   │       ├── neo4j_client.py   # Neo4j接続クライアント
│   │       └── sales_graph_service.py # グラフ操作サービス
│   ├── routers/
│   │   ├── meeting_minutes.py
│   │   ├── proposals.py
│   │   ├── simulation.py
│   │   ├── search.py             # ベクトル検索
│   │   ├── graph.py              # グラフ推薦
│   │   └── health.py
│   └── main.py
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── .env
```

## API エンドポイント

### 提案パイプライン (`/api/sales/proposal-pipeline`) ★新機能

議事録から6段階LLMチェーンで構造化提案書を自動生成する。

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/stream` | SSEストリーミング パイプライン実行 |
| POST | `/generate` | 非ストリーミング パイプライン実行（JSON応答） |
| GET | `/health` | パイプラインヘルスチェック |
| GET | `/runs` | 実行履歴一覧（ページネーション） |

**6段階パイプライン:**

| Stage | 名称 | 処理 |
|-------|------|------|
| 0 | コンテキスト収集 | 議事録 + DB + KB検索（非LLM） |
| 1 | 課題構造化 + BANT-C | LLM: 議事録から課題抽出・構造化 |
| 2 | 逆算プランニング | LLM + DB: 料金・シミュレーション + 提案プラン |
| 3 | アクションプラン | LLM: 次回商談までのタスク詳細化 |
| 4 | 原稿提案 | LLM + KB: キャッチコピー・求人原稿案 |
| 5 | チェックリスト + まとめ | LLM: BANT-C未充足確認 + 総括 |

**SSEイベント:** `pipeline_start`, `stage_start`, `stage_info`, `stage_chunk`, `stage_complete`, `pipeline_complete`, `result`, `error`

**設定:** テナント別パイプライン設定は api-admin の `GET /internal/proposal-pipeline/config` 経由で取得、Redisキャッシュ TTL 300秒

**ファイル:**
- `app/services/pipeline_config.py` - 設定取得 + Redisキャッシュ
- `app/services/pipeline_prompts.py` - Stage 1-5 プロンプトテンプレート
- `app/services/pipeline_stages.py` - Stage 0-5 実装
- `app/services/proposal_pipeline_service.py` - オーケストレーター + SSE + 実行ログ
- `app/routers/proposal_pipeline.py` - ルーター

### 議事録 (`/api/sales/meeting-minutes`)

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/` | 議事録一覧取得 |
| GET | `/{id}` | 議事録詳細取得 |
| POST | `/` | 議事録作成 |
| PUT | `/{id}` | 議事録更新 |
| DELETE | `/{id}` | 議事録削除 |
| POST | `/{id}/analyze` | AI解析実行 |
| GET | `/{id}/analysis` | 解析結果取得 |

### 提案 (`/api/sales/proposals`)

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/` | 提案一覧取得 |
| GET | `/{id}` | 提案詳細取得 |
| POST | `/generate/{minute_id}` | 提案自動生成 |
| PUT | `/{id}/feedback` | フィードバック更新 |
| DELETE | `/{id}` | 提案削除 |

### シミュレーション (`/api/sales/simulation`)

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/` | 詳細シミュレーション |
| POST | `/quick-estimate` | 簡易見積もり |

### 類似案件検索 (`/api/sales/search`)

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/health` | 検索サービスヘルスチェック |
| POST | `/meetings` | 類似議事録検索 |
| POST | `/success-cases` | 類似成功事例検索 |
| POST | `/sales-talks` | 類似セールストーク検索 |
| POST | `/products` | 類似商品検索 |

### グラフベース推薦 (`/api/sales/graph`)

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/health` | Neo4j接続状態チェック |
| GET | `/recommendations/{minute_id}` | 議事録に対するグラフベース推薦取得 |
| GET | `/stats` | テナントのグラフ統計情報 |
| DELETE | `/meetings/{minute_id}` | 議事録関連グラフデータ削除 |

## 商材提案チャット（9段階ハイブリッド検索）

### 概要

**ProposalChatService**は、api-ragの9段階ハイブリッド検索パイプラインを使用して
商材検索を実行します。これにより、front-adminのチャット機能と同一の検索ロジック
（GraphRAG、BM25、Cross-Encoder等）が適用されます。

### 9段階パイプライン

| Stage | 処理内容 | 説明 |
|-------|---------|------|
| 0 | Graph Query Expansion | Neo4jでエンティティ関係探索 |
| 1 | Atlas層フィルタリング | KB/Collection要約ベクトルで事前絞り込み |
| 2 | メタデータフィルタ構築 | テナント、部署等のフィルタ生成 |
| 3 | Sparse検索 | BM25全文検索（100件取得） |
| 4 | Dense検索 | HNSWベクトル検索（100件取得） |
| 5 | RRFマージ | Sparse + Denseの統合スコアリング |
| 6 | BM25 Re-ranker | 600件→100件に絞り込み |
| 7 | Cross-Encoder | 100件→10件に精密リランキング |
| 8 | Graph Context Enrichment | エンティティ関係情報を付加 |

### エンドポイント

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/stream` | SSEストリーミング提案生成 |
| POST | `/generate` | 非ストリーミング提案生成 |
| GET | `/health` | サービスヘルスチェック |

### 使用例

```bash
# ストリーミング提案生成
curl -X POST http://localhost:8005/api/sales/proposal-chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "飲食店の人材採用で困っている。予算は50万円程度",
    "knowledge_base_id": "xxx-xxx-xxx",
    "area": "関東"
  }'
```

### 処理フロー

```
1. 顧客要件/議事録入力
   ↓
2. api-rag 9段階ハイブリッド検索（GraphRAG含む）
   ↓
3. 検索結果からmedia_name抽出
   ↓
4. salesdb.media_pricingから料金情報取得
   ↓
5. LLM提案生成（コンテキスト: 商材情報 + 料金情報）
   ↓
6. SSEストリーミングレスポンス
```

---

## ベクトル検索機能

### 概要

bge-m3:567m モデルを使用したベクトル検索機能を提供します。

- **Embeddingモデル**: bge-m3:567m (1024次元)
- **類似度計算**: コサイン類似度
- **インデックス**: IVFFlat

### 検索タイプ

1. **議事録検索**: 過去の類似議事録を検索（自分の議事録のみ）
2. **成功事例検索**: 業種・地域でフィルタ可能な成功事例検索
3. **セールストーク検索**: 課題タイプ・業種でフィルタ可能
4. **商品検索**: カテゴリでフィルタ可能な商品検索

### 使用例

```bash
# 類似成功事例の検索
curl -X POST http://localhost:8005/api/sales/search/success-cases \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "人材採用の課題を解決したい",
    "industry": "IT",
    "limit": 5,
    "threshold": 0.6
  }'
```

## 一般的なコマンド

### 開発セットアップ

```bash
# 依存関係のインストール
poetry install

# 開発サーバーの起動
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8005 --reload
```

### Docker操作

```bash
# ビルドと起動
docker compose up -d --build

# ログ表示
docker compose logs -f sales-api

# ヘルスチェック
curl http://localhost:8005/healthz
```

## 環境変数

```bash
# Database
SALESDB_URL=postgresql://postgres:password@host.docker.internal:5432/salesdb

# Redis
REDIS_URL=redis://:password@host.docker.internal:6379

# Authentication
AUTH_SERVICE_URL=http://host.docker.internal:8002
ADMIN_SERVICE_URL=http://host.docker.internal:8003
JWKS_URL=http://host.docker.internal:8002/.well-known/jwks.json
JWT_ISSUER=https://auth.example.com
JWT_AUDIENCE=fastapi-api

# RAG Service (9段階ハイブリッド検索パイプライン) ★重要
RAG_SERVICE_URL=http://host.docker.internal:8010

# LLM
OLLAMA_BASE_URL=http://host.docker.internal:11434
OPENAI_API_KEY=your-api-key

# Neo4j Graph Database
NEO4J_URI=bolt://host.docker.internal:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-neo4j-password
NEO4J_DATABASE=neo4j

# Application
LOG_LEVEL=INFO
CORS_ORIGINS=["http://localhost:3005","http://localhost:3003"]
```

## Neo4j グラフデータベース統合

### 概要

議事録解析結果をNeo4jグラフデータベースに保存し、グラフトラバーサルによる高度な推薦機能を提供します。

### グラフスキーマ

**ノード型:**
- `Meeting` - 議事録ノード（meeting_id, company_name, industry）
- `Problem` - 課題・問題（name）
- `Need` - ニーズ（name）
- `Industry` - 業種（name）
- `Target` - ターゲット顧客層（name）
- `Product` - 商品（既存マスタとの連携）
- `SuccessCase` - 成功事例

**リレーション型:**
- `HAS_PROBLEM` - Meeting → Problem
- `HAS_NEED` - Meeting → Need
- `IN_INDUSTRY` - Meeting → Industry
- `TARGETS` - Meeting → Target
- `SOLVED_BY` - Problem → Product
- `ADDRESSED_BY` - Need → Product
- `MENTIONED_IN` - Problem → SuccessCase

### 動作フロー

```
1. 議事録作成（POST /meeting-minutes）
   ↓
2. AI解析実行（POST /meeting-minutes/{id}/analyze）
   ↓
3. 解析結果をNeo4jに保存（自動）
   - Meeting, Problem, Need, Industry ノード作成
   - リレーション作成
   ↓
4. グラフベース推薦取得（GET /graph/recommendations/{id}）
   - 問題を解決する商品を検索
   - 類似議事録を検索
   - 関連成功事例を検索
```

### 使用例

```bash
# グラフ接続状態確認
curl http://localhost:8005/api/sales/graph/health

# 議事録に対する推薦取得
curl -X GET http://localhost:8005/api/sales/graph/recommendations/{minute_id} \
  -H "Authorization: Bearer $TOKEN"

# テナントのグラフ統計
curl -X GET http://localhost:8005/api/sales/graph/stats \
  -H "Authorization: Bearer $TOKEN"
```

## データベーステーブル

このサービスは `salesdb` データベースを使用します。

### 主要テーブル

| テーブル | 説明 | 操作 |
|---------|------|------|
| `meeting_minutes` | 議事録 | CRUD |
| `proposal_history` | 提案履歴 | CRUD |
| `products` | 商品マスタ | 読み取りのみ |
| `campaigns` | キャンペーン | 読み取りのみ |
| `simulation_params` | シミュレーション係数 | 読み取りのみ |
| `wage_data` | 地域別時給相場 | 読み取りのみ |

### ステータス遷移

**議事録ステータス:**
- `draft` → `analyzed` → `proposed` → `closed`

**提案フィードバック:**
- `pending`, `accepted`, `rejected`, `modified`

## LLM統合

### 使用モデル

- **解析**: `gemma2:9b` (Ollama)
- **温度**: 0.3（解析）、0.5（提案生成）

### プロンプトテンプレート

**議事録解析:**
- 課題・ニーズ抽出
- キーワード抽出
- 要約生成
- 決裁者判定

**提案生成:**
- 商品マッチング
- トークポイント生成
- 反論対応策

## セキュリティ

- JWT認証（RS256）
- JWKS経由での公開鍵取得
- ユーザー所有権チェック（自分のデータのみアクセス可能）

## トラブルシューティング

### Ollama接続エラー

```bash
# Ollamaが起動しているか確認
curl http://localhost:11434/api/tags

# モデルがインストールされているか確認
ollama list
```

### データベース接続エラー

```bash
# salesdbが存在するか確認
docker exec ai-micro-postgres psql -U postgres -c "\l" | grep salesdb

# テーブルが作成されているか確認
docker exec ai-micro-postgres psql -U postgres -d salesdb -c "\dt"
```

### JWT認証エラー

```bash
# JWKSエンドポイントが応答するか確認
curl http://localhost:8002/.well-known/jwks.json
```

### Neo4j接続エラー

```bash
# Neo4jコンテナが起動しているか確認
docker ps | grep neo4j

# 接続テスト
curl http://localhost:7474

# Sales APIからのグラフ接続確認
curl http://localhost:8005/api/sales/graph/health
```

## 関連サービス

- **ai-micro-api-rag** (Port 8010): 9段階ハイブリッド検索パイプライン ★商材提案チャットで使用
- **ai-micro-api-admin**: マスタデータ管理（商品、キャンペーン等）
- **ai-micro-api-auth**: 認証サービス
- **ai-micro-neo4j**: グラフデータベース（GraphRAG用）
- **ai-micro-front-sales**: フロントエンド（未実装）

---

**作成日**: 2025-12-17
**更新日**: 2026-01-21
**バージョン**: 1.2.0
