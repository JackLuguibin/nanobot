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

# 确保可以导入console模块
_console_root = Path(__file__).parent.parent.parent
if str(_console_root) not in sys.path:
    sys.path.insert(0, str(_console_root))

import typer

from console.server.extension import (
    build_frontend,
    run_console_server,
    run_console_with_gateway,
    run_frontend_dev,
    run_full_stack,
)

__logo__ = """
  _   _      _ _         _
 | \\ | | ___| | | ___   | |
 |  \\| |/ _ \\ | |/ _ \\  | |
 | |\\  |  __/ | | (_) | |_|
 |_| \\_|\\___|_|_|\\___/  (_)
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
