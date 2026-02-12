"""
LLM Service Client - Shared client for api-llm service.

Copy this file into each service that needs to call api-llm:
  - ai-micro-celery-llm/app/services/llm_client.py
  - ai-micro-api-rag/app/services/llm_client.py
  - ai-micro-api-admin/app/services/llm_client.py
  - ai-micro-api-sales/app/services/llm_client.py

Usage (async):
    client = LLMClient(base_url="http://host.docker.internal:8012", secret="change-me")
    result = await client.generate(prompt="Hello", task_type="summary", service_name="api-rag")
    async for token in client.chat_stream(messages=[{"role": "user", "content": "Hi"}], service_name="api-admin"):
        print(token, end="")

Usage (sync, for Celery workers):
    client = LLMClient(base_url="http://host.docker.internal:8012", secret="change-me")
    result = client.generate_sync(prompt="Hello", task_type="summary", service_name="celery-llm")
"""

import json
import logging
from typing import Any, AsyncIterator, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 120.0
STREAM_TIMEOUT = 300.0


class LLMClient:
    """Client for the centralized LLM service (api-llm)."""

    def __init__(
        self,
        base_url: str,
        secret: str,
        timeout: float = DEFAULT_TIMEOUT,
        stream_timeout: float = STREAM_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.secret = secret
        self.timeout = timeout
        self.stream_timeout = stream_timeout

    def _headers(self) -> dict[str, str]:
        return {
            "X-Internal-Secret": self.secret,
            "Content-Type": "application/json",
        }

    # -------------------------------------------------------------------------
    # Async methods (for FastAPI services: api-rag, api-admin, api-sales)
    # -------------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        task_type: str,
        service_name: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        format: Optional[str] = None,
        provider_options: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """Non-streaming generate call. Returns {"response": str, "model": str, "total_tokens": int}."""
        payload: dict[str, Any] = {
            "service_name": service_name,
            "task_type": task_type,
            "prompt": prompt,
            "temperature": temperature,
            "stream": False,
        }
        if model:
            payload["model"] = model
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if format:
            payload["format"] = format
        if provider_options:
            payload["provider_options"] = provider_options

        async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/llm/generate",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def chat(
        self,
        messages: list[dict[str, str]],
        service_name: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        provider_options: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """Non-streaming chat call. Returns {"response": str, "model": str, "total_tokens": int}."""
        payload: dict[str, Any] = {
            "service_name": service_name,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if model:
            payload["model"] = model
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if provider_options:
            payload["provider_options"] = provider_options

        async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/llm/chat",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        service_name: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        provider_options: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> AsyncIterator[str]:
        """Streaming chat call. Yields token strings from SSE stream."""
        payload: dict[str, Any] = {
            "service_name": service_name,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if model:
            payload["model"] = model
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if provider_options:
            payload["provider_options"] = provider_options

        async with httpx.AsyncClient(timeout=timeout or self.stream_timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/llm/chat",
                headers=self._headers(),
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = json.loads(line[6:])
                    if data.get("done"):
                        break
                    token = data.get("token", "")
                    if token:
                        yield token

    async def list_models(self) -> list[dict]:
        """Get available models. Returns list of model info dicts."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self.base_url}/llm/models",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json().get("models", [])

    # -------------------------------------------------------------------------
    # Sync methods (for Celery workers: celery-llm)
    # -------------------------------------------------------------------------

    def generate_sync(
        self,
        prompt: str,
        task_type: str,
        service_name: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        format: Optional[str] = None,
        provider_options: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """Synchronous generate call for Celery workers. Returns {"response": str, "model": str, "total_tokens": int}."""
        payload: dict[str, Any] = {
            "service_name": service_name,
            "task_type": task_type,
            "prompt": prompt,
            "temperature": temperature,
            "stream": False,
        }
        if model:
            payload["model"] = model
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if format:
            payload["format"] = format
        if provider_options:
            payload["provider_options"] = provider_options

        with httpx.Client(timeout=timeout or self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/llm/generate",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    def chat_sync(
        self,
        messages: list[dict[str, str]],
        service_name: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        provider_options: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """Synchronous chat call for Celery workers. Returns {"response": str, "model": str, "total_tokens": int}."""
        payload: dict[str, Any] = {
            "service_name": service_name,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if model:
            payload["model"] = model
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if provider_options:
            payload["provider_options"] = provider_options

        with httpx.Client(timeout=timeout or self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/llm/chat",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()
