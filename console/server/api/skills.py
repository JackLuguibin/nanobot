"""API routes for skills management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from console.server.api.state import get_state
from console.server.models.skills import (
    SkillContentResponse,
    SkillCopyResponse,
    SkillCreateRequest,
    SkillCreateResponse,
    SkillDeleteResponse,
    SkillInfo,
    SkillInstallFromRegistryRequest,
    SkillInstallResponse,
    SkillUpdateResponse,
)

router = APIRouter(prefix="/skills")


def _resolve_state(bot_id: str | None = None):
    return get_state(bot_id)


@router.get("", response_model=list[SkillInfo])
async def list_skills(bot_id: str | None = Query(None)) -> list[SkillInfo]:
    """List all skills (builtin + workspace) for a bot."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        return []

    from console.server.extension.skills import list_skills_for_bot

    skills = list_skills_for_bot(workspace)
    config = await state.get_config()
    skills_config = config.get("skills") or {}

    result = []
    for s in skills:
        cfg = skills_config.get(s["name"])
        enabled = cfg.get("enabled", True) if isinstance(cfg, dict) else True
        result.append(
            SkillInfo(
                name=s["name"],
                description=s.get("description"),
                path=s.get("path"),
                builtin=s.get("builtin", False),
                workspace=s.get("workspace", False),
                enabled=enabled,
            )
        )

    return result


@router.get("/{name}/content", response_model=SkillContentResponse)
async def get_skill_content(
    name: str,
    bot_id: str | None = Query(None),
) -> SkillContentResponse:
    """Get skill content (read-only for builtin, editable for workspace)."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    from console.server.extension.skills import get_skill_content as _get_content

    content = _get_content(workspace, name)
    if content is None:
        raise HTTPException(status_code=404, detail="Skill not found")

    return SkillContentResponse(name=name, content=content)


@router.post("/{name}/copy-to-workspace", response_model=SkillCopyResponse)
async def copy_skill_to_workspace(
    name: str,
    bot_id: str | None = Query(None),
) -> SkillCopyResponse:
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
    return SkillCopyResponse(name=name)


@router.put("/{name}/content", response_model=SkillUpdateResponse)
async def update_skill_content(
    name: str,
    request: SkillContentUpdateRequest,
    bot_id: str | None = Query(None),
) -> SkillUpdateResponse:
    """Update workspace skill content. Builtin skills are read-only."""
    state = _resolve_state(bot_id)
    workspace = state.workspace
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    from console.server.extension.skills import update_skill_content as _update_content

    if not _update_content(workspace, name, request.content):
        raise HTTPException(
            status_code=400,
            detail="Skill not found or builtin (read-only)",
        )
    return SkillUpdateResponse(name=name)


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


@router.post("/install-from-registry", response_model=SkillInstallResponse)
async def install_skill_from_registry(
    request: SkillInstallFromRegistryRequest,
    bot_id: str | None = Query(None),
) -> SkillInstallResponse:
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
    return SkillInstallResponse(name=request.name)


@router.post("", response_model=SkillCreateResponse)
async def create_skill(
    request: SkillCreateRequest,
    bot_id: str | None = Query(None),
) -> SkillCreateResponse:
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
    return SkillCreateResponse(name=request.name)


@router.delete("/{name}", response_model=SkillDeleteResponse)
async def delete_skill(
    name: str,
    bot_id: str | None = Query(None),
) -> SkillDeleteResponse:
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
    return SkillDeleteResponse(name=name)
