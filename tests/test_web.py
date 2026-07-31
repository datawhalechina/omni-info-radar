import asyncio
import json
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx

from repo_courier import web
from repo_courier.config import (
    AppConfig,
    RssChannelConfig,
    RssConfig,
    RssSourceConfig,
    WechatAccountConfig,
    WechatConfig,
)
from repo_courier.models import ChannelRun, Repository, RssItem


def request(app, method: str, path: str, **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def config_with_news() -> AppConfig:
    return AppConfig(
        rss=RssConfig(
            channels={
                "news": RssChannelConfig(
                    "news",
                    "科技新闻",
                    "repo_courier.prompts.news:build_messages",
                    sources=[RssSourceConfig("wired", "WIRED", "https://example.com/rss")],
                )
            }
        )
    )


def test_preview_request_cleans_interests_and_sources() -> None:
    payload = web.PreviewRequest(
        interests=[" Agent ", "agent", "developer   tools"],
        sources=[" GitHub ", "news", "news"],
    )

    assert payload.interests == ["Agent", "developer tools"]
    assert payload.sources == ["github", "news"]
    assert payload.ui_language == "zh"


def test_preview_request_accepts_only_supported_ui_languages() -> None:
    assert web.PreviewRequest(interests=["agent"], ui_language=" EN ").ui_language == "en"

    try:
        web.PreviewRequest(interests=["agent"], ui_language="fr")
    except ValueError as exc:
        assert "界面语言" in str(exc)
    else:
        raise AssertionError("不支持的界面语言应被拒绝")


def test_source_options_follow_configured_rss_channels() -> None:
    options = web.source_options(config_with_news())

    assert [option["id"] for option in options] == ["github", "news"]
    assert options[0]["default"] is True
    assert options[1]["source_count"] == 1


def test_source_options_include_wechat_only_when_accounts_are_configured() -> None:
    config = config_with_news()
    assert "wechat" not in [option["id"] for option in web.source_options(config)]

    config.wechat = WechatConfig(accounts=[WechatAccountConfig("Account", "fake-1")])
    options = web.source_options(config)

    assert [option["id"] for option in options] == ["wechat", "github", "news"]
    assert options[0]["source_count"] == 1
    assert options[0]["requires_key"] is True

    config.wechat.auth_key = "server-secret"
    assert web.source_options(config)[0]["requires_key"] is False


def test_product_display_name_removes_release_feed_suffix() -> None:
    assert web.product_display_name("Claude Code Releases") == "Claude Code"
    assert web.product_display_name("OpenAI Codex Release") == "OpenAI Codex"


def test_wechat_source_requires_request_or_server_key() -> None:
    config = config_with_news()
    config.wechat = WechatConfig(accounts=[WechatAccountConfig("Account", "fake-1")])
    payload = web.PreviewRequest(interests=["agent"], sources=["wechat"])

    try:
        web.validate_wechat_settings(payload, config)
    except ValueError as exc:
        assert "微信公众号 API Key" in str(exc)
    else:
        raise AssertionError("未配置 API Key 时微信公众号频道应被拒绝")

    request_payload = web.PreviewRequest(
        interests=["agent"], sources=["wechat"], wechat_auth_key="request-secret"
    )
    assert web.validate_wechat_settings(request_payload, config) == "request-secret"

    config.wechat.auth_key = "server-secret"
    assert web.validate_wechat_settings(payload, config) == "server-secret"


def test_generate_preview_uses_request_scoped_config(monkeypatch) -> None:
    captured = {}

    def fake_run(config, **kwargs):
        captured["config"] = config
        captured["kwargs"] = kwargs
        repository = Repository(
            rank=2,
            owner="acme",
            name="agent-kit",
            url="https://github.com/acme/agent-kit",
            stars=1_200,
            stars_today=240,
            relevance_score=72,
            recommendation="深挖",
            why_for_you="命中 agent",
            analysis_status="fallback",
            pick_rank=1,
        )
        return SimpleNamespace(repositories=[repository], rss_channels={}, scanned_count=20)

    monkeypatch.setattr(web, "load_web_config", config_with_news)
    monkeypatch.setattr(web, "run", fake_run)

    result = web.generate_preview(
        web.PreviewRequest(
            interests=["agent"],
            sources=["github"],
            github_token="github-secret",
            wechat_auth_key="wechat-secret",
        )
    )

    config = captured["config"]
    assert config.profile.interests == ["agent"]
    assert config.profile.daily_picks == 3
    assert config.profile.output_language == "zh"
    assert config.github.token == "github-secret"
    assert config.wechat.auth_key == "wechat-secret"
    assert config.repo_llm.enabled is False
    assert config.repo_llm.api_key == ""
    assert config.repo_llm.output_language == "zh"
    assert config.push.enabled is False
    assert captured["kwargs"] == {"dry_run": True, "channels": ["github"]}
    assert result["repositories"][0]["full_name"] == "acme/agent-kit"
    assert result["repositories"][0]["analysis_status"] == "fallback"
    assert result["channels"] == []
    assert result["used_ai"] is False


def test_generate_preview_serializes_rss_channels(monkeypatch) -> None:
    item = RssItem(
        channel_id="news",
        source_id="wired",
        source_name="WIRED",
        entry_id="entry",
        title="Agent news",
        url="https://example.com/news",
        summary="新闻摘要",
        recommendation_reason="命中 agent",
        published_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        relevance_score=8,
        innovation_score=7,
        analysis_status="ai",
        pick_rank=1,
    )
    channel = ChannelRun("news", "科技新闻", [item], 12, 4)

    monkeypatch.setattr(web, "load_web_config", config_with_news)
    monkeypatch.setattr(
        web,
        "run",
        lambda config, **kwargs: SimpleNamespace(
            repositories=[], rss_channels={"news": channel}, scanned_count=0
        ),
    )

    result = web.generate_preview(
        web.PreviewRequest(
            interests=["agent"],
            sources=["news"],
            ai_model="model",
            ai_api_key="secret",
        )
    )

    assert result["rss_scanned_count"] == 12
    assert result["channels"][0]["id"] == "news"
    assert result["channels"][0]["items"][0]["source_name"] == "WIRED"
    assert result["used_ai"] is True


def test_generate_preview_serializes_product_name_and_version(monkeypatch) -> None:
    item = RssItem(
        channel_id="products",
        source_id="claude-code",
        source_name="Claude Code Releases",
        entry_id="v2.1.212",
        title="v2.1.212",
        url="https://example.com/releases/v2.1.212",
        summary="Release summary",
        recommendation_reason="Matched agent.",
        analysis_status="fallback",
        pick_rank=1,
    )
    channel = ChannelRun("products", "产品更新", [item], 3, 3)
    config = config_with_news()
    config.rss.channels["products"] = RssChannelConfig(
        "products",
        "产品更新",
        "repo_courier.prompts.products:build_messages",
        sources=[RssSourceConfig("claude-code", "Claude Code Releases", "https://example.com")],
    )

    monkeypatch.setattr(web, "load_web_config", lambda: config)
    monkeypatch.setattr(
        web,
        "run",
        lambda config, **kwargs: SimpleNamespace(
            repositories=[], rss_channels={"products": channel}, scanned_count=0
        ),
    )

    result = web.generate_preview(
        web.PreviewRequest(interests=["agent"], sources=["products"], ui_language="en")
    )
    product = result["channels"][0]["items"][0]

    assert product["product_name"] == "Claude Code"
    assert product["version"] == "v2.1.212"
    assert product["title"] == "v2.1.212"


def test_unknown_source_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(web, "load_web_config", config_with_news)
    payload = web.PreviewRequest(interests=["agent"], sources=["unknown"])

    try:
        web.generate_preview(payload)
    except ValueError as exc:
        assert "未知内容频道" in str(exc)
    else:
        raise AssertionError("未配置的频道应被拒绝")


def test_ai_base_url_must_be_explicitly_allowed(monkeypatch) -> None:
    monkeypatch.delenv("REPO_COURIER_ALLOWED_AI_BASE_URLS", raising=False)
    payload = web.PreviewRequest(
        interests=["agent"],
        ai_base_url="https://internal.example/v1/chat/completions",
        ai_model="model",
        ai_api_key="secret",
    )

    try:
        web.validate_ai_settings(payload)
    except ValueError as exc:
        assert "未被当前站点允许" in str(exc)
    else:
        raise AssertionError("未在白名单中的模型地址应被拒绝")


def test_official_openai_compatible_providers_are_allowed_by_default(monkeypatch) -> None:
    monkeypatch.delenv("REPO_COURIER_ALLOWED_AI_BASE_URLS", raising=False)

    for base_url in web.OFFICIAL_AI_BASE_URLS:
        payload = web.PreviewRequest(
            interests=["agent"],
            ai_base_url=base_url,
            ai_model="provider-model",
            ai_api_key="secret",
        )
        endpoint, _, _ = web.validate_ai_settings(payload)
        assert endpoint.endswith("/chat/completions")


def test_ai_base_url_accepts_root_and_normalizes_endpoint(monkeypatch) -> None:
    monkeypatch.setenv(
        "REPO_COURIER_ALLOWED_AI_BASE_URLS",
        "https://compatible.example/v1",
    )
    payload = web.PreviewRequest(
        interests=["agent"],
        ai_base_url="https://compatible.example/v1",
        ai_model="compatible-model",
        ai_api_key="secret",
    )

    endpoint, model, key = web.validate_ai_settings(payload)

    assert endpoint == "https://compatible.example/v1/chat/completions"
    assert model == "compatible-model"
    assert key == "secret"


def test_ai_base_url_accepts_full_endpoint_from_root_allowlist(monkeypatch) -> None:
    monkeypatch.setenv(
        "REPO_COURIER_ALLOWED_AI_BASE_URLS",
        "https://compatible.example/api/v1",
    )
    payload = web.PreviewRequest(
        interests=["agent"],
        ai_base_url="https://compatible.example/api/v1/chat/completions",
        ai_model="compatible-model",
        ai_api_key="secret",
    )

    endpoint, _, _ = web.validate_ai_settings(payload)

    assert endpoint == "https://compatible.example/api/v1/chat/completions"


def test_preview_api_does_not_echo_secrets(monkeypatch) -> None:
    captured = {}

    def fake_preview(payload):
        captured["ai"] = payload.ai_api_key.get_secret_value()
        captured["github"] = payload.github_token.get_secret_value()
        return {
            "scanned_count": 20,
            "rss_scanned_count": 0,
            "repositories": [],
            "channels": [],
            "sources": ["github"],
            "used_ai": True,
        }

    monkeypatch.setattr(web, "generate_preview", fake_preview)
    response = request(
        web.create_app(),
        "POST",
        "/api/preview",
        json={
            "interests": ["agent"],
            "github_token": "github-secret",
            "ai_model": "model",
            "ai_api_key": "top-secret",
        },
    )

    assert response.status_code == 200
    assert captured == {"ai": "top-secret", "github": "github-secret"}
    assert "top-secret" not in response.text
    assert "github-secret" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_stream_preview_emits_channel_results_and_isolates_failures(monkeypatch) -> None:
    monkeypatch.setattr(web, "load_web_config", config_with_news)

    def fake_preview(payload):
        source = payload.sources[0]
        if source == "news":
            raise RuntimeError("private failure detail")
        return {
            "scanned_count": 20,
            "rss_scanned_count": 0,
            "repositories": [{"full_name": "acme/agent-kit"}],
            "channels": [],
            "sources": [source],
            "used_ai": False,
        }

    monkeypatch.setattr(web, "generate_preview", fake_preview)
    response = request(
        web.create_app(),
        "POST",
        "/api/preview/stream",
        json={"interests": ["agent"], "sources": ["github", "news"]},
    )
    events = [json.loads(line) for line in response.text.splitlines() if line]

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert events[0]["type"] == "start"
    assert {event["source"] for event in events if event["type"] == "channel_started"} == {
        "github",
        "news",
    }
    completed = [event for event in events if event["type"] == "channel_complete"]
    assert completed[0]["source"] == "github"
    assert completed[0]["result"]["repositories"][0]["full_name"] == "acme/agent-kit"
    errors = [event for event in events if event["type"] == "channel_error"]
    assert errors == [
        {
            "type": "channel_error",
            "source": "news",
            "title": "科技新闻",
            "message": "该频道暂时不可用",
        }
    ]
    assert events[-1] == {"type": "complete", "total": 2, "completed": 1, "failed": 1}
    assert "private failure detail" not in response.text


def test_stream_preview_times_out_slow_channel(monkeypatch) -> None:
    monkeypatch.setattr(web, "load_web_config", config_with_news)

    def slow_preview(payload):
        del payload
        time.sleep(0.05)
        return {}

    monkeypatch.setattr(web, "generate_preview", slow_preview)
    app = web.create_app()
    app.state.preview_channel_timeout = 0.01
    response = request(
        app,
        "POST",
        "/api/preview/stream",
        json={"interests": ["agent"], "sources": ["news"]},
    )
    events = [json.loads(line) for line in response.text.splitlines() if line]

    assert [event["type"] for event in events] == [
        "start",
        "channel_started",
        "channel_error",
        "complete",
    ]
    assert events[2]["message"] == "该频道处理超时"
    assert events[-1]["failed"] == 1


def test_stream_preview_treats_reported_upstream_failure_as_channel_error(
    monkeypatch,
) -> None:
    monkeypatch.setattr(web, "load_web_config", config_with_news)

    def failed_preview(payload):
        source = payload.sources[0]
        return {
            "scanned_count": 0,
            "rss_scanned_count": 0,
            "repositories": [],
            "channels": [
                {
                    "id": source,
                    "status": "error",
                    "message": "上游服务拒绝访问",
                    "items": [],
                }
            ],
            "sources": [source],
            "used_ai": False,
        }

    monkeypatch.setattr(web, "generate_preview", failed_preview)
    response = request(
        web.create_app(),
        "POST",
        "/api/preview/stream",
        json={"interests": ["agent"], "sources": ["news"]},
    )
    events = [json.loads(line) for line in response.text.splitlines() if line]

    assert [event["type"] for event in events] == [
        "start",
        "channel_started",
        "channel_error",
        "complete",
    ]
    assert events[2]["message"] == "上游服务拒绝访问"
    assert events[-1]["failed"] == 1


def test_stream_preview_reports_request_scoped_wechat_key_without_exposing_it(
    monkeypatch,
) -> None:
    config = config_with_news()
    config.wechat = WechatConfig(accounts=[WechatAccountConfig("Account", "fake-1")])
    monkeypatch.setattr(web, "load_web_config", lambda: config)

    def failed_preview(payload):
        assert payload.wechat_auth_key.get_secret_value() == "request-secret"
        return {
            "channels": [
                {
                    "id": "wechat",
                    "status": "error",
                    "message": "公众号接口拒绝访问",
                    "items": [],
                }
            ]
        }

    monkeypatch.setattr(web, "generate_preview", failed_preview)
    response = request(
        web.create_app(),
        "POST",
        "/api/preview/stream",
        json={
            "interests": ["agent"],
            "sources": ["wechat"],
            "wechat_auth_key": "request-secret",
        },
    )
    events = [json.loads(line) for line in response.text.splitlines() if line]

    started = next(event for event in events if event["type"] == "channel_started")
    failed = next(event for event in events if event["type"] == "channel_error")
    assert started["credential_source"] == "request"
    assert failed["credential_source"] == "request"
    assert "request-secret" not in response.text


def test_web_home_health_and_options_are_available() -> None:
    app = web.create_app()
    home = request(app, "GET", "/")
    health = request(app, "GET", "/health")
    options = request(app, "GET", "/api/options")

    assert home.status_code == 200
    assert "七个技术频道" in home.text
    assert 'id="language-toggle"' in home.text
    assert "github.com/datawhalechina/omni-info-radar" in home.text
    assert health.json() == {"status": "ok"}
    assert {source["id"] for source in options.json()["sources"]} == {
        "github",
        "news",
        "blogs",
        "academic",
        "products",
        "security",
        "wechat",
    }


def test_web_rejects_oversized_requests_without_echoing_content() -> None:
    secret = "secret-that-must-not-be-echoed"
    response = request(
        web.create_app(),
        "POST",
        "/api/preview",
        content=(secret + "x" * web.MAX_REQUEST_BYTES),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert secret not in response.text


def test_web_validation_errors_do_not_echo_secret_fields() -> None:
    github_secret = "github-secret-" + "x" * 500
    wechat_secret = "wechat-secret-" + "x" * 500
    ai_secret = "ai-secret-" + "x" * 500
    response = request(
        web.create_app(),
        "POST",
        "/api/preview",
        json={
            "interests": ["agent"],
            "github_token": github_secret,
            "wechat_auth_key": wechat_secret,
            "ai_api_key": ai_secret,
            "ai_model": "model",
        },
    )

    assert response.status_code == 422
    assert github_secret not in response.text
    assert wechat_secret not in response.text
    assert ai_secret not in response.text
    assert '"input"' not in response.text
