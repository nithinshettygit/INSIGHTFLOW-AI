"""Aggregate API routers for the application."""

from fastapi import APIRouter

from app.api.routes import analytics, datasets, health, intent, visualization

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(datasets.router)
api_router.include_router(intent.router)
api_router.include_router(analytics.router)
api_router.include_router(visualization.router)
