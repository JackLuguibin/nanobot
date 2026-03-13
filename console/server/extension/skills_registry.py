"""Skills Registry extension - discover and install skills from remote registry."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


def _fetch_url(url: str) -> str:
    """Fetch URL content."""
    req = Request(url, headers={"User-Agent": "Nanobot-Console/1.0"})
    with urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8")


def fetch_registry(registry_url: str | None = None) -> list[dict[str, Any]]:
    """Fetch skills list from registry URL.
    Format: { "skills": [ { "name", "description", "url", "version?" } ] }
    If no registry_url, returns empty list.
    """
    if not registry_url or not registry_url.strip():
        return []
    url = registry_url.strip()
    try:
        data = json.loads(_fetch_url(url))
        return data.get("skills", [])
    except Exception:
        return []


def search_registry(query: str, registry_url: str | None = None) -> list[dict[str, Any]]:
    """Search skills in registry by name or description."""
    skills = fetch_registry(registry_url)
    if not query or not query.strip():
        return skills
    q = query.strip().lower()
    return [
        s
        for s in skills
        if q in (s.get("name") or "").lower() or q in (s.get("description") or "").lower()
    ]


def install_skill_from_registry(
    name: str,
    workspace: Path,
    registry_url: str | None = None,
) -> bool:
    """Install a skill from registry into workspace. Returns False if not found or invalid."""
    skills = fetch_registry(registry_url)
    skill = next((s for s in skills if (s.get("name") or "").lower() == name.lower()), None)
    if not skill:
        return False

    url = skill.get("url")
    if not url:
        return False

    # Validate name
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        return False

    skill_dir = workspace / "skills" / name
    if skill_dir.exists():
        return False  # Already exists

    # Fetch SKILL.md - URL might point to file or we append /SKILL.md
    try:
        content = _fetch_url(url)
    except Exception:
        # Try appending /SKILL.md if URL looks like a folder
        if not url.endswith(".md"):
            try:
                base = url.rstrip("/")
                content = _fetch_url(f"{base}/SKILL.md")
            except Exception:
                return False
        else:
            return False

    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return True
