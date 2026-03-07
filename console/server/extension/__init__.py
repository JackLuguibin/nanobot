"""Nanobot extensions for console.

这个目录包含对nanobot核心功能的扩展和补丁。
所有对nanobot核心的定制都应该放在这里，保持nanobot本身的独立性。
"""

from console.server.extension.cli import (
    build_frontend,
    run_console_server,
    run_console_with_gateway,
    run_frontend_dev,
    run_full_stack,
)

__all__ = [
    "run_console_server",
    "run_console_with_gateway",
    "run_frontend_dev",
    "build_frontend",
    "run_full_stack",
]

# 扩展模块说明：
# - cli.py     : Console CLI扩展（启动命令实现）
# - agent.py     : 扩展Agent相关功能
# - channels.py : 扩展通道管理功能
# - providers.py : 扩展LLM Provider功能
# - session.py  : 扩展会话管理功能
# - config.py   : 扩展配置加载功能
