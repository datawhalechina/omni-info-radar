from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urlsplit, urlunsplit

import tiktoken
import yaml


@dataclass(slots=True)
class GitHubConfig:
    enabled: bool = True
    token: str = ""
    language: str = ""
    spoken_language_code: str = ""
    since: str = "daily"
    limit: int = 10
    include_readme: bool = True
    readme_max_chars: int = 6000


@dataclass(slots=True)
class RepoLlmConfig:
    enabled: bool = True
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1/chat/completions"
    model: str = ""
    output_language: str = "zh"
    verify_ssl: bool = True
    timeout_seconds: float = 90.0


@dataclass(slots=True)
class ProfileConfig:
    interests: list[str] = field(default_factory=lambda: ["agent", "llm", "mcp", "ai"])
    exclude_keywords: list[str] = field(
        default_factory=lambda: ["awesome list", "interview", "tutorial collection"]
    )
    daily_picks: int = 3
    output_language: str = "zh"


@dataclass(frozen=True, slots=True)
class RssSourceConfig:
    source_id: str
    name: str
    url: str


@dataclass(slots=True)
class RssDefaultsConfig:
    max_items_per_source: int = 10
    llm_candidates: int = 10
    top_k: int = 5
    max_input_tokens: int = 1000
    token_encoding: str = "cl100k_base"
    max_analysis_workers: int = 10


@dataclass(slots=True)
class RssChannelConfig:
    channel_id: str
    title: str
    prompt: str
    enabled: bool = True
    sources: list[RssSourceConfig] = field(default_factory=list)


@dataclass(slots=True)
class RssConfig:
    defaults: RssDefaultsConfig = field(default_factory=RssDefaultsConfig)
    channels: dict[str, RssChannelConfig] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WechatAccountConfig:
    name: str
    fakeid: str


@dataclass(slots=True)
class WechatConfig:
    enabled: bool = False
    title: str = "微信公众号"
    api_base_url: str = "https://down.mptext.top/api/public/v1"
    content_api_fallback_enabled: bool = False
    verify_ssl: bool = True
    content_max_chars: int = 5000
    prompt: str = "repo_courier.prompts.wechat:build_messages"
    accounts: list[WechatAccountConfig] = field(default_factory=list)
    auth_key: str = ""


@dataclass(slots=True)
class ReportConfig:
    output_dir: str = "reports"
    data_dir: str = "data/history"
    title: str = "RepoCourier · GitHub Trending 日报"
    product_display_names: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class PushConfig:
    enabled: bool = True
    feishu_webhook: str = ""
    wecom_webhook: str = ""
    serverchan_sendkey: str = ""
    onebot_url: str = ""
    onebot_token: str = ""
    onebot_user_id: str = ""
    email_smtp_host: str = ""
    email_smtp_port: int = 465
    email_username: str = ""
    email_auth_code: str = ""
    email_to: str = ""
    email_use_ssl: bool = True


@dataclass(slots=True)
class AppConfig:
    github: GitHubConfig = field(default_factory=GitHubConfig)
    repo_llm: RepoLlmConfig = field(default_factory=RepoLlmConfig)
    profile: ProfileConfig = field(default_factory=ProfileConfig)
    rss: RssConfig = field(default_factory=RssConfig)
    wechat: WechatConfig = field(default_factory=WechatConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    push: PushConfig = field(default_factory=PushConfig)


def load_config(path: str | Path = "config/config.yaml") -> AppConfig:
    config_path = Path(path)
    data: dict[str, Any] = {}
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"配置文件根节点必须是对象: {config_path}")
        data = loaded

    github = GitHubConfig(**_known(GitHubConfig, _section(data, "github")))
    repo_llm_values = _known(RepoLlmConfig, _section(data, "repo_llm"))
    repo_llm_values.pop("api_key", None)
    repo_llm = RepoLlmConfig(**repo_llm_values)
    profile = ProfileConfig(**_known(ProfileConfig, _section(data, "profile")))
    rss = _rss_config(_section(data, "rss"))
    wechat = _wechat_config(_section(data, "wechat"))
    report = ReportConfig(**_known(ReportConfig, _section(data, "report")))
    push = PushConfig(**_known(PushConfig, _section(data, "push")))

    github.token = _env("GITHUB_TOKEN", github.token)
    repo_llm.api_key = os.getenv("REPO_LLM_API_KEY", "")
    repo_llm.base_url = _env("REPO_LLM_BASE_URL", repo_llm.base_url)
    repo_llm.model = _env("REPO_LLM_MODEL", repo_llm.model)
    wechat.auth_key = os.getenv("WECHAT_AUTH_KEY", "")
    push.feishu_webhook = _env("FEISHU_WEBHOOK", push.feishu_webhook)
    push.wecom_webhook = _env("WECOM_WEBHOOK", push.wecom_webhook)
    push.serverchan_sendkey = _env("SERVERCHAN_SENDKEY", push.serverchan_sendkey)
    push.onebot_url = _env("ONEBOT_URL", push.onebot_url)
    push.onebot_token = _env("ONEBOT_TOKEN", push.onebot_token)
    push.onebot_user_id = _env("ONEBOT_USER_ID", push.onebot_user_id)
    push.email_smtp_host = _env("EMAIL_SMTP_HOST", push.email_smtp_host)
    push.email_username = _env("EMAIL_USERNAME", push.email_username)
    push.email_auth_code = _env("EMAIL_AUTH_CODE", push.email_auth_code)
    push.email_to = _env("EMAIL_TO", push.email_to)
    smtp_port = os.getenv("EMAIL_SMTP_PORT", "")
    if smtp_port:
        push.email_smtp_port = _positive_int(smtp_port, "EMAIL_SMTP_PORT")
    use_ssl = os.getenv("EMAIL_USE_SSL", "")
    if use_ssl:
        push.email_use_ssl = _env_bool("EMAIL_USE_SSL", use_ssl)
    interests = os.getenv("REPO_COURIER_INTERESTS", "")
    if interests:
        profile.interests = [item.strip() for item in interests.split(",") if item.strip()]
    return AppConfig(
        github=github,
        repo_llm=repo_llm,
        profile=profile,
        rss=rss,
        wechat=wechat,
        report=report,
        push=push,
    )


def _wechat_config(values: dict[str, Any]) -> WechatConfig:
    scalar_values = _known(WechatConfig, values)
    scalar_values.pop("accounts", None)
    scalar_values.pop("auth_key", None)
    if "content_max_chars" in scalar_values:
        scalar_values["content_max_chars"] = _positive_int(
            scalar_values["content_max_chars"], "wechat.content_max_chars"
        )
    config = WechatConfig(**scalar_values)
    if not isinstance(config.enabled, bool):
        raise ValueError("配置 wechat.enabled 必须是布尔值")
    if not isinstance(config.content_api_fallback_enabled, bool):
        raise ValueError("配置 wechat.content_api_fallback_enabled 必须是布尔值")
    if not isinstance(config.verify_ssl, bool):
        raise ValueError("配置 wechat.verify_ssl 必须是布尔值")
    config.title = config.title.strip()
    config.api_base_url = config.api_base_url.strip().rstrip("/")
    config.prompt = config.prompt.strip()
    if not config.title or not config.api_base_url or not config.prompt:
        raise ValueError("配置 wechat 必须包含非空 title、api_base_url 和 prompt")
    if config.enabled:
        _validate_prompt(config.prompt, "wechat")

    raw_accounts = values.get("accounts", [])
    if not isinstance(raw_accounts, list):
        raise ValueError("配置 wechat.accounts 必须是数组")
    seen_fakeids: set[str] = set()
    for index, raw in enumerate(raw_accounts):
        if not isinstance(raw, dict):
            raise ValueError(f"配置 wechat.accounts[{index}] 必须是对象")
        name = str(raw.get("name") or "").strip()
        fakeid = str(raw.get("fakeid") or "").strip()
        if not name or not fakeid:
            raise ValueError(f"配置 wechat.accounts[{index}] 必须包含 name、fakeid")
        if fakeid in seen_fakeids:
            raise ValueError(f"配置 wechat.accounts 包含重复 fakeid: {fakeid}")
        seen_fakeids.add(fakeid)
        config.accounts.append(WechatAccountConfig(name=name, fakeid=fakeid))
    if config.enabled and not config.accounts:
        raise ValueError("启用 wechat 时必须至少配置一个公众号")
    return config


def _rss_config(values: dict[str, Any]) -> RssConfig:
    defaults_values = _known(RssDefaultsConfig, _section(values, "defaults"))
    for name in (
        "max_items_per_source",
        "llm_candidates",
        "top_k",
        "max_input_tokens",
        "max_analysis_workers",
    ):
        if name in defaults_values:
            defaults_values[name] = _positive_int(defaults_values[name], f"rss.defaults.{name}")
    defaults = RssDefaultsConfig(**defaults_values)
    try:
        tiktoken.get_encoding(defaults.token_encoding)
    except ValueError as exc:
        raise ValueError(f"未知的 Token encoding: {defaults.token_encoding}") from exc

    raw_channels = values.get("channels", {})
    if not isinstance(raw_channels, dict):
        raise ValueError("配置 rss.channels 必须是对象")
    channels: dict[str, RssChannelConfig] = {}
    seen_urls: set[str] = set()
    for raw_id, raw_channel in raw_channels.items():
        channel_id = str(raw_id).strip()
        if not channel_id or not isinstance(raw_channel, dict):
            raise ValueError(f"配置 rss.channels.{raw_id} 必须是对象")
        title = str(raw_channel.get("title") or "").strip()
        prompt = str(raw_channel.get("prompt") or "").strip()
        enabled = raw_channel.get("enabled", True)
        if not title or not prompt or not isinstance(enabled, bool):
            raise ValueError(
                f"配置 rss.channels.{channel_id} 必须包含 title、prompt 和布尔 enabled"
            )
        if enabled:
            _validate_prompt(prompt, channel_id)
        sources = _rss_sources(raw_channel.get("sources", []), channel_id, seen_urls)
        channels[channel_id] = RssChannelConfig(channel_id, title, prompt, enabled, sources)
    return RssConfig(defaults=defaults, channels=channels)


def _rss_sources(
    raw_sources: object, channel_id: str, seen_urls: set[str]
) -> list[RssSourceConfig]:
    if not isinstance(raw_sources, list):
        raise ValueError(f"配置 rss.channels.{channel_id}.sources 必须是数组")
    sources: list[RssSourceConfig] = []
    for index, raw in enumerate(raw_sources):
        if not isinstance(raw, dict):
            raise ValueError(f"配置 rss.channels.{channel_id}.sources[{index}] 必须是对象")
        source_id = str(raw.get("id") or raw.get("source_id") or "").strip()
        name = str(raw.get("name") or "").strip()
        url = str(raw.get("url") or "").strip()
        if not source_id or not name or not url:
            raise ValueError(
                f"配置 rss.channels.{channel_id}.sources[{index}] 必须包含 id、name、url"
            )
        normalized = _normalized_url(url)
        if normalized in seen_urls:
            continue
        seen_urls.add(normalized)
        sources.append(RssSourceConfig(source_id, name, url))
    return sources


def _validate_prompt(path: str, channel_id: str) -> None:
    module_name, separator, function_name = path.partition(":")
    if not separator or not module_name or not function_name:
        raise ValueError(f"专题 {channel_id} 的 prompt 必须使用 module:function 格式")
    try:
        function = getattr(importlib.import_module(module_name), function_name)
    except (ImportError, AttributeError) as exc:
        raise ValueError(f"专题 {channel_id} 无法加载 Prompt: {path}") from exc
    if not callable(function):
        raise ValueError(f"专题 {channel_id} 的 Prompt 不是可调用函数: {path}")


def _normalized_url(url: str) -> str:
    clean = urldefrag(url.strip())[0]
    parts = urlsplit(clean)
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, "")
    )


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    return value if isinstance(value, dict) else {}


def _known(cls: type[Any], values: dict[str, Any]) -> dict[str, Any]:
    fields = cls.__dataclass_fields__.keys()
    return {key: value for key, value in values.items() if key in fields}


def _env(name: str, default: str) -> str:
    return os.getenv(name) or default


def _env_bool(name: str, value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"环境变量 {name} 必须是布尔值，当前值: {value!r}")


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"配置 {name} 必须是正整数，当前值: {value!r}")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"配置 {name} 必须是正整数，当前值: {value!r}") from exc
    if parsed <= 0 or str(parsed) != str(value).strip():
        raise ValueError(f"配置 {name} 必须是正整数，当前值: {value!r}")
    return parsed
