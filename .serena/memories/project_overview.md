# ai-micro-api-sales プロジェクト概要

## 概要
営業支援AIサービス。議事録解析と提案書自動生成を行うFastAPIベースのマイクロサービス。LLMを活用して商談議事録から顧客課題を抽出し、最適な商品提案を自動生成。

## 技術スタック
- **言語**: Python 3.11
- **フレームワーク**: FastAPI
- **パッケージ管理**: Poetry
- **データベース**: PostgreSQL (salesdb)
- **キャッシュ**: Redis
- **グラフDB**: Neo4j
- **LLM**: Ollama (gemma2:9b), OpenAI
- **RAG**: api-rag連携（9段階ハイブリッド検索）
- **コンテナ**: Docker Compose

## アーキテクチャ
```
ai-micro-api-sales (Port 8005)
    ├── salesdb (PostgreSQL)
    ├── api-rag (Port 8010) ← 9段階ハイブリッド検索
    ├── api-admin (Port 8003) ← マスタデータ
    ├── api-auth (Port 8002) ← JWT認証
    ├── Ollama (Port 11434) ← LLM処理
    └── Neo4j (Port 7687) ← グラフDB
```

## 主要機能
1. **議事録管理** - CRUD、AI解析（課題・ニーズ抽出）
2. **提案書生成** - 自動提案、商品マッチング
3. **シミュレーション** - コスト試算、ROI計算
4. **グラフベース推薦** - Neo4j関係性ベース推薦
5. **商材提案チャット** - 9段階ハイブリッド検索パイプライン

## ディレクトリ構成
```
app/
├── core/       # 設定・セキュリティ
├── db/         # DBセッション
├── models/     # SQLAlchemyモデル
├── schemas/    # Pydanticスキーマ
├── services/   # ビジネスロジック
│   └── graph/  # Neo4jサービス
└── routers/    # APIエンドポイント
```

## データベーステーブル
| テーブル | 説明 |
|---------|------|
| meeting_minutes | 議事録 |
| proposal_history | 提案履歴 |
| products | 商品マスタ（読取専用） |
| campaigns | キャンペーン（読取専用） |
