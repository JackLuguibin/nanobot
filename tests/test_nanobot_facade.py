"""Tests for the Nanobot programmatic facade."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanobot.nanobot import Nanobot, RunResult


def _write_config(tmp_path: Path, overrides: dict | None = None) -> Path:
    data = {
        "providers": {"openrouter": {"apiKey": "sk-test-key"}},
        "agents": {"defaults": {"model": "openai/gpt-4.1"}},
    }
    if overrides:
        data.update(overrides)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data))
    return config_path


def test_from_config_missing_file():
    with pytest.raises(FileNotFoundError):
        Nanobot.from_config("/nonexistent/config.json")


def test_from_config_creates_instance(tmp_path):
    config_path = _write_config(tmp_path)
    bot = Nanobot.from_config(config_path, workspace=tmp_path)
    assert bot._loop is not None
    assert bot._loop.workspace == tmp_path


def test_from_config_default_path():
    from nanobot.config.schema import Config

    with patch("nanobot.config.loader.load_config") as mock_load, \
         patch("nanobot.nanobot._make_provider") as mock_prov:
        mock_load.return_value = Config()
        mock_prov.return_value = MagicMock()
        mock_prov.return_value.get_default_model.return_value = "test"
        mock_prov.return_value.generation.max_tokens = 4096
        Nanobot.from_config()
        mock_load.assert_called_once_with(None)


@pytest.mark.asyncio
async def test_run_returns_result(tmp_path):
    config_path = _write_config(tmp_path)
    bot = Nanobot.from_config(config_path, workspace=tmp_path)

    from nanobot.bus.events import OutboundMessage

    mock_response = OutboundMessage(
        channel="cli", chat_id="direct", content="Hello back!"
    )
    bot._loop.process_direct = AsyncMock(return_value=mock_response)

    result = await bot.run("hi")

    assert isinstance(result, RunResult)
    assert result.content == "Hello back!"
    bot._loop.process_direct.assert_awaited_once_with("hi", session_key="sdk:default")


@pytest.mark.asyncio
async def test_run_with_hooks(tmp_path):
    from nanobot.agent.hook import AgentHook, AgentHookContext
    from nanobot.bus.events import OutboundMessage

    config_path = _write_config(tmp_path)
    bot = Nanobot.from_config(config_path, workspace=tmp_path)

    class TestHook(AgentHook):
        async def before_iteration(self, context: AgentHookContext) -> None:
            pass

    mock_response = OutboundMessage(
        channel="cli", chat_id="direct", content="done"
    )
    bot._loop.process_direct = AsyncMock(return_value=mock_response)

    result = await bot.run("hi", hooks=[TestHook()])

    assert result.content == "done"
    assert bot._loop._extra_hooks == []


@pytest.mark.asyncio
async def test_run_hooks_restored_on_error(tmp_path):
    config_path = _write_config(tmp_path)
    bot = Nanobot.from_config(config_path, workspace=tmp_path)

    from nanobot.agent.hook import AgentHook

    bot._loop.process_direct = AsyncMock(side_effect=RuntimeError("boom"))
    original_hooks = bot._loop._extra_hooks

    with pytest.raises(RuntimeError):
        await bot.run("hi", hooks=[AgentHook()])

    assert bot._loop._extra_hooks is original_hooks


@pytest.mark.asyncio
async def test_run_none_response(tmp_path):
    config_path = _write_config(tmp_path)
    bot = Nanobot.from_config(config_path, workspace=tmp_path)
    bot._loop.process_direct = AsyncMock(return_value=None)

    result = await bot.run("hi")
    assert result.content == ""


def test_workspace_override(tmp_path):
    config_path = _write_config(tmp_path)
    custom_ws = tmp_path / "custom_workspace"
    custom_ws.mkdir()

    bot = Nanobot.from_config(config_path, workspace=custom_ws)
    assert bot._loop.workspace == custom_ws


def test_sdk_make_provider_uses_github_copilot_backend():
    from nanobot.config.schema import Config
    from nanobot.nanobot import _make_provider
    from nanobot.utils.usage import make_token_usage_jsonl_handler

    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "provider": "github-copilot",
                    "model": "github-copilot/gpt-4.1",
                }
            }
        }
    )

    captured_usage_dirs: list[Path] = []

    def traced_make_token_usage_jsonl_handler(usage_dir):
        captured_usage_dirs.append(Path(usage_dir).expanduser().resolve())
        return make_token_usage_jsonl_handler(usage_dir)

    with patch(
        "nanobot.utils.usage.make_token_usage_jsonl_handler",
        side_effect=traced_make_token_usage_jsonl_handler,
    ):
        with patch("nanobot.providers.openai_compat_provider.AsyncOpenAI"):
            provider = _make_provider(config)

    assert provider.__class__.__name__ == "GitHubCopilotProvider"
    assert len(provider.on_completion) == 1
    assert captured_usage_dirs == [config.workspace_path.resolve() / "usage"]


@pytest.mark.asyncio
async def test_run_custom_session_key(tmp_path):
    from nanobot.bus.events import OutboundMessage

    config_path = _write_config(tmp_path)
    bot = Nanobot.from_config(config_path, workspace=tmp_path)

    mock_response = OutboundMessage(
        channel="cli", chat_id="direct", content="ok"
    )
    bot._loop.process_direct = AsyncMock(return_value=mock_response)

    await bot.run("hi", session_key="user-alice")
    bot._loop.process_direct.assert_awaited_once_with("hi", session_key="user-alice")


def test_import_from_top_level():
    from nanobot import Nanobot as N, RunResult as R
    assert N is Nanobot
    assert R is RunResult


@pytest.mark.asyncio
async def test_attach_token_usage_jsonl_registers_callback_on_provider(tmp_path):
    from datetime import datetime, timezone

    from nanobot.providers.base import LLMResponse
    from nanobot.providers.openai_compat_provider import OpenAICompatProvider
    from nanobot.utils.usage import attach_token_usage_jsonl

    provider = OpenAICompatProvider(default_model="gpt-4o")
    handler = attach_token_usage_jsonl(provider, tmp_path)
    assert len(provider.on_completion) == 1
    assert provider.on_completion[0] is handler

    response = LLMResponse(
        content="ok", finish_reason="stop", usage={"prompt_tokens": 3, "completion_tokens": 1}
    )
    await handler(response, {"model": "gpt-4o"})
    date_str = datetime.now(timezone.utc).date().isoformat()
    jsonl_path = tmp_path.resolve() / "usage" / f"token_usage_{date_str}.jsonl"
    assert jsonl_path.is_file()
    payload = json.loads(jsonl_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert payload["model"] == "gpt-4o"
    assert payload["prompt_tokens"] == 3
    assert payload["completion_tokens"] == 1


def test_add_on_completion_appends_in_order():
    from nanobot.providers.base import LLMResponse
    from nanobot.providers.openai_compat_provider import OpenAICompatProvider

    provider = OpenAICompatProvider(default_model="gpt-4o")

    async def first_callback(response: LLMResponse, request_meta: dict) -> None:
        del response, request_meta

    async def second_callback(response: LLMResponse, request_meta: dict) -> None:
        del response, request_meta

    provider.add_on_completion(first_callback)
    provider.add_on_completion(second_callback)

    assert provider.on_completion == [first_callback, second_callback]


@pytest.mark.asyncio
async def test_notify_on_completion_invokes_each_callback_in_order():
    from nanobot.providers.base import LLMResponse
    from nanobot.providers.openai_compat_provider import OpenAICompatProvider

    provider = OpenAICompatProvider(default_model="gpt-4o")
    invocation_order: list[str] = []

    async def first_callback(response: LLMResponse, request_meta: dict) -> None:
        invocation_order.append("first")
        assert request_meta.get("model") == "test-model"
        assert response.usage.get("prompt_tokens") == 5

    async def second_callback(response: LLMResponse, request_meta: dict) -> None:
        invocation_order.append("second")
        assert request_meta.get("model") == "test-model"
        assert response.usage.get("prompt_tokens") == 5

    provider.add_on_completion(first_callback)
    provider.add_on_completion(second_callback)

    response = LLMResponse(content="ok", usage={"prompt_tokens": 5})
    await provider._notify_on_completion(response, {"model": "test-model"})

    assert invocation_order == ["first", "second"]
