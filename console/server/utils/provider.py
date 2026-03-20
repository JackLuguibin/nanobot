"""LLM provider factory for the console server."""

import os
from typing import Any

from loguru import logger

from nanobot.config.schema import ProviderConfig
from nanobot.providers.custom_provider import CustomProvider
from nanobot.providers.litellm_provider import LiteLLMProvider
from nanobot.providers.openai_codex_provider import OpenAICodexProvider
from nanobot.providers.registry import find_by_name


def _make_provider(config) -> Any:
    """Create the appropriate LLM provider from config."""
    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    provider = config.get_provider(model)

    if provider and not provider.api_key and provider_name:
        spec = find_by_name(provider_name)
        env_key = getattr(spec, "env_key", None) if spec else None
        from_env = os.environ.get(env_key, "").strip() if env_key else ""
        if from_env:
            provider = ProviderConfig(api_key=from_env, api_base=provider.api_base, extra_headers=provider.extra_headers)

    if provider_name == "openai_codex" or model.startswith("openai-codex/"):
        return OpenAICodexProvider(default_model=model)

    if provider_name == "azure_openai":
        from nanobot.providers.azure_openai_provider import AzureOpenAIProvider

        if provider and provider.api_key and provider.api_base:
            return AzureOpenAIProvider(api_key=provider.api_key, api_base=provider.api_base, default_model=model)
        logger.warning("Azure OpenAI requires api_key and api_base in config")

    if provider_name == "custom":
        return CustomProvider(
            api_key=provider.api_key if provider else "no-key",
            api_base=config.get_api_base(model) or "http://localhost:8000/v1",
            default_model=model,
        )

    return LiteLLMProvider(
        api_key=provider.api_key if provider else None,
        api_base=config.get_api_base(model),
        default_model=model,
        extra_headers=provider.extra_headers if provider else None,
        provider_name=provider_name,
    )
