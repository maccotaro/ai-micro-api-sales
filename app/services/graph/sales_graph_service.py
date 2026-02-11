"""Sales Graph Service for Neo4j operations (v2 schema).

Provides sales-specific graph operations using the v2 unified schema:
- Meeting source nodes with v2 entities (Concept/Claim/Condition/Actor)
- Product recommendations via MENTIONED_IN + RELATED_TO traversal
- Success case discovery through shared entity graph traversal
- Cross-graph queries spanning Admin Chunks and Sales Meetings
"""
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.services.graph.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)

# v1 analysis_result fields → v2 label + type mapping (for fallback)
_FALLBACK_MAPPING = {
    "issues": ("Concept", "problem"),
    "needs": ("Concept", "need"),
}


class SalesGraphService:
    """Sales-specific graph operations using v2 schema."""

    def __init__(self):
        self.client = neo4j_client

    async def ensure_connected(self) -> bool:
        """Ensure Neo4j connection is established."""
        try:
            await self.client.connect()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            return False

    # ------------------------------------------------------------------
    # Store: v2 graph creation
    # ------------------------------------------------------------------

    async def store_meeting_analysis_v2(
        self,
        meeting_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        analysis_result: Dict[str, Any],
        entity_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Store meeting analysis in the graph using v2 schema.

        If entity_data is provided (from celery-llm entity_extractor),
        creates v2 entity nodes (Concept/Claim/Condition/Actor) with
        MENTIONED_IN relationships to the Meeting source node, plus
        inter-entity relations from entity_data.relations.

        If entity_data is None (extraction failed), falls back to creating
        basic v2 nodes from the LLM analysis_result fields.
        """
        try:
            tenant_str = str(tenant_id)
            meeting_str = str(meeting_id)

            # 1. MERGE Meeting source node
            await self.client.execute_write(
                """
                MERGE (m:Meeting {meeting_id: $meeting_id, tenant_id: $tenant_id})
                ON CREATE SET
                    m.user_id = $user_id,
                    m.company_name = $company_name,
                    m.industry = $industry,
                    m.created_at = datetime()
                ON MATCH SET
                    m.company_name = $company_name,
                    m.industry = $industry,
                    m.updated_at = datetime()
                RETURN m
                """,
                {
                    "meeting_id": meeting_str,
                    "tenant_id": tenant_str,
                    "user_id": str(user_id),
                    "company_name": analysis_result.get("company_name", ""),
                    "industry": analysis_result.get("industry", ""),
                },
            )

            # 2. Store entities
            entity_count = 0
            mode = "fallback"
            if entity_data and entity_data.get("entities"):
                entity_count = await self._store_v2_entities(
                    meeting_str, tenant_str, entity_data
                )
                mode = "v2"

            # Fallback: if v2 extracted 0 entities, supplement from analysis
            if entity_count == 0:
                entity_count = await self._store_fallback_entities(
                    meeting_str, tenant_str, analysis_result
                )
                mode = f"{mode}+fallback" if mode == "v2" else "fallback"

            logger.info(
                f"Stored v2 meeting analysis: meeting_id={meeting_id}, "
                f"entities={entity_count}, "
                f"mode={mode}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to store v2 meeting analysis: {e}")
            return False

    async def _store_v2_entities(
        self,
        meeting_id: str,
        tenant_id: str,
        entity_data: Dict[str, Any],
    ) -> int:
        """Store v2 entities from celery-llm extraction result."""
        count = 0
        entities = entity_data.get("entities", {})

        # Map entity type keys to Neo4j labels
        label_map = {
            "concepts": "Concept",
            "claims": "Claim",
            "conditions": "Condition",
            "actors": "Actor",
        }

        for entity_key, label in label_map.items():
            for entity in entities.get(entity_key, []):
                name = entity.get("name", "").strip()
                if not name:
                    continue
                entity_type = entity.get("type", entity_key.rstrip("s"))
                await self._merge_entity_with_mention(
                    label, name, entity_type, meeting_id, tenant_id
                )
                count += 1

        # Create inter-entity relations
        relations = entity_data.get("relations", [])
        for rel in relations:
            await self._create_inter_entity_relation(rel, tenant_id)

        return count

    async def _store_fallback_entities(
        self,
        meeting_id: str,
        tenant_id: str,
        analysis_result: Dict[str, Any],
    ) -> int:
        """Create basic v2 nodes from LLM analysis fields (fallback)."""
        count = 0

        # issues → Concept(type='problem'), needs → Concept(type='need')
        for field, (label, entity_type) in _FALLBACK_MAPPING.items():
            for item in analysis_result.get(field, []):
                name = item.strip() if isinstance(item, str) else ""
                if not name:
                    continue
                await self._merge_entity_with_mention(
                    label, name, entity_type, meeting_id, tenant_id
                )
                count += 1

        # industry → Condition(type='industry')
        industry = analysis_result.get("industry")
        if industry:
            await self._merge_entity_with_mention(
                "Condition", industry, "industry", meeting_id, tenant_id
            )
            count += 1

        # target_persona → Actor(type='target_persona')
        target = analysis_result.get("target_persona")
        if target:
            await self._merge_entity_with_mention(
                "Actor", target, "target_persona", meeting_id, tenant_id
            )
            count += 1

        return count

    async def _merge_entity_with_mention(
        self,
        label: str,
        name: str,
        entity_type: str,
        meeting_id: str,
        tenant_id: str,
    ) -> None:
        """MERGE a v2 entity node and create MENTIONED_IN → Meeting."""
        await self.client.execute_write(
            f"""
            MERGE (e:{label} {{name: $name, tenant_id: $tenant_id}})
            ON CREATE SET e.type = $entity_type, e.created_at = datetime()
            ON MATCH SET e.updated_at = datetime()
            WITH e
            MATCH (m:Meeting {{meeting_id: $meeting_id, tenant_id: $tenant_id}})
            MERGE (e)-[:MENTIONED_IN]->(m)
            """,
            {
                "name": name,
                "entity_type": entity_type,
                "tenant_id": tenant_id,
                "meeting_id": meeting_id,
            },
        )

    async def _create_inter_entity_relation(
        self,
        rel: Dict[str, Any],
        tenant_id: str,
    ) -> None:
        """Create a relationship between two v2 entities."""
        source = rel.get("source", "").strip()
        target = rel.get("target", "").strip()
        rel_type = rel.get("type", "RELATED_TO").upper().replace(" ", "_")
        if not source or not target:
            return

        # Use RELATED_TO as safe default; map known types
        safe_types = {
            "RELATED_TO", "ABOUT", "SUPPORTS", "CONTRADICTS",
            "CAUSED_BY", "REQUIRES", "PART_OF",
        }
        if rel_type not in safe_types:
            rel_type = "RELATED_TO"

        await self.client.execute_write(
            f"""
            MATCH (s {{name: $source, tenant_id: $tenant_id}})
            MATCH (t {{name: $target, tenant_id: $tenant_id}})
            MERGE (s)-[:{rel_type}]->(t)
            """,
            {
                "source": source,
                "target": target,
                "tenant_id": tenant_id,
            },
        )

    # ------------------------------------------------------------------
    # Query: v2 traversal patterns
    # ------------------------------------------------------------------

    async def find_products_for_meeting(
        self,
        meeting_id: UUID,
        tenant_id: UUID,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Find recommended products via v2 graph traversal.

        Path: Meeting ← MENTIONED_IN ← Concept(problem/need)
              → RELATED_TO → Concept(product)
        """
        result = await self.client.execute_read(
            """
            MATCH (m:Meeting {meeting_id: $meeting_id, tenant_id: $tenant_id})
            MATCH (entity)-[:MENTIONED_IN]->(m)
            WHERE entity:Concept AND entity.type IN ['problem', 'need']
            MATCH (entity)-[:RELATED_TO]->(prod:Concept {type: 'product'})
            WHERE prod.tenant_id = $tenant_id
            WITH prod, collect(DISTINCT entity.name) as matched_entities
            RETURN DISTINCT prod.name as product_name,
                   coalesce(prod.source_document_id, '') as product_id,
                   coalesce(prod.confidence, 0.8) as relevance_score,
                   matched_entities as matched_problems
            LIMIT $limit
            """,
            {
                "meeting_id": str(meeting_id),
                "tenant_id": str(tenant_id),
                "limit": limit,
            },
        )
        return result

    async def find_similar_meetings(
        self,
        meeting_id: UUID,
        tenant_id: UUID,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Find similar meetings based on shared v2 entities.

        Path: M1 ← MENTIONED_IN ← entity → MENTIONED_IN → M2
        """
        result = await self.client.execute_read(
            """
            MATCH (m1:Meeting {meeting_id: $meeting_id, tenant_id: $tenant_id})
            MATCH (entity)-[:MENTIONED_IN]->(m1)
            MATCH (entity)-[:MENTIONED_IN]->(m2:Meeting)
            WHERE m2.meeting_id <> $meeting_id
              AND m2.tenant_id = $tenant_id
            WITH m2, collect(DISTINCT entity.name) as shared_entities,
                 count(DISTINCT entity) as shared_count
            WITH m2, shared_entities, shared_count,
                 (shared_count * 0.3 + 0.5) as score
            ORDER BY score DESC
            LIMIT $limit
            RETURN m2.meeting_id as meeting_id,
                   m2.company_name as company_name,
                   score as similarity_score,
                   shared_entities as shared_problems,
                   [] as shared_needs
            """,
            {
                "meeting_id": str(meeting_id),
                "tenant_id": str(tenant_id),
                "limit": limit,
            },
        )
        return result

    async def find_success_cases_for_meeting(
        self,
        meeting_id: UUID,
        tenant_id: UUID,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Find success cases via shared entities with Admin Chunks.

        Path: Meeting ← MENTIONED_IN ← Concept → MENTIONED_IN → Chunk
        """
        result = await self.client.execute_read(
            """
            MATCH (m:Meeting {meeting_id: $meeting_id, tenant_id: $tenant_id})
            MATCH (entity)-[:MENTIONED_IN]->(m)
            WHERE entity:Concept OR entity:Condition
            MATCH (entity)-[:MENTIONED_IN]->(c:Chunk)
            WHERE c.tenant_id = $tenant_id
            WITH c, collect(DISTINCT entity.name) as shared_entities,
                 count(DISTINCT entity) as relevance
            ORDER BY relevance DESC
            LIMIT $limit
            RETURN DISTINCT c.chunk_id as id,
                   coalesce(c.document_id, '') as title,
                   coalesce(c.industry, '') as industry,
                   apoc.text.join(shared_entities, ', ') as achievement
            """,
            {
                "meeting_id": str(meeting_id),
                "tenant_id": str(tenant_id),
                "limit": limit,
            },
        )
        return result

    async def find_related_products(
        self,
        product_name: str,
        tenant_id: UUID,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Find related products via v2 RELATED_TO traversal.

        Path: Concept(product) → RELATED_TO → Concept(product)
        """
        result = await self.client.execute_read(
            """
            MATCH (p:Concept {name: $product_name, type: 'product',
                              tenant_id: $tenant_id})
            OPTIONAL MATCH (p)-[r:RELATED_TO]->(related:Concept {type: 'product'})
            WHERE related.tenant_id = $tenant_id
            WITH collect(DISTINCT {
                name: related.name,
                reason: coalesce(r.reason, '')
            }) as related_raw
            RETURN [r IN related_raw WHERE r.name IS NOT NULL] as related
            """,
            {
                "product_name": product_name,
                "tenant_id": str(tenant_id),
            },
        )
        related = result[0].get("related", []) if result else []
        return {"requires": [], "cross_sell": related}

    async def find_products_with_relations(
        self,
        meeting_id: UUID,
        tenant_id: UUID,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Find products for meeting with their RELATED_TO products.

        Combines find_products_for_meeting with related product lookup.
        """
        result = await self.client.execute_read(
            """
            MATCH (m:Meeting {meeting_id: $meeting_id, tenant_id: $tenant_id})
            MATCH (entity)-[:MENTIONED_IN]->(m)
            WHERE entity:Concept AND entity.type IN ['problem', 'need']
            MATCH (entity)-[:RELATED_TO]->(prod:Concept {type: 'product'})
            WHERE prod.tenant_id = $tenant_id
            WITH prod, collect(DISTINCT entity.name) as matched_problems

            OPTIONAL MATCH (prod)-[r:RELATED_TO]->(related:Concept {type: 'product'})
            WHERE related.tenant_id = $tenant_id
            WITH prod, matched_problems,
                 collect(DISTINCT {
                     name: related.name, reason: coalesce(r.reason, '')
                 }) as related_raw

            RETURN DISTINCT prod.name as product_name,
                   coalesce(prod.source_document_id, '') as product_id,
                   coalesce(prod.confidence, 0.8) as relevance_score,
                   matched_problems,
                   [] as requires,
                   [r IN related_raw WHERE r.name IS NOT NULL] as cross_sell
            LIMIT $limit
            """,
            {
                "meeting_id": str(meeting_id),
                "tenant_id": str(tenant_id),
                "limit": limit,
            },
        )
        return result

    async def link_product_to_problem(
        self,
        product_name: str,
        problem_name: str,
        tenant_id: UUID,
    ) -> bool:
        """Create RELATED_TO between a problem Concept and product Concept."""
        try:
            await self.client.execute_write(
                """
                MATCH (prob:Concept {name: $problem_name, tenant_id: $tenant_id})
                WHERE prob.type IN ['problem', 'need']
                MATCH (prod:Concept {name: $product_name, type: 'product',
                                     tenant_id: $tenant_id})
                MERGE (prob)-[:RELATED_TO]->(prod)
                """,
                {
                    "problem_name": problem_name,
                    "product_name": product_name,
                    "tenant_id": str(tenant_id),
                },
            )
            return True
        except Exception as e:
            logger.error(f"Failed to link product to problem: {e}")
            return False

    async def get_graph_stats(
        self,
        tenant_id: UUID,
    ) -> Dict[str, int]:
        """Get graph statistics for a tenant."""
        result = await self.client.execute_read(
            """
            MATCH (n)
            WHERE n.tenant_id = $tenant_id
            WITH labels(n)[0] as label, count(n) as count
            RETURN label, count
            ORDER BY count DESC
            """,
            {"tenant_id": str(tenant_id)},
        )
        return {r["label"]: r["count"] for r in result}

    async def delete_meeting_graph(
        self,
        meeting_id: UUID,
        tenant_id: UUID,
    ) -> bool:
        """Delete Meeting node only. Shared entities are preserved."""
        try:
            await self.client.execute_write(
                """
                MATCH (m:Meeting {meeting_id: $meeting_id, tenant_id: $tenant_id})
                DETACH DELETE m
                """,
                {
                    "meeting_id": str(meeting_id),
                    "tenant_id": str(tenant_id),
                },
            )
            return True
        except Exception as e:
            logger.error(f"Failed to delete meeting graph: {e}")
            return False


# Singleton instance
sales_graph_service = SalesGraphService()
