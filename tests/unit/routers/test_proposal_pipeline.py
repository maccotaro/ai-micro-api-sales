# ai-micro-api-sales/tests/unit/routers/test_proposal_pipeline.py
"""
Unit tests for proposal_pipeline router: PATCH presentation and GET download.

Tests:
- update_run_presentation: DB update, MinIO upload, fallback when disabled
- download_run_presentation: MinIO download, Presenton fallback, 404 cases
"""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.proposal_pipeline import router


# =============================================================================
# Test App Setup
# =============================================================================


def _create_app(
    db_rows=None,
    storage_service=None,
    current_user=None,
):
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


# =============================================================================
# PATCH /runs/{run_id}/presentation Tests
# =============================================================================


@pytest.mark.unit
class TestUpdateRunPresentation:
    """Tests for PATCH /runs/{run_id}/presentation endpoint."""

    def test_update_without_minio(self):
        """When MinIO is disabled, only DB update happens."""
        run_id = uuid4()
        returning_row = MagicMock()
        returning_row.__getitem__ = MagicMock(return_value=str(run_id))

        app, mock_db = _create_app(db_rows=returning_row)

        with patch("app.routers.proposal_pipeline.get_storage_service", return_value=None):
            client = TestClient(app)
            resp = client.patch(
                f"/api/sales/proposal-pipeline/runs/{run_id}/presentation",
                json={
                    "presentation_path": "/exports/abc/presentation.pptx",
                    "presentation_format": "pptx",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["minio_object_key"] is None

    def test_update_with_minio_success(self):
        """When MinIO is enabled, file is downloaded from Presenton and uploaded."""
        run_id = uuid4()
        tenant_id = str(uuid4())
        user_id = str(uuid4())
        returning_row = MagicMock()
        returning_row.__getitem__ = MagicMock(return_value=str(run_id))

        current_user = {
            "sub": user_id,
            "tenant_id": tenant_id,
            "roles": ["sales"],
        }

        app, mock_db = _create_app(db_rows=returning_row, current_user=current_user)
        expected_key = f"presentations/{tenant_id}/{run_id}/proposal.pptx"

        mock_storage = AsyncMock()
        mock_storage.upload_bytes = AsyncMock(return_value=expected_key)

        mock_httpx_resp = MagicMock()
        mock_httpx_resp.status_code = 200
        mock_httpx_resp.content = b"fake pptx data"
        mock_httpx_resp.raise_for_status = MagicMock()

        with patch("app.routers.proposal_pipeline.get_storage_service", return_value=mock_storage), \
             patch("app.routers.proposal_pipeline.httpx.AsyncClient") as mock_httpx_cls:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_httpx_resp)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_cls.return_value = mock_client_instance

            client = TestClient(app)
            resp = client.patch(
                f"/api/sales/proposal-pipeline/runs/{run_id}/presentation",
                json={
                    "presentation_path": "/exports/abc/presentation.pptx",
                    "presentation_format": "pptx",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["minio_object_key"] == expected_key
        mock_storage.upload_bytes.assert_called_once()

    def test_update_run_not_found(self):
        """Returns 404 when run_id doesn't match."""
        run_id = uuid4()

        app, mock_db = _create_app()
        mock_db.execute = MagicMock(return_value=MagicMock(
            fetchone=MagicMock(return_value=None),
        ))

        with patch("app.routers.proposal_pipeline.get_storage_service", return_value=None):
            client = TestClient(app)
            resp = client.patch(
                f"/api/sales/proposal-pipeline/runs/{run_id}/presentation",
                json={
                    "presentation_path": "/exports/abc/presentation.pptx",
                    "presentation_format": "pptx",
                },
            )

        assert resp.status_code == 404

    def test_update_minio_failure_still_ok(self):
        """MinIO upload failure doesn't cause endpoint to fail."""
        run_id = uuid4()
        returning_row = MagicMock()
        returning_row.__getitem__ = MagicMock(return_value=str(run_id))

        app, mock_db = _create_app(db_rows=returning_row)

        mock_storage = AsyncMock()
        mock_storage.upload_bytes = AsyncMock(side_effect=Exception("Connection refused"))

        mock_httpx_resp = MagicMock()
        mock_httpx_resp.status_code = 200
        mock_httpx_resp.content = b"fake data"
        mock_httpx_resp.raise_for_status = MagicMock()

        with patch("app.routers.proposal_pipeline.get_storage_service", return_value=mock_storage), \
             patch("app.routers.proposal_pipeline.httpx.AsyncClient") as mock_httpx_cls:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_httpx_resp)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_cls.return_value = mock_client_instance

            client = TestClient(app)
            resp = client.patch(
                f"/api/sales/proposal-pipeline/runs/{run_id}/presentation",
                json={
                    "presentation_path": "/exports/abc/presentation.pptx",
                    "presentation_format": "pptx",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["minio_object_key"] is None  # upload failed

    def test_invalid_format_rejected(self):
        """Only pptx/pdf formats are accepted."""
        run_id = uuid4()
        app, _ = _create_app()

        with patch("app.routers.proposal_pipeline.get_storage_service", return_value=None):
            client = TestClient(app)
            resp = client.patch(
                f"/api/sales/proposal-pipeline/runs/{run_id}/presentation",
                json={
                    "presentation_path": "/exports/abc/presentation.docx",
                    "presentation_format": "docx",
                },
            )

        assert resp.status_code == 422  # validation error


# =============================================================================
# GET /runs/{run_id}/download Tests
# =============================================================================


@pytest.mark.unit
class TestDownloadRunPresentation:
    """Tests for GET /runs/{run_id}/download endpoint."""

    def test_download_from_minio(self):
        """Downloads from MinIO when minio_object_key is set."""
        run_id = uuid4()
        minio_key = f"presentations/t1/{run_id}/proposal.pptx"

        # DB row: (minio_object_key, presentation_path)
        db_row = MagicMock()
        db_row.__getitem__ = MagicMock(side_effect=lambda i: {
            0: minio_key,
            1: "/exports/abc/presentation.pptx",
        }[i])

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

    def test_download_fallback_to_presenton(self):
        """Falls back to Presenton when no minio_object_key."""
        run_id = uuid4()

        db_row = MagicMock()
        db_row.__getitem__ = MagicMock(side_effect=lambda i: {
            0: None,  # no minio key
            1: "/exports/abc/presentation.pptx",
        }[i])

        app, mock_db = _create_app()
        mock_db.execute = MagicMock(return_value=MagicMock(
            fetchone=MagicMock(return_value=db_row),
        ))

        mock_httpx_resp = MagicMock()
        mock_httpx_resp.status_code = 200
        mock_httpx_resp.content = b"presenton pptx data"
        mock_httpx_resp.headers = {"content-type": "application/octet-stream"}

        with patch("app.routers.proposal_pipeline.get_storage_service", return_value=None), \
             patch("app.routers.proposal_pipeline.httpx.AsyncClient") as mock_httpx_cls:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_httpx_resp)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_cls.return_value = mock_client_instance

            client = TestClient(app)
            resp = client.get(f"/api/sales/proposal-pipeline/runs/{run_id}/download")

        assert resp.status_code == 200
        assert resp.content == b"presenton pptx data"

    def test_download_minio_failure_falls_back(self):
        """Falls back to Presenton when MinIO download fails."""
        run_id = uuid4()
        minio_key = f"presentations/t1/{run_id}/proposal.pptx"

        db_row = MagicMock()
        db_row.__getitem__ = MagicMock(side_effect=lambda i: {
            0: minio_key,
            1: "/exports/abc/presentation.pptx",
        }[i])

        app, mock_db = _create_app()
        mock_db.execute = MagicMock(return_value=MagicMock(
            fetchone=MagicMock(return_value=db_row),
        ))

        mock_storage = AsyncMock()
        mock_storage.download_bytes = AsyncMock(side_effect=Exception("MinIO down"))

        mock_httpx_resp = MagicMock()
        mock_httpx_resp.status_code = 200
        mock_httpx_resp.content = b"fallback data"
        mock_httpx_resp.headers = {"content-type": "application/octet-stream"}

        with patch("app.routers.proposal_pipeline.get_storage_service", return_value=mock_storage), \
             patch("app.routers.proposal_pipeline.httpx.AsyncClient") as mock_httpx_cls:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_httpx_resp)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_httpx_cls.return_value = mock_client_instance

            client = TestClient(app)
            resp = client.get(f"/api/sales/proposal-pipeline/runs/{run_id}/download")

        assert resp.status_code == 200
        assert resp.content == b"fallback data"

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

    def test_download_no_file_available(self):
        """Returns 404 when neither MinIO key nor presentation_path exists."""
        run_id = uuid4()

        db_row = MagicMock()
        db_row.__getitem__ = MagicMock(side_effect=lambda i: {
            0: None,  # no minio key
            1: None,  # no presentation_path
        }[i])

        app, mock_db = _create_app()
        mock_db.execute = MagicMock(return_value=MagicMock(
            fetchone=MagicMock(return_value=db_row),
        ))

        with patch("app.routers.proposal_pipeline.get_storage_service", return_value=None):
            client = TestClient(app)
            resp = client.get(f"/api/sales/proposal-pipeline/runs/{run_id}/download")

        assert resp.status_code == 404
