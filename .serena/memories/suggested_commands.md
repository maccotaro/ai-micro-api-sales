# 推奨コマンド

## 開発環境セットアップ
```bash
# 依存関係インストール
poetry install

# 開発サーバー起動（自動リロード）
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8005 --reload
```

## コード品質
```bash
# フォーマット
poetry run black .

# リント
poetry run ruff check .

# 型チェック
poetry run mypy app/

# テスト実行
poetry run pytest
```

## Docker操作
```bash
# ビルドと起動
docker compose up -d --build

# ログ表示
docker compose logs -f sales-api

# コンテナ再起動
docker compose restart sales-api

# ヘルスチェック
curl http://localhost:8005/healthz
```

## サービス確認
```bash
# Ollama接続確認
curl http://localhost:11434/api/tags

# Neo4j接続確認
curl http://localhost:8005/api/sales/graph/health

# JWKS確認
curl http://localhost:8002/.well-known/jwks.json

# salesdb確認
docker exec ai-micro-postgres psql -U postgres -d salesdb -c "\dt"
```

## API テスト例
```bash
# ストリーミング提案生成
curl -X POST http://localhost:8005/api/sales/proposal-chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "人材採用の課題", "knowledge_base_id": "xxx"}'
```
