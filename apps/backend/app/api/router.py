"""
Central API router — registers all route modules.

Adding a new feature means importing its router here.
"""

from fastapi import APIRouter

from app.api import chat, health, documents, workflows

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(chat.router)
api_router.include_router(documents.router)
api_router.include_router(workflows.router)
