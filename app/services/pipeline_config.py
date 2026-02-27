"""Pipeline configuration fetcher with Redis cache (TTL 300s)."""
import json
import logging
from typing import Optional
from uuid import UUID

import httpx
import redis
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # 5 minutes
CACHE_PREFIX = "proposal_pipeline_config"


class StageConfig(BaseModel):
    enabled: bool = True
    name: str = ""
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    prompt_override: Optional[str] = None
    use_simulation: Optional[bool] = None
    use_wage_data: Optional[bool] = None
    generate_catchcopy: Optional[bool] = None
    catchcopy_count: Optional[int] = None


class KBMappingCategory(BaseModel):
    knowledge_base_ids: list[str] = Field(default_factory=list)
    used_in_stages: list[int] = Field(default_factory=list)
    search_query_template: str = ""
    max_chunks: int = 10


class OutputSection(BaseModel):
    id: str = ""
    title: str = ""
    stage: int = 0
    required: bool = True
    description: str = ""


class OutputTemplate(BaseModel):
    sections: list[OutputSection] = Field(default_factory=list)
    format: str = "markdown"
    locale: str = "ja"


class PipelineConfigData(BaseModel):
    """Parsed pipeline configuration from api-admin."""
    enabled: bool = True
    pipeline_name: str = "次回商談提案書"
    stage_config: dict[str, StageConfig] = Field(default_factory=dict)
    kb_mapping: dict[str, KBMappingCategory] = Field(default_factory=dict)
    output_template: OutputTemplate = Field(default_factory=OutputTemplate)
    is_default: bool = False

    def get_stage(self, stage_num: int) -> StageConfig:
        """Get config for a specific stage."""
        key = f"stage_{stage_num}"
        return self.stage_config.get(key, StageConfig(name=f"Stage {stage_num}"))

    def get_kb_categories_for_stage(self, stage_num: int) -> dict[str, KBMappingCategory]:
        """Get KB categories that apply to a specific stage."""
        return {
            name: cat
            for name, cat in self.kb_mapping.items()
            if stage_num in cat.used_in_stages
        }


def _get_redis() -> Optional[redis.Redis]:
    """Get Redis client, returning None on failure."""
    try:
        return redis.from_url(settings.redis_url, decode_responses=True)
    except Exception as e:
        logger.warning("Redis unavailable: %s", e)
        return None


async def fetch_pipeline_config(tenant_id: UUID) -> PipelineConfigData:
    """Fetch pipeline config with Redis cache (TTL 300s).

    1. Check Redis cache
    2. On miss, call api-admin internal API
    3. Store in cache
    """
    cache_key = f"{CACHE_PREFIX}:{tenant_id}"

    # Try cache first
    r = _get_redis()
    if r:
        try:
            cached = r.get(cache_key)
            if cached:
                logger.debug("Pipeline config cache hit: %s", cache_key)
                return PipelineConfigData(**json.loads(cached))
        except Exception as e:
            logger.warning("Cache read error: %s", e)

    # Fetch from api-admin internal API
    admin_url = settings.admin_internal_url
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{admin_url}/internal/proposal-pipeline/config",
                params={"tenant_id": str(tenant_id)},
                headers={"X-Internal-Secret": settings.internal_api_secret},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error("Failed to fetch pipeline config from api-admin: %s", e)
        # Return empty defaults
        return PipelineConfigData()

    # Parse stage_config
    stage_config = {}
    for key, val in (data.get("stage_config") or {}).items():
        stage_config[key] = StageConfig(**val) if isinstance(val, dict) else val

    # Parse kb_mapping
    kb_mapping = {}
    for key, val in (data.get("kb_mapping") or {}).items():
        kb_mapping[key] = KBMappingCategory(**val) if isinstance(val, dict) else val

    # Parse output_template
    output_template = OutputTemplate(**(data.get("output_template") or {}))

    config = PipelineConfigData(
        enabled=data.get("enabled", True),
        pipeline_name=data.get("pipeline_name", "次回商談提案書"),
        stage_config=stage_config,
        kb_mapping=kb_mapping,
        output_template=output_template,
        is_default=data.get("is_default", False),
    )

    # Store in cache
    if r:
        try:
            r.setex(cache_key, CACHE_TTL, config.model_dump_json())
            logger.debug("Pipeline config cached: %s", cache_key)
        except Exception as e:
            logger.warning("Cache write error: %s", e)

    return config
