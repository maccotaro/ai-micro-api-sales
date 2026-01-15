"""Neo4j async client for Sales GraphRAG.

Provides connection management and query execution for the Neo4j graph database.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from uuid import UUID

from neo4j import AsyncGraphDatabase, AsyncDriver

from app.core.config import settings

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Neo4j async client with connection pooling."""

    def __init__(self):
        self._driver: Optional[AsyncDriver] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Establish connection to Neo4j (thread-safe)."""
        async with self._lock:
            if self._driver is not None:
                try:
                    async with self._driver.session() as session:
                        await session.run("RETURN 1")
                    return
                except Exception:
                    try:
                        await self._driver.close()
                    except Exception:
                        pass
                    self._driver = None

            self._driver = AsyncGraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
                database=settings.neo4j_database,
                max_connection_lifetime=3600,
                max_connection_pool_size=50,
                connection_acquisition_timeout=60,
            )
            async with self._driver.session() as session:
                await session.run("RETURN 1")
            logger.info("Neo4j connected successfully")

    async def close(self) -> None:
        """Close Neo4j connection (no-op for singleton)."""
        pass

    async def shutdown(self) -> None:
        """Shutdown the Neo4j driver."""
        async with self._lock:
            if self._driver:
                await self._driver.close()
                self._driver = None
                logger.info("Neo4j connection closed")

    @asynccontextmanager
    async def session(self):
        """Get a Neo4j session context manager."""
        if not self._driver:
            await self.connect()
        try:
            async with self._driver.session() as session:
                yield session
        except Exception as e:
            if "defunct" in str(e).lower():
                async with self._lock:
                    self._driver = None
            raise

    async def execute_write(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a write transaction."""
        async with self.session() as session:
            result = await session.run(query, parameters or {})
            records = await result.data()
            return records

    async def execute_read(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a read transaction."""
        async with self.session() as session:
            result = await session.run(query, parameters or {})
            records = await result.data()
            return records

    async def merge_node(
        self,
        label: str,
        properties: Dict[str, Any],
        tenant_id: UUID,
    ) -> Dict[str, Any]:
        """Merge a node (create if not exists, update if exists)."""
        query = f"""
        MERGE (n:{label} {{name: $name, tenant_id: $tenant_id}})
        ON CREATE SET n += $properties, n.created_at = datetime()
        ON MATCH SET n += $properties, n.updated_at = datetime()
        RETURN n
        """
        props = {**properties, "tenant_id": str(tenant_id)}
        result = await self.execute_write(
            query,
            {
                "name": properties["name"],
                "tenant_id": str(tenant_id),
                "properties": props,
            },
        )
        return result[0] if result else {}

    async def create_relationship(
        self,
        from_label: str,
        from_name: str,
        rel_type: str,
        to_label: str,
        to_name: str,
        tenant_id: UUID,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create a relationship between two nodes."""
        query = f"""
        MATCH (a:{from_label} {{name: $from_name, tenant_id: $tenant_id}})
        MATCH (b:{to_label} {{name: $to_name, tenant_id: $tenant_id}})
        MERGE (a)-[r:{rel_type}]->(b)
        SET r += $properties
        """
        await self.execute_write(
            query,
            {
                "from_name": from_name,
                "to_name": to_name,
                "tenant_id": str(tenant_id),
                "properties": properties or {},
            },
        )

    async def find_related_products(
        self,
        problem_name: str,
        tenant_id: UUID,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Find products that solve a specific problem."""
        query = """
        MATCH (prob:Problem {name: $problem_name, tenant_id: $tenant_id})
              -[:SOLVED_BY]->(prod:Product)
        RETURN prod.name as name, prod.description as description,
               prod.category as category
        LIMIT $limit
        """
        return await self.execute_read(
            query,
            {
                "problem_name": problem_name,
                "tenant_id": str(tenant_id),
                "limit": limit,
            },
        )

    async def find_success_cases_by_industry(
        self,
        industry: str,
        tenant_id: UUID,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Find success cases in a specific industry."""
        query = """
        MATCH (ind:Industry {name: $industry, tenant_id: $tenant_id})
              <-[:OCCURS_IN]-(prob:Problem)
              -[:MENTIONED_IN]->(c:Chunk)
        WHERE c.document_type = 'success_case'
        RETURN c.chunk_id as chunk_id, c.document_id as document_id,
               prob.name as problem
        LIMIT $limit
        """
        return await self.execute_read(
            query,
            {
                "industry": industry,
                "tenant_id": str(tenant_id),
                "limit": limit,
            },
        )


# Singleton instance
neo4j_client = Neo4jClient()
