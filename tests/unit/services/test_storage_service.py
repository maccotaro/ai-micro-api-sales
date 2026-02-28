# ai-micro-api-sales/tests/unit/services/test_storage_service.py
"""
Unit tests for app.services.storage_service module.

Tests:
- StorageService._object_key generation
- StorageService.ensure_bucket (existing / new)
- StorageService.upload_bytes
- StorageService.download_bytes
- StorageService.delete_object
- get_storage_service singleton (enabled / disabled)
"""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# =============================================================================
# _object_key Tests
# =============================================================================


@pytest.mark.unit
class TestObjectKey:
    """Tests for StorageService._object_key."""

    def test_default_filename(self):
        with patch("app.services.storage_service.settings") as mock_settings:
            mock_settings.minio_enabled = True
            mock_settings.minio_endpoint = "http://localhost:9000"
            mock_settings.minio_access_key = "key"
            mock_settings.minio_secret_key = "secret"
            mock_settings.minio_bucket = "documents"
            mock_settings.minio_presentations_prefix = "presentations"

            from app.services.storage_service import StorageService
            service = StorageService()
            key = service._object_key("tenant-abc", "run-123")
            assert key == "presentations/tenant-abc/run-123/proposal.pptx"

    def test_custom_filename(self):
        with patch("app.services.storage_service.settings") as mock_settings:
            mock_settings.minio_enabled = True
            mock_settings.minio_endpoint = "http://localhost:9000"
            mock_settings.minio_access_key = "key"
            mock_settings.minio_secret_key = "secret"
            mock_settings.minio_bucket = "documents"
            mock_settings.minio_presentations_prefix = "presentations"

            from app.services.storage_service import StorageService
            service = StorageService()
            key = service._object_key("t1", "r1", "custom.pdf")
            assert key == "presentations/t1/r1/custom.pdf"

    def test_custom_prefix(self):
        with patch("app.services.storage_service.settings") as mock_settings:
            mock_settings.minio_enabled = True
            mock_settings.minio_endpoint = "http://localhost:9000"
            mock_settings.minio_access_key = "key"
            mock_settings.minio_secret_key = "secret"
            mock_settings.minio_bucket = "documents"
            mock_settings.minio_presentations_prefix = "files"

            from app.services.storage_service import StorageService
            service = StorageService()
            key = service._object_key("t1", "r1")
            assert key == "files/t1/r1/proposal.pptx"


# =============================================================================
# ensure_bucket Tests
# =============================================================================


@pytest.mark.unit
class TestEnsureBucket:
    """Tests for StorageService.ensure_bucket."""

    @pytest.mark.asyncio
    async def test_bucket_exists(self):
        with patch("app.services.storage_service.settings") as mock_settings:
            mock_settings.minio_enabled = True
            mock_settings.minio_endpoint = "http://localhost:9000"
            mock_settings.minio_access_key = "key"
            mock_settings.minio_secret_key = "secret"
            mock_settings.minio_bucket = "documents"
            mock_settings.minio_presentations_prefix = "presentations"

            from app.services.storage_service import StorageService
            service = StorageService()

            mock_client = AsyncMock()
            mock_client.head_bucket = AsyncMock()

            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            service._client = MagicMock(return_value=mock_cm)

            await service.ensure_bucket()
            mock_client.head_bucket.assert_called_once_with(Bucket="documents")
            mock_client.create_bucket.assert_not_called()

    @pytest.mark.asyncio
    async def test_bucket_created_when_missing(self):
        with patch("app.services.storage_service.settings") as mock_settings:
            mock_settings.minio_enabled = True
            mock_settings.minio_endpoint = "http://localhost:9000"
            mock_settings.minio_access_key = "key"
            mock_settings.minio_secret_key = "secret"
            mock_settings.minio_bucket = "documents"
            mock_settings.minio_presentations_prefix = "presentations"

            from app.services.storage_service import StorageService
            service = StorageService()

            mock_client = AsyncMock()
            mock_client.head_bucket = AsyncMock(side_effect=Exception("Not Found"))
            mock_client.create_bucket = AsyncMock()

            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            service._client = MagicMock(return_value=mock_cm)

            await service.ensure_bucket()
            mock_client.create_bucket.assert_called_once_with(Bucket="documents")


# =============================================================================
# upload_bytes Tests
# =============================================================================


@pytest.mark.unit
class TestUploadBytes:
    """Tests for StorageService.upload_bytes."""

    @pytest.mark.asyncio
    async def test_upload_returns_key(self):
        with patch("app.services.storage_service.settings") as mock_settings:
            mock_settings.minio_enabled = True
            mock_settings.minio_endpoint = "http://localhost:9000"
            mock_settings.minio_access_key = "key"
            mock_settings.minio_secret_key = "secret"
            mock_settings.minio_bucket = "test-bucket"
            mock_settings.minio_presentations_prefix = "presentations"

            from app.services.storage_service import StorageService
            service = StorageService()

            mock_client = AsyncMock()
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            service._client = MagicMock(return_value=mock_cm)

            data = b"fake pptx content"
            key = await service.upload_bytes(data, "tenant-1", "run-1")

            assert key == "presentations/tenant-1/run-1/proposal.pptx"
            mock_client.put_object.assert_called_once_with(
                Bucket="test-bucket",
                Key="presentations/tenant-1/run-1/proposal.pptx",
                Body=data,
                ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )

    @pytest.mark.asyncio
    async def test_upload_custom_filename(self):
        with patch("app.services.storage_service.settings") as mock_settings:
            mock_settings.minio_enabled = True
            mock_settings.minio_endpoint = "http://localhost:9000"
            mock_settings.minio_access_key = "key"
            mock_settings.minio_secret_key = "secret"
            mock_settings.minio_bucket = "test-bucket"
            mock_settings.minio_presentations_prefix = "presentations"

            from app.services.storage_service import StorageService
            service = StorageService()

            mock_client = AsyncMock()
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            service._client = MagicMock(return_value=mock_cm)

            key = await service.upload_bytes(
                b"pdf data", "t1", "r1",
                filename="report.pdf",
                content_type="application/pdf",
            )
            assert key == "presentations/t1/r1/report.pdf"
            call_kwargs = mock_client.put_object.call_args.kwargs
            assert call_kwargs["ContentType"] == "application/pdf"


# =============================================================================
# download_bytes Tests
# =============================================================================


@pytest.mark.unit
class TestDownloadBytes:
    """Tests for StorageService.download_bytes."""

    @pytest.mark.asyncio
    async def test_download_returns_bytes(self):
        with patch("app.services.storage_service.settings") as mock_settings:
            mock_settings.minio_enabled = True
            mock_settings.minio_endpoint = "http://localhost:9000"
            mock_settings.minio_access_key = "key"
            mock_settings.minio_secret_key = "secret"
            mock_settings.minio_bucket = "docs"
            mock_settings.minio_presentations_prefix = "presentations"

            from app.services.storage_service import StorageService
            service = StorageService()

            expected_data = b"downloaded content"
            mock_body = AsyncMock()
            mock_body.read = AsyncMock(return_value=expected_data)

            mock_client = AsyncMock()
            mock_client.get_object = AsyncMock(return_value={
                "Body": mock_body,
                "ContentLength": len(expected_data),
            })

            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            service._client = MagicMock(return_value=mock_cm)

            result = await service.download_bytes("presentations/t1/r1/proposal.pptx")
            assert result == expected_data
            mock_client.get_object.assert_called_once_with(
                Bucket="docs",
                Key="presentations/t1/r1/proposal.pptx",
            )


# =============================================================================
# delete_object Tests
# =============================================================================


@pytest.mark.unit
class TestDeleteObject:
    """Tests for StorageService.delete_object."""

    @pytest.mark.asyncio
    async def test_delete_calls_client(self):
        with patch("app.services.storage_service.settings") as mock_settings:
            mock_settings.minio_enabled = True
            mock_settings.minio_endpoint = "http://localhost:9000"
            mock_settings.minio_access_key = "key"
            mock_settings.minio_secret_key = "secret"
            mock_settings.minio_bucket = "docs"
            mock_settings.minio_presentations_prefix = "presentations"

            from app.services.storage_service import StorageService
            service = StorageService()

            mock_client = AsyncMock()
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            service._client = MagicMock(return_value=mock_cm)

            await service.delete_object("presentations/t1/r1/proposal.pptx")
            mock_client.delete_object.assert_called_once_with(
                Bucket="docs",
                Key="presentations/t1/r1/proposal.pptx",
            )


# =============================================================================
# get_storage_service Tests
# =============================================================================


@pytest.mark.unit
class TestGetStorageService:
    """Tests for get_storage_service singleton."""

    def test_returns_none_when_disabled(self):
        with patch("app.services.storage_service.settings") as mock_settings:
            mock_settings.minio_enabled = False

            import app.services.storage_service as mod
            mod._storage_service = None  # reset singleton

            result = mod.get_storage_service()
            assert result is None

    def test_returns_instance_when_enabled(self):
        with patch("app.services.storage_service.settings") as mock_settings:
            mock_settings.minio_enabled = True
            mock_settings.minio_endpoint = "http://localhost:9000"
            mock_settings.minio_access_key = "key"
            mock_settings.minio_secret_key = "secret"
            mock_settings.minio_bucket = "docs"
            mock_settings.minio_presentations_prefix = "presentations"

            import app.services.storage_service as mod
            mod._storage_service = None  # reset singleton

            result = mod.get_storage_service()
            assert result is not None

            # Calling again returns same instance
            result2 = mod.get_storage_service()
            assert result is result2

            # Cleanup
            mod._storage_service = None
