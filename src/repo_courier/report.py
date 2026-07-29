# ruff: noqa: E501
from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

from .config import ReportConfig
from .feeds import BEIJING
from .models import ChannelRun, DailyReport, Repository, RssItem

HTML_SECTION_ORDER = (
    "wechat",
    "github",
    "academic",
    "blogs",
    "products",
    "news",
    "security",
)


class ReportWriter:
    def __init__(self, config: ReportConfig) -> None:
        self.config = config

    def write(self, report: DailyReport, day: date) -> dict[str, Path]:
        output_dir = Path(self.config.output_dir) / day.isoformat()
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = {
            "markdown": output_dir / "daily.md",
            "html": output_dir / "daily.html",
            "json": output_dir / "daily.json",
        }
        paths["markdown"].write_text(self.markdown(report, day), encoding="utf-8")
        paths["html"].write_text(self.html(report, day), encoding="utf-8")
        paths["json"].write_text(
            json.dumps(
                {
                    "date": day.isoformat(),
                    "rss_window": report.rss_window,
                    "repositories": [item.to_dict() for item in report.repositories],
                    "rss_channels": {
                        channel_id: channel.to_dict()
                        for channel_id, channel in report.rss_channels.items()
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return paths

    def markdown(self, report: DailyReport, day: date) -> str:
        lines = [
            f"# {self.config.title}",
            "",
            f"> {self._summary_line(report, day)}",
            "",
            "## GitHub 推荐",
            "",
        ]
        if not report.repositories:
            lines.extend(["本次没有入选 GitHub 项目。", ""])
        for item in report.repositories:
            lines.extend(self._repository_markdown(item))
        for channel in report.rss_channels.values():
            lines.extend([f"## {channel.title}", ""])
            lines.extend(self._channel_errors_markdown(channel))
            if not channel.items:
                lines.extend([f"本检索窗口没有入选{channel.title}内容。", ""])
            for item in channel.items:
                lines.extend(self._rss_markdown(item))
        lines.extend(["---", "", "由 RepoCourier 自动生成。", ""])
        return "\n".join(lines)

    def html(self, report: DailyReport, day: date) -> str:
        github_cards = "".join(self._repository_html(item) for item in report.repositories)
        github_section = (
            "<h1>GitHub 推荐</h1>"
            + (github_cards or "<p>本次没有入选 GitHub 项目。</p>")
        )
        channel_sections = {}
        for channel_id, channel in report.rss_channels.items():
            cards = "".join(self._rss_html(item) for item in channel.items)
            warning = ""
            if channel.errors:
                warning = (
                    '<p class="risk">部分数据源获取失败：'
                    + html.escape("、".join(channel.errors))
                    + "；其他来源不受影响。</p>"
                )
            body = cards or f"<p>本检索窗口没有入选{html.escape(channel.title)}内容。</p>"
            channel_sections[channel_id] = (
                f"<h1>{html.escape(channel.title)}</h1>{warning}{body}"
            )
        sections = []
        for channel_id in HTML_SECTION_ORDER:
            if channel_id == "github":
                sections.append(github_section)
            elif channel_id in channel_sections:
                sections.append(channel_sections.pop(channel_id))
        sections.extend(channel_sections.values())
        return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(self.config.title)}</title>
<style>body{{margin:0;background:#f6f8fa;color:#1f2328;font:15px/1.6 system-ui,sans-serif}}main{{max-width:900px;margin:auto;padding:32px 18px}}header{{padding:26px;background:#0d1117;color:white;border-radius:16px;margin-bottom:18px}}header h1{{margin:0 0 6px}}article{{display:flex;gap:18px;background:white;padding:24px;margin:14px 0;border:1px solid #d0d7de;border-radius:14px}}.rank{{font-size:32px;font-weight:800;color:#8250df}}.content{{flex:1}}h2{{margin:0}}h2 a{{color:#0969da;text-decoration:none}}small{{font-size:12px;background:#fbefff;color:#8250df;padding:3px 7px;border-radius:12px}}.why{{background:#f6f8ff;border-left:4px solid #8250df;padding:10px 12px}}.meta{{color:#59636e;margin:12px 0}}.columns{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}h3{{font-size:14px;margin-bottom:2px}}.risk{{background:#fff8c5;padding:8px 12px;border-radius:8px}}footer{{text-align:center;color:#656d76;padding:20px}}@media(max-width:600px){{.columns{{grid-template-columns:1fr}}article{{padding:16px}}}}</style></head>
<body><main><header><h1>{html.escape(self.config.title)}</h1><div>{html.escape(self._summary_line(report, day))}</div></header>
{''.join(sections)}<footer>Generated by RepoCourier</footer></main></body></html>"""

    def digest(self, report: DailyReport, day: date, limit: int = 5) -> str:
        lines = [f"📮 RepoCourier · {day.isoformat()}", ""]
        if report.repositories:
            lines.extend(["🔥 GitHub 推荐", ""])
            for item in report.repositories[:limit]:
                lines.extend(
                    [
                        f"{item.pick_rank}. [{item.recommendation}] {item.full_name}",
                        f"为什么：{item.why_for_you}",
                        (item.summary or item.description)[:120],
                        item.url,
                        "",
                    ]
                )
        for channel in report.rss_channels.values():
            if not channel.items:
                continue
            lines.extend([f"📚 {channel.title}", ""])
            for item in channel.items:
                lines.extend(
                    [
                        f"{item.pick_rank}. {item.title}",
                        f"推荐理由：{item.recommendation_reason}",
                        item.summary[:120],
                        item.url,
                        "",
                    ]
                )
        lines.append("少看榜单，多看真正与你有关的内容。")
        return "\n".join(lines)

    @staticmethod
    def _summary_line(report: DailyReport, day: date) -> str:
        parts = [day.isoformat(), f"{len(report.repositories)} 个开源项目"]
        parts.extend(f"{len(channel.items)} 条{channel.title}" for channel in report.rss_channels.values())
        return " · ".join(parts)

    @staticmethod
    def _repository_markdown(item: Repository) -> list[str]:
        return [
            f"### {item.pick_rank}. [{item.full_name}]({item.url})",
            "",
            f"`{item.recommendation}` · Trending 第 {item.rank} 名 `{item.rank_change}`",
            "",
            f"> **为什么适合你**：{item.why_for_you}",
            "",
            item.summary or item.description,
            "",
            f"**数据**：{_repository_data(item)}",
            "",
        ]

    def _rss_markdown(self, item: RssItem) -> list[str]:
        published = item.published_at.astimezone(BEIJING).date().isoformat() if item.published_at else "未知"
        keywords = "、".join(item.matched_keywords) or "无"
        title = _display_title(item, self.config.product_display_names)
        return [
            f"### {item.pick_rank}. [{title}]({item.url})",
            "",
            f"> **推荐理由**：{item.recommendation_reason}",
            "",
            item.summary,
            "",
            f"**来源**：{item.source_name} · **发布日期**：{published} · **命中词**：{keywords}",
            "",
        ]

    @staticmethod
    def _channel_errors_markdown(channel: ChannelRun) -> list[str]:
        if not channel.errors:
            return []
        return [f"> 部分数据源获取失败：{'、'.join(channel.errors)}；其他来源不受影响。", ""]

    @staticmethod
    def _repository_html(item: Repository) -> str:
        return f"""<article><div class="rank">{item.pick_rank}</div><div class="content">
        <h2><a href="{html.escape(item.url)}">{html.escape(item.full_name)}</a>
        <small>{html.escape(item.recommendation)}</small></h2>
        <p class="why"><strong>为什么适合你：</strong>{html.escape(item.why_for_you)}</p>
        <p>{html.escape(item.summary or item.description)}</p>
        <div class="meta">Trending #{item.rank} · ⭐ {item.stars:,} · 今日 +{item.stars_today:,}</div>
        </div></article>"""

    def _rss_html(self, item: RssItem) -> str:
        keywords = "、".join(item.matched_keywords) or "无"
        title = _display_title(item, self.config.product_display_names)
        return f"""<article><div class="rank">{item.pick_rank}</div><div class="content">
        <h2><a href="{html.escape(item.url)}">{html.escape(title)}</a></h2>
        <p class="why"><strong>推荐理由：</strong>{html.escape(item.recommendation_reason)}</p>
        <p>{html.escape(item.summary)}</p>
        <div class="meta">{html.escape(item.source_name)} · 命中词 {html.escape(keywords)}</div>
        </div></article>"""


def _display_title(item: RssItem, product_display_names: dict[str, str]) -> str:
    if item.channel_id != "products":
        return item.title
    product = product_display_names.get(item.source_id)
    if product is None:
        product = item.source_name.removesuffix(" Releases").strip() or item.source_id
    return f"{product}：{item.title}"


def _repository_data(item: Repository) -> str:
    parts = [
        f"⭐ {item.stars:,}",
        f"今日 +{item.stars_today:,}",
        f"Fork {item.forks:,}",
    ]
    if item.language and item.language.lower() != "unknown":
        parts.append(item.language)
    if item.license and item.license.lower() not in {"unknown", "noassertion", "other"}:
        parts.append(item.license)
    return " · ".join(parts)
