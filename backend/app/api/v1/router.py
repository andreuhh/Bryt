"""Aggregates all v1 routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import activities, agent_runs, chat, health, integrations, me, plans

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(me.router)
api_router.include_router(integrations.router)
api_router.include_router(activities.router)
api_router.include_router(plans.router)
api_router.include_router(chat.router)
api_router.include_router(agent_runs.router)
