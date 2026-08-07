"""Aggregate API routers for the application."""

from fastapi import APIRouter

from app.api.routes import (
    analytics,
    datasets,
    health,
    insight,
    intent,
    ml,
    rag,
    visualization,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(datasets.router)
api_router.include_router(intent.router)
api_router.include_router(analytics.router)
api_router.include_router(visualization.router)
api_router.include_router(rag.router)
api_router.include_router(ml.router)
api_router.include_router(insight.router)
