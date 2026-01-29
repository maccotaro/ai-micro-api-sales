# ai-micro-api-sales/Makefile
# ============================================================
# テストコマンド（Poetry版）
# ============================================================

.PHONY: help test-unit test-contract test-integration test-all \
        test-cov lint lint-fix check

PYTEST = poetry run pytest
PYTHON = poetry run python

# デフォルトターゲット
help:
	@echo "=== $(notdir $(CURDIR)) テストコマンド ==="
	@echo ""
	@echo "テスト実行:"
	@echo "  make test-unit        Unit テスト"
	@echo "  make test-contract    Contract テスト"
	@echo "  make test-integration Integration テスト"
	@echo "  make test-all         全テスト"
	@echo "  make test-cov         カバレッジ付きテスト"
	@echo ""
	@echo "コード品質:"
	@echo "  make lint             Lint チェック"
	@echo "  make lint-fix         Lint 自動修正"
	@echo "  make check            Lint + Unit テスト"
	@echo ""

# ============================================================
# テスト実行
# ============================================================

test-unit:
	$(PYTEST) -m unit -v --tb=short

test-contract:
	$(PYTEST) -m contract -v --tb=short

test-integration:
	$(PYTEST) -m integration -v --tb=short

test-all: test-unit test-contract test-integration

# ============================================================
# カバレッジ付きテスト
# ============================================================

test-cov:
	$(PYTEST) --cov=app --cov-report=html --cov-report=term
	@echo ""
	@echo "カバレッジレポート: htmlcov/index.html"

# ============================================================
# Lint
# ============================================================

lint:
	poetry run ruff check .
	poetry run black --check .

lint-fix:
	poetry run ruff check . --fix
	poetry run black .

# ============================================================
# 複合コマンド
# ============================================================

check: lint test-unit
	@echo "=== チェック完了 ==="
