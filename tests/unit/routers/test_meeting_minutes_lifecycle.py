"""Tests for meeting minutes lifecycle: finalize, version management, status transitions."""
import uuid
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db
from app.core.security import require_sales_access


@pytest.fixture
def mock_db():
    session = MagicMock()
    session.commit = MagicMock()
    session.refresh = MagicMock(side_effect=lambda obj: None)
    session.add = MagicMock()
    return session


@pytest.fixture
def mock_user():
    return {
        "user_id": str(uuid.uuid4()),
        "email": "test@example.com",
        "roles": ["admin"],
        "permissions": ["*:*"],
        "tenant_id": str(uuid.uuid4()),
    }


@pytest.fixture
def client(mock_db, mock_user):
    def override_get_db():
        try:
            yield mock_db
        finally:
            pass

    async def override_require_sales():
        return mock_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_sales_access] = override_require_sales
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _make_minute(tenant_id, stt_job_id=None, minutes_status="raw"):
    minute = MagicMock()
    minute.id = uuid.uuid4()
    minute.tenant_id = uuid.UUID(tenant_id)
    minute.stt_job_id = uuid.uuid4() if stt_job_id is True else stt_job_id
    minute.minutes_status = minutes_status
    minute.version = 1
    minute.raw_text = "Test text"
    minute.corrected_text = "Corrected text"
    minute.final_text = None
    minute.created_by = uuid.uuid4()
    minute.company_name = "Test Co"
    minute.status = "draft"
    minute.created_at = "2026-04-14T00:00:00Z"
    minute.updated_at = "2026-04-14T00:00:00Z"
    minute.parsed_json = None
    minute.company_id = None
    minute.industry = None
    minute.area = None
    minute.meeting_date = None
    minute.attendees = []
    minute.next_action_date = None
    minute.entity_data = None
    minute.entity_extraction_status = None
    return minute


class TestFinalizeEndpoint:
    def test_finalize_success(self, client, mock_db, mock_user):
        """Finalize transitions minutes_status to finalized."""
        minute = _make_minute(mock_user["tenant_id"], stt_job_id=True, minutes_status="reviewed")
        mock_db.query.return_value.filter.return_value.first.return_value = minute

        response = client.post(f"/api/sales/meeting-minutes/{minute.id}/finalize")
        assert response.status_code == 200
        assert minute.minutes_status == "finalized"
        mock_db.commit.assert_called()

    def test_finalize_already_finalized(self, client, mock_db, mock_user):
        """Cannot finalize already-finalized minutes."""
        minute = _make_minute(mock_user["tenant_id"], stt_job_id=True, minutes_status="finalized")
        mock_db.query.return_value.filter.return_value.first.return_value = minute

        response = client.post(f"/api/sales/meeting-minutes/{minute.id}/finalize")
        assert response.status_code == 409

    def test_finalize_non_stt_rejected(self, client, mock_db, mock_user):
        """Cannot finalize non-STT (manual) minutes."""
        minute = _make_minute(mock_user["tenant_id"], stt_job_id=None, minutes_status="manual")
        mock_db.query.return_value.filter.return_value.first.return_value = minute

        response = client.post(f"/api/sales/meeting-minutes/{minute.id}/finalize")
        assert response.status_code == 400


class TestFinalizedUpdateRejection:
    @patch("app.routers.meeting_minutes.AnalysisService")
    def test_update_finalized_rejected(self, mock_analysis, client, mock_db, mock_user):
        """Updating finalized minutes returns 409."""
        minute = _make_minute(mock_user["tenant_id"], stt_job_id=True, minutes_status="finalized")
        mock_db.query.return_value.filter.return_value.first.return_value = minute

        response = client.put(
            f"/api/sales/meeting-minutes/{minute.id}",
            json={"raw_text": "Updated text"},
        )
        assert response.status_code == 409


class TestVersionManagement:
    @patch("app.routers.meeting_minutes.AnalysisService")
    def test_update_creates_version(self, mock_analysis, client, mock_db, mock_user):
        """Updating STT-originated minutes creates a version record."""
        minute = _make_minute(mock_user["tenant_id"], stt_job_id=True, minutes_status="corrected")
        mock_db.query.return_value.filter.return_value.first.return_value = minute

        response = client.put(
            f"/api/sales/meeting-minutes/{minute.id}",
            json={"raw_text": "Updated text"},
        )
        assert response.status_code == 200
        # Version should be saved via db.add
        assert mock_db.add.called
        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.version == 1  # original version
        assert minute.version == 2  # incremented

    @patch("app.routers.meeting_minutes.AnalysisService")
    def test_update_manual_no_version(self, mock_analysis, client, mock_db, mock_user):
        """Updating manual (non-STT) minutes does NOT create a version record."""
        minute = _make_minute(mock_user["tenant_id"], stt_job_id=None, minutes_status="manual")
        mock_db.query.return_value.filter.return_value.first.return_value = minute

        response = client.put(
            f"/api/sales/meeting-minutes/{minute.id}",
            json={"raw_text": "Updated text"},
        )
        assert response.status_code == 200
        mock_db.add.assert_not_called()
