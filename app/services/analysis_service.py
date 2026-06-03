"""
Meeting Minutes Lightweight Extraction Service

業種/地域の軽量抽出など、議事録に対する軽量なLLM補助を提供する。

注: 旧「AI解析」(analyze_meeting による issues/needs/summary の parsed_json 生成) は廃止した。
議事録の構造化は celery-llm `parse_meeting_minutes`（12セクション）が単一スキーマで担い、
知識グラフへのエンティティ登録（グラフ連携）は parse 完了時に celery-llm 側で自動起動する。
"""
import logging
import json
from typing import Optional, Dict, Any, List

from app.core.config import settings
from app.core.model_settings_client import get_chat_num_ctx
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


EXTRACTION_PROMPT = """以下の議事録テキストから、顧客企業の「業種」と「地域」を推定してください。
JSONのみ出力し、他の説明は不要です。

会社名: {company_name}
テキスト（冒頭部分）:
{raw_text}

出力形式:
{{"industry": "業種（例: IT, 飲食, フィットネス, 製造, 不動産, 医療等）またはnull", "area": "地域（例: 東京, 関東, 大阪, 関西等）またはnull"}}
"""


class AnalysisService:
    """Lightweight meeting minutes extraction helpers using LLM."""

    def __init__(self):
        self.llm_client = LLMClient(
            base_url=settings.llm_service_url,
            secret=settings.internal_api_secret,
        )

    async def extract_industry_area(
        self, raw_text: str, company_name: str
    ) -> Dict[str, Optional[str]]:
        """Extract industry and area from meeting text using a lightweight LLM call.

        Returns {"industry": str|None, "area": str|None}.
        Never raises; returns nulls on failure.
        """
        try:
            prompt = EXTRACTION_PROMPT.format(
                company_name=company_name,
                raw_text=raw_text[:3000],
            )
            result = await self.llm_client.generate(
                prompt=prompt,
                task_type="extraction",
                service_name="api-sales",
                temperature=0.1,
                max_tokens=500,
                format="json",
            )
            response = result.get("response", "")
            data = self._parse_json_response(response)
            industry = data.get("industry")
            area = data.get("area")
            # Treat literal "null" string as None
            if isinstance(industry, str) and industry.lower() in ("null", "none", "不明", ""):
                industry = None
            if isinstance(area, str) and area.lower() in ("null", "none", "不明", ""):
                area = None
            # Enforce max_length=100
            if industry and len(industry) > 100:
                industry = industry[:100]
            if area and len(area) > 100:
                area = area[:100]
            return {"industry": industry, "area": area}
        except Exception as e:
            logger.warning(f"Failed to extract industry/area: {e}")
            return {"industry": None, "area": None}

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse a JSON response from LLM, handling common formatting issues."""
        import re

        response = response.strip()
        # Strip markdown code blocks
        code_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response, re.DOTALL | re.IGNORECASE)
        if code_match:
            response = code_match.group(1).strip()

        # Try direct parse
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                # Fix trailing commas and single quotes
                fixed = re.sub(r',\s*([}\]])', r'\1', json_match.group(0))
                fixed = fixed.replace("'", '"')
                try:
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass

        return {}

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM via api-llm and return response."""
        try:
            result = await self.llm_client.generate(
                prompt=prompt,
                task_type="analysis",
                service_name="api-sales",
                temperature=0.3,
                provider_options={"num_ctx": get_chat_num_ctx()},
            )
            return result.get("response", "")
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    async def extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text."""
        prompt = f"""以下のテキストから重要なキーワードを10個以内で抽出してください。
カンマ区切りで出力してください。

テキスト:
{text[:5000]}

キーワード:"""

        response = await self._call_llm(prompt)
        keywords = [k.strip() for k in response.split(",") if k.strip()]
        return keywords[:10]

    async def summarize_text(self, text: str, max_length: int = 500) -> str:
        """Summarize text."""
        prompt = f"""以下のテキストを{max_length}文字以内で要約してください。

テキスト:
{text[:10000]}

要約:"""

        response = await self._call_llm(prompt)
        return response[:max_length]
