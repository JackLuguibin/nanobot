"""Skills management extension for console.

Provides PatchedContextBuilder for per-bot skill enable/disable,
and helper functions for skill CRUD operations.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from nanobot.agent.context import ContextBuilder
from nanobot.agent.skills import SkillsLoader


def _is_skill_enabled(name: str, skills_config: dict[str, Any]) -> bool:
    """Check if a skill is enabled. Unlisted skills default to True."""
    cfg = skills_config.get(name)
    if cfg is None:
        return True
    if isinstance(cfg, dict):
        return cfg.get("enabled", True)
    return True


class PatchedContextBuilder(ContextBuilder):
    """ContextBuilder that respects per-bot skills enable/disable config."""

    def __init__(self, workspace: Path, skills_config: dict[str, Any] | None = None):
        super().__init__(workspace)
        self._skills_config = skills_config or {}

    def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
        """Build system prompt with skills filtered by skills_config."""
        parts = [self._get_identity()]

        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)

        memory = self.memory.get_memory_context()
        if memory:
            parts.append(f"# Memory\n\n{memory}")

        all_skills = self.skills.list_skills(filter_unavailable=False)
        enabled_skills = [s for s in all_skills if _is_skill_enabled(s["name"], self._skills_config)]

        always_skill_names = [
            s["name"]
            for s in enabled_skills
            if self._is_always_skill(s["name"])
        ]
        if always_skill_names:
            always_content = self.skills.load_skills_for_context(always_skill_names)
            if always_content:
                parts.append(f"# Active Skills\n\n{always_content}")

        skills_summary = self._build_filtered_skills_summary(enabled_skills)
        if skills_summary:
            parts.append(f"""# Skills

The following skills extend your capabilities. To use a skill, read its SKILL.md file using the read_file tool.
Skills with available="false" need dependencies installed first - you can try installing them with apt/brew.

{skills_summary}""")

        return "\n\n---\n\n".join(parts)

    def _is_always_skill(self, name: str) -> bool:
        """Check if skill is marked as always (from SkillsLoader logic)."""
        meta = self.skills.get_skill_metadata(name) or {}
        skill_meta = self.skills._parse_nanobot_metadata(meta.get("metadata", ""))
        return bool(skill_meta.get("always") or meta.get("always"))

    def _build_filtered_skills_summary(self, skills: list[dict[str, str]]) -> str:
        """Build XML summary for filtered skills (reuse SkillsLoader helpers)."""
        if not skills:
            return ""

        def escape_xml(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        lines = ["<skills>"]
        for s in skills:
            name = escape_xml(s["name"])
            path = s["path"]
            desc = escape_xml(self.skills._get_skill_description(s["name"]))
            skill_meta = self.skills._get_skill_meta(s["name"])
            available = self.skills._check_requirements(skill_meta)

            lines.append(f'  <skill available="{str(available).lower()}">')
            lines.append(f"    <name>{name}</name>")
            lines.append(f"    <description>{desc}</description>")
            lines.append(f"    <location>{path}</location>")

            if not available:
                missing = self.skills._get_missing_requirements(skill_meta)
                if missing:
                    lines.append(f"    <requires>{escape_xml(missing)}</requires>")

            lines.append("  </skill>")
        lines.append("</skills>")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Skill CRUD helpers (for API routes)
# ---------------------------------------------------------------------------


def list_skills_for_bot(workspace: Path) -> list[dict[str, Any]]:
    """List all skills (builtin + workspace) with metadata for a bot."""
    loader = SkillsLoader(workspace)
    raw = loader.list_skills(filter_unavailable=False)

    result = []
    for s in raw:
        meta = loader.get_skill_metadata(s["name"]) or {}
        skill_meta = loader._parse_nanobot_metadata(meta.get("metadata", ""))
        available = loader._check_requirements(skill_meta)
        result.append({
            "name": s["name"],
            "source": s["source"],
            "description": loader._get_skill_description(s["name"]),
            "path": s["path"],
            "available": available,
        })
    return result


def get_skill_content(workspace: Path, name: str) -> str | None:
    """Get skill content. Works for both builtin and workspace."""
    loader = SkillsLoader(workspace)
    return loader.load_skill(name)


def update_skill_content(workspace: Path, name: str, content: str) -> bool:
    """Update workspace skill content. Returns False if builtin (read-only)."""
    skill_path = workspace / "skills" / name / "SKILL.md"
    if not skill_path.exists():
        return False
    skill_path.write_text(content, encoding="utf-8")
    return True


def create_workspace_skill(
    workspace: Path,
    name: str,
    description: str,
    content: str,
) -> bool:
    """Create a new workspace skill. Returns False if invalid name or exists."""
    if not _is_valid_skill_name(name):
        return False
    skill_dir = workspace / "skills" / name
    if skill_dir.exists():
        return False
    skill_dir.mkdir(parents=True, exist_ok=True)

    desc_escaped = description.replace('"', '\\"').replace("\n", " ")
    frontmatter = f'---\nname: "{name}"\ndescription: "{desc_escaped}"\n---\n\n'
    full_content = frontmatter + content
    (skill_dir / "SKILL.md").write_text(full_content, encoding="utf-8")
    return True


def delete_workspace_skill(workspace: Path, name: str) -> bool:
    """Delete a workspace skill. Returns False if builtin or not found."""
    skill_dir = workspace / "skills" / name
    if not skill_dir.exists() or not (skill_dir / "SKILL.md").exists():
        return False
    import shutil
    shutil.rmtree(skill_dir)
    return True


def copy_builtin_skill_to_workspace(workspace: Path, name: str) -> bool:
    """Copy a built-in skill to workspace, enabling editing. Returns False if already in workspace or not found."""
    loader = SkillsLoader(workspace)
    skill_dir = workspace / "skills" / name
    if skill_dir.exists():
        return False  # Already in workspace
    content = loader.load_skill(name)
    if content is None:
        return False
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return True


def _is_valid_skill_name(name: str) -> bool:
    """Validate skill name to prevent path injection."""
    if not name or not name.strip():
        return False
    clean = name.strip()
    if ".." in clean or "/" in clean or "\\" in clean:
        return False
    if not re.match(r"^[a-zA-Z0-9_-]+$", clean):
        return False
    return True
