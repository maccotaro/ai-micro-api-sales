"""
Proposal Chat Service - 商材提案RAGチャットサービス。
媒体ごとにLLM呼び出しを分離し、順次ストリーミングで提案を生成する。
"""
import logging
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, AsyncGenerator
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal

from app.core.config import settings
from app.core.model_settings_client import get_chat_num_ctx
from app.services.llm_client import LLMClient
from app.services.proposal_prompts import MEDIA_PROPOSAL_PROMPT, SUMMARY_PROPOSAL_PROMPT
from app.services.product_data_aggregator import (
    MediaProductData,
    aggregate_product_data,
    build_data_summary,
)

logger = logging.getLogger(__name__)

class ProposalChatService:
    """商材提案チャットサービス（9段階ハイブリッド検索パイプライン使用）"""

    def __init__(self):
        self.llm_client = LLMClient(
            base_url=settings.llm_service_url,
            secret=settings.internal_api_secret,
        )
        # RAGサービス（9段階ハイブリッド検索）
        self.rag_service_url = settings.rag_service_url
        # 管理サービス（フォールバック用）
        self.admin_service_url = settings.admin_service_url

    async def search_products(
        self,
        query: str,
        knowledge_base_id: UUID,
        tenant_id: UUID,
        top_k: int = 10,
        pipeline_version: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """api-ragの9段階ハイブリッド検索パイプラインで商材ドキュメントを検索。"""
        search_url = f"{self.rag_service_url}/internal/search/hybrid"

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                search_json: Dict[str, Any] = {
                    "query": query,
                    "tenant_id": str(tenant_id),
                    "knowledge_base_id": str(knowledge_base_id),
                    "top_k": top_k,
                    "enable_graph": True,  # GraphRAG有効化
                }
                if pipeline_version:
                    search_json["pipeline_version"] = pipeline_version

                response = await client.post(
                    search_url,
                    json=search_json,
                    headers={
                        "X-Internal-Secret": settings.internal_api_secret,
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()

                results = data.get("results") or []
                metrics = data.get("metrics") or {}
                graph_expansion = data.get("graph_expansion") or {}

                logger.info(
                    f"Hybrid search completed: {len(results)} results, "
                    f"total_time={metrics.get('total_time_ms', 0):.0f}ms, "
                    f"graph_products={graph_expansion.get('matched_products', [])}"
                )

                # 結果を統一フォーマットに変換
                formatted_results = []
                for item in results:
                    formatted_results.append({
                        "content": item.get("content") or "",
                        "metadata": item.get("metadata") or {},
                        "score": item.get("final_score") or item.get("cross_encoder_score") or 0.0,
                        "graph_context": item.get("graph_context"),
                    })

                return formatted_results

            except httpx.HTTPError as e:
                logger.error(f"Hybrid search failed: {e}")
                return []

    def extract_media_names(
        self, search_results: List[Dict[str, Any]], db: Optional[Session] = None
    ) -> List[str]:
        """検索結果からmedia_nameを抽出（重複排除、フォールバック付き）。"""
        media_names = set()
        for result in search_results:
            metadata = result.get("metadata") or {}
            media_name = metadata.get("media_name")
            if media_name:
                media_names.add(media_name)
                logger.debug(f"Found media_name: {media_name}")

        if media_names:
            return list(media_names)

        # フォールバック: metadataにmedia_nameがない場合、
        # 検索結果のコンテンツからmedia_pricing上の媒体名を照合
        if not search_results or not db:
            return []

        try:
            result = db.execute(
                text("SELECT DISTINCT media_name FROM media_pricing")
            )
            all_media_names = [row[0] for row in result.fetchall() if row[0]]
        except Exception as e:
            logger.warning(f"Failed to fetch media_names from media_pricing: {e}")
            return []

        if not all_media_names:
            return []

        # 検索結果のコンテンツを結合して媒体名を検索
        combined_content = " ".join(
            (r.get("content") or "") for r in search_results
        )
        for name in all_media_names:
            if name in combined_content:
                media_names.add(name)
                logger.info(f"Fallback: found media_name '{name}' in search content")

        return list(media_names)

    def _build_product_context(self, search_results: List[Dict[str, Any]]) -> str:
        """検索結果から商材コンテキストを構築"""
        if not search_results:
            return "(関連する商材情報が見つかりませんでした)"

        context_parts = []
        for i, result in enumerate(search_results[:5], 1):
            metadata = result.get("metadata") or {}
            filename = metadata.get("filename", metadata.get("original_filename", "不明"))
            media_name = metadata.get("media_name", "未設定")
            content = result.get("content", "")[:500]
            score = result.get("score", 0)

            context_parts.append(
                f"### 商材 {i}: {filename}\n"
                f"- 媒体: {media_name}\n"
                f"- 関連度: {score:.2f}\n"
                f"- 内容:\n{content}\n"
            )

        return "\n".join(context_parts)

    def _build_product_context_for_media(self, search_results: List[Dict[str, Any]], target_media: str) -> str:
        """特定媒体の検索結果のみからコンテキスト構築"""
        filtered = [r for r in search_results if (r.get("metadata") or {}).get("media_name", "") == target_media]
        if not filtered:
            return f"({target_media}に関連する商材情報が見つかりませんでした)"
        return self._build_product_context(filtered)

    def _build_single_media_pricing_context(self, data: MediaProductData) -> str:
        """単一媒体の料金コンテキストを構築"""
        if data.pricing_source == "db":
            lines = [f"データベース: {len(data.pricing_plans)}件"]
            for plan in data.pricing_plans[:15]:
                price_str = f"¥{plan['price']:,.0f}" if plan.get("price") else "要問合せ"
                area_str = plan.get("area") or "全国"
                period_str = f"({plan['listing_period']})" if plan.get("listing_period") else ""
                cat_str = f"[{plan['category']}] " if plan.get("category") else ""
                lines.append(f"- {cat_str}{plan['product_name']}: {price_str} / {area_str} {period_str}")
            return "\n".join(lines)
        elif data.pricing_source == "kb":
            return f"※ 参考情報（KBより）\n{data.kb_pricing_context}"
        else:
            return "(料金情報なし - 要確認)"

    def _build_single_media_publication_context(self, data: MediaProductData) -> str:
        """単一媒体の掲載実績コンテキストを構築"""
        if data.publication_source == "db":
            records = data.publication_records
            lines = [f"データベース: {len(records)}件"]
            for i, rec in enumerate(records[:5], 1):
                job_str = rec.get("job_category_large") or "不明"
                pref_str = rec.get("prefecture") or "不明"
                lines.append(
                    f"事例{i}: {pref_str}/{job_str} "
                    f"PV:{rec.get('pv_count', 0):,} 応募:{rec.get('application_count', 0):,} "
                    f"採用:{rec.get('hire_count', 0):,}"
                )
            if records:
                total = len(records)
                avg_app = sum(r.get("application_count", 0) for r in records) / total
                avg_hire = sum(r.get("hire_count", 0) for r in records) / total
                lines.append(f"集計: {total}件平均 応募:{avg_app:.1f} 採用:{avg_hire:.1f}")
            return "\n".join(lines)
        elif data.publication_source == "kb":
            return f"※ 参考情報（KBより）\n{data.kb_publication_context}"
        else:
            return "(掲載実績なし)"

    async def _stream_single_media_proposal(
        self,
        media_name: str,
        data: MediaProductData,
        query: str,
        search_results: List[Dict[str, Any]],
        model: Optional[str] = None,
        provider_options: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        """単一媒体の提案をストリーミング生成。最後に media_proposal_text イベントで全文送信。"""
        # 該当媒体の検索結果のみをコンテキストに使用
        media_product_context = self._build_product_context_for_media(search_results, media_name)
        system_prompt = MEDIA_PROPOSAL_PROMPT.format(
            media_name=media_name,
            query_context=query,
            product_context=media_product_context,
            media_pricing_context=self._build_single_media_pricing_context(data),
            media_publication_context=self._build_single_media_publication_context(data),
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]

        full_text = ""
        async for chunk in self.llm_client.chat_stream(
            messages=messages,
            service_name="api-sales",
            model=model,
            temperature=0.5,
            provider_options=provider_options,
        ):
            token = chunk.get("token", "")
            chunk_type = chunk.get("type", "content")
            if token:
                if chunk_type == "content":
                    full_text += token
                yield f"data: {json.dumps({'type': chunk_type, 'content': token})}\n\n"

        # 提案テキスト全体を内部イベントとしてyield（総合提案用）
        yield f"data: {json.dumps({'type': 'media_proposal_text', 'media_name': media_name, 'text': full_text})}\n\n"

    async def stream_proposal(
        self,
        query: str,
        knowledge_base_id: UUID,
        tenant_id: UUID,
        db: Session,
        area: Optional[str] = None,
        pipeline_version: Optional[str] = None,
        model: Optional[str] = None,
        think: Optional[bool] = None,
        prefecture: Optional[str] = None,
        job_category: Optional[str] = None,
        employment_type: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """商材提案をストリーミング生成（媒体別LLM呼び出し分離版）。"""
        try:
            # Send start event
            yield f"data: {json.dumps({'type': 'start', 'status': 'searching'})}\n\n"

            # Step 1: 9段階ハイブリッド検索（GraphRAG含む）
            search_results = await self.search_products(
                query=query,
                knowledge_base_id=knowledge_base_id,
                tenant_id=tenant_id,
                top_k=10,
                pipeline_version=pipeline_version,
            )

            if not search_results:
                yield f"data: {json.dumps({'type': 'info', 'message': '関連する商材が見つかりませんでした'})}\n\n"

            # Step 2: media_name抽出
            own_db = SessionLocal()
            try:
                media_names = self.extract_media_names(search_results, own_db)
                logger.info(f"Extracted media_names: {media_names}")

                yield f"data: {json.dumps({'type': 'info', 'message': f'{len(search_results)}件の商材情報を検索', 'media_names': media_names})}\n\n"

                # Step 3: 媒体別データ集約（DB料金+DB実績+KBフォールバック）
                media_data = await aggregate_product_data(
                    own_db, media_names, knowledge_base_id,
                    tenant_id, area, prefecture,
                    job_category, employment_type,
                )
            finally:
                own_db.close()

            # SSE info: 媒体別サマリー送信
            summary = build_data_summary(media_data)
            yield f"data: {json.dumps({'type': 'info', 'message': summary, 'status': 'generating'})}\n\n"

            provider_options: Dict[str, Any] = {"num_ctx": get_chat_num_ctx()}
            if think is not None:
                provider_options["think"] = think

            # Step 4: 媒体別LLM呼び出し（順次ストリーミング）
            media_proposals: Dict[str, str] = {}
            total_media = len(media_data)

            for idx, (media_name, data) in enumerate(media_data.items(), 1):
                # 媒体開始イベント送信
                yield f"data: {json.dumps({'type': 'media_start', 'media_name': media_name, 'index': idx, 'total': total_media})}\n\n"

                # 単一媒体の提案ストリーミング（媒体別にフィルタした検索結果を使用）
                async for chunk in self._stream_single_media_proposal(
                    media_name=media_name,
                    data=data,
                    query=query,
                    search_results=search_results,
                    model=model,
                    provider_options=provider_options,
                ):
                    # media_proposal_text は内部用 → 提案テキスト収集
                    if '"type": "media_proposal_text"' in chunk:
                        try:
                            event_data = json.loads(chunk.replace("data: ", "").strip())
                            media_proposals[event_data["media_name"]] = event_data["text"]
                        except (json.JSONDecodeError, KeyError):
                            pass
                        continue  # フロントには送信しない
                    yield chunk

            # Step 6: 総合提案（2媒体以上の場合のみ）
            if len(media_proposals) >= 2:
                yield f"data: {json.dumps({'type': 'media_start', 'media_name': '総合比較・推薦', 'index': total_media + 1, 'total': total_media + 1})}\n\n"

                all_media_text = ""
                for name, proposal_text in media_proposals.items():
                    all_media_text += f"## {name}\n{proposal_text}\n\n"

                summary_prompt = SUMMARY_PROPOSAL_PROMPT.format(
                    media_names_list=", ".join(media_proposals.keys()),
                    all_media_proposals=all_media_text,
                )

                messages = [
                    {"role": "system", "content": summary_prompt},
                    {"role": "user", "content": query},
                ]

                async for chunk in self.llm_client.chat_stream(
                    messages=messages,
                    service_name="api-sales",
                    model=model,
                    temperature=0.5,
                    provider_options=provider_options,
                ):
                    token = chunk.get("token", "")
                    chunk_type = chunk.get("type", "content")
                    if token:
                        yield f"data: {json.dumps({'type': chunk_type, 'content': token})}\n\n"

            # Send completion event with metadata
            media_summary = {
                name: {
                    "pricing_source": d.pricing_source,
                    "pricing_count": len(d.pricing_plans),
                    "publication_source": d.publication_source,
                    "publication_count": len(d.publication_records),
                }
                for name, d in media_data.items()
            }
            yield f"data: {json.dumps({'type': 'done', 'media_names': media_names, 'total_products': len(search_results), 'media_summary': media_summary})}\n\n"

        except Exception as e:
            logger.error(f"Proposal generation error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    async def generate_proposal(
        self,
        query: str,
        knowledge_base_id: UUID,
        tenant_id: UUID,
        db: Session,
        area: Optional[str] = None,
        pipeline_version: Optional[str] = None,
        model: Optional[str] = None,
        think: Optional[bool] = None,
        prefecture: Optional[str] = None,
        job_category: Optional[str] = None,
        employment_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """商材提案を生成（非ストリーミング、媒体別LLM呼び出し分離版）。"""
        # Step 1: 9段階ハイブリッド検索（GraphRAG含む）
        search_results = await self.search_products(
            query=query,
            knowledge_base_id=knowledge_base_id,
            tenant_id=tenant_id,
            pipeline_version=pipeline_version,
        )

        # Step 2: media_name抽出（フォールバック付き）
        media_names = self.extract_media_names(search_results, db)

        # Step 3: 媒体別データ集約（DB料金+DB実績+KBフォールバック）
        media_data = await aggregate_product_data(
            db, media_names, knowledge_base_id,
            tenant_id, area, prefecture,
            job_category, employment_type,
        )

        provider_options = None
        if think is not None:
            provider_options = {"think": think}

        # Step 4: 媒体別LLM呼び出し（順次実行）
        media_proposals: Dict[str, str] = {}
        for media_name, data in media_data.items():
            media_product_context = self._build_product_context_for_media(search_results, media_name)
            system_prompt = MEDIA_PROPOSAL_PROMPT.format(
                media_name=media_name,
                query_context=query,
                product_context=media_product_context,
                media_pricing_context=self._build_single_media_pricing_context(data),
                media_publication_context=self._build_single_media_publication_context(data),
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ]

            result = await self.llm_client.chat(
                messages=messages,
                service_name="api-sales",
                model=model,
                temperature=0.5,
                provider_options=provider_options,
            )
            media_proposals[media_name] = result.get("response", "")

        # Step 6: 総合提案（2媒体以上の場合のみ）
        combined_proposal = ""
        for name, proposal_text in media_proposals.items():
            combined_proposal += f"## {name}\n{proposal_text}\n\n"

        if len(media_proposals) >= 2:
            all_media_text = ""
            for name, proposal_text in media_proposals.items():
                all_media_text += f"## {name}\n{proposal_text}\n\n"

            summary_prompt = SUMMARY_PROPOSAL_PROMPT.format(
                media_names_list=", ".join(media_proposals.keys()),
                all_media_proposals=all_media_text,
            )

            messages = [
                {"role": "system", "content": summary_prompt},
                {"role": "user", "content": query},
            ]

            summary_result = await self.llm_client.chat(
                messages=messages,
                service_name="api-sales",
                model=model,
                temperature=0.5,
                provider_options=provider_options,
            )
            combined_proposal += f"## 総合比較・推薦\n{summary_result.get('response', '')}\n"

        return {
            "proposal": combined_proposal,
            "media_names": media_names,
            "search_results": search_results,
            "media_data": {
                name: {
                    "pricing_source": d.pricing_source,
                    "pricing_count": len(d.pricing_plans),
                    "publication_source": d.publication_source,
                    "publication_count": len(d.publication_records),
                }
                for name, d in media_data.items()
            },
            "generated_at": datetime.utcnow().isoformat(),
        }

# Singleton instance
proposal_chat_service = ProposalChatService()
