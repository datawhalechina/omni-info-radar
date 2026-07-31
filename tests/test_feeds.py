from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import date

import pytest

from repo_courier.config import (
    ProfileConfig,
    RepoLlmConfig,
    RssChannelConfig,
    RssDefaultsConfig,
    RssSourceConfig,
)
from repo_courier.feeds import (
    MockLlmClient,
    RssAnalyzer,
    RssPipeline,
    SearchWindow,
    TokenLimiter,
    analyze_channel_items,
    combined_score,
    load_prompt_builder,
    parse_feed,
    score_item,
)
from repo_courier.models import RssItem


def _rss_item_xml(index: int, hour: int = 1, body: str = "MCP automation") -> str:
    return f"""<item><guid>{index}</guid><title>Agent release {index}</title>
    <link>https://example.com/{index}</link><description>{body}</description>
    <category>Developer Tools</category>
    <pubDate>Sun, 12 Jul 2026 {hour:02d}:00:00 GMT</pubDate></item>"""


def _item(**overrides) -> RssItem:
    values = {
        "channel_id": "news",
        "source_id": "source",
        "source_name": "Source",
        "entry_id": "entry",
        "title": "Agent platform",
        "url": "https://example.com/item",
        "content_excerpt": "MCP automation implementation",
    }
    values.update(overrides)
    return RssItem(**values)


def test_parser_filters_by_date_before_cleaning_and_supports_atom(monkeypatch) -> None:
    window = SearchWindow.for_beijing_day(date(2026, 7, 12))
    current = _rss_item_xml(1)
    previous = _rss_item_xml(2).replace("12 Jul", "11 Jul")
    rss = f"<rss><channel>{current}{previous}</channel></rss>"
    entries = parse_feed(rss, window)
    assert [entry.entry_id for entry in entries] == ["1"]

    atom = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
    <id>release</id><title>Release</title><link href="https://example.com/release"/>
    <content>Agent release body</content><updated>2026-07-12T02:00:00Z</updated>
    </entry></feed>"""
    assert parse_feed(atom, window)[0].url == "https://example.com/release"

    def must_not_clean(value):
        raise AssertionError("日期窗口外的正文不应被处理")

    monkeypatch.setattr("repo_courier.feeds._clean_html", must_not_clean)
    outside = _rss_item_xml(3).replace("12 Jul", "11 Jul")
    assert parse_feed(f"<rss><channel>{outside}</channel></rss>", window) == []


def test_parser_streams_rule_top_ten_per_source_and_drops_missing_dates() -> None:
    window = SearchWindow.for_beijing_day(date(2026, 7, 12))
    items = "".join(
        _rss_item_xml(index, index, "MCP automation" if index <= 2 else "Database storage")
        for index in range(1, 13)
    )
    items += "<item><title>No date</title><link>https://example.com/no-date</link></item>"

    entries = parse_feed(
        f"<rss><channel>{items}</channel></rss>",
        window,
        limit=10,
        profile=ProfileConfig(interests=["mcp"], exclude_keywords=[]),
    )

    assert len(entries) == 10
    assert [entry.entry_id for entry in entries[:2]] == ["2", "1"]
    assert entries[0].rule_score == 10
    assert {entry.entry_id for entry in entries}.isdisjoint({"3", "4"})


def test_parser_truncates_large_content_after_date_filter() -> None:
    window = SearchWindow.for_beijing_day(date(2026, 7, 12))
    large = _rss_item_xml(1, body="中文正文" * 3000)

    entry = parse_feed(f"<rss><channel>{large}</channel></rss>", window)[0]

    limiter = TokenLimiter("cl100k_base", 1000)
    assert len(limiter.encoding.encode(entry.content)) <= 1000


def test_keyword_score_keeps_zero_matches_and_hard_filters_exclusions() -> None:
    profile = ProfileConfig(interests=["agent", "automation", "mcp"], exclude_keywords=[])
    item = _item(tags=["automation"])
    assert score_item(item, profile) is True
    assert item.rule_score == 60

    unrelated = _item(title="Database", content_excerpt="Storage engine")
    assert score_item(unrelated, profile) is True
    assert unrelated.rule_score == 0

    item.content_excerpt += " tutorial collection"
    profile.exclude_keywords = ["tutorial collection"]
    assert score_item(item, profile) is False


def test_technical_keywords_match_common_chinese_names_without_partial_ai_matches() -> None:
    profile = ProfileConfig(interests=["agent", "llm", "mcp", "ai"], exclude_keywords=[])
    item = _item(
        title="智能体与大语言模型的新进展",
        content_excerpt="通过模型上下文协议连接人工智能工具",
    )

    assert score_item(item, profile) is True
    assert item.matched_keywords == ["agent", "llm", "mcp", "ai"]

    unrelated = _item(title="Daily build", content_excerpt="Database availability")
    assert score_item(unrelated, ProfileConfig(interests=["ai"], exclude_keywords=[])) is True
    assert unrelated.matched_keywords == []
    assert unrelated.rule_score == 0


def test_channel_picks_cover_different_keywords_before_filling_by_score() -> None:
    class RuleAnalyzer:
        def analyze(self, item, profile):
            del item, profile

    def candidate(index, keyword, score):
        return _item(
            entry_id=str(index),
            title=f"Item {index}",
            matched_keywords=[keyword],
            rule_score=score,
        )

    items = [
        candidate(1, "ai", 100),
        candidate(2, "ai", 90),
        candidate(3, "ai", 80),
        candidate(4, "agent", 30),
        candidate(5, "mcp", 20),
    ]
    result = analyze_channel_items(
        "news",
        "科技新闻",
        items,
        {},
        ProfileConfig(interests=["agent", "mcp", "ai"], exclude_keywords=[]),
        RssDefaultsConfig(llm_candidates=4, top_k=3),
        RuleAnalyzer(),
    )

    assert [item.matched_keywords for item in result.items] == [
        ["agent"],
        ["mcp"],
        ["ai"],
    ]


def test_token_limiter_caps_complete_messages_at_one_thousand() -> None:
    builder = load_prompt_builder("repo_courier.prompts.news:build_messages")
    limiter = TokenLimiter("cl100k_base", 1000)
    item = _item(content_excerpt="这是很长的内容。" * 3000)

    messages = limiter.fit(builder, item, ProfileConfig(interests=["agent"]))

    assert limiter.count_messages(messages) <= 1000
    assert len(item.content_excerpt) < 8 * 3000


def test_token_limiter_rejects_oversized_fixed_prompt() -> None:
    def builder(item, profile):
        return [{"role": "system", "content": "固定内容" * 2000}]

    with pytest.raises(ValueError, match="固定 Prompt"):
        TokenLimiter("cl100k_base", 1000).fit(builder, _item(), ProfileConfig())


class _StreamResponse(AbstractContextManager):
    def __init__(self, text: str) -> None:
        self.text = text

    def __exit__(self, *args) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self):
        midpoint = len(self.text) // 2
        yield self.text[:midpoint].encode()
        yield self.text[midpoint:].encode()


class _FeedClient:
    def __init__(self, feeds: dict[str, str]) -> None:
        self.feeds = feeds

    def stream(self, method: str, url: str) -> _StreamResponse:
        return _StreamResponse(self.feeds[url])


def test_pipeline_applies_per_source_ten_llm_ten_and_final_five() -> None:
    feed_a = f"<rss><channel>{''.join(_rss_item_xml(i, i) for i in range(1, 13))}</channel></rss>"
    feed_b_items = "".join(_rss_item_xml(i + 20, i) for i in range(1, 13))
    feed_b = f"<rss><channel>{feed_b_items}</channel></rss>"
    channel = RssChannelConfig(
        "news",
        "科技新闻",
        "repo_courier.prompts.news:build_messages",
        sources=[
            RssSourceConfig("a", "A", "https://example.com/a"),
            RssSourceConfig("b", "B", "https://example.com/b"),
        ],
    )
    llm = RepoLlmConfig(api_key="mock", model="mock")
    pipeline = RssPipeline(
        channel,
        RssDefaultsConfig(),
        llm,
        client=_FeedClient({"https://example.com/a": feed_a, "https://example.com/b": feed_b}),
        llm_client=MockLlmClient(),
    )

    result = pipeline.run(
        ProfileConfig(interests=["agent"], exclude_keywords=[]),
        SearchWindow.for_beijing_day(date(2026, 7, 12)),
    )

    assert result.scanned_count == 20
    assert result.llm_candidate_count == 10
    assert len(result.items) == 5
    assert [item.pick_rank for item in result.items] == [1, 2, 3, 4, 5]
    assert all(item.analysis_status == "ai" for item in result.items)


def test_pipeline_isolates_source_errors_and_keeps_low_llm_relevance() -> None:
    class LowRelevanceAnalyzer:
        def analyze(self, item, profile):
            item.relevance_score = 3
            item.innovation_score = 10
            item.summary = "中文概要"
            item.recommendation_reason = "中文理由"
            item.analysis_status = "ai"

    channel = RssChannelConfig(
        "security",
        "安全资讯",
        "repo_courier.prompts.security:build_messages",
        sources=[
            RssSourceConfig("good", "Good", "https://example.com/good"),
            RssSourceConfig("bad", "Bad", "https://example.com/bad"),
        ],
    )
    client = _FeedClient(
        {
            "https://example.com/good": f"<rss><channel>{_rss_item_xml(1)}</channel></rss>",
            "https://example.com/bad": "<rss><broken>",
        }
    )
    pipeline = RssPipeline(
        channel,
        RssDefaultsConfig(),
        RepoLlmConfig(),
        client=client,
        analyzer=LowRelevanceAnalyzer(),
    )

    result = pipeline.run(
        ProfileConfig(interests=["agent"], exclude_keywords=[]),
        SearchWindow.for_beijing_day(date(2026, 7, 12)),
    )

    assert result.scanned_count == 1
    assert len(result.items) == 1
    assert result.items[0].relevance_score == 3
    assert result.items[0].analysis_status == "ai"
    assert "bad" in result.errors


def test_analyzer_invalid_response_falls_back_and_combined_score_uses_40_60() -> None:
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "{}"}}]}

    class Client:
        def post(self, *args, **kwargs):
            return Response()

    item = _item(rule_score=60)
    analyzer = RssAnalyzer(
        RepoLlmConfig(api_key="key", model="model"),
        RssDefaultsConfig(),
        load_prompt_builder("repo_courier.prompts.news:build_messages"),
        Client(),
    )
    analyzer.analyze(item, ProfileConfig(interests=["agent"]))
    assert item.analysis_status == "fallback"
    assert combined_score(item) == 60.0

    item.analysis_status = "ai"
    item.relevance_score = 8
    item.innovation_score = 7
    assert combined_score(item) == 69.6


def test_rss_fallback_supports_english_output() -> None:
    item = _item(matched_keywords=["agent"], feed_summary="Original feed summary")
    analyzer = RssAnalyzer(
        RepoLlmConfig(),
        RssDefaultsConfig(),
        load_prompt_builder("repo_courier.prompts.news:build_messages"),
    )

    analyzer.analyze(
        item,
        ProfileConfig(
            interests=["agent"],
            exclude_keywords=[],
            output_language="en",
        ),
    )

    assert item.recommendation_reason == "Matched interests: agent."
    assert item.summary == "Original feed summary"


def test_all_five_prompt_builders_are_dynamically_loadable() -> None:
    for channel in ("news", "blogs", "academic", "products", "security"):
        builder = load_prompt_builder(f"repo_courier.prompts.{channel}:build_messages")
        messages = builder(_item(channel_id=channel), ProfileConfig(interests=["agent"]))
        assert [message["role"] for message in messages] == ["system", "user"]
