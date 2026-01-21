"""
Proposal Chat Service

商材提案RAGシステムのチャットサービス。
議事録/顧客要件を入力として、RAG検索→料金取得→提案生成のフローを実行する。

【重要】このサービスはapi-ragの9段階ハイブリッド検索パイプラインを使用します。
これにより、front-adminと同一の検索ロジック（GraphRAG、BM25、Cross-Encoder等）が
適用されます。
"""
import logging
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, AsyncGenerator
from decimal import Decimal
from uuid import UUID

import httpx
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)


# 商材提案用システムプロンプト
PROPOSAL_SYSTEM_PROMPT = """あなたは営業支援AIアシスタントです。顧客の要件に基づいて最適な商材を提案してください。

## あなたの役割
1. 顧客の課題・ニーズを理解する
2. 適切な商材を推薦する
3. 【重要】下記の「料金情報」セクションから具体的な金額を必ず提示する
4. 提案書のドラフトを作成する

## 利用可能な商材名（正式名称）
{media_names_list}

【重要】商材名は上記の正式名称を必ず使用してください。略称や誤記は使用しないでください。

## 検索された商材情報
{product_context}

## 料金情報（必ずこの金額を提案に含めること）
{pricing_context}

## 回答形式
以下の形式で回答してください：

### 推奨商材
（商材名と推奨理由）

### 料金プラン
（**必ず上記「料金情報」セクションの具体的な金額を記載**）
例：
- 商品名: ¥XXX,XXX（エリア）

### 提案理由
（なぜこの商材が顧客に適しているか）

## 指示
- 顧客の要件に最も適した商材を推薦してください
- 商材名は「利用可能な商材名」に記載された正式名称を使用してください
- 【最重要】「料金情報」セクションに記載された具体的な金額（¥で始まる数字）を必ず提案に含めてください
- 提案理由を明確に説明してください
- 日本語で回答してください
- 不明な点がある場合は追加質問してください
"""


class ProposalChatService:
    """商材提案チャットサービス

    9段階ハイブリッド検索パイプラインを使用して商材検索を実行します。
    - Stage 0: Graph Query Expansion（GraphRAG）
    - Stage 1-7: Atlas、Sparse、Dense、RRF、BM25、Cross-Encoder
    - Stage 8: Graph Context Enrichment
    """

    def __init__(self):
        self.llm = ChatOllama(
            model=settings.default_llm_model,
            base_url=settings.ollama_base_url,
            temperature=0.5,
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
        jwt_token: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        api-ragの9段階ハイブリッド検索パイプラインで商材ドキュメントを検索。

        9段階パイプライン:
        - Stage 0: Graph Query Expansion（GraphRAG）
        - Stage 1: Atlas層フィルタリング
        - Stage 2: メタデータフィルタ構築
        - Stage 3: Sparse検索（BM25）
        - Stage 4: Dense検索（ベクトル）
        - Stage 5: RRFマージ + Graph Boost
        - Stage 6: BM25 Re-ranker
        - Stage 7: Cross-Encoder Re-ranker
        - Stage 8: Graph Context Enrichment

        Args:
            query: 検索クエリ
            knowledge_base_id: ナレッジベースID
            tenant_id: テナントID
            jwt_token: 認証トークン
            top_k: 取得件数

        Returns:
            List[Dict]: 検索結果（content, metadata, score, graph_context等）
        """
        search_url = f"{self.rag_service_url}/api/rag/search/hybrid"

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    search_url,
                    json={
                        "query": query,
                        "tenant_id": str(tenant_id),
                        "knowledge_base_id": str(knowledge_base_id),
                        "top_k": top_k,
                        "enable_graph": True,  # GraphRAG有効化
                    },
                    headers={
                        "Authorization": f"Bearer {jwt_token}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()

                results = data.get("results", [])
                metrics = data.get("metrics", {})
                graph_expansion = data.get("graph_expansion", {})

                logger.info(
                    f"Hybrid search completed: {len(results)} results, "
                    f"total_time={metrics.get('total_time_ms', 0):.0f}ms, "
                    f"graph_products={graph_expansion.get('matched_products', [])}"
                )

                # 結果を統一フォーマットに変換
                formatted_results = []
                for item in results:
                    formatted_results.append({
                        "content": item.get("content", ""),
                        "metadata": item.get("metadata", {}),
                        "score": item.get("final_score", item.get("cross_encoder_score", 0.0)),
                        "graph_context": item.get("graph_context"),
                    })

                return formatted_results

            except httpx.HTTPError as e:
                logger.error(f"Hybrid search failed: {e}")
                return []

    def extract_media_names(self, search_results: List[Dict[str, Any]]) -> List[str]:
        """
        検索結果からmedia_nameを抽出（重複排除）。

        Args:
            search_results: RAG検索結果

        Returns:
            List[str]: 一意のmedia_name一覧
        """
        media_names = set()
        for result in search_results:
            metadata = result.get("metadata", {})
            media_name = metadata.get("media_name")
            if media_name:
                media_names.add(media_name)
                logger.debug(f"Found media_name: {media_name}")

        return list(media_names)

    def get_pricing_info(
        self,
        db: Session,
        media_names: List[str],
        area: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        media_nameに対応する料金情報を取得。

        Args:
            db: データベースセッション
            media_names: 媒体名リスト
            area: オプション。エリアフィルタ

        Returns:
            Dict[str, List[Dict]]: 媒体名→料金プランリストのマッピング
        """
        if not media_names:
            return {}

        pricing_info = {}

        for media_name in media_names:
            query = """
                SELECT media_name, category_large, product_name, price, area,
                       listing_period, price_type, remarks
                FROM media_pricing
                WHERE media_name = :media_name
            """
            params = {"media_name": media_name}

            if area:
                query += " AND area = :area"
                params["area"] = area

            query += " ORDER BY category_large, product_name LIMIT 10"

            result = db.execute(text(query), params)
            rows = result.fetchall()

            plans = []
            for row in rows:
                plans.append({
                    "media_name": row.media_name,
                    "category": row.category_large,
                    "product_name": row.product_name,
                    "price": float(row.price) if row.price else None,
                    "area": row.area,
                    "listing_period": row.listing_period,
                    "price_type": row.price_type,
                    "remarks": row.remarks,
                })

            if plans:
                pricing_info[media_name] = plans
                logger.info(f"Found {len(plans)} pricing plans for {media_name}")

        return pricing_info

    def _build_product_context(self, search_results: List[Dict[str, Any]]) -> str:
        """検索結果から商材コンテキストを構築"""
        if not search_results:
            return "（関連する商材情報が見つかりませんでした）"

        context_parts = []
        for i, result in enumerate(search_results[:5], 1):
            metadata = result.get("metadata", {})
            filename = metadata.get("filename", metadata.get("original_filename", "不明"))
            media_name = metadata.get("media_name", "未設定")
            content = result.get("content", "")[:500]  # Limit content length
            score = result.get("score", 0)

            context_parts.append(
                f"### 商材 {i}: {filename}\n"
                f"- 媒体: {media_name}\n"
                f"- 関連度: {score:.2f}\n"
                f"- 内容:\n{content}\n"
            )

        return "\n".join(context_parts)

    def _build_pricing_context(self, pricing_info: Dict[str, List[Dict]]) -> str:
        """料金情報からコンテキストを構築"""
        if not pricing_info:
            return "（料金情報が見つかりませんでした）"

        context_parts = ["以下は提案時に使用すべき正式な料金です：\n"]
        for media_name, plans in pricing_info.items():
            context_parts.append(f"【{media_name}】の料金表:")
            for plan in plans[:5]:  # Limit plans per media
                price_str = f"¥{plan['price']:,.0f}" if plan['price'] else "要問合せ"
                area_str = plan['area'] if plan['area'] else "全国"
                period_str = f"({plan['listing_period']})" if plan['listing_period'] else ""
                category_str = f"[{plan['category']}] " if plan.get('category') else ""

                context_parts.append(
                    f"  - {category_str}{plan['product_name']}: {price_str} / {area_str} {period_str}"
                )
            context_parts.append("")  # Add blank line between media

        return "\n".join(context_parts)

    async def stream_proposal(
        self,
        query: str,
        knowledge_base_id: UUID,
        tenant_id: UUID,
        jwt_token: str,
        db: Session,
        area: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        商材提案をストリーミング生成（9段階ハイブリッド検索使用）。

        Args:
            query: 顧客要件/議事録テキスト
            knowledge_base_id: 商材KBのID
            tenant_id: テナントID
            jwt_token: 認証トークン
            db: データベースセッション
            area: オプション。エリアフィルタ

        Yields:
            str: SSE形式のチャンク
        """
        try:
            # Send start event
            yield f"data: {json.dumps({'type': 'start', 'status': 'searching'})}\n\n"

            # Step 1: 9段階ハイブリッド検索（GraphRAG含む）
            search_results = await self.search_products(
                query=query,
                knowledge_base_id=knowledge_base_id,
                tenant_id=tenant_id,
                jwt_token=jwt_token,
                top_k=10,
            )

            if not search_results:
                yield f"data: {json.dumps({'type': 'info', 'message': '関連する商材が見つかりませんでした'})}\n\n"

            # Step 2: media_name抽出
            media_names = self.extract_media_names(search_results)
            logger.info(f"Extracted media_names: {media_names}")

            yield f"data: {json.dumps({'type': 'info', 'message': f'{len(search_results)}件の商材情報を検索', 'media_names': media_names})}\n\n"

            # Step 3: 料金情報取得
            pricing_info = self.get_pricing_info(db, media_names, area)

            yield f"data: {json.dumps({'type': 'info', 'message': f'{len(pricing_info)}件の料金情報を取得', 'status': 'generating'})}\n\n"

            # Step 4: コンテキスト構築
            product_context = self._build_product_context(search_results)
            pricing_context = self._build_pricing_context(pricing_info)

            # 商材名リストを作成（正式名称をLLMに明示）
            media_names_list = ", ".join(media_names) if media_names else "（なし）"

            # Step 5: LLM呼び出し
            system_prompt = PROPOSAL_SYSTEM_PROMPT.format(
                media_names_list=media_names_list,
                product_context=product_context,
                pricing_context=pricing_context,
            )

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=query),
            ]

            full_response = ""
            async for chunk in self.llm.astream(messages):
                if chunk.content:
                    full_response += chunk.content
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk.content})}\n\n"

            # Send completion event with metadata
            yield f"data: {json.dumps({'type': 'done', 'media_names': media_names, 'total_products': len(search_results), 'total_pricing': sum(len(p) for p in pricing_info.values())})}\n\n"

        except Exception as e:
            logger.error(f"Proposal generation error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    async def generate_proposal(
        self,
        query: str,
        knowledge_base_id: UUID,
        tenant_id: UUID,
        jwt_token: str,
        db: Session,
        area: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        商材提案を生成（非ストリーミング、9段階ハイブリッド検索使用）。

        Args:
            query: 顧客要件/議事録テキスト
            knowledge_base_id: 商材KBのID
            tenant_id: テナントID
            jwt_token: 認証トークン
            db: データベースセッション
            area: オプション。エリアフィルタ

        Returns:
            Dict: 提案結果（proposal, media_names, search_results, pricing_info）
        """
        # Step 1: 9段階ハイブリッド検索（GraphRAG含む）
        search_results = await self.search_products(
            query=query,
            knowledge_base_id=knowledge_base_id,
            tenant_id=tenant_id,
            jwt_token=jwt_token,
        )

        # Step 2: media_name抽出
        media_names = self.extract_media_names(search_results)

        # Step 3: 料金情報取得
        pricing_info = self.get_pricing_info(db, media_names, area)

        # Step 4: コンテキスト構築
        product_context = self._build_product_context(search_results)
        pricing_context = self._build_pricing_context(pricing_info)

        # 商材名リストを作成（正式名称をLLMに明示）
        media_names_list = ", ".join(media_names) if media_names else "（なし）"

        # Step 5: LLM呼び出し
        system_prompt = PROPOSAL_SYSTEM_PROMPT.format(
            media_names_list=media_names_list,
            product_context=product_context,
            pricing_context=pricing_context,
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=query),
        ]

        response = await self.llm.ainvoke(messages)

        return {
            "proposal": response.content,
            "media_names": media_names,
            "search_results": search_results,
            "pricing_info": pricing_info,
            "generated_at": datetime.utcnow().isoformat(),
        }


# Singleton instance
proposal_chat_service = ProposalChatService()
