"""Configuration schema using Pydantic."""

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, BeforeValidator, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings

from nanobot.cron.types import CronSchedule


class Base(BaseModel):
    """Base model that accepts both camelCase and snake_case keys."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

class ChannelsConfig(Base):
    """Configuration for chat channels.

    Built-in and plugin channel configs are stored as extra fields (dicts).
    Each channel parses its own config in __init__.
    Per-channel "streaming": true enables streaming output (requires send_delta impl).
    """

    model_config = ConfigDict(extra="allow")

    send_progress: bool = True  # stream agent's text progress to the channel
    send_tool_hints: bool = False  # stream tool-call hints (e.g. read_file("…"))
    send_max_retries: int = Field(default=3, ge=0, le=10)  # Max delivery attempts (initial send included)
    transcription_provider: str = "groq"  # Voice transcription backend: "groq" or "openai"


class DreamConfig(Base):
    """Dream memory consolidation configuration."""

    _HOUR_MS = 3_600_000

    interval_h: int = Field(default=2, ge=1)  # Every 2 hours by default
    cron: str | None = Field(default=None, exclude=True)  # Legacy compatibility override
    model_override: str | None = Field(
        default=None,
        validation_alias=AliasChoices("modelOverride", "model", "model_override"),
    )  # Optional Dream-specific model override
    max_batch_size: int = Field(default=20, ge=1)  # Max history entries per run
    max_iterations: int = Field(default=10, ge=1)  # Max tool calls per Phase 2

    def build_schedule(self, timezone: str) -> CronSchedule:
        """Build the runtime schedule, preferring the legacy cron override if present."""
        if self.cron:
            return CronSchedule(kind="cron", expr=self.cron, tz=timezone)
        return CronSchedule(kind="every", every_ms=self.interval_h * self._HOUR_MS)

    def describe_schedule(self) -> str:
        """Return a human-readable summary for logs and startup output."""
        if self.cron:
            return f"cron {self.cron} (legacy)"
        hours = self.interval_h
        return f"every {hours}h"


class AgentDefaults(Base):
    """Default agent configuration."""

    workspace: str = "~/.nanobot/workspace"
    model: str = "anthropic/claude-opus-4-5"
    provider: str = (
        "auto"  # Provider name (e.g. "anthropic", "openrouter") or "auto" for auto-detection
    )
    max_tokens: int = 8192
    context_window_tokens: int = 65_536
    context_block_limit: int | None = None
    temperature: float = 0.1
    max_tool_iterations: int = 200
    max_tool_result_chars: int = 16_000
    provider_retry_mode: Literal["standard", "persistent"] = "standard"
    reasoning_effort: str | None = None  # low / medium / high / adaptive - enables LLM thinking mode
    timezone: str = "UTC"  # IANA timezone, e.g. "Asia/Shanghai", "America/New_York"
    unified_session: bool = False  # Share one session across all channels (single-user multi-device)
    dream: DreamConfig = Field(default_factory=DreamConfig)


class AgentsConfig(Base):
    """Agent configuration."""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ProviderConfig(Base):
    """LLM provider configuration."""

    api_key: str = ""
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None  # Custom headers (e.g. APP-Code for AiHubMix)
    models: list[str] = Field(default_factory=list)


def _coerce_provider_entry_list(v: Any) -> Any:
    """Normalize one provider object or a list per registry key (multi-endpoint).

    Legacy JSON uses a single object; new JSON uses an array. Loader migration
    may already wrap dicts in a list; this validator keeps both paths safe.
    """
    if v is None:
        return [{}]
    if isinstance(v, list):
        return v if v else [{}]
    return [v]


ProviderEntryList = Annotated[
    list[ProviderConfig],
    BeforeValidator(_coerce_provider_entry_list),
]


def _provider_entries(providers: "ProvidersConfig", name: str) -> list[ProviderConfig]:
    lst = getattr(providers, name, None)
    return list(lst) if lst else []


class ProvidersConfig(Base):
    """Configuration for LLM providers.

    **New format:** each registry key is a JSON array of provider blocks, e.g.
    ``"openrouter": [ {"apiKey": "...", "models": [...]}, {...} ]``.

    **Legacy format (still supported):** a single object per key,
    ``"openrouter": {"apiKey": "..."}``, is accepted in JSON and via
    :func:`nanobot.config.loader._migrate_config`; it is normalized to a
    one-element list. :class:`ProviderConfig` also runs the same coercion at
    parse time.

    Runtime matching walks each list in registry order and uses the first
    eligible block (see :meth:`Config._match_provider`).
    """

    custom: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])  # Any OpenAI-compatible endpoint
    azure_openai: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])  # Azure OpenAI (model = deployment name)
    anthropic: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])
    openai: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])
    openrouter: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])
    deepseek: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])
    groq: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])
    zhipu: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])
    dashscope: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])
    vllm: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])
    ollama: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])  # Ollama local models
    ovms: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])  # OpenVINO Model Server (OVMS)
    gemini: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])
    moonshot: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])
    minimax: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])
    mistral: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])
    stepfun: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])  # Step Fun (阶跃星辰)
    xiaomi_mimo: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])  # Xiaomi MIMO (小米)
    aihubmix: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])  # AiHubMix API gateway
    siliconflow: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])  # SiliconFlow (硅基流动)
    volcengine: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])  # VolcEngine (火山引擎)
    volcengine_coding_plan: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])  # VolcEngine Coding Plan
    byteplus: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])  # BytePlus (VolcEngine international)
    byteplus_coding_plan: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])  # BytePlus Coding Plan
    openai_codex: ProviderEntryList = Field(
        default_factory=lambda: [ProviderConfig()], exclude=True
    )  # OpenAI Codex (OAuth)
    github_copilot: ProviderEntryList = Field(
        default_factory=lambda: [ProviderConfig()], exclude=True
    )  # Github Copilot (OAuth)
    qianfan: ProviderEntryList = Field(default_factory=lambda: [ProviderConfig()])  # Qianfan (百度千帆)

    def primary(self, registry_name: str) -> ProviderConfig:
        """First provider block for *registry_name* (same as legacy single-object access).

        Use this when you only need the default/first endpoint. For multiple
        entries, access the list attribute (e.g. ``config.providers.groq``) or
        iterate.
        """
        lst = getattr(self, registry_name, None)
        if lst:
            return lst[0]
        return ProviderConfig()


class HeartbeatConfig(Base):
    """Heartbeat service configuration."""

    enabled: bool = True
    interval_s: int = 30 * 60  # 30 minutes
    keep_recent_messages: int = 8


class ApiConfig(Base):
    """OpenAI-compatible API server configuration."""

    host: str = "127.0.0.1"  # Safer default: local-only bind.
    port: int = 8900
    timeout: float = 120.0  # Per-request timeout in seconds.


class GatewayConfig(Base):
    """Gateway/server configuration."""

    host: str = "0.0.0.0"
    port: int = 18790
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)


class WebSearchConfig(Base):
    """Web search tool configuration."""

    provider: str = "duckduckgo"  # brave, tavily, duckduckgo, searxng, jina
    api_key: str = ""
    base_url: str = ""  # SearXNG base URL
    max_results: int = 5
    timeout: int = 30  # Wall-clock timeout (seconds) for search operations


class WebToolsConfig(Base):
    """Web tools configuration."""

    enable: bool = True
    proxy: str | None = (
        None  # HTTP/SOCKS5 proxy URL, e.g. "http://127.0.0.1:7890" or "socks5://127.0.0.1:1080"
    )
    search: WebSearchConfig = Field(default_factory=WebSearchConfig)


class ExecToolConfig(Base):
    """Shell exec tool configuration."""

    enable: bool = True
    timeout: int = 60
    path_append: str = ""
    sandbox: str = ""  # sandbox backend: "" (none) or "bwrap"
    allowed_env_keys: list[str] = Field(default_factory=list)  # Env var names to pass through to subprocess (e.g. ["GOPATH", "JAVA_HOME"])

class MCPServerConfig(Base):
    """MCP server connection configuration (stdio or HTTP)."""

    type: Literal["stdio", "sse", "streamableHttp"] | None = None  # auto-detected if omitted
    command: str = ""  # Stdio: command to run (e.g. "npx")
    args: list[str] = Field(default_factory=list)  # Stdio: command arguments
    env: dict[str, str] = Field(default_factory=dict)  # Stdio: extra env vars
    url: str = ""  # HTTP/SSE: endpoint URL
    headers: dict[str, str] = Field(default_factory=dict)  # HTTP/SSE: custom headers
    tool_timeout: int = 30  # seconds before a tool call is cancelled
    enabled_tools: list[str] = Field(default_factory=lambda: ["*"])  # Only register these tools; accepts raw MCP names or wrapped mcp_<server>_<tool> names; ["*"] = all tools; [] = no tools

class ToolsConfig(Base):
    """Tools configuration."""

    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    restrict_to_workspace: bool = False  # restrict all tool access to workspace directory
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)
    ssrf_whitelist: list[str] = Field(default_factory=list)  # CIDR ranges to exempt from SSRF blocking (e.g. ["100.64.0.0/10"] for Tailscale)


class Config(BaseSettings):
    """Root configuration for nanobot."""

    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)

    @property
    def workspace_path(self) -> Path:
        """Get expanded workspace path."""
        return Path(self.agents.defaults.workspace).expanduser()

    def _match_provider(
        self, model: str | None = None
    ) -> tuple["ProviderConfig | None", str | None]:
        """Match provider config and its registry name. Returns (config, spec_name)."""
        from nanobot.providers.registry import PROVIDERS, find_by_name

        forced = self.agents.defaults.provider
        if forced != "auto":
            spec = find_by_name(forced)
            if spec:
                for p in _provider_entries(self.providers, spec.name):
                    if p is not None:
                        return p, spec.name
            return None, None

        model_lower = (model or self.agents.defaults.model).lower()
        model_normalized = model_lower.replace("-", "_")
        model_prefix = model_lower.split("/", 1)[0] if "/" in model_lower else ""
        normalized_prefix = model_prefix.replace("-", "_")

        def _kw_matches(kw: str) -> bool:
            kw = kw.lower()
            return kw in model_lower or kw.replace("-", "_") in model_normalized

        def _models_list_matches(models: list[str]) -> bool:
            """True if the requested model equals a configured entry (case-insensitive; -/_ normalized)."""
            for entry in models:
                e = entry.strip().lower()
                if not e:
                    continue
                e_norm = e.replace("-", "_")
                if model_lower == e or model_normalized == e_norm:
                    return True
                if "/" in model_lower:
                    tail = model_lower.split("/", 1)[1]
                    tail_norm = tail.replace("-", "_")
                    if tail == e or tail_norm == e_norm:
                        return True
            return False

        # Explicit provider prefix wins — prevents `github-copilot/...codex` matching openai_codex.
        for spec in PROVIDERS:
            for p in _provider_entries(self.providers, spec.name):
                if not p:
                    continue
                if model_prefix and normalized_prefix == spec.name:
                    if spec.is_oauth or spec.is_local or p.api_key:
                        return p, spec.name

        # Prefer providers that explicitly list this model (providers.<name>[].models); registry order breaks ties.
        for spec in PROVIDERS:
            for p in _provider_entries(self.providers, spec.name):
                if not (p and p.models):
                    continue
                if _models_list_matches(p.models):
                    if spec.is_oauth or spec.is_local or p.api_key:
                        return p, spec.name

        # Match by keyword (order follows PROVIDERS registry)
        for spec in PROVIDERS:
            for p in _provider_entries(self.providers, spec.name):
                if p and any(_kw_matches(kw) for kw in spec.keywords):
                    if spec.is_oauth or spec.is_local or p.api_key:
                        return p, spec.name

        # Fallback: configured local providers can route models without
        # provider-specific keywords (for example plain "llama3.2" on Ollama).
        # Prefer providers whose detect_by_base_keyword matches the configured api_base
        # (e.g. Ollama's "11434" in "http://localhost:11434") over plain registry order.
        local_fallback: tuple[ProviderConfig, str] | None = None
        for spec in PROVIDERS:
            if not spec.is_local:
                continue
            for p in _provider_entries(self.providers, spec.name):
                if not (p and p.api_base):
                    continue
                if spec.detect_by_base_keyword and spec.detect_by_base_keyword in p.api_base:
                    return p, spec.name
                if local_fallback is None:
                    local_fallback = (p, spec.name)
        if local_fallback:
            return local_fallback

        # Fallback: gateways first, then others (follows registry order)
        # OAuth providers are NOT valid fallbacks — they require explicit model selection
        for spec in PROVIDERS:
            if spec.is_oauth:
                continue
            for p in _provider_entries(self.providers, spec.name):
                if p and p.api_key:
                    return p, spec.name
        return None, None

    def get_provider(self, model: str | None = None) -> ProviderConfig | None:
        """Get matched provider config (api_key, api_base, extra_headers). Falls back to first available."""
        p, _ = self._match_provider(model)
        return p

    def get_provider_name(self, model: str | None = None) -> str | None:
        """Get the registry name of the matched provider (e.g. "deepseek", "openrouter")."""
        _, name = self._match_provider(model)
        return name

    def get_api_key(self, model: str | None = None) -> str | None:
        """Get API key for the given model. Falls back to first available key."""
        p = self.get_provider(model)
        return p.api_key if p else None

    def get_api_base(self, model: str | None = None) -> str | None:
        """Get API base URL for the given model. Applies default URLs for gateway/local providers."""
        from nanobot.providers.registry import find_by_name

        p, name = self._match_provider(model)
        if p and p.api_base:
            return p.api_base
        # Only gateways get a default api_base here. Standard providers
        # resolve their base URL from the registry in the provider constructor.
        if name:
            spec = find_by_name(name)
            if spec and (spec.is_gateway or spec.is_local) and spec.default_api_base:
                return spec.default_api_base
        return None

    model_config = ConfigDict(env_prefix="NANOBOT_", env_nested_delimiter="__")
