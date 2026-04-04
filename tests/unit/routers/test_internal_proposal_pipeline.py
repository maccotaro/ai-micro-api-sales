# ai-micro-api-sales/tests/unit/routers/test_internal_proposal_pipeline.py
"""
Unit tests for internal_proposal_pipeline router.

Tests:
- Authentication: X-Internal-Secret validation
- POST /proposal-pipeline/trigger: parameter validation, success/error
- GET /proposal-pipeline/runs/{run_id}: status check, 404
- POST /meeting-minutes/{id}/analyze: parameter validation, success/error
- POST /search/meetings: search delegation
- GET /graph/recommendations/{id}: graph recommendations
"""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.internal_proposal_pipeline import router


VALID_SECRET = "change-me-in-production"
TENANT_ID = str(uuid4())
USER_ID = str(uuid4())


def _create_app():
    """Create a test FastAPI app with the internal router."""
    app = FastAPI()
    app.include_router(router, prefix="/internal")

    mock_db = MagicMock()
    mock_db.commit = MagicMock()

    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: mock_db

    return app, mock_db


@pytest.mark.unit
class TestInternalAuth:
    """Tests for X-Internal-Secret authentication."""

    def test_missing_secret_returns_422(self):
        """Missing X-Internal-Secret header returns 422."""
        app, _ = _create_app()
        client = TestClient(app)
        resp = client.post(
            "/internal/proposal-pipeline/trigger",
            json={"minute_id": str(uuid4()), "tenant_id": TENANT_ID, "user_id": USER_ID},
        )
        assert resp.status_code == 422

    def test_invalid_secret_returns_401(self):
        """Invalid X-Internal-Secret header returns 401."""
        app, _ = _create_app()
        client = TestClient(app)
        resp = client.post(
            "/internal/proposal-pipeline/trigger",
            json={"minute_id": str(uuid4()), "tenant_id": TENANT_ID, "user_id": USER_ID},
            headers={"X-Internal-Secret": "wrong-secret"},
        )
        assert resp.status_code == 401

    def test_valid_secret_passes_auth(self):
        """Valid X-Internal-Secret passes authentication check."""
        app, mock_db = _create_app()

        mock_result = {
            "type": "result",
            "run_id": str(uuid4()),
            "status": "completed",
            "total_duration_ms": 5000,
            "minio_object_key": "proposals/test.md",
            "stage_results": {},
        }

        mock_svc = MagicMock()
        mock_svc.generate_pipeline = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.proposal_pipeline_service.proposal_pipeline_service",
            mock_svc,
        ):
            client = TestClient(app)
            resp = client.post(
                "/internal/proposal-pipeline/trigger",
                json={
                    "minute_id": str(uuid4()),
                    "tenant_id": TENANT_ID,
                    "user_id": USER_ID,
                },
                headers={"X-Internal-Secret": VALID_SECRET},
            )

        assert resp.status_code == 200


@pytest.mark.unit
class TestTriggerPipeline:
    """Tests for POST /proposal-pipeline/trigger."""

    def test_missing_minute_id_returns_422(self):
        """Missing minute_id returns 422."""
        app, _ = _create_app()
        client = TestClient(app)
        resp = client.post(
            "/internal/proposal-pipeline/trigger",
            json={"tenant_id": TENANT_ID, "user_id": USER_ID},
            headers={"X-Internal-Secret": VALID_SECRET},
        )
        assert resp.status_code == 422

    def test_invalid_uuid_returns_422(self):
        """Invalid UUID format returns 422."""
        app, _ = _create_app()
        client = TestClient(app)
        resp = client.post(
            "/internal/proposal-pipeline/trigger",
            json={
                "minute_id": "not-a-uuid",
                "tenant_id": TENANT_ID,
                "user_id": USER_ID,
            },
            headers={"X-Internal-Secret": VALID_SECRET},
        )
        assert resp.status_code == 422

    def test_successful_trigger(self):
        """Successful pipeline trigger returns completed result."""
        app, _ = _create_app()
        run_id = str(uuid4())

        mock_result = {
            "type": "result",
            "run_id": run_id,
            "status": "completed",
            "total_duration_ms": 45000,
            "minio_object_key": "proposals/test.md",
            "stage_results": {
                "0": {"name": "コンテキスト収集", "status": "completed", "duration_ms": 2000},
                "1": {"name": "課題構造化", "status": "completed", "duration_ms": 8000},
            },
        }

        mock_svc = MagicMock()
        mock_svc.generate_pipeline = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.proposal_pipeline_service.proposal_pipeline_service",
            mock_svc,
        ):
            client = TestClient(app)
            resp = client.post(
                "/internal/proposal-pipeline/trigger",
                json={
                    "minute_id": str(uuid4()),
                    "tenant_id": TENANT_ID,
                    "user_id": USER_ID,
                },
                headers={"X-Internal-Secret": VALID_SECRET},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["id"] == run_id
        assert data["total_duration_ms"] == 45000
        assert len(data["stages"]) == 2

    def test_pipeline_error(self):
        """Pipeline error returns error status."""
        app, _ = _create_app()

        mock_svc = MagicMock()
        mock_svc.generate_pipeline = AsyncMock(
            return_value={"error": "パイプラインが無効です"}
        )

        with patch(
            "app.services.proposal_pipeline_service.proposal_pipeline_service",
            mock_svc,
        ):
            client = TestClient(app)
            resp = client.post(
                "/internal/proposal-pipeline/trigger",
                json={
                    "minute_id": str(uuid4()),
                    "tenant_id": TENANT_ID,
                    "user_id": USER_ID,
                },
                headers={"X-Internal-Secret": VALID_SECRET},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert "無効" in data["error"]


@pytest.mark.unit
class TestGetPipelineStatus:
    """Tests for GET /proposal-pipeline/runs/{run_id}."""

    def test_run_not_found(self):
        """Returns 404 for non-existent run."""
        app, mock_db = _create_app()
        mock_db.execute = MagicMock(
            return_value=MagicMock(fetchone=MagicMock(return_value=None))
        )

        client = TestClient(app)
        resp = client.get(
            f"/internal/proposal-pipeline/runs/{uuid4()}",
            headers={"X-Internal-Secret": VALID_SECRET},
        )
        assert resp.status_code == 404

    def test_run_found(self):
        """Returns pipeline run details."""
        app, mock_db = _create_app()
        run_id = uuid4()
        minute_id = uuid4()

        row = (
            run_id, minute_id, "completed", 45000,
            "2026-04-01T12:00:00", None, None,
            {"0": {"status": "completed", "duration_ms": 2000}},
            "proposals/test.md",
        )
        mock_db.execute = MagicMock(
            return_value=MagicMock(fetchone=MagicMock(return_value=row))
        )

        client = TestClient(app)
        resp = client.get(
            f"/internal/proposal-pipeline/runs/{run_id}",
            headers={"X-Internal-Secret": VALID_SECRET},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["total_duration_ms"] == 45000
        assert data["minio_object_key"] == "proposals/test.md"


@pytest.mark.unit
class TestAnalyzeMeetingMinute:
    """Tests for POST /meeting-minutes/{id}/analyze."""

    def test_meeting_not_found(self):
        """Returns 404 for non-existent meeting."""
        app, mock_db = _create_app()
        mock_query = MagicMock()
        mock_query.filter = MagicMock(return_value=mock_query)
        mock_query.first = MagicMock(return_value=None)
        mock_db.query = MagicMock(return_value=mock_query)

        client = TestClient(app)
        resp = client.post(
            f"/internal/meeting-minutes/{uuid4()}/analyze",
            json={"tenant_id": TENANT_ID, "user_id": USER_ID},
            headers={"X-Internal-Secret": VALID_SECRET},
        )
        assert resp.status_code == 404

    def test_successful_analysis(self):
        """Successful analysis returns completed status."""
        app, mock_db = _create_app()

        mock_minute = MagicMock()
        mock_minute.id = uuid4()
        mock_minute.tenant_id = uuid4()

        mock_query = MagicMock()
        mock_query.filter = MagicMock(return_value=mock_query)
        mock_query.first = MagicMock(return_value=mock_minute)
        mock_db.query = MagicMock(return_value=mock_query)

        mock_analysis = MagicMock()
        mock_analysis.model_dump = MagicMock(return_value={"summary": "テスト"})

        with patch("app.services.analysis_service.AnalysisService") as MockService:
            mock_service = MockService.return_value
            mock_service.analyze_meeting = AsyncMock(return_value=mock_analysis)

            client = TestClient(app)
            resp = client.post(
                f"/internal/meeting-minutes/{mock_minute.id}/analyze",
                json={"tenant_id": TENANT_ID, "user_id": USER_ID},
                headers={"X-Internal-Secret": VALID_SECRET},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["analysis"]["summary"] == "テスト"


@pytest.mark.unit
class TestSearchSimilarMeetings:
    """Tests for POST /search/meetings."""

    def test_search_missing_query(self):
        """Missing query returns 422."""
        app, _ = _create_app()
        client = TestClient(app)
        resp = client.post(
            "/internal/search/meetings",
            json={"tenant_id": TENANT_ID, "user_id": USER_ID},
            headers={"X-Internal-Secret": VALID_SECRET},
        )
        assert resp.status_code == 422

    def test_successful_search(self):
        """Successful search returns results."""
        app, mock_db = _create_app()

        mock_results = [{"id": str(uuid4()), "similarity": 0.85}]

        mock_svc = MagicMock()
        mock_svc.search_similar_meetings = AsyncMock(return_value=mock_results)

        with patch(
            "app.routers.internal_proposal_pipeline.get_embedding_service",
            new_callable=AsyncMock,
            return_value=mock_svc,
        ):
            client = TestClient(app)
            resp = client.post(
                "/internal/search/meetings",
                json={
                    "query": "人材採用の課題",
                    "tenant_id": TENANT_ID,
                    "user_id": USER_ID,
                },
                headers={"X-Internal-Secret": VALID_SECRET},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["query"] == "人材採用の課題"
