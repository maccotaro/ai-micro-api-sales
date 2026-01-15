"""Sales Graph Service for Neo4j operations.

Provides sales-specific graph operations:
- Meeting minute entity extraction and graph population
- Product recommendations based on graph relationships
- Success case discovery through graph traversal
"""
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.services.graph.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)


class SalesGraphService:
    """Sales-specific graph operations."""

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

    async def store_meeting_analysis(
        self,
        meeting_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        analysis_result: Dict[str, Any],
    ) -> bool:
        """
        Store meeting analysis results in the graph.

        Creates nodes for:
        - Meeting (central node)
        - Problems/Issues extracted
        - Needs identified
        - Products mentioned
        - Industry/Target if identified

        Args:
            meeting_id: UUID of the meeting minute
            tenant_id: Tenant ID for multi-tenancy
            user_id: User who owns the meeting
            analysis_result: Analysis result containing extracted entities
        """
        try:
            tenant_str = str(tenant_id)

            # Create Meeting node
            await self.client.execute_write(
                """
                MERGE (m:Meeting {meeting_id: $meeting_id, tenant_id: $tenant_id})
                ON CREATE SET
                    m.user_id = $user_id,
                    m.company_name = $company_name,
                    m.industry = $industry,
                    m.created_at = datetime()
                ON MATCH SET
                    m.updated_at = datetime()
                RETURN m
                """,
                {
                    "meeting_id": str(meeting_id),
                    "tenant_id": tenant_str,
                    "user_id": str(user_id),
                    "company_name": analysis_result.get("company_name", ""),
                    "industry": analysis_result.get("industry", ""),
                },
            )

            # Create Problem nodes and relationships
            problems = analysis_result.get("issues", [])
            for problem in problems:
                if isinstance(problem, str) and problem.strip():
                    await self._create_problem_node(
                        meeting_id, tenant_str, problem.strip()
                    )

            # Create Need nodes and relationships
            needs = analysis_result.get("needs", [])
            for need in needs:
                if isinstance(need, str) and need.strip():
                    await self._create_need_node(
                        meeting_id, tenant_str, need.strip()
                    )

            # Create Industry node if present
            industry = analysis_result.get("industry")
            if industry:
                await self._create_industry_node(
                    meeting_id, tenant_str, industry
                )

            # Create Target node if present
            target = analysis_result.get("target_persona")
            if target:
                await self._create_target_node(
                    meeting_id, tenant_str, target
                )

            logger.info(
                f"Stored meeting analysis in graph: meeting_id={meeting_id}, "
                f"problems={len(problems)}, needs={len(needs)}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to store meeting analysis in graph: {e}")
            return False

    async def _create_problem_node(
        self,
        meeting_id: UUID,
        tenant_id: str,
        problem_name: str,
    ) -> None:
        """Create Problem node and link to Meeting."""
        await self.client.execute_write(
            """
            MERGE (p:Problem {name: $name, tenant_id: $tenant_id})
            ON CREATE SET p.created_at = datetime()
            WITH p
            MATCH (m:Meeting {meeting_id: $meeting_id, tenant_id: $tenant_id})
            MERGE (m)-[:HAS_PROBLEM]->(p)
            """,
            {
                "name": problem_name,
                "tenant_id": tenant_id,
                "meeting_id": str(meeting_id),
            },
        )

    async def _create_need_node(
        self,
        meeting_id: UUID,
        tenant_id: str,
        need_name: str,
    ) -> None:
        """Create Need node and link to Meeting."""
        await self.client.execute_write(
            """
            MERGE (n:Need {name: $name, tenant_id: $tenant_id})
            ON CREATE SET n.created_at = datetime()
            WITH n
            MATCH (m:Meeting {meeting_id: $meeting_id, tenant_id: $tenant_id})
            MERGE (m)-[:HAS_NEED]->(n)
            """,
            {
                "name": need_name,
                "tenant_id": tenant_id,
                "meeting_id": str(meeting_id),
            },
        )

    async def _create_industry_node(
        self,
        meeting_id: UUID,
        tenant_id: str,
        industry_name: str,
    ) -> None:
        """Create Industry node and link to Meeting."""
        await self.client.execute_write(
            """
            MERGE (i:Industry {name: $name, tenant_id: $tenant_id})
            ON CREATE SET i.created_at = datetime()
            WITH i
            MATCH (m:Meeting {meeting_id: $meeting_id, tenant_id: $tenant_id})
            MERGE (m)-[:IN_INDUSTRY]->(i)
            """,
            {
                "name": industry_name,
                "tenant_id": tenant_id,
                "meeting_id": str(meeting_id),
            },
        )

    async def _create_target_node(
        self,
        meeting_id: UUID,
        tenant_id: str,
        target_name: str,
    ) -> None:
        """Create Target node and link to Meeting."""
        await self.client.execute_write(
            """
            MERGE (t:Target {name: $name, tenant_id: $tenant_id})
            ON CREATE SET t.created_at = datetime()
            WITH t
            MATCH (m:Meeting {meeting_id: $meeting_id, tenant_id: $tenant_id})
            MERGE (m)-[:TARGETS]->(t)
            """,
            {
                "name": target_name,
                "tenant_id": tenant_id,
                "meeting_id": str(meeting_id),
            },
        )

    async def find_products_for_meeting(
        self,
        meeting_id: UUID,
        tenant_id: UUID,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Find recommended products based on meeting's problems and needs.

        Traverses:
        Meeting -> Problem -> SOLVED_BY -> Product
        Meeting -> Need -> ADDRESSED_BY -> Product
        """
        result = await self.client.execute_read(
            """
            MATCH (m:Meeting {meeting_id: $meeting_id, tenant_id: $tenant_id})
            OPTIONAL MATCH (m)-[:HAS_PROBLEM]->(prob:Problem)<-[:SOLVED_BY]-(prod:Product)
            WITH prod, collect(DISTINCT prob.name) as matched_problems
            WHERE prod IS NOT NULL
            RETURN DISTINCT prod.name as product_name,
                   coalesce(prod.source_document_id, '') as product_id,
                   coalesce(prod.confidence, 0.8) as relevance_score,
                   matched_problems
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
        """
        Find similar meetings based on shared problems, needs, or industry.

        Uses graph traversal to find meetings with common characteristics.
        """
        result = await self.client.execute_read(
            """
            MATCH (m1:Meeting {meeting_id: $meeting_id, tenant_id: $tenant_id})
            OPTIONAL MATCH (m1)-[:HAS_PROBLEM]->(p1:Problem)<-[:HAS_PROBLEM]-(m2:Meeting)
            WHERE m2.meeting_id <> $meeting_id AND m2.tenant_id = $tenant_id
            WITH m1, m2, collect(DISTINCT p1.name) as shared_probs
            OPTIONAL MATCH (m1)-[:IN_INDUSTRY]->(ind:Industry)<-[:IN_INDUSTRY]-(m2)
            WITH m2, shared_probs,
                 CASE WHEN ind IS NOT NULL THEN 1 ELSE 0 END as industry_match
            WHERE m2 IS NOT NULL
            WITH m2, shared_probs, industry_match,
                 (size(shared_probs) * 0.3 + industry_match * 0.2 + 0.5) as score
            ORDER BY score DESC
            LIMIT $limit
            RETURN m2.meeting_id as meeting_id,
                   m2.company_name as company_name,
                   score as similarity_score,
                   shared_probs as shared_problems,
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
        """
        Find success cases related to meeting's problems and industry.

        Traverses:
        Meeting -> Problem -> MENTIONED_IN -> SuccessCase
        Meeting -> Industry -> HAS_SUCCESS_CASE -> SuccessCase
        """
        result = await self.client.execute_read(
            """
            MATCH (m:Meeting {meeting_id: $meeting_id, tenant_id: $tenant_id})
            OPTIONAL MATCH (m)-[:HAS_PROBLEM]->(prob:Problem)
                          -[:MENTIONED_IN]->(sc1:SuccessCase)
            OPTIONAL MATCH (m)-[:IN_INDUSTRY]->(ind:Industry)
                          -[:HAS_SUCCESS_CASE]->(sc2:SuccessCase)
            WITH [c IN collect(DISTINCT sc1) + collect(DISTINCT sc2) WHERE c IS NOT NULL] as cases
            UNWIND cases as sc
            RETURN DISTINCT sc.id as id,
                   sc.title as title,
                   sc.industry as industry,
                   sc.achievement as achievement
            LIMIT $limit
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
        """
        Find REQUIRES and CROSS_SELL related products for a given product.

        Returns:
            Dict with 'requires' and 'cross_sell' lists
        """
        result = await self.client.execute_read(
            """
            MATCH (p:Product {name: $product_name, tenant_id: $tenant_id})
            OPTIONAL MATCH (p)-[req:REQUIRES]->(reqProd:Product)
            OPTIONAL MATCH (p)-[cs:CROSS_SELL]->(csProd:Product)
            WITH p,
                 collect(DISTINCT {name: reqProd.name, reason: req.reason}) as requires,
                 collect(DISTINCT {name: csProd.name, reason: cs.reason}) as cross_sells
            RETURN
                [r IN requires WHERE r.name IS NOT NULL] as requires,
                [c IN cross_sells WHERE c.name IS NOT NULL] as cross_sells
            """,
            {
                "product_name": product_name,
                "tenant_id": str(tenant_id),
            },
        )
        if result:
            return {
                "requires": result[0].get("requires", []),
                "cross_sell": result[0].get("cross_sells", []),
            }
        return {"requires": [], "cross_sell": []}

    async def find_products_with_relations(
        self,
        meeting_id: UUID,
        tenant_id: UUID,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Find recommended products with their REQUIRES and CROSS_SELL relations.

        Enhanced version of find_products_for_meeting that includes
        related products via REQUIRES and CROSS_SELL relationships.
        """
        # First get base product recommendations
        result = await self.client.execute_read(
            """
            MATCH (m:Meeting {meeting_id: $meeting_id, tenant_id: $tenant_id})
            OPTIONAL MATCH (m)-[:HAS_PROBLEM]->(prob:Problem)<-[:SOLVED_BY]-(prod:Product)
            WITH prod, collect(DISTINCT prob.name) as matched_problems
            WHERE prod IS NOT NULL

            // Get REQUIRES relationships
            OPTIONAL MATCH (prod)-[req:REQUIRES]->(reqProd:Product)
            WITH prod, matched_problems,
                 collect(DISTINCT {name: reqProd.name, reason: req.reason}) as requires_raw

            // Get CROSS_SELL relationships
            OPTIONAL MATCH (prod)-[cs:CROSS_SELL]->(csProd:Product)
            WITH prod, matched_problems, requires_raw,
                 collect(DISTINCT {name: csProd.name, reason: cs.reason}) as cross_sell_raw

            RETURN DISTINCT prod.name as product_name,
                   coalesce(prod.source_document_id, '') as product_id,
                   coalesce(prod.confidence, 0.8) as relevance_score,
                   matched_problems,
                   [r IN requires_raw WHERE r.name IS NOT NULL] as requires,
                   [c IN cross_sell_raw WHERE c.name IS NOT NULL] as cross_sell
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
        """Create SOLVED_BY relationship between Problem and Product."""
        try:
            await self.client.execute_write(
                """
                MATCH (prob:Problem {name: $problem_name, tenant_id: $tenant_id})
                MATCH (prod:Product {name: $product_name, tenant_id: $tenant_id})
                MERGE (prob)-[:SOLVED_BY]->(prod)
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
        """Delete all graph data related to a meeting."""
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
