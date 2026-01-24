# タスク完了時チェックリスト

## 必須チェック
1. **コードフォーマット**
   ```bash
   poetry run black .
   ```

2. **リント**
   ```bash
   poetry run ruff check .
   ```

3. **型チェック**
   ```bash
   poetry run mypy app/
   ```

4. **テスト実行**
   ```bash
   poetry run pytest
   ```

## コード変更後
- **Dockerコンテナ再起動**
  ```bash
  docker compose restart sales-api
  ```

## ドキュメント更新
- CLAUDE.md更新（重要な変更時）
