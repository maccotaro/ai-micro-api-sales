# ai-micro-api-sales プロジェクト概要

## 目的
営業支援AIサービス。議事録解析と提案書自動生成を行うFastAPIベースのマイクロサービス。
LLMを活用して商談議事録から顧客課題を抽出し、最適な商品提案を自動生成。

## 技術スタック
- **言語**: Python 3.11+
- **フレームワーク**: FastAPI
- **データベース**: PostgreSQL (salesdb)
- **グラフDB**: Neo4j
- **キャッシュ**: Redis
- **Embedding**: bge-m3:567m (1024次元)
- **LLM**: Ollama (gemma2:9b, qwen2.5:14b)

## サービス構成

```
ai-micro-api-sales (Port 8005)
    ├── salesdb (PostgreSQL)
    ├── api-rag (Port 8010) ← 9段階ハイブリッド検索
    ├── api-admin (Port 8003) ← マスタデータ管理
    ├── api-auth (Port 8002) ← JWT認証
    ├── Ollama (Port 11434) ← LLM処理
    └── Neo4j (Port 7687) ← グラフデータベース
```

## 主要機能

### 1. 議事録管理 (`/api/sales/meeting-minutes`)
- 議事録のCRUD操作
- AIによる議事録解析（課題・ニーズ抽出）

### 2. 提案書生成 (`/api/sales/proposals`)
- 解析結果に基づく自動提案生成
- 商品マッチング

### 3. シミュレーション (`/api/sales/simulation`)
- 地域・業界パラメータに基づくコスト試算
- ROI計算

### 4. グラフベース推薦 (`/api/sales/graph`)
- Neo4jによる関係性ベース推薦
- 類似議事録検索

### 5. 商材提案チャット (`/api/sales/proposal-chat`) ★重要
- api-ragの9段階ハイブリッド検索パイプライン連携
- GraphRAG Query Expansion
- LLMによる提案生成

## ディレクトリ構造

```
app/
├── main.py
├── core/             # 設定、認証
├── db/               # DB接続
├── models/           # SQLAlchemyモデル
├── schemas/          # Pydanticスキーマ
├── services/
│   ├── analysis_service.py   # 議事録解析
│   ├── proposal_service.py   # 提案生成
│   ├── simulation_service.py
│   ├── embedding_service.py
│   └── graph/                # Neo4jサービス
└── routers/          # APIエンドポイント
```

## Neo4jグラフスキーマ

**ノード**: Meeting, Problem, Need, Industry, Target, Product, SuccessCase

**リレーション**:
- `HAS_PROBLEM`, `HAS_NEED`, `IN_INDUSTRY`
- `SOLVED_BY`, `ADDRESSED_BY`, `MENTIONED_IN`

## データベーステーブル (salesdb)

| テーブル | 操作 |
|---------|------|
| `meeting_minutes` | CRUD |
| `proposal_history` | CRUD |
| `products` | 読み取りのみ |
| `campaigns` | 読み取りのみ |

## 環境変数
- `SALESDB_URL` - PostgreSQL接続
- `REDIS_URL` - Redis接続
- `NEO4J_URI` - Neo4j Bolt URI
- `RAG_SERVICE_URL` - api-rag URL ★重要
- `OLLAMA_BASE_URL` - Ollama URL
- `JWKS_URL` - JWT公開鍵
