"""Console CLI - nanobot web console启动命令。

用法:
    console run dev   - 启动开发环境 (gateway + console + 前端热更新)
    console run build - 构建前端静态文件
"""

from __future__ import annotations

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent
_repo_root_str = str(_repo_root)
while _repo_root_str in sys.path:
    sys.path.remove(_repo_root_str)
sys.path.insert(0, _repo_root_str)
for key in list(sys.modules.keys()):
    if key == "console" or key.startswith("console."):
        del sys.modules[key]

import typer

from console.server.extension.cli import run_dev, run_build

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


@app.command("dev")
def console_dev(
    gateway_port: int = typer.Option(18790, "--gateway-port", "-g", help="Gateway port"),
    console_port: int = typer.Option(18791, "--console-port", "-c", help="Console API port"),
    frontend_port: int = typer.Option(3000, "--frontend-port", "-f", help="Frontend dev server port"),
):
    """启动开发环境：gateway + console API + 前端热更新。"""
    run_dev(
        gateway_port=gateway_port,
        console_port=console_port,
        frontend_port=frontend_port,
    )


@app.command("build")
def console_build(
    gateway_port: int = typer.Option(18790, "--gateway-port", "-g", help="Gateway port"),
    console_port: int = typer.Option(18791, "--console-port", "-c", help="Console API port"),
):
    """构建前端并启动生产环境：gateway + console API（静态文件）。"""
    run_build(
        gateway_port=gateway_port,
        console_port=console_port,
    )


if __name__ == "__main__":
    app()
