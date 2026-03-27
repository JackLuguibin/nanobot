"""API routes for workspace files."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from console.server.api.state import get_state
from console.server.models.workspace import (
    WorkspaceFileItem,
    WorkspaceFileListResponse,
    WorkspaceFileReadResponse,
    WorkspaceFileUpdateRequest,
    WorkspaceFileUpdateResponse,
)

router = APIRouter(prefix="/workspace")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


def _resolve_workspace_path(workspace: Path, rel_path: str) -> Path | None:
    """Resolve relative path within workspace. Returns None if path escapes workspace."""
    if not workspace or not workspace.exists():
        return None
    try:
        resolved = (workspace / rel_path).resolve()
        if not str(resolved).startswith(str(workspace.resolve())):
            return None
        return resolved
    except (OSError, ValueError):
        return None


@router.get("/files", response_model=WorkspaceFileListResponse)
async def list_workspace_files(
    path: str = Query("", description="Relative path from workspace root"),
    depth: int = Query(2, ge=1, le=5),
    bot_id: str | None = Query(None),
) -> WorkspaceFileListResponse:
    """List workspace directory structure. depth limits recursion."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace or not workspace.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    resolved = _resolve_workspace_path(workspace, path or ".")
    if resolved is None or not resolved.exists():
        raise HTTPException(status_code=400, detail="Invalid path")

    def _list_dir(p: Path, d: int) -> list[WorkspaceFileItem]:
        if d <= 0:
            return []
        items = []
        for child in sorted(p.iterdir()):
            name = child.name
            if name.startswith(".") and name != ".env":
                continue
            rel = child.relative_to(workspace)
            children = None
            if child.is_dir() and d > 1:
                children = _list_dir(child, d - 1)
            items.append(
                WorkspaceFileItem(
                    name=name,
                    path=str(rel).replace("\\", "/"),
                    is_dir=child.is_dir(),
                    children=children,
                )
            )
        return items

    return WorkspaceFileListResponse(path=path or ".", items=_list_dir(resolved, depth))


@router.get("/file", response_model=WorkspaceFileReadResponse)
async def get_workspace_file(
    path: str = Query(..., description="Relative path from workspace root"),
    bot_id: str | None = Query(None),
) -> WorkspaceFileReadResponse:
    """Read a file from workspace."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace or not workspace.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    resolved = _resolve_workspace_path(workspace, path)
    if resolved is None or not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = resolved.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return WorkspaceFileReadResponse(path=path, content=content)


@router.put("/file", response_model=WorkspaceFileUpdateResponse)
async def update_workspace_file(
    request: WorkspaceFileUpdateRequest,
    bot_id: str | None = Query(None),
) -> WorkspaceFileUpdateResponse:
    """Update a file in workspace."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace or not workspace.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    resolved = _resolve_workspace_path(workspace, request.path)
    if resolved is None or not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        resolved.write_text(request.content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return WorkspaceFileUpdateResponse(path=request.path)
