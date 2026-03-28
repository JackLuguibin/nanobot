"""API routes - unified through Facade layer.

This module re-exports the Facade router to maintain backward compatibility
for code that imports from console.server.api.routes.
"""

from __future__ import annotations

from fastapi import APIRouter

# All API routes now go through the Facade layer
from console.server.facade.router import router as facade_router

router = APIRouter(prefix="/api/v1")
router.include_router(facade_router)
