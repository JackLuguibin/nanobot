"""Nanobot Console Server API module.

This module serves as a backward-compatibility shim. All actual API
implementation has been migrated to the Facade layer (facade/router.py).
The routes router (console.server.api.routes) now simply includes facade.router.

For new code, import directly from:
  - console.server.facade.router   (API endpoints)
  - console.server.api.state        (BotState utilities, internal use)
  - console.server.api.response     (HTTP/middleware, shared with facade)
  - console.server.api.websocket     (WebSocket utilities)
"""

from __future__ import annotations

# Backward compatibility: re-export routes so code importing
# "from console.server.api import routes" still works
from console.server.api import routes

__all__ = ["routes"]
