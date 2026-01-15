"""
Database session management for Sales API
"""
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from app.core.config import settings

logger = logging.getLogger(__name__)

# Sync engine and session for salesdb
sync_database_url = settings.salesdb_url
sync_engine = create_engine(sync_database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

# Async engine and session for salesdb
async_database_url = settings.salesdb_url.replace("postgresql://", "postgresql+asyncpg://")
async_engine = create_async_engine(async_database_url)
AsyncSessionLocal = async_sessionmaker(
    autocommit=False, autoflush=False, bind=async_engine, class_=AsyncSession
)

# Base class for models
SalesDBBase = declarative_base()


def get_db():
    """
    Dependency for getting sync database session.

    Yields:
        Session: Database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db():
    """
    Dependency for getting async database session.

    Yields:
        AsyncSession: Async database session
    """
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.close()
