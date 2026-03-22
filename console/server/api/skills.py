"""API routes for skills management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from console.server.api.state import get_state

router = APIRouter(prefix="/api/skills")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class SkillCreateRequest(BaseModel):
    name: str
    description: str
    content: str = ""


class SkillContentUpdateRequest(BaseModel):
    content: str


class SkillInstallFromRegistryRequest(BaseModel):
    name: str
    registry_url: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[dict[str, Any]])
async def list_skills(bot_id: str | None = Query(None)) -> list[dict[str, Any]]:
    """List all skills (builtin + workspace) for a bot."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        return []

    from console.server.extension.skills import list_skills_for_bot

    skills = list_skills_for_bot(workspace)
    config = await state.get_config()
    skills_config = config.get("skills") or {}

    for s in skills:
        cfg = skills_config.get(s["name"])
        s["enabled"] = cfg.get("enabled", True) if isinstance(cfg, dict) else True

    return skills


@router.get("/{name}/content")
async def get_skill_content(
    name: str,
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Get skill content (read-only for builtin, editable for workspace)."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    from console.server.extension.skills import get_skill_content as _get_content

    content = _get_content(workspace, name)
    if content is None:
        raise HTTPException(status_code=404, detail="Skill not found")

    return {"name": name, "content": content}


@router.post("/{name}/copy-to-workspace")
async def copy_skill_to_workspace(
    name: str,
    bot_id: str | None = Query(None),
) -> dict[str, str]:
    """Copy a built-in skill to workspace, enabling editing."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    from console.server.extension.skills import copy_builtin_skill_to_workspace

    if not copy_builtin_skill_to_workspace(workspace, name):
        raise HTTPException(
            status_code=400,
            detail="Skill already in workspace or not found",
        )
    return {"status": "copied", "name": name}


@router.put("/{name}/content")
async def update_skill_content(
    name: str,
    request: SkillContentUpdateRequest,
    bot_id: str | None = Query(None),
) -> dict[str, str]:
    """Update workspace skill content. Builtin skills are read-only."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    from console.server.extension.skills import update_skill_content as _update_content

    content = request.content
    if not _update_content(workspace, name, content):
        raise HTTPException(
            status_code=400,
            detail="Skill not found or builtin (read-only)",
        )
    return {"status": "updated", "name": name}


@router.get("/registry/search")
async def search_skills_registry(
    q: str = Query("", description="Search query"),
    registry_url: str | None = Query(None),
    bot_id: str | None = Query(None),
) -> list[dict[str, Any]]:
    """Search skills in the registry."""
    from console.server.extension.skills_registry import search_registry

    config = {}
    if bot_id:
        state = _resolve_state(bot_id)
        config = await state.get_config()
    url = registry_url or config.get("console", {}).get("skills_registry_url")
    return search_registry(q or "", url)


@router.post("/install-from-registry")
async def install_skill_from_registry(
    request: SkillInstallFromRegistryRequest,
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Install a skill from the registry into workspace."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace or not workspace.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")

    from console.server.extension.skills_registry import install_skill_from_registry as _install

    config = await state.get_config()
    url = request.registry_url or config.get("console", {}).get("skills_registry_url")
    ok = _install(request.name, workspace, url)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Skill not found in registry, already installed, or invalid name",
        )
    return {"status": "installed", "name": request.name}


@router.post("")
async def create_skill(
    request: SkillCreateRequest,
    bot_id: str | None = Query(None),
) -> dict[str, Any]:
    """Create a new workspace skill."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    from console.server.extension.skills import create_workspace_skill

    if not create_workspace_skill(
        workspace,
        request.name,
        request.description,
        request.content,
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid skill name or skill already exists",
        )
    return {"status": "created", "name": request.name}


@router.delete("/{name}")
async def delete_skill(
    name: str,
    bot_id: str | None = Query(None),
) -> dict[str, str]:
    """Delete a workspace skill. Builtin skills cannot be deleted."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    from console.server.extension.skills import delete_workspace_skill

    if not delete_workspace_skill(workspace, name):
        raise HTTPException(
            status_code=400,
            detail="Skill not found or builtin (cannot delete)",
        )
    return {"status": "deleted", "name": name}
