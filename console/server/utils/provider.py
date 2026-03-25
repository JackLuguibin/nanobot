"""LLM provider factory for the console server."""

from __future__ import annotations

import os
from typing import Any

from loguru import logger

from nanobot.config.schema import ProviderConfig
from nanobot.providers.registry import find_by_name


def _make_provider(config) -> Any:
    """Create the appropriate LLM provider from config.

    Follows the new ProviderSpec registry architecture:
      - "anthropic" backend  → AnthropicProvider (native SDK)
      - "openai_compat"      → OpenAICompatProvider (unified OpenAI-compatible)
      - "azure_openai"       → AzureOpenAIProvider
      - "openai_codex"       → OpenAICodexProvider (OAuth)
    """
    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    provider = config.get_provider(model)

    # Fall back to environment variable when config has no api_key
    if provider and not provider.api_key and provider_name:
        spec = find_by_name(provider_name)
        env_key = getattr(spec, "env_key", None) if spec else None
        from_env = os.environ.get(env_key, "").strip() if env_key else ""
        if from_env:
            provider = ProviderConfig(
                api_key=from_env,
                api_base=provider.api_base,
                extra_headers=provider.extra_headers,
            )

    # OpenAI Codex — OAuth-based, special handling
    if provider_name == "openai_codex" or model.startswith("openai-codex/"):
        from nanobot.providers.openai_codex_provider import OpenAICodexProvider

        return OpenAICodexProvider(default_model=model)

    # Look up the ProviderSpec to determine backend type
    spec = find_by_name(provider_name) if provider_name else None
    backend = getattr(spec, "backend", "openai_compat") if spec else "openai_compat"

    # Anthropic — native SDK
    if backend == "anthropic":
        from nanobot.providers.anthropic_provider import AnthropicProvider

        api_key = provider.api_key if provider else None
        return AnthropicProvider(
            api_key=api_key,
            api_base=provider.api_base if provider else None,
            default_model=model,
            extra_headers=provider.extra_headers if provider else None,
        )

    # Azure OpenAI — special configuration
    if backend == "azure_openai":
        from nanobot.providers.azure_openai_provider import AzureOpenAIProvider

        if provider and provider.api_key and provider.api_base:
            return AzureOpenAIProvider(
                api_key=provider.api_key,
                api_base=provider.api_base,
                default_model=model,
            )
        logger.warning("Azure OpenAI requires api_key and api_base in config")
        # Fall through to OpenAICompat

    # OpenAI-compatible providers (custom, deepseek, gemini, mistral, openrouter, etc.)
    from nanobot.providers.openai_compat_provider import OpenAICompatProvider

    api_key = provider.api_key if provider else None
    api_base = config.get_api_base(model)  # applies default bases for known gateways
    if provider and provider.api_base:
        api_base = provider.api_base  # explicit config base takes precedence

    return OpenAICompatProvider(
        api_key=api_key,
        api_base=api_base,
        default_model=model,
        extra_headers=provider.extra_headers if provider else None,
        spec=spec,
    )
