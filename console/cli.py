"""Console CLI - 独立的Web控制台启动命令。

这个模块提供独立的console命令，与nanobot核心完全分离。
用法:
    console start    - 启动web控制台
    console dev      - 启动完整开发环境 (默认: Gateway + Console + Frontend)
    console dev --frontend-only  - 只启动前端开发服务器
    console build   - 构建前端
    console run     - 启动完整stack (gateway + console)
"""

from __future__ import annotations

import sys
from pathlib import Path

# 调试/开发时强制使用本地 console 代码，避免加载 .venv 里安装的包
_repo_root = Path(__file__).resolve().parent.parent
_repo_root_str = str(_repo_root)
# 把仓库根插到 sys.path 最前，保证 import console 时命中本地包
while _repo_root_str in sys.path:
    sys.path.remove(_repo_root_str)
sys.path.insert(0, _repo_root_str)
# 若 console 已被加载（例如由其它入口先加载），则卸载以便从本地重新加载
for key in list(sys.modules.keys()):
    if key == "console" or key.startswith("console."):
        del sys.modules[key]

import typer

from console.server.extension import (
    build_frontend,
    run_console_with_gateway,
    run_frontend_dev,
    run_full_stack,
)

__logo__ = r"""
  _   _      _ _         _
 | \ | | ___| | | ___   | |
 |  \| |/ _ \ | |/ _ \  | |
 | |\  |  __/ | | (_) | |_|
 |_| \_|\___|_|_|\___/  (_)
"""

app = typer.Typer(
    name="console",
    help=f"{__logo__} Nanobot Web Console",
    no_args_is_help=True,
)


@app.command("start")
def console_start(
    port: int = typer.Option(18791, "--port", "-p", help="Console server port"),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Console server host"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open browser after starting"),
    with_gateway: bool = typer.Option(False, "--with-gateway/--gateway-only", help="Also start the gateway"),
    gateway_port: int = typer.Option(18790, "--gateway-port", help="Gateway port"),
):
    """Start the nanobot web console (and optionally the gateway)."""
    run_console_with_gateway(
        port=port,
        host=host,
        open_browser=open_browser,
        gateway_port=gateway_port if with_gateway else 0,
    )


@app.command("dev")
def console_dev(
    port: int = typer.Option(18791, "--port", "-p", help="Console server port"),
    gateway_port: int = typer.Option(18790, "--gateway-port", "-g", help="Gateway port"),
    frontend_only: bool = typer.Option(False, "--frontend-only", help="Only start frontend dev server"),
):
    """Start the nanobot console in development mode (full stack)."""
    if frontend_only:
        run_frontend_dev(port=port)
    else:
        run_full_stack(
            gateway_port=gateway_port,
            console_port=port,
            open_browser=True,
            frontend=True,
        )


@app.command("build")
def console_build():
    """Build the nanobot console frontend."""
    build_frontend()


@app.command("skills")
def console_skills(
    action: str = typer.Argument(..., help="search | install"),
    query: str = typer.Option("", "--query", "-q", help="Search query (for search)"),
    name: str = typer.Option("", "--name", "-n", help="Skill name (for install)"),
    registry_url: str = typer.Option("", "--registry", "-r", help="Registry JSON URL"),
):
    """Search or install skills from registry."""
    from console.server.extension.skills_registry import search_registry, install_skill_from_registry
    from nanobot.config.loader import get_config_path, load_config

    config_path = get_config_path()
    config = load_config(config_path)
    cfg = config.model_dump() if hasattr(config, "model_dump") else {}
    url = registry_url or (cfg.get("console") or {}).get("skills_registry_url") or ""

    if action == "search":
        skills = search_registry(query, url or None)
        if not skills:
            typer.echo("No skills found. Configure registry URL with --registry or in config.")
            raise typer.Exit(1)
        for s in skills:
            typer.echo(f"  {s.get('name', '')}: {s.get('description', '')}")
    elif action == "install":
        if not name:
            typer.echo("Use --name to specify skill to install")
            raise typer.Exit(1)
        workspace = Path(config.workspace_path)
        ok = install_skill_from_registry(name, workspace, url or None)
        if ok:
            typer.echo(f"Installed skill: {name}")
        else:
            typer.echo("Failed to install. Skill not found or already installed.")
            raise typer.Exit(1)
    else:
        typer.echo("Use 'search' or 'install'")
        raise typer.Exit(1)


@app.command("run")
def console_run(
    gateway_port: int = typer.Option(18790, "--gateway-port", "-g", help="Gateway port"),
    console_port: int = typer.Option(18791, "--console-port", "-c", help="Console server port"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open browser after starting"),
    frontend: bool = typer.Option(False, "--frontend/--no-frontend", help="Start frontend dev server"),
):
    """Start both gateway and console server."""
    run_full_stack(
        gateway_port=gateway_port,
        console_port=console_port,
        open_browser=open_browser,
        frontend=frontend,
    )


if __name__ == "__main__":
    app()
