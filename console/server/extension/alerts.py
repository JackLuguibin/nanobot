"""Smart Alerts extension for console.

告警规则：成本超阈值、Cron 逾期、MCP 离线、通道异常。
告警存储到 {config_dir}/alerts.json，按严重度排序。
支持简单阈值配置（如 cost_daily_limit）。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _get_alerts_file_path(bot_id: str) -> Path:
    """获取指定 bot 的 alerts 存储文件路径。"""
    try:
        from console.server.bot_registry import get_registry

        bot = get_registry().get_bot(bot_id)
        if bot:
            return Path(bot.config_path).parent / "alerts.json"
    except Exception:
        pass
    return Path.home() / ".nanobot" / "bots" / bot_id / "alerts.json"


def _load_alerts(bot_id: str) -> list[dict[str, Any]]:
    """加载告警列表。"""
    path = _get_alerts_file_path(bot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("alerts", [])
    except Exception:
        return []


def _save_alerts(bot_id: str, alerts: list[dict[str, Any]]) -> None:
    """保存告警列表。"""
    path = _get_alerts_file_path(bot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"alerts": alerts}, f, indent=2, ensure_ascii=False)


def _get_alert_config(bot_id: str) -> dict[str, Any]:
    """从 config 或环境变量读取告警阈值配置。"""
    import os

    cfg: dict[str, Any] = {
        "cost_daily_limit": 10.0,
        "cron_overdue_minutes": 60,
    }
    try:
        from console.server.bot_registry import get_registry

        registry = get_registry()
        bot = (
            registry.get_bot(bot_id) if bot_id else registry.get_bot(registry.default_bot_id or "")
        )
        if bot and bot.config_path:
            path = Path(bot.config_path)
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                console_cfg = data.get("console", {}) or data.get("alerts", {})
                if isinstance(console_cfg, dict):
                    cfg["cost_daily_limit"] = float(
                        console_cfg.get("cost_daily_limit", cfg["cost_daily_limit"])
                    )
                    cfg["cron_overdue_minutes"] = int(
                        console_cfg.get("cron_overdue_minutes", cfg["cron_overdue_minutes"])
                    )
    except Exception:
        pass
    env_limit = os.environ.get("NANOBOT_COST_DAILY_LIMIT")
    if env_limit is not None:
        try:
            cfg["cost_daily_limit"] = float(env_limit)
        except ValueError:
            pass
    return cfg


def _add_alert(
    bot_id: str,
    alert_type: str,
    severity: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """添加一条告警，避免重复（同 type+message 24h 内不重复）。"""
    alerts = _load_alerts(bot_id)
    now_ms = int(time.time() * 1000)
    new_id = f"a{now_ms}"
    for a in alerts:
        if (
            a.get("type") == alert_type
            and a.get("message") == message
            and not a.get("dismissed")
            and (now_ms - a.get("created_at_ms", 0)) < 86400 * 1000
        ):
            return
    alerts.append(
        {
            "id": new_id,
            "type": alert_type,
            "severity": severity,
            "message": message,
            "bot_id": bot_id,
            "created_at_ms": now_ms,
            "dismissed": False,
            "metadata": metadata or {},
        }
    )
    alerts.sort(
        key=lambda x: (_SEVERITY_ORDER.get(x.get("severity", ""), 99), -x.get("created_at_ms", 0))
    )
    _save_alerts(bot_id, alerts)


def get_alerts(bot_id: str, include_dismissed: bool = False) -> list[dict[str, Any]]:
    """获取告警列表，按严重度排序。"""
    alerts = _load_alerts(bot_id)
    if not include_dismissed:
        alerts = [a for a in alerts if not a.get("dismissed")]
    alerts.sort(
        key=lambda x: (_SEVERITY_ORDER.get(x.get("severity", ""), 99), -x.get("created_at_ms", 0))
    )
    return alerts


def dismiss_alert(bot_id: str, alert_id: str) -> bool:
    """关闭/忽略一条告警。"""
    alerts = _load_alerts(bot_id)
    for a in alerts:
        if a.get("id") == alert_id:
            a["dismissed"] = True
            _save_alerts(bot_id, alerts)
            return True
    return False


def refresh_alerts(
    bot_id: str, status: dict[str, Any], cron_jobs: list[dict], usage_today: dict[str, Any]
) -> None:
    """根据当前状态刷新告警（成本、Cron 逾期、MCP、通道）。"""
    cfg = _get_alert_config(bot_id)
    cost_limit = cfg.get("cost_daily_limit", 10.0)
    cron_overdue_mins = cfg.get("cron_overdue_minutes", 60)

    # 成本超阈值
    cost_usd = usage_today.get("cost_usd") or 0
    if cost_usd > cost_limit:
        _add_alert(
            bot_id,
            "cost_over_limit",
            "warning",
            f"当日成本 ${cost_usd:.2f} 超过阈值 ${cost_limit:.2f}",
            {"cost_usd": cost_usd, "limit": cost_limit},
        )

    # Cron 逾期
    from datetime import datetime, timezone

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    overdue_threshold_ms = now_ms - cron_overdue_mins * 60 * 1000
    for job in cron_jobs:
        if not job.get("enabled"):
            continue
        state = job.get("state") or {}
        next_run = state.get("next_run_at_ms")
        last_run = state.get("last_run_at_ms")
        if next_run is not None and next_run < overdue_threshold_ms and (last_run or 0) < next_run:
            _add_alert(
                bot_id,
                "cron_overdue",
                "warning",
                f"Cron 任务「{job.get('name', 'unknown')}」已逾期",
                {"job_id": job.get("id"), "next_run_at_ms": next_run},
            )

    # MCP 离线（仅当配置了 MCP 但全部离线时告警）
    mcp_servers = status.get("mcp_servers") or []
    if mcp_servers:
        connected = sum(1 for m in mcp_servers if m.get("status") == "connected")
        if connected == 0:
            _add_alert(
                bot_id,
                "mcp_all_offline",
                "warning",
                "所有 MCP 服务器均离线",
                {},
            )

    # 通道异常（有启用的通道但全部离线）
    channels = status.get("channels") or []
    enabled = [c for c in channels if c.get("enabled")]
    if enabled:
        online = sum(1 for c in enabled if c.get("status") == "online")
        if online == 0:
            _add_alert(
                bot_id,
                "channels_all_offline",
                "info",
                "所有启用的通道均离线",
                {},
            )

    # Health Audit 严重问题
    try:
        from console.server.bot_registry import get_registry
        from console.server.extension.health import run_health_audit

        bot = get_registry().get_bot(bot_id)
        if bot:
            workspace = Path(bot.workspace_path) if bot.workspace_path else None
            try:
                config = json.loads(Path(bot.config_path).read_text(encoding="utf-8"))
            except Exception:
                config = {}
            health_issues = run_health_audit(bot_id, workspace, config, status)
            for issue in health_issues:
                if issue.get("severity") == "critical":
                    _add_alert(
                        bot_id,
                        "health_critical",
                        "critical",
                        issue.get("message", "健康检查发现严重问题"),
                        {"path": issue.get("path")},
                    )
    except Exception:
        pass
