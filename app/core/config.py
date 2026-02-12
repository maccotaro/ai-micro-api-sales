"""
Configuration settings for Sales API Service
"""
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    salesdb_url: str = "postgresql://postgres:password@localhost:5432/salesdb"

    # Redis
    redis_url: str = "redis://:password@localhost:6379"

    # Authentication
    auth_service_url: str = "http://localhost:8002"
    admin_service_url: str = "http://localhost:8003"
    jwks_url: str = "http://localhost:8002/.well-known/jwks.json"

    # RAG Service (9-stage hybrid search pipeline)
    rag_service_url: str = "http://localhost:8010"
    jwt_issuer: str = "https://auth.example.com"
    jwt_audience: str = "fastapi-api"

    # LLM Services (model names are managed via DB system_settings, fetched via internal API)
    ollama_base_url: str = "http://localhost:11434"
    llm_service_url: str = "http://localhost:8012"
    openai_api_key: str = ""
    admin_internal_url: str = "http://localhost:8003"
    internal_api_secret: str = "change-me-in-production"

    # Neo4j Graph Database
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str = "neo4j"

    # Application
    log_level: str = "INFO"
    cors_origins: List[str] = ["http://localhost:3004", "http://localhost:3003"]

    # Analysis settings
    max_meeting_text_length: int = 50000
    max_proposal_products: int = 10

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
