from __future__ import annotations

import threading
from datetime import date, datetime

import httpx
import pytest

from repo_courier.config import (
    ProfileConfig,
    RepoLlmConfig,
    RssDefaultsConfig,
    WechatAccountConfig,
    WechatConfig,
)
from repo_courier.feeds import BEIJING, SearchWindow
from repo_courier.wechat import (
    MAX_CONTENT_FETCH_WORKERS,
    WechatArticle,
    WechatPipeline,
    _article_objects,
    _extract_article_text,
    _raise_for_status,
)


class Response:
    def __init__(self, payload=None, text: str = "", error: Exception | None = None) -> None:
        self.payload = payload
        self._text = text
        self.error = error

    @property
    def text(self) -> str:
        return self._text

    def raise_for_status(self) -> None:
        if self.error:
            raise self.error

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, articles: dict[tuple[str, int], object], contents: dict[str, object]):
        self.articles = articles
        self.contents = contents
        self.article_calls: list[tuple[str, int]] = []
        self.content_calls: list[dict[str, object]] = []

    def get(self, url, *, params, headers=None):
        if url.endswith("/article"):
            key = (str(params["fakeid"]), int(params["begin"]))
            self.article_calls.append(key)
            value = self.articles.get(key, {"articles": []})
            return value if isinstance(value, Response) else Response(value)
        article_url = str(params.get("url") or url)
        self.content_calls.append({"request_url": url, **params})
        value = self.contents[article_url]
        return value if isinstance(value, Response) else Response(text=str(value))


class RecordingAnalyzer:
    def __init__(self) -> None:
        self.items = []

    def analyze(self, item, profile) -> None:
        self.items.append(item)
        item.analysis_status = "ai"
        item.relevance_score = 8
        item.innovation_score = 7
        item.summary = "中文概要"
        item.recommendation_reason = "中文理由"


def timestamp(day: int, hour: int = 12) -> int:
    return int(datetime(2026, 7, day, hour, tzinfo=BEIJING).timestamp())


def raw_article(index: int, *, day: int = 17, title: str | None = None) -> dict[str, object]:
    return {
        "title": title or f"Article {index}",
        "link": f"https://mp.weixin.qq.com/s/{index}",
        "create_time": timestamp(day),
    }


def config(*accounts: WechatAccountConfig) -> WechatConfig:
    return WechatConfig(enabled=True, auth_key="secret", accounts=list(accounts))


def test_article_parser_supports_top_level_and_nested_shapes() -> None:
    first = raw_article(1)
    second = raw_article(2)

    assert _article_objects({"articles": [first]}) == [first]
    assert _article_objects({"data": {"list": [{"articles": [second]}]}}) == [second]
    assert _article_objects({"list": [{"articles": [first, second]}]}) == [first, second]


def test_network_policy_block_is_reported_separately_from_api_authentication() -> None:
    request = httpx.Request("GET", "https://down.mptext.top/api/public/v1/article")
    response = httpx.Response(
        403,
        request=request,
        text="您要访问的域名不在安全策略默认允许的范围内",
    )

    with pytest.raises(RuntimeError, match="网络安全策略拦截"):
        _raise_for_status(response)


def test_account_pagination_collects_all_target_day_articles_and_stops_on_old_page() -> None:
    account = WechatAccountConfig("Account", "fake-1")
    first_page = [raw_article(index) for index in range(20)]
    second_page = [raw_article(20), raw_article(21), raw_article(22, day=16)]
    client = FakeClient(
        {
            ("fake-1", 0): {"articles": first_page},
            ("fake-1", 20): {"data": {"list": [{"articles": second_page}]}},
        },
        {},
    )
    pipeline = WechatPipeline(config(account), RssDefaultsConfig(), RepoLlmConfig(), client=client)

    articles = pipeline._fetch_account_articles(
        account, SearchWindow.for_beijing_day(date(2026, 7, 17))
    )

    assert len(articles) == 22
    assert client.article_calls == [("fake-1", 0), ("fake-1", 20)]
    assert all(article.published_at.date() == date(2026, 7, 17) for article in articles)


def test_pipeline_deduplicates_urls_skips_failed_content_and_applies_channel_limits() -> None:
    one = WechatAccountConfig("One", "fake-1")
    two = WechatAccountConfig("Two", "fake-2")
    shared = raw_article(1, title="Agent release")
    second = raw_article(2, title="Database release")
    failed = raw_article(3, title="Agent failure")
    client = FakeClient(
        {
            ("fake-1", 0): {"articles": [shared, failed]},
            ("fake-2", 0): {"articles": [shared, second]},
        },
        {
            str(shared["link"]): "Agent MCP content",
            str(second["link"]): "Database content",
            str(failed["link"]): Response(text=""),
        },
    )
    analyzer = RecordingAnalyzer()
    defaults = RssDefaultsConfig(llm_candidates=1, top_k=1)
    pipeline = WechatPipeline(
        config(one, two), defaults, RepoLlmConfig(), client=client, analyzer=analyzer
    )

    result = pipeline.run(
        ProfileConfig(interests=["agent"], exclude_keywords=[]),
        SearchWindow.for_beijing_day(date(2026, 7, 17)),
    )

    assert result.scanned_count == 2
    assert result.llm_candidate_count == 1
    assert len(result.items) == 1
    assert result.items[0].url == shared["link"]
    assert result.items[0].content_excerpt == "Agent release\n\nAgent MCP content"
    assert len(analyzer.items) == 1
    assert any(key.startswith("fake-1:article:") for key in result.errors)


def test_download_content_truncates_to_configured_character_limit() -> None:
    account = WechatAccountConfig("One", "fake-1")
    article = WechatArticle(
        account,
        "Title",
        "https://mp.weixin.qq.com/s/long",
        datetime(2026, 7, 17, tzinfo=BEIJING),
    )
    client = FakeClient({}, {article.url: "文" * 6000})
    pipeline = WechatPipeline(config(account), RssDefaultsConfig(), RepoLlmConfig(), client=client)

    assert len(pipeline._download_content(article)) == 5000
    assert client.content_calls == [{"request_url": article.url}]


def test_article_text_is_extracted_from_wechat_content_without_page_chrome() -> None:
    document = """
    <html><body>
      <h1>Page title</h1>
      <section id="js_content">
        <p>First paragraph</p>
        <script>tracking()</script>
        <p>Second <strong>paragraph</strong></p>
      </section>
      <footer>Unrelated footer</footer>
    </body></html>
    """

    assert _extract_article_text(document) == (
        "First paragraph\nSecond\nparagraph"
    )


def test_article_text_falls_back_to_plain_response_content() -> None:
    assert _extract_article_text("plain article content") == "plain article content"


def test_article_text_rejects_html_without_wechat_content() -> None:
    assert _extract_article_text("<html><body>Access verification</body></html>") == ""


def test_content_api_fallback_is_disabled_by_default() -> None:
    account = WechatAccountConfig("One", "fake-1")
    article = WechatArticle(
        account,
        "Title",
        "https://mp.weixin.qq.com/s/blocked",
        datetime(2026, 7, 17, tzinfo=BEIJING),
    )
    client = FakeClient({}, {article.url: "<html><body>Access verification</body></html>"})
    pipeline = WechatPipeline(config(account), RssDefaultsConfig(), RepoLlmConfig(), client=client)

    assert pipeline._download_content(article) == ""
    assert client.content_calls == [{"request_url": article.url}]


def test_enabled_content_api_fallback_uses_html_download() -> None:
    account = WechatAccountConfig("One", "fake-1")
    article = WechatArticle(
        account,
        "Title",
        "https://mp.weixin.qq.com/s/blocked",
        datetime(2026, 7, 17, tzinfo=BEIJING),
    )

    class FallbackClient:
        def __init__(self) -> None:
            self.calls = []

        def get(self, url, *, params, headers=None):
            self.calls.append((url, params, headers))
            if url == article.url:
                return Response(text="<html><body>Access verification</body></html>")
            return Response(text='<section id="js_content"><p>Fallback content</p></section>')

    client = FallbackClient()
    wechat_config = config(account)
    wechat_config.content_api_fallback_enabled = True
    pipeline = WechatPipeline(
        wechat_config, RssDefaultsConfig(), RepoLlmConfig(), client=client
    )

    assert pipeline._download_content(article) == "Fallback content"
    assert client.calls[1][1] == {"url": article.url, "format": "html"}


def test_wechat_ssl_verification_setting_only_configures_its_http_client(monkeypatch) -> None:
    captured = {}
    fake_client = FakeClient({}, {})

    def client_factory(**kwargs):
        captured.update(kwargs)
        return fake_client

    monkeypatch.setattr("repo_courier.wechat.httpx.Client", client_factory)

    WechatPipeline(
        WechatConfig(verify_ssl=False),
        RssDefaultsConfig(),
        RepoLlmConfig(),
        analyzer=RecordingAnalyzer(),
    )

    assert captured["verify"] is False


def test_missing_auth_fails_only_when_configured_channel_has_accounts() -> None:
    account = WechatAccountConfig("One", "fake-1")
    pipeline = WechatPipeline(
        WechatConfig(enabled=True, accounts=[account]),
        RssDefaultsConfig(),
        RepoLlmConfig(),
        client=FakeClient({}, {}),
    )

    with pytest.raises(RuntimeError, match="WECHAT_AUTH_KEY"):
        pipeline.run(ProfileConfig(), SearchWindow.for_beijing_day(date(2026, 7, 17)))


def test_repeated_page_and_account_error_are_isolated() -> None:
    repeated = WechatAccountConfig("Repeated", "fake-1")
    failed = WechatAccountConfig("Failed", "fake-2")
    good = WechatAccountConfig("Good", "fake-3")
    full_page = [raw_article(index) for index in range(20)]
    client = FakeClient(
        {
            ("fake-1", 0): {"articles": full_page},
            ("fake-1", 20): {"articles": full_page},
            ("fake-2", 0): Response(error=RuntimeError("account unavailable")),
            ("fake-3", 0): {"articles": [raw_article(30)]},
        },
        {},
    )
    pipeline = WechatPipeline(
        config(repeated, failed, good), RssDefaultsConfig(), RepoLlmConfig(), client=client
    )

    articles, errors = pipeline._fetch_articles(
        SearchWindow.for_beijing_day(date(2026, 7, 17))
    )

    assert [article.account.fakeid for article in articles] == ["fake-3"]
    assert "重复分页" in errors["fake-1"]
    assert errors["fake-2"] == "account unavailable"


class ConcurrentClient:
    def __init__(self, article_accounts: int = 0, content_articles: int = 0) -> None:
        self.article_barrier = threading.Barrier(min(article_accounts, 10))
        self.content_barrier = threading.Barrier(
            min(content_articles, MAX_CONTENT_FETCH_WORKERS)
        )
        self.lock = threading.Lock()
        self.article_active = 0
        self.article_max = 0
        self.content_active = 0
        self.content_max = 0

    def get(self, url, *, params, headers=None):
        if url.endswith("/article"):
            index = int(str(params["fakeid"]).split("-")[-1])
            with self.lock:
                self.article_active += 1
                self.article_max = max(self.article_max, self.article_active)
            if index < 10:
                self.article_barrier.wait(timeout=2)
            with self.lock:
                self.article_active -= 1
            return Response({"articles": []})

        article_url = str(params.get("url") or url)
        index = int(article_url.rsplit("/", 1)[-1])
        with self.lock:
            self.content_active += 1
            self.content_max = max(self.content_max, self.content_active)
        if index < MAX_CONTENT_FETCH_WORKERS:
            self.content_barrier.wait(timeout=2)
        with self.lock:
            self.content_active -= 1
        return Response(text="content")


def test_account_and_content_fetches_are_parallel_and_bounded() -> None:
    accounts = [WechatAccountConfig(f"Account {index}", f"fake-{index}") for index in range(12)]
    client = ConcurrentClient(article_accounts=12, content_articles=12)
    pipeline = WechatPipeline(
        config(*accounts), RssDefaultsConfig(), RepoLlmConfig(), client=client
    )
    window = SearchWindow.for_beijing_day(date(2026, 7, 17))

    articles, errors = pipeline._fetch_articles(window)
    assert articles == []
    assert errors == {}
    assert client.article_max == 10

    content_articles = [
        WechatArticle(
            accounts[index],
            f"Title {index}",
            f"https://mp.weixin.qq.com/s/{index}",
            datetime(2026, 7, 17, tzinfo=BEIJING),
        )
        for index in range(12)
    ]
    items = pipeline._fetch_contents(
        content_articles, ProfileConfig(interests=[], exclude_keywords=[]), errors
    )
    assert len(items) == 12
    assert client.content_max == MAX_CONTENT_FETCH_WORKERS
