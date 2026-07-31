import json
from datetime import date, datetime, timezone

from repo_courier.config import ReportConfig
from repo_courier.models import ChannelRun, DailyReport, Repository, RssItem
from repo_courier.report import ReportWriter


def _repository() -> Repository:
    return Repository(
        rank=1,
        owner="acme",
        name="rocket",
        url="https://github.com/acme/rocket",
        description="Ship applications",
        stars=1_000,
        stars_today=100,
        summary="一个快速的应用交付工具。",
        relevance_score=82,
        recommendation="深挖",
        why_for_you="命中 developer tools。",
        pick_rank=1,
    )


def _channel(channel_id: str, title: str) -> ChannelRun:
    item = RssItem(
        channel_id=channel_id,
        source_id="source",
        source_name="Source",
        entry_id=f"{channel_id}-1",
        title=f"{title}内容",
        url=f"https://example.com/{channel_id}",
        published_at=datetime(2026, 7, 12, 1, tzinfo=timezone.utc),
        matched_keywords=["agent"],
        relevance_score=8,
        innovation_score=7,
        final_score=69.6,
        summary="中文内容概要。",
        recommendation_reason="值得进一步阅读。",
        analysis_status="ai",
        pick_rank=1,
    )
    return ChannelRun(channel_id, title, [item], 10, 10)


def test_writer_outputs_sections_in_fixed_html_order(tmp_path) -> None:
    channels = dict(
        [
            ("news", _channel("news", "科技新闻")),
            ("wechat", _channel("wechat", "微信公众号")),
            ("blogs", _channel("blogs", "大厂博客")),
            ("academic", _channel("academic", "学术论文")),
            ("products", _channel("products", "AI产品更新")),
            ("security", _channel("security", "安全资讯")),
        ]
    )
    writer = ReportWriter(ReportConfig(output_dir=str(tmp_path / "reports")))

    paths = writer.write(
        DailyReport(repositories=[_repository()], rss_channels=channels),
        date(2026, 7, 12),
    )

    assert set(paths) == {"markdown", "html", "json"}
    markdown = paths["markdown"].read_text(encoding="utf-8")
    positions = [markdown.index(f"## {channel.title}") for channel in channels.values()]
    assert positions == sorted(positions)
    assert "acme/rocket" in markdown
    assert "为什么适合你" in markdown
    assert "/100" not in markdown
    assert "/10" not in markdown
    assert "许可证未知" not in markdown
    html_report = paths["html"].read_text(encoding="utf-8")
    assert "<!doctype html>" in html_report
    assert "/100" not in html_report
    assert "/10" not in html_report
    html_headings = [
        "微信公众号",
        "GitHub 推荐",
        "学术论文",
        "大厂博客",
        "AI产品更新",
        "科技新闻",
        "安全资讯",
    ]
    html_positions = [html_report.index(f"<h1>{heading}</h1>") for heading in html_headings]
    assert html_positions == sorted(html_positions)
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["repositories"][0]["full_name"] == "acme/rocket"
    assert list(payload["rss_channels"]) == list(channels)
    assert payload["rss_channels"]["academic"]["items"][0]["channel_id"] == "academic"


def test_digest_contains_github_and_rss_links() -> None:
    report = DailyReport(
        repositories=[_repository()],
        rss_channels={"news": _channel("news", "科技新闻")},
    )
    digest = ReportWriter(ReportConfig()).digest(report, date(2026, 7, 10))

    assert "https://github.com/acme/rocket" in digest
    assert "https://example.com/news" in digest
    assert "科技新闻" in digest
    assert "/100" not in digest
    assert "/10" not in digest


def test_product_titles_include_source_product_in_markdown_and_html(tmp_path) -> None:
    products = _channel("products", "产品更新")
    item = products.items[0]
    item.source_id = "claude-code"
    item.source_name = "Claude Code Releases"
    item.title = "v2.1.210"
    writer = ReportWriter(
        ReportConfig(
            output_dir=str(tmp_path / "reports"),
            product_display_names={"claude-code": "Claude 配置名称"},
        )
    )

    paths = writer.write(
        DailyReport(rss_channels={"products": products}),
        date(2026, 7, 15),
    )

    assert "[Claude 配置名称：v2.1.210]" in paths["markdown"].read_text(encoding="utf-8")
    assert "Claude 配置名称：v2.1.210" in paths["html"].read_text(encoding="utf-8")
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["rss_channels"]["products"]["items"][0]["title"] == "v2.1.210"
