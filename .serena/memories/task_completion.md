# ai-micro-api-sales タスク完了チェックリスト

## コード変更後の必須手順

### 1. コード品質チェック
```bash
poetry run black .
poetry run ruff check .
poetry run mypy app/
```

### 2. テスト実行
```bash
poetry run pytest
```

### 3. Dockerコンテナ再起動
```bash
docker compose restart sales-api
```

### 4. 動作確認
```bash
curl http://localhost:8005/healthz
docker compose logs -f sales-api
```

## 変更タイプ別追加手順

### 議事録解析変更
- [ ] プロンプトテンプレート更新
- [ ] LLMレスポンスパース処理確認
- [ ] Neo4jグラフ更新処理確認

### 提案生成変更
- [ ] api-rag連携確認
- [ ] 料金情報取得処理確認
- [ ] LLM提案生成プロンプト確認

### グラフ機能変更
- [ ] Cypherクエリテスト
- [ ] Neo4j接続確認
- [ ] グラフスキーマ整合性確認

### シミュレーション変更
- [ ] 計算ロジック確認
- [ ] マスタデータ参照確認

### 商材提案チャット変更
- [ ] api-rag連携確認（9段階パイプライン）
- [ ] SSEストリーミング動作確認
- [ ] 料金情報連携確認

## 関連サービス確認

api-salesは複数のサービスと連携:

- [ ] api-rag (8010): ハイブリッド検索
- [ ] Ollama (11434): LLM処理
- [ ] Neo4j (7687): グラフDB
- [ ] api-auth (8002): JWT認証

## コミット前チェック

- [ ] すべてのテストがパス
- [ ] リンティングエラーなし
- [ ] 型チェックエラーなし
- [ ] コンテナ再起動後の動作確認完了
- [ ] 関連サービスとの連携確認完了
