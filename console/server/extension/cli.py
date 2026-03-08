"""Console CLI extensions - 提供console启动命令的实现。

这个模块包含console启动的所有业务逻辑，作为nanobot的扩展层。
CLI命令只是轻量级入口点，实际逻辑在这里实现。
"""

from __future__ import annotations

import asyncio
import shlex
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from rich.console import Console

# 尝试导入rich console，如果不可用则使用简单的print
try:
    from rich.console import Console

    _console = Console()
except ImportError:
    _console = None


def _run_npm(args: list[str], cwd: Path, **kwargs) -> subprocess.CompletedProcess:
    """在 Windows 与 Unix 上正确执行 npm（Windows 上 npm 为 npm.cmd）。"""
    if sys.platform == "win32":
        cmd = "npm " + " ".join(shlex.quote(a) for a in args)
        return subprocess.run(cmd, cwd=cwd, shell=True, **kwargs)
    return subprocess.run(["npm"] + args, cwd=cwd, **kwargs)


def _get_console_root() -> Path:
    """获取console根目录路径。

    优先从项目根目录查找，而不是依赖__file__的相对路径，
    以便在包被安装到venv时也能正常工作。
    """
    # 首先尝试从当前工作目录向上查找项目根目录
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / "pyproject.toml").exists() and (parent / "console").exists():
            return parent / "console"

    # 回退方案：使用__file__的相对路径（适用于开发模式）
    return Path(__file__).parent.parent.parent


def _setup_sys_path() -> None:
    """设置sys.path以便导入console模块。"""
    console_root = _get_console_root()
    if str(console_root) not in sys.path:
        sys.path.insert(0, str(console_root))


def _make_provider(config) -> "any":
    """根据配置创建LLM provider。"""
    from nanobot.providers.custom_provider import CustomProvider
    from nanobot.providers.litellm_provider import LiteLLMProvider
    from nanobot.providers.openai_codex_provider import OpenAICodexProvider

    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)

    # OpenAI Codex (OAuth)
    if provider_name == "openai_codex" or model.startswith("openai-codex/"):
        return OpenAICodexProvider(default_model=model)

    # Azure OpenAI: direct Azure endpoint, deployment name as model
    if provider_name == "azure_openai" and p and p.api_key and p.api_base:
        from nanobot.providers.azure_openai_provider import AzureOpenAIProvider

        return AzureOpenAIProvider(
            api_key=p.api_key,
            api_base=p.api_base,
            default_model=model,
        )

    # Custom: direct OpenAI-compatible endpoint, bypasses LiteLLM
    if provider_name == "custom":
        return CustomProvider(
            api_key=p.api_key if p else "no-key",
            api_base=config.get_api_base(model) or "http://localhost:8000/v1",
            default_model=model,
        )

    from nanobot.providers.registry import find_by_name

    spec = find_by_name(provider_name)
    if not model.startswith("bedrock/") and not (p and p.api_key) and not (spec and spec.is_oauth):
        raise ValueError("No API key configured")

    return LiteLLMProvider(
        api_key=p.api_key if p else None,
        api_base=config.get_api_base(model),
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=provider_name,
    )


def _print(msg: str, style: str = "") -> None:
    """统一的打印输出。"""
    if _console:
        if style:
            _console.print(f"[{style}]{msg}[/{style}]")
        else:
            _console.print(msg)
    else:
        print(msg)


def _get_logo() -> str:
    """获取logo。"""
    return """
  _   _      _ _         _
 | \\ | | ___| | | ___   | |
 |  \\| |/ _ \\ | |/ _ \\  | |
 | |\\  |  __/ | | (_) | |_|
 |_| \\_|\\___|_|_|\\___/  (_)
"""


# ============================================================================
# Console Server 启动逻辑
# ============================================================================


def run_console_server(
    port: int = 18791,
    host: str = "0.0.0.0",
    open_browser: bool = True,
) -> None:
    """启动console API服务器。"""
    import uvicorn

    _setup_sys_path()

    from console.server.main import app as fastapi_app

    if open_browser:

        def open_browser_delayed():
            time.sleep(2)
            webbrowser.open(f"http://{host}:{port}")

        browser_thread = threading.Thread(target=open_browser_delayed)
        browser_thread.daemon = True
        browser_thread.start()

    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        log_level="info",
    )


def ensure_frontend_built() -> bool:
    """确保前端已构建，如果没有则构建。"""
    console_web = _get_console_root() / "web"
    dist_path = console_web / "dist"

    if dist_path.exists():
        return True

    _print("[yellow]Frontend not built. Building now...[/yellow]")
    try:
        _run_npm(["install"], console_web, check=True, capture_output=True)
        _run_npm(["run", "build"], console_web, check=True, capture_output=True)
        _print("[green]✓[/green] Frontend built")
        return True
    except subprocess.CalledProcessError as e:
        _print(f"[red]Build failed: {e}[/red]")
        return False


def check_and_run_onboard() -> None:
    """检查配置并运行onboard流程。"""
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
# Gateway 启动逻辑
# ============================================================================


def run_gateway(
    gateway_port: int = 18790,
    console_port: int = 18791,
    open_browser: bool = True,
) -> None:
    """启动gateway + console服务器。"""
    _setup_sys_path()

    check_and_run_onboard()

    _print(f"{_get_logo()} Starting nanobot full stack...")

    # 1. Start gateway in a background thread
    _print(f"[green]✓[/green] Starting gateway on port {gateway_port}...")

    def run_gateway_internal():
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

        # Try to create provider, if failed (no API key), continue in limited mode
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
            temperature=config.agents.defaults.temperature,
            max_tokens=config.agents.defaults.max_tokens,
            max_iterations=config.agents.defaults.max_tool_iterations,
            memory_window=config.agents.defaults.memory_window,
            reasoning_effort=config.agents.defaults.reasoning_effort,
            brave_api_key=config.tools.web.search.api_key or None,
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

        # Start in limited mode if no provider (no API key)
        if provider is None:

            async def run_limited():
                try:
                    await asyncio.gather(
                        channels.start_all(),
                    )
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
                await asyncio.gather(
                    agent.run(),
                    channels.start_all(),
                )
            except KeyboardInterrupt:
                _print("\nShutting down gateway...")
            finally:
                await agent.close_mcp()
                heartbeat.stop()
                cron.stop()
                agent.stop()
                await channels.stop_all()

        asyncio.run(run_full())

    # Start gateway in a daemon thread
    gateway_thread = threading.Thread(target=run_gateway_internal, daemon=True)
    gateway_thread.start()

    # Wait a bit for gateway to start
    time.sleep(2)

    # 2. Start console API server
    _print(f"[green]✓[/green] Starting console API on port {console_port}...")

    def run_console_server_thread():
        import uvicorn

        from console.server.main import app as fastapi_app

        uvicorn.run(fastapi_app, host="0.0.0.0", port=console_port, log_level="info")

    console_thread = threading.Thread(target=run_console_server_thread, daemon=True)
    console_thread.start()

    # Print startup info
    _print("\n" + "=" * 50)
    _print(f"{_get_logo()} Nanobot is running!")
    _print("=" * 50)
    _print(f"  Gateway:  http://localhost:{gateway_port}")
    _print(f"  Console:  http://localhost:{console_port}")
    _print("=" * 50)

    if open_browser:

        def open_browser_delayed():
            time.sleep(2)
            webbrowser.open(f"http://localhost:{console_port}")

        browser_thread = threading.Thread(target=open_browser_delayed, daemon=True)
        browser_thread.start()

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _print("\n[yellow]Shutting down...[/yellow]")


def run_console_with_gateway(
    port: int = 18791,
    host: str = "0.0.0.0",
    open_browser: bool = True,
    gateway_port: int = 18790,
) -> None:
    """启动console + 可选的gateway。"""
    _setup_sys_path()

    # 检查是否需要运行onboard
    if gateway_port:
        check_and_run_onboard()

    # 确保前端已构建
    _print(f"{_get_logo()} Starting nanobot console on {host}:{port}...")

    if not ensure_frontend_built():
        raise RuntimeError("Frontend build failed")

    # 如果需要同时启动gateway
    if gateway_port:
        _print(f"[green]✓[/green] Starting gateway on port {gateway_port}...")

        def run_gateway_only():
            run_gateway(gateway_port=gateway_port, console_port=port, open_browser=False)

        gateway_thread = threading.Thread(target=run_gateway_only, daemon=True)
        gateway_thread.start()
        time.sleep(2)

    # 启动FastAPI服务器
    _print(f"[green]✓[/green] Starting API server on {host}:{port}...")

    try:
        import uvicorn

        from console.server.main import app as fastapi_app

        if open_browser:

            def open_browser_delayed():
                time.sleep(2)
                webbrowser.open(f"http://{host}:{port}")

            browser_thread = threading.Thread(target=open_browser_delayed)
            browser_thread.daemon = True
            browser_thread.start()

        uvicorn.run(
            fastapi_app,
            host=host,
            port=port,
            log_level="info",
        )
    except ImportError as e:
        _print(f"[red]Error: {e}[/red]")
        _print("Install console dependencies: pip install nanobot-ai[console]")
        raise typer.Exit(1)


# ============================================================================
# Frontend 开发命令
# ============================================================================


def run_frontend_dev(port: int = 18791) -> None:
    """启动前端开发服务器。"""
    console_web = _get_console_root() / "web"

    if not (console_web / "node_modules").exists():
        _print("[yellow]Installing dependencies...[/yellow]")
        _run_npm(["install"], console_web, check=True)

    _print(f"{_get_logo()} Starting console in development mode...")

    try:
        _run_npm(["run", "dev", "--", "--port", str(port)], console_web)
    except KeyboardInterrupt:
        _print("\n[yellow]Console stopped[/yellow]")


def build_frontend() -> None:
    """构建前端。"""
    console_web = _get_console_root() / "web"

    _print(f"{_get_logo()} Building console frontend...")

    try:
        _run_npm(["install"], console_web, check=True)
        _run_npm(["run", "build"], console_web, check=True)
        _print("[green]✓[/green] Console built successfully")
    except subprocess.CalledProcessError as e:
        _print(f"[red]Build failed: {e}[/red]")
        raise


# ============================================================================
# 完整启动 (Gateway + Console + Frontend)
# ============================================================================


def run_full_stack(
    gateway_port: int = 18790,
    console_port: int = 18791,
    open_browser: bool = True,
    frontend: bool = False,
) -> None:
    """启动完整stack (gateway + console + 可选的frontend)。"""
    _setup_sys_path()

    check_and_run_onboard()

    _print(f"{_get_logo()} Starting nanobot full stack...")

    # 1. Start gateway in a background thread
    _print(f"[green]✓[/green] Starting gateway on port {gateway_port}...")

    def run_gateway_internal():
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
            temperature=config.agents.defaults.temperature,
            max_tokens=config.agents.defaults.max_tokens,
            max_iterations=config.agents.defaults.max_tool_iterations,
            memory_window=config.agents.defaults.memory_window,
            reasoning_effort=config.agents.defaults.reasoning_effort,
            brave_api_key=config.tools.web.search.api_key or None,
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
                    await asyncio.gather(
                        channels.start_all(),
                    )
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
                await asyncio.gather(
                    agent.run(),
                    channels.start_all(),
                )
            except KeyboardInterrupt:
                _print("\nShutting down gateway...")
            finally:
                await agent.close_mcp()
                heartbeat.stop()
                cron.stop()
                agent.stop()
                await channels.stop_all()

        asyncio.run(run_full())

    gateway_thread = threading.Thread(target=run_gateway_internal, daemon=True)
    gateway_thread.start()

    time.sleep(2)

    # 2. Start console API server
    _print(f"[green]✓[/green] Starting console API on port {console_port}...")

    def run_console_server_thread():
        import uvicorn

        from console.server.main import app as fastapi_app

        uvicorn.run(fastapi_app, host="0.0.0.0", port=console_port, log_level="info")

    console_thread = threading.Thread(target=run_console_server_thread, daemon=True)
    console_thread.start()

    # 3. Optionally start frontend dev server
    if frontend:
        console_web = _get_console_root() / "web"
        if not (console_web / "node_modules").exists():
            _print("[yellow]Installing frontend dependencies...[/yellow]")
            _run_npm(["install"], console_web, check=True)

        _print("[green]✓[/green] Starting frontend dev server on port 3000...")

        def run_frontend():
            _run_npm(["run", "dev", "--", "--port", "3000"], console_web)

        frontend_thread = threading.Thread(target=run_frontend, daemon=True)
        frontend_thread.start()

        _print("\n" + "=" * 50)
        _print(f"{_get_logo()} Nanobot is running!")
        _print("=" * 50)
        _print(f"  Gateway:  http://localhost:{gateway_port}")
        _print(f"  Console API: http://localhost:{console_port}")
        _print("  Frontend:  http://localhost:3000")
        _print("=" * 50)
    else:
        _print("\n" + "=" * 50)
        _print(f"{_get_logo()} Nanobot is running!")
        _print("=" * 50)
        _print(f"  Gateway:  http://localhost:{gateway_port}")
        _print(f"  Console:  http://localhost:{console_port}")
        _print("=" * 50)

        if open_browser:

            def open_browser_delayed():
                time.sleep(2)
                webbrowser.open(f"http://localhost:{console_port}")

            browser_thread = threading.Thread(target=open_browser_delayed, daemon=True)
            browser_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _print("\n[yellow]Shutting down...[/yellow]")
