# ai-micro-api-sales/tests/unit/routers/test_proposal_pipeline.py
"""
Unit tests for proposal_pipeline router: GET download.

Tests:
- download_run_presentation: MinIO download, 404 cases
"""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.proposal_pipeline import router


def _create_app(db_rows=None, current_user=None):
    """Create a test FastAPI app with dependency overrides."""
    app = FastAPI()
    app.include_router(router, prefix="/api/sales")

    if current_user is None:
        current_user = {
            "sub": str(uuid4()),
            "tenant_id": str(uuid4()),
            "roles": ["sales"],
        }

    mock_db = MagicMock()
    if db_rows is not None:
        mock_db.execute = MagicMock(return_value=MagicMock(
            fetchone=MagicMock(side_effect=db_rows if isinstance(db_rows, list) else [db_rows]),
            fetchall=MagicMock(return_value=db_rows if isinstance(db_rows, list) else [db_rows]),
        ))
    mock_db.commit = MagicMock()

    from app.core.security import require_sales_access
    from app.db.session import get_db

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[require_sales_access] = lambda: current_user

    return app, mock_db


@pytest.mark.unit
class TestDownloadRunPresentation:
    """Tests for GET /runs/{run_id}/download endpoint."""

    def test_download_from_minio(self):
        """Downloads from MinIO when minio_object_key is set."""
        run_id = uuid4()
        minio_key = f"presentations/t1/{run_id}/proposal.pptx"

        db_row = MagicMock()
        db_row.__getitem__ = MagicMock(side_effect=lambda i: {0: minio_key}[i])

        app, mock_db = _create_app()
        mock_db.execute = MagicMock(return_value=MagicMock(
            fetchone=MagicMock(return_value=db_row),
        ))

        mock_storage = AsyncMock()
        mock_storage.download_bytes = AsyncMock(return_value=b"minio pptx data")

        with patch("app.routers.proposal_pipeline.get_storage_service", return_value=mock_storage):
            client = TestClient(app)
            resp = client.get(f"/api/sales/proposal-pipeline/runs/{run_id}/download")

        assert resp.status_code == 200
        assert resp.content == b"minio pptx data"
        assert "proposal.pptx" in resp.headers.get("content-disposition", "")

    def test_download_run_not_found(self):
        """Returns 404 when run doesn't exist."""
        run_id = uuid4()

        app, mock_db = _create_app()
        mock_db.execute = MagicMock(return_value=MagicMock(
            fetchone=MagicMock(return_value=None),
        ))

        with patch("app.routers.proposal_pipeline.get_storage_service", return_value=None):
            client = TestClient(app)
            resp = client.get(f"/api/sales/proposal-pipeline/runs/{run_id}/download")

        assert resp.status_code == 404

    def test_download_no_minio_key(self):
        """Returns 404 when no minio_object_key exists."""
        run_id = uuid4()

        db_row = MagicMock()
        db_row.__getitem__ = MagicMock(side_effect=lambda i: {0: None}[i])

        app, mock_db = _create_app()
        mock_db.execute = MagicMock(return_value=MagicMock(
            fetchone=MagicMock(return_value=db_row),
        ))

        with patch("app.routers.proposal_pipeline.get_storage_service", return_value=None):
            client = TestClient(app)
            resp = client.get(f"/api/sales/proposal-pipeline/runs/{run_id}/download")

        assert resp.status_code == 404
