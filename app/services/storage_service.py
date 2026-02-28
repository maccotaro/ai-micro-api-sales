"""Async MinIO storage service for presentation file persistence."""

import logging
from io import BytesIO
from typing import AsyncIterator, Optional

import aioboto3
from botocore.config import Config as BotoConfig

from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """Async S3-compatible storage client for MinIO."""

    def __init__(self) -> None:
        self._session = aioboto3.Session()
        self._endpoint = settings.minio_endpoint
        self._access_key = settings.minio_access_key
        self._secret_key = settings.minio_secret_key
        self._bucket = settings.minio_bucket
        self._prefix = settings.minio_presentations_prefix

    def _client(self):
        """Create an async S3 client context manager."""
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            config=BotoConfig(signature_version="s3v4"),
        )

    async def ensure_bucket(self) -> None:
        """Ensure the target bucket exists."""
        async with self._client() as client:
            try:
                await client.head_bucket(Bucket=self._bucket)
                logger.info(f"Bucket '{self._bucket}' exists")
            except Exception:
                logger.info(f"Creating bucket '{self._bucket}'")
                await client.create_bucket(Bucket=self._bucket)

    def _object_key(self, tenant_id: str, run_id: str, filename: str = "proposal.pptx") -> str:
        """Build the object key: presentations/{tenant_id}/{run_id}/proposal.pptx"""
        return f"{self._prefix}/{tenant_id}/{run_id}/{filename}"

    async def upload_bytes(
        self,
        data: bytes,
        tenant_id: str,
        run_id: str,
        filename: str = "proposal.pptx",
        content_type: str = "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ) -> str:
        """Upload bytes to MinIO. Returns the object key."""
        key = self._object_key(tenant_id, run_id, filename)
        async with self._client() as client:
            await client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        logger.info(f"Uploaded {len(data)} bytes to {self._bucket}/{key}")
        return key

    async def download_stream(self, object_key: str) -> tuple[AsyncIterator[bytes], int]:
        """Download object as an async byte stream. Returns (stream, content_length)."""
        async with self._client() as client:
            response = await client.get_object(Bucket=self._bucket, Key=object_key)
            content_length = response["ContentLength"]
            body = await response["Body"].read()
            return body, content_length

    async def download_bytes(self, object_key: str) -> bytes:
        """Download object as bytes."""
        async with self._client() as client:
            response = await client.get_object(Bucket=self._bucket, Key=object_key)
            return await response["Body"].read()

    async def delete_object(self, object_key: str) -> None:
        """Delete an object from MinIO."""
        async with self._client() as client:
            await client.delete_object(Bucket=self._bucket, Key=object_key)
        logger.info(f"Deleted {self._bucket}/{object_key}")


# Singleton
_storage_service: Optional[StorageService] = None


def get_storage_service() -> Optional[StorageService]:
    """Get storage service singleton. Returns None if MinIO is disabled."""
    global _storage_service
    if not settings.minio_enabled:
        return None
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
