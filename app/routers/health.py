"""
Health Check Router
"""
from datetime import datetime

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "ai-micro-api-sales",
        "version": "1.0.0",
    }


@router.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "ai-micro-api-sales",
        "version": "1.0.0",
        "description": "Sales Support AI Service - Meeting Minutes Analysis and Proposal Generation",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "docs_url": "/docs",
    }
