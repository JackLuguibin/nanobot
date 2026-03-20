"""Console CLI - nanobot web console启动命令。

用法:
    console run dev   - 启动开发环境 (gateway + console + 前端热更新)
    console run build - 构建前端静态文件
"""

from __future__ import annotations

import sys
import threading
import time
import webbrowser
from pathlib import Path
import shlex
import subprocess
import socket
import asyncio

_repo_root = Path(__file__).resolve().parent.parent
_repo_root_str = str(_repo_root)
if _repo_root_str not in sys.path:
    sys.path.insert(0, _repo_root_str)

import typer

from console.server.utils.provider import _make_provider


# ============================================================================
# 辅助函数
# ============================================================================

try:
    from rich.console import Console
    _console = Console()
except ImportError:
    _console = None


def _print(msg: str, style: str = "") -> None:
    if _console:
        if style:
            _console.print(f"[{style}]{msg}[/{style}]")
        else:
            _console.print(msg)
    else:
        print(msg)


def _get_local_ip() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def _get_logo() -> str:
    return r"""
  _   _      _ _         _
 | \ | | ___| | | ___   | |
 |  \| |/ _ \ | |/ _ \  | |
 | |\  |  __/ | | (_) | |_|
 |_| \_|\___|_|_|\___/  (_)
"""


def _run_npm(args: list[str], cwd: Path, **kwargs) -> subprocess.CompletedProcess:
    if sys.platform == "win32":
        cmd = "npm " + " ".join(shlex.quote(a) for a in args)
        return subprocess.run(cmd, cwd=cwd, shell=True, **kwargs)
    return subprocess.run(["npm"] + args, cwd=cwd, **kwargs)


def _get_console_root() -> Path:
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / "pyproject.toml").exists() and (parent / "console").exists():
            return parent / "console"
    return Path(__file__).parent.parent.parent


def _setup_sys_path() -> None:
    console_root = _get_console_root()
    if str(console_root) not in sys.path:
        sys.path.insert(0, str(console_root))


def _open_browser_delayed(url: str) -> threading.Thread:
    def _open():
        time.sleep(2)
        webbrowser.open(url)
    t = threading.Thread(target=_open)
    t.daemon = True
    t.start()
    return t


# ============================================================================
# Gateway 内部启动逻辑
# ============================================================================


def _start_gateway_internal(gateway_port: int) -> None:
    """启动 nanobot gateway（agent + channels + cron + heartbeat）。"""
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus
    from nanobot.channels.manager import ChannelManager
    from nanobot.config.loader import load_config
    from nanobot.config.paths import get_data_dir
    from nanobot.cron.service import CronService
    from nanobot.cron.types import CronJob
    from nanobot.heartbeat.service import HeartbeatService
    from nanobot.session.manager import SessionManager
    from nanobot.utils.helpers import sync_workspace_templates

    config = load_config()
    sync_workspace_templates(config.workspace_path)
    bus = MessageBus()

    try:
        provider = _make_provider(config)
    except Exception as e:
        _print(f"[yellow]Warning: {e}[/yellow]")
        _print("[yellow]Starting in limited mode (no agent)[/yellow]")
        provider = None

    session_manager = SessionManager(config.workspace_path)

    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        context_window_tokens=config.agents.defaults.context_window_tokens,
        web_search_config=config.tools.web.search,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
    )

    async def on_cron_job(job: CronJob) -> str | None:
        from nanobot.agent.tools.cron import CronTool
        from nanobot.agent.tools.message import MessageTool

        reminder_note = (
            "[Scheduled Task] Timer finished.\n\n"
            f"Task '{job.name}' has been triggered.\n"
            f"Scheduled instruction: {job.payload.message}"
        )
        cron_tool = agent.tools.get("cron")
        cron_token = None
        if isinstance(cron_tool, CronTool):
            cron_token = cron_tool.set_cron_context(True)
        try:
            response = await agent.process_direct(
                reminder_note,
                session_key=f"cron:{job.id}",
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to or "direct",
            )
        finally:
            if isinstance(cron_tool, CronTool) and cron_token is not None:
                cron_tool.reset_cron_context(cron_token)
        message_tool = agent.tools.get("message")
        if isinstance(message_tool, MessageTool) and message_tool._sent_in_turn:
            return response
        if job.payload.deliver and job.payload.to and response:
            from nanobot.bus.events import OutboundMessage
            await bus.publish_outbound(
                OutboundMessage(
                    channel=job.payload.channel or "cli",
                    chat_id=job.payload.to,
                    content=response,
                )
            )
        return response

    cron.on_job = on_cron_job

    channels = ChannelManager(config, bus)

    def _pick_heartbeat_target():
        enabled = set(channels.enabled_channels)
        for item in session_manager.list_sessions():
            key = item.get("key") or ""
            if ":" not in key:
                continue
            channel, chat_id = key.split(":", 1)
            if channel in {"cli", "system"}:
                continue
            if channel in enabled and chat_id:
                return channel, chat_id
        return "cli", "direct"

    async def on_heartbeat_execute(tasks):
        channel, chat_id = _pick_heartbeat_target()

        async def _silent(*_args, **_kwargs):
            pass

        return await agent.process_direct(
            tasks,
            session_key="heartbeat",
            channel=channel,
            chat_id=chat_id,
            on_progress=_silent,
        )

    async def on_heartbeat_notify(response):
        from nanobot.bus.events import OutboundMessage

        channel, chat_id = _pick_heartbeat_target()
        if channel == "cli":
            return
        await bus.publish_outbound(
            OutboundMessage(channel=channel, chat_id=chat_id, content=response)
        )

    hb_cfg = config.gateway.heartbeat

    if provider is None:

        async def run_limited():
            try:
                await asyncio.gather(channels.start_all())
            except KeyboardInterrupt:
                _print("\nShutting down gateway...")
            finally:
                await channels.stop_all()

        asyncio.run(run_limited())
        return

    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        provider=provider,
        model=agent.model,
        on_execute=on_heartbeat_execute,
        on_notify=on_heartbeat_notify,
        interval_s=hb_cfg.interval_s,
        enabled=hb_cfg.enabled,
    )

    async def run_full():
        try:
            await cron.start()
            await heartbeat.start()
            await asyncio.gather(agent.run(), channels.start_all())
        except KeyboardInterrupt:
            _print("\nShutting down gateway...")
        finally:
            await agent.close_mcp()
            heartbeat.stop()
            cron.stop()
            agent.stop()
            await channels.stop_all()

    asyncio.run(run_full())


# ============================================================================
# Onboard
# ============================================================================


def _check_and_run_onboard() -> None:
    from nanobot.config.loader import get_config_path, save_config
    from nanobot.config.paths import get_workspace_path
    from nanobot.config.schema import Config
    from nanobot.utils.helpers import sync_workspace_templates

    config_path = get_config_path()
    if not config_path.exists():
        _print("[yellow]Config not found. Running onboard...[/yellow]")
        config = Config()
        save_config(config)
        _print(f"[green]✓[/green] Created config at {config_path}")

        workspace = get_workspace_path()
        if not workspace.exists():
            workspace.mkdir(parents=True, exist_ok=True)
            _print(f"[green]✓[/green] Created workspace at {workspace}")

        sync_workspace_templates(workspace)
        _print("[green]✓[/green] Onboard complete!\n")


# ============================================================================
# 公开命令
# ============================================================================


def run_dev(
    gateway_port: int = 18790,
    console_port: int = 18791,
    frontend_port: int = 3000,
) -> None:
    """启动开发环境：gateway + console API + 前端热更新。"""
    _setup_sys_path()
    _check_and_run_onboard()

    console_web = _get_console_root() / "web"
    if not (console_web / "node_modules").exists():
        _print("[yellow]Installing frontend dependencies...[/yellow]")
        _run_npm(["install"], console_web, check=True)

    _print(f"{_get_logo()} Starting nanobot in development mode...")

    # Start gateway
    _print(f"[green]✓[/green] Starting gateway on port {gateway_port}...")
    gateway_thread = threading.Thread(
        target=_start_gateway_internal,
        args=(gateway_port,),
        daemon=True,
    )
    gateway_thread.start()
    time.sleep(2)

    # Start frontend dev server
    _print(f"[green]✓[/green] Starting frontend dev server on port {frontend_port}...")

    def run_frontend():
        _run_npm(["run", "dev", "--", "--port", str(frontend_port)], console_web)

    frontend_thread = threading.Thread(target=run_frontend, daemon=True)
    frontend_thread.start()

    _print(f"[green]✓[/green] Starting console API on port {console_port}...")
    _open_browser_delayed(f"http://localhost:{frontend_port}")

    _print("\n" + "=" * 50)
    _print(f"{_get_logo()} Nanobot is running!")
    _print("=" * 50)
    _print(f"  Gateway:     http://localhost:{gateway_port}")
    _print(f"  Console API: http://localhost:{console_port}")
    _print(f"  Frontend:    http://localhost:{frontend_port}")
    if local_ip := _get_local_ip():
        _print(f"  [{local_ip}] Gateway:     http://{local_ip}:{gateway_port}")
        _print(f"  [{local_ip}] Console API: http://{local_ip}:{console_port}")
        _print(f"  [{local_ip}] Frontend:    http://{local_ip}:{frontend_port}")
    _print("=" * 50)

    try:
        import uvicorn
        uvicorn.run(
            "console.server.main:app",
            host="0.0.0.0",
            port=console_port,
            log_level="info",
            reload=True,
        )
    except KeyboardInterrupt:
        _print("\n[yellow]Shutting down...[/yellow]")


def run_build(
    gateway_port: int = 18790,
    console_port: int = 18791,
) -> None:
    """构建前端并启动生产环境：gateway + console API（静态文件）。"""
    _setup_sys_path()
    _check_and_run_onboard()

    console_web = _get_console_root() / "web"
    dist_path = console_web / "dist"

    if dist_path.exists():
        _print("[green]✓[/green] Frontend already built")
    else:
        _print("[yellow]Frontend not built. Building now...[/yellow]")
        if not (console_web / "node_modules").exists():
            _print("[yellow]Installing frontend dependencies...[/yellow]")
            _run_npm(["install"], console_web, check=True)
        try:
            _run_npm(["run", "build"], console_web, check=True)
            _print("[green]✓[/green] Frontend built successfully")
        except subprocess.CalledProcessError as e:
            _print(f"[red]Build failed: {e}[/red]")
            raise typer.Exit(1)

    _print(f"{_get_logo()} Starting nanobot in production mode...")

    # Start gateway
    _print(f"[green]✓[/green] Starting gateway on port {gateway_port}...")
    gateway_thread = threading.Thread(
        target=_start_gateway_internal,
        args=(gateway_port,),
        daemon=True,
    )
    gateway_thread.start()
    time.sleep(2)

    _print(f"[green]✓[/green] Starting console API on port {console_port}...")
    _open_browser_delayed(f"http://localhost:{console_port}")

    _print("\n" + "=" * 50)
    _print(f"{_get_logo()} Nanobot is running!")
    _print("=" * 50)
    _print(f"  Gateway:  http://localhost:{gateway_port}")
    _print(f"  Console:  http://localhost:{console_port}")
    if local_ip := _get_local_ip():
        _print(f"  [{local_ip}] Gateway:  http://{local_ip}:{gateway_port}")
        _print(f"  [{local_ip}] Console:  http://{local_ip}:{console_port}")
    _print("=" * 50)

    try:
        import uvicorn
        uvicorn.run(
            "console.server.main:app",
            host="0.0.0.0",
            port=console_port,
            log_level="info",
        )
    except KeyboardInterrupt:
        _print("\n[yellow]Shutting down...[/yellow]")
