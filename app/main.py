"""
AI Micro Service - Sales API

Sales Support AI Service for meeting minutes analysis and proposal generation.
"""
import logging
import sys
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.routers import meeting_minutes, proposals, simulation, health, search, graph, chat, pricing, proposal_chat, proposal_pipeline
from app.services.graph import neo4j_client

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="AI Micro Service - Sales API",
    description="Sales Support AI Service for meeting minutes analysis and proposal generation",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Permission denial middleware (captures 403 responses for audit)
from app.middleware.permission_denial_middleware import PermissionDenialMiddleware
app.add_middleware(PermissionDenialMiddleware)

# Include routers
app.include_router(health.router)
app.include_router(meeting_minutes.router, prefix="/api/sales")
app.include_router(proposals.router, prefix="/api/sales")
app.include_router(simulation.router, prefix="/api/sales")
app.include_router(search.router, prefix="/api/sales")
app.include_router(graph.router, prefix="/api/sales")
app.include_router(chat.router, prefix="/api/sales")
app.include_router(pricing.router, prefix="/api/sales")
app.include_router(proposal_chat.router, prefix="/api/sales")
app.include_router(proposal_pipeline.router, prefix="/api/sales")


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Global exception handler: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("AI Micro API Sales service starting up...")
    logger.info(f"Database URL: {settings.salesdb_url.split('@')[-1] if '@' in settings.salesdb_url else '***'}")
    logger.info(f"Ollama URL: {settings.ollama_base_url}")
    logger.info(f"CORS origins: {settings.cors_origins}")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("AI Micro API Sales service shutting down...")
    # Close Neo4j connection
    await neo4j_client.shutdown()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8005,
        reload=True,
        log_level=settings.log_level.lower(),
    )
