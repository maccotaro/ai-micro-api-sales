"""
Embedding Service for Sales API

Provides vector embedding generation and similarity search functionality
for meeting minutes, proposals, and similar case matching.
"""
import logging
from typing import List, Dict, Any, Optional
from uuid import UUID
import asyncio
import json

from langchain_community.embeddings import OllamaEmbeddings
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.model_settings_client import get_embedding_model

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating embeddings and similarity search."""

    def __init__(self):
        self.embeddings = None
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize the embedding model."""
        try:
            if self._initialized:
                return True

            logger.info("Initializing EmbeddingService...")

            self.embeddings = OllamaEmbeddings(
                base_url=settings.ollama_base_url,
                model=get_embedding_model(),
            )

            # Test embedding generation
            test_embedding = await asyncio.to_thread(
                self.embeddings.embed_query,
                "テスト"
            )
            logger.info(f"Embedding dimension: {len(test_embedding)}")

            self._initialized = True
            logger.info("EmbeddingService initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize EmbeddingService: {e}")
            return False

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding vector for given text.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector
        """
        try:
            if not self._initialized:
                await self.initialize()

            if not text.strip():
                return None

            embedding = await asyncio.to_thread(
                self.embeddings.embed_query,
                text
            )
            return embedding

        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None

    async def store_meeting_embedding(
        self,
        db: Session,
        meeting_id: UUID,
        text_content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Generate and store embedding for a meeting minute.

        Args:
            db: Database session
            meeting_id: Meeting minute ID
            text_content: Text to embed
            metadata: Additional metadata

        Returns:
            True if successful
        """
        try:
            embedding = await self.generate_embedding(text_content)
            if embedding is None:
                return False

            # Store in meeting_minute_embeddings table
            # Format embedding as PostgreSQL array literal for vector type
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
            metadata_json = json.dumps(metadata or {})

            db.execute(
                text("""
                    INSERT INTO meeting_minute_embeddings
                    (meeting_minute_id, content, embedding, emb_metadata)
                    VALUES (:meeting_id, :content, :embedding, :metadata)
                    ON CONFLICT (meeting_minute_id)
                    DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        emb_metadata = EXCLUDED.emb_metadata,
                        updated_at = NOW()
                """),
                {
                    "meeting_id": str(meeting_id),
                    "content": text_content[:5000],  # Truncate for storage
                    "embedding": embedding_str,
                    "metadata": metadata_json,
                }
            )
            db.commit()

            logger.info(f"Stored embedding for meeting {meeting_id}")
            return True

        except Exception as e:
            logger.error(f"Error storing meeting embedding: {e}")
            db.rollback()
            return False

    async def search_similar_meetings(
        self,
        db: Session,
        query: str,
        user_id: UUID,
        limit: int = 5,
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Search for similar meeting minutes using vector similarity.

        Args:
            db: Database session
            query: Search query text
            user_id: Current user ID for filtering
            limit: Maximum number of results
            threshold: Similarity threshold (0-1)

        Returns:
            List of similar meeting minutes with similarity scores
        """
        try:
            query_embedding = await self.generate_embedding(query)
            if query_embedding is None:
                return []

            # Format embedding as PostgreSQL array literal for vector type
            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

            # Use cosine similarity search
            result = db.execute(
                text("""
                    SELECT
                        mme.meeting_minute_id,
                        mm.company_name,
                        mm.industry,
                        mm.area,
                        mm.meeting_date,
                        mm.status,
                        mme.content,
                        1 - (mme.embedding <=> :query_embedding) as similarity
                    FROM meeting_minute_embeddings mme
                    JOIN meeting_minutes mm ON mm.id = mme.meeting_minute_id
                    WHERE mm.created_by = :user_id
                      AND 1 - (mme.embedding <=> :query_embedding) >= :threshold
                    ORDER BY mme.embedding <=> :query_embedding
                    LIMIT :limit
                """),
                {
                    "query_embedding": embedding_str,
                    "user_id": str(user_id),
                    "threshold": threshold,
                    "limit": limit,
                }
            )

            meetings = []
            for row in result:
                meetings.append({
                    "meeting_id": row.meeting_minute_id,
                    "company_name": row.company_name,
                    "industry": row.industry,
                    "area": row.area,
                    "meeting_date": row.meeting_date.isoformat() if row.meeting_date else None,
                    "status": row.status,
                    "content_preview": row.content[:200] + "..." if len(row.content) > 200 else row.content,
                    "similarity": float(row.similarity),
                })

            logger.info(f"Found {len(meetings)} similar meetings for query")
            return meetings

        except Exception as e:
            logger.error(f"Error searching similar meetings: {e}")
            return []

    async def search_similar_success_cases(
        self,
        db: Session,
        query: str,
        industry: Optional[str] = None,
        area: Optional[str] = None,
        limit: int = 5,
        threshold: float = 0.6
    ) -> List[Dict[str, Any]]:
        """
        Search for similar success cases using vector similarity.

        Args:
            db: Database session
            query: Search query text
            industry: Optional industry filter
            area: Optional area filter
            limit: Maximum number of results
            threshold: Similarity threshold (0-1)

        Returns:
            List of similar success cases with similarity scores
        """
        try:
            query_embedding = await self.generate_embedding(query)
            if query_embedding is None:
                return []

            # Format embedding as PostgreSQL array literal for vector type
            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

            # Build dynamic filter conditions
            filters = ["sce.is_public = true"]
            params = {
                "query_embedding": embedding_str,
                "threshold": threshold,
                "limit": limit,
            }

            if industry:
                filters.append("sce.industry = :industry")
                params["industry"] = industry
            if area:
                filters.append("sce.area = :area")
                params["area"] = area

            filter_clause = " AND ".join(filters)

            result = db.execute(
                text(f"""
                    SELECT
                        sce.id,
                        sce.title,
                        sce.content,
                        sce.industry,
                        sce.area,
                        sce.company_size,
                        sce.achievement,
                        sce.metrics,
                        sce.case_date,
                        1 - (sce.embedding <=> :query_embedding) as similarity
                    FROM success_case_embeddings sce
                    WHERE {filter_clause}
                      AND 1 - (sce.embedding <=> :query_embedding) >= :threshold
                    ORDER BY sce.embedding <=> :query_embedding
                    LIMIT :limit
                """),
                params
            )

            cases = []
            for row in result:
                cases.append({
                    "id": row.id,
                    "title": row.title,
                    "content_preview": row.content[:300] + "..." if len(row.content) > 300 else row.content,
                    "industry": row.industry,
                    "area": row.area,
                    "company_size": row.company_size,
                    "achievement": row.achievement,
                    "metrics": row.metrics,
                    "case_date": row.case_date.isoformat() if row.case_date else None,
                    "similarity": float(row.similarity),
                })

            logger.info(f"Found {len(cases)} similar success cases")
            return cases

        except Exception as e:
            logger.error(f"Error searching similar success cases: {e}")
            return []

    async def search_similar_sales_talks(
        self,
        db: Session,
        query: str,
        issue_type: Optional[str] = None,
        industry: Optional[str] = None,
        limit: int = 5,
        threshold: float = 0.6
    ) -> List[Dict[str, Any]]:
        """
        Search for similar sales talks using vector similarity.

        Args:
            db: Database session
            query: Search query text
            issue_type: Optional issue type filter
            industry: Optional industry filter
            limit: Maximum number of results
            threshold: Similarity threshold (0-1)

        Returns:
            List of similar sales talks with similarity scores
        """
        try:
            query_embedding = await self.generate_embedding(query)
            if query_embedding is None:
                return []

            # Format embedding as PostgreSQL array literal for vector type
            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

            # Build dynamic filter conditions
            filters = ["1=1"]
            params = {
                "query_embedding": embedding_str,
                "threshold": threshold,
                "limit": limit,
            }

            if issue_type:
                filters.append("ste.issue_type = :issue_type")
                params["issue_type"] = issue_type
            if industry:
                filters.append("ste.industry = :industry")
                params["industry"] = industry

            filter_clause = " AND ".join(filters)

            result = db.execute(
                text(f"""
                    SELECT
                        ste.id,
                        ste.title,
                        ste.content,
                        ste.issue_type,
                        ste.industry,
                        ste.target_persona,
                        ste.effectiveness_score,
                        ste.usage_count,
                        ste.tags,
                        1 - (ste.embedding <=> :query_embedding) as similarity
                    FROM sales_talk_embeddings ste
                    WHERE {filter_clause}
                      AND 1 - (ste.embedding <=> :query_embedding) >= :threshold
                    ORDER BY ste.embedding <=> :query_embedding
                    LIMIT :limit
                """),
                params
            )

            talks = []
            for row in result:
                talks.append({
                    "id": row.id,
                    "title": row.title,
                    "content": row.content,
                    "issue_type": row.issue_type,
                    "industry": row.industry,
                    "target_persona": row.target_persona,
                    "effectiveness_score": float(row.effectiveness_score) if row.effectiveness_score else None,
                    "usage_count": row.usage_count,
                    "tags": row.tags,
                    "similarity": float(row.similarity),
                })

            logger.info(f"Found {len(talks)} similar sales talks")
            return talks

        except Exception as e:
            logger.error(f"Error searching similar sales talks: {e}")
            return []

    async def search_similar_products(
        self,
        db: Session,
        query: str,
        category: Optional[str] = None,
        limit: int = 5,
        threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Search for similar products using vector similarity.

        Args:
            db: Database session
            query: Search query text
            category: Optional category filter
            limit: Maximum number of results
            threshold: Similarity threshold (0-1)

        Returns:
            List of similar products with similarity scores
        """
        try:
            query_embedding = await self.generate_embedding(query)
            if query_embedding is None:
                return []

            # Format embedding as PostgreSQL array literal for vector type
            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

            # Build filter
            filters = ["p.is_active = true"]
            params = {
                "query_embedding": embedding_str,
                "threshold": threshold,
                "limit": limit,
            }

            if category:
                filters.append("pe.category = :category")
                params["category"] = category

            filter_clause = " AND ".join(filters)

            result = db.execute(
                text(f"""
                    SELECT DISTINCT ON (p.id)
                        p.id,
                        p.name,
                        p.category,
                        p.base_price,
                        p.price_unit,
                        p.description,
                        p.features,
                        pe.content as matched_content,
                        1 - (pe.embedding <=> :query_embedding) as similarity
                    FROM product_embeddings pe
                    JOIN products p ON p.id = pe.product_id
                    WHERE {filter_clause}
                      AND 1 - (pe.embedding <=> :query_embedding) >= :threshold
                    ORDER BY p.id, pe.embedding <=> :query_embedding
                    LIMIT :limit
                """),
                params
            )

            products = []
            for row in result:
                products.append({
                    "id": row.id,
                    "name": row.name,
                    "category": row.category,
                    "base_price": float(row.base_price) if row.base_price else None,
                    "price_unit": row.price_unit,
                    "description": row.description,
                    "features": row.features,
                    "matched_content": row.matched_content[:200] + "..." if len(row.matched_content) > 200 else row.matched_content,
                    "similarity": float(row.similarity),
                })

            logger.info(f"Found {len(products)} similar products")
            return products

        except Exception as e:
            logger.error(f"Error searching similar products: {e}")
            return []

    def is_ready(self) -> bool:
        """Check if the service is initialized."""
        return self._initialized


# Global instance
embedding_service = EmbeddingService()


async def get_embedding_service() -> EmbeddingService:
    """Get the embedding service instance."""
    if not embedding_service.is_ready():
        await embedding_service.initialize()
    return embedding_service
