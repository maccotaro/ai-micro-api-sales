# コードスタイル・規約

## フォーマット
- **ツール**: Black
- **行長**: 100文字
- **ターゲット**: Python 3.11

## リント
- **ツール**: Ruff
- **行長**: 100文字
- **ターゲット**: Python 3.11

## 型ヒント
- **ツール**: mypy
- **設定**:
  - `warn_return_any = true`
  - `warn_unused_configs = true`

## 命名規則
- **モジュール**: snake_case
- **クラス**: PascalCase
- **関数/変数**: snake_case
- **定数**: UPPER_SNAKE_CASE

## ディレクトリ構成パターン
```
routers/   # APIエンドポイント
services/  # ビジネスロジック
schemas/   # Pydanticスキーマ
models/    # SQLAlchemyモデル
```
