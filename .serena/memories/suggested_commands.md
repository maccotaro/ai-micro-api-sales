# ai-micro-api-sales 開発コマンド

## 開発環境

### 依存関係インストール
```bash
poetry install
```

### ローカル開発サーバー起動
```bash
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8005 --reload
```

## コード品質

### フォーマット
```bash
poetry run black .
```

### リンティング
```bash
poetry run ruff check .
poetry run ruff check . --fix
```

### 型チェック
```bash
poetry run mypy app/
```

### テスト
```bash
poetry run pytest
```

## Docker操作

### コンテナ起動
```bash
docker compose up -d --build
```

### コンテナ再起動
```bash
docker compose restart sales-api
```

### ログ確認
```bash
docker compose logs -f sales-api
```

### ヘルスチェック
```bash
curl http://localhost:8005/healthz
```

## API確認

### Swagger UI
http://localhost:8005/docs

### 議事録作成
```bash
curl -X POST http://localhost:8005/api/sales/meeting-minutes \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "テスト株式会社",
    "content": "商談内容...",
    "industry": "IT"
  }'
```

### 議事録解析
```bash
curl -X POST http://localhost:8005/api/sales/meeting-minutes/{id}/analyze \
  -H "Authorization: Bearer $TOKEN"
```

### 商材提案チャット（9段階ハイブリッド検索）
```bash
curl -X POST http://localhost:8005/api/sales/proposal-chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "人材採用で困っている",
    "knowledge_base_id": "xxx",
    "area": "関東"
  }'
```

### グラフ推薦取得
```bash
curl http://localhost:8005/api/sales/graph/recommendations/{minute_id} \
  -H "Authorization: Bearer $TOKEN"
```

## 関連サービス確認

### Ollama接続確認
```bash
curl http://localhost:11434/api/tags
```

### Neo4j接続確認
```bash
curl http://localhost:8005/api/sales/graph/health
```

### api-rag接続確認
```bash
curl http://localhost:8010/health
```

## データベース

### salesdb接続
```bash
docker exec ai-micro-postgres psql -U postgres -d salesdb
```

### テーブル確認
```bash
docker exec ai-micro-postgres psql -U postgres -d salesdb -c "\dt"
```

## トラブルシューティング

### コンテナ再ビルド
```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```
