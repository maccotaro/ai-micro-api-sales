"""Tests for internal meeting transcript dispatch receiver."""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db
from app.routers.internal_meeting import verify_internal_secret


@pytest.fixture
def mock_db():
    session = MagicMock()
    session.commit = MagicMock()
    session.refresh = MagicMock(side_effect=lambda obj: None)
    return session


@pytest.fixture
def client(mock_db):
    def override_get_db():
        try:
            yield mock_db
        finally:
            pass

    async def override_secret():
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[verify_internal_secret] = override_secret
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


PAYLOAD = {
    "stt_job_id": str(uuid.uuid4()),
    "tenant_id": str(uuid.uuid4()),
    "meeting_type": "sales",
    "title": "Q3 Sales Review",
    "full_text": "Speaker A: Let's discuss Q3 results.",
    "segments": [
        {"speaker_label": "SPEAKER_00", "text": "Let's discuss Q3 results.", "start_time": 0.0, "end_time": 3.0}
    ],
    "speaker_mappings": [
        {"speaker_label": "SPEAKER_00", "participant_name": "Tanaka"}
    ],
    "created_by": str(uuid.uuid4()),
}


class TestReceiveMeetingTranscript:
    def test_creates_meeting_minutes(self, client, mock_db):
        """Dispatch creates a new meeting_minutes record with status=raw."""
        # No existing record
        mock_db.query.return_value.filter.return_value.first.return_value = None

        response = client.post("/internal/sales/meeting-transcript", json=PAYLOAD)

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert data["stt_job_id"] == PAYLOAD["stt_job_id"]
        assert "meeting_minutes_id" in data

        # Verify db.add was called
        mock_db.add.assert_called_once()
        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.minutes_status == "raw"
        assert added_obj.stt_job_id == uuid.UUID(PAYLOAD["stt_job_id"])
        assert added_obj.raw_text == PAYLOAD["full_text"]
        assert added_obj.company_name == PAYLOAD["title"]
        mock_db.commit.assert_called_once()

    def test_idempotent_duplicate_dispatch(self, client, mock_db):
        """Duplicate stt_job_id returns existing record without creating new one."""
        existing = MagicMock()
        existing.id = uuid.uuid4()
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        response = client.post("/internal/sales/meeting-transcript", json=PAYLOAD)

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "already_exists"
        assert data["meeting_minutes_id"] == str(existing.id)
        mock_db.add.assert_not_called()

    def test_uses_meeting_type_fallback_title(self, client, mock_db):
        """When title is None, uses meeting_type as company_name."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        payload_no_title = {**PAYLOAD, "title": None}
        response = client.post("/internal/sales/meeting-transcript", json=payload_no_title)

        assert response.status_code == 202
        added_obj = mock_db.add.call_args[0][0]
        assert "sales" in added_obj.company_name

    def test_speaker_names_in_attendees(self, client, mock_db):
        """Speaker participant_names are saved as attendees."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        response = client.post("/internal/sales/meeting-transcript", json=PAYLOAD)

        assert response.status_code == 202
        added_obj = mock_db.add.call_args[0][0]
        assert "Tanaka" in added_obj.attendees
