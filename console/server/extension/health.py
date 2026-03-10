"""Health Audit extension for console.

检查 bootstrap 文件缺失、空指令、MCP 配置错误、通道未配置等。
返回 issues 列表，按严重度排序。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_BOOTSTRAP_FILES = ["SOUL.md", "USER.md", "AGENTS.md", "TOOLS.md", "IDENTITY.md"]
_EMPTY_THRESHOLD = 50  # chars


def run_health_audit(bot_id: str, workspace: Path | None, config: dict[str, Any], status: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """执行健康检查，返回 issues 列表。
    每个 issue: { type, severity, message, bot_id?, path? }
    severity: critical, warning, info
    """
    issues: list[dict[str, Any]] = []

    if not workspace or not workspace.exists():
        issues.append({
            "type": "workspace_missing",
            "severity": "critical",
            "message": "工作区路径不存在",
            "bot_id": bot_id,
        })
        return issues

    # 1. Bootstrap 文件缺失
    for fname in _BOOTSTRAP_FILES:
        path = workspace / fname
        if not path.exists():
            issues.append({
                "type": "bootstrap_missing",
                "severity": "warning",
                "message": f"Bootstrap 文件缺失: {fname}",
                "bot_id": bot_id,
                "path": fname,
            })

    # 2. 空指令（文件存在但内容过短）
    for fname in _BOOTSTRAP_FILES:
        path = workspace / fname
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                stripped = content.strip()
                if len(stripped) < _EMPTY_THRESHOLD:
                    issues.append({
                        "type": "empty_instruction",
                        "severity": "info",
                        "message": f"{fname} 内容过短或为空",
                        "bot_id": bot_id,
                        "path": fname,
                    })
            except Exception:
                pass

    # 3. MCP 配置错误
    tools_config = config.get("tools") or {}
    mcp_servers = tools_config.get("mcpServers") or tools_config.get("mcp_servers") or {}
    for name, mcp_cfg in mcp_servers.items():
        if not isinstance(mcp_cfg, dict):
            continue
        has_cmd = bool(mcp_cfg.get("command"))
        has_url = bool(mcp_cfg.get("url"))
        if not has_cmd and not has_url:
            issues.append({
                "type": "mcp_config_error",
                "severity": "warning",
                "message": f"MCP 服务器「{name}」未配置 command 或 url",
                "bot_id": bot_id,
                "metadata": {"mcp_name": name},
            })

    # 4. 通道未配置（仅当用户可能期望有时提示）
    channels = config.get("channels") or {}
    enabled = [k for k, v in channels.items() if isinstance(v, dict) and v.get("enabled")]
    if not enabled and status:
        ch_from_status = status.get("channels") or []
        if any(c.get("enabled") for c in ch_from_status):
            pass  # 有启用的
        else:
            issues.append({
                "type": "no_channels",
                "severity": "info",
                "message": "未配置任何启用的通道（WhatsApp、Telegram 等）",
                "bot_id": bot_id,
            })

    # 5. Provider/API 未配置
    providers = config.get("providers") or {}
    general = config.get("general") or {}
    model = general.get("model") or (config.get("agents") or {}).get("defaults", {}).get("model")
    if model:
        # 简单检查：是否有对应 provider 配置
        provider_name = (model.split("/")[0] if "/" in model else "openai_codex")
        if provider_name not in providers and "custom" not in str(providers.keys()).lower():
            p = next((p for p in providers.values() if isinstance(p, dict) and p.get("apiKey")), None)
            if not p:
                issues.append({
                    "type": "provider_missing",
                    "severity": "critical",
                    "message": "未配置 LLM Provider 或 API Key",
                    "bot_id": bot_id,
                })

    # 按严重度排序
    _order = {"critical": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda x: (_order.get(x.get("severity", ""), 99), x.get("message", "")))
    return issues
