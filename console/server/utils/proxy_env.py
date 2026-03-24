"""Normalize proxy-related environment variables for httpx/OpenAI clients.

httpx only accepts http(s), socks5, and socks5h proxy URL schemes. Corporate
environments often set ALL_PROXY to ``socks://host:port``, which raises
``ValueError: Unknown scheme for proxy URL``. Map the generic ``socks://``
prefix to ``socks5://`` so AsyncOpenAI/httpx can connect.
"""

from __future__ import annotations

import os

from loguru import logger

_PROXY_KEYS = frozenset(
    {
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "ftp_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "FTP_PROXY",
    }
)


def normalize_proxy_env_urls() -> None:
    """Rewrite ``socks://`` proxy URLs in the environment to ``socks5://``."""
    for key in _PROXY_KEYS:
        val = os.environ.get(key)
        if not val or not isinstance(val, str):
            continue
        stripped = val.strip()
        if not stripped.startswith("socks://"):
            continue
        fixed = "socks5://" + stripped[len("socks://") :]
        if fixed != val:
            os.environ[key] = fixed
            logger.info(
                "Normalized {} for httpx compatibility: socks:// → socks5:// (host unchanged)",
                key,
            )
