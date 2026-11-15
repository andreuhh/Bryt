"""Aggregates all v1 routers. New domains (integrations, activities, plans, chat) register here."""

from fastapi import APIRouter

from app.api.v1.endpoints import health

api_router = APIRouter()
api_router.include_router(health.router)
