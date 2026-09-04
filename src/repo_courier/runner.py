from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path

from .config import AppConfig
from .feeds import BEIJING, RssPipeline, SearchWindow
from .github import GitHubClient
from .models import ChannelRun, DailyReport, Repository
from .personalize import Personalizer
from .pushers import PushResult, configured_pushers
from .report import ReportWriter
from .storage import HistoryStore
from .summary import Summarizer
from .trending import TrendingClient
from .wechat import CHANNEL_ID as WECHAT_CHANNEL_ID
from .wechat import WechatPipeline

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RunResult:
    repositories: list[Repository]
    rss_channels: dict[str, ChannelRun]
    scanned_count: int
    report_paths: dict[str, Path]
    history_path: Path | None
    push_results: list[PushResult]
    ran_github: bool
    all_repositories: list[Repository] = field(default_factory=list)
    eval_candidates_path: Path | None = None


def run(
    config: AppConfig,
    *,
    day: date | None = None,
    dry_run: bool = False,
    channels: list[str] | None = None,
) -> RunResult:
    today = datetime.now(BEIJING).date()
    rss_day = day or today
    report_day = today
    repositories: list[Repository] = []
    picks: list[Repository] = []
    history_path: Path | None = None
    if channels is None:
        run_github = config.github.enabled
        selected_rss_channels = [
            channel_id
            for channel_id, channel in config.rss.channels.items()
            if channel.enabled
        ]
        run_wechat = config.wechat.enabled
    else:
        run_github = "github" in channels
        run_wechat = WECHAT_CHANNEL_ID in channels
        selected_rss_channels = [
            channel_id
            for channel_id in channels
            if channel_id not in {"github", WECHAT_CHANNEL_ID}
        ]

    if run_github:
        logger.info("正在获取 GitHub Trending")
        repositories = TrendingClient(config.github).fetch()
        logger.info("已获取 %d 个项目，正在补充 GitHub 元数据", len(repositories))
        github = GitHubClient(config.github)
        github.enrich(repositories)

        history = HistoryStore(config.report.data_dir)
        history.apply_rank_history(repositories, today)
        picks = Personalizer(config.profile).select(repositories)
        github.enrich_readmes(picks)
        Summarizer(config.repo_llm).summarize(picks)
        history_path = history.save(repositories, today)
    else:
        logger.info("GitHub 通道未启用，跳过 GitHub Trending")

    window = SearchWindow.for_beijing_day(rss_day)
    channel_runs: dict[str, ChannelRun] = {}
    for channel_id in selected_rss_channels:
        channel = config.rss.channels[channel_id]
        if channels is not None:
            channel = replace(channel, enabled=True)
        try:
            run_result = RssPipeline(channel, config.rss.defaults, config.repo_llm).run(
                config.profile, window
            )
        except Exception as exc:  # Keep every report category independently available.
            logger.exception("RSS 专题 %s 运行失败，继续生成其他类别: %s", channel_id, exc)
            run_result = ChannelRun(channel_id, channel.title, [], 0, 0, {"pipeline": str(exc)})
        channel_runs[channel_id] = run_result

    if run_wechat:
        wechat = replace(config.wechat, enabled=True) if channels is not None else config.wechat
        try:
            run_result = WechatPipeline(wechat, config.rss.defaults, config.repo_llm).run(
                config.profile, window
            )
        except Exception as exc:  # Keep every report category independently available.
            logger.exception("微信公众号频道运行失败，继续生成其他类别: %s", exc)
            run_result = ChannelRun(
                WECHAT_CHANNEL_ID,
                wechat.title,
                [],
                0,
                0,
                {"pipeline": str(exc)},
            )
        channel_runs[WECHAT_CHANNEL_ID] = run_result

    writer = ReportWriter(config.report)
    daily = DailyReport(
        repositories=picks,
        rss_channels=channel_runs,
        rss_window=window.to_dict(),
    )
    report_paths = writer.write(daily, report_day)
    logger.info("报告已生成: %s", report_paths["markdown"])

    eval_candidates_path: Path | None = None
    if config.report.eval_dump:
        eval_candidates_path = writer.write_eval_dump(daily, repositories, report_day)
        logger.info("评测候选池已导出: %s", eval_candidates_path)

    push_results: list[PushResult] = []
    has_rss_items = any(channel.items for channel in channel_runs.values())
    if config.push.enabled and not dry_run and (picks or has_rss_items):
        title = f"RepoCourier 日报 · {report_day.isoformat()}"
        digest = writer.digest(daily, report_day, limit=config.profile.daily_picks)
        for pusher in configured_pushers(config.push):
            result = pusher.send(title, digest)
            push_results.append(result)
            log = logger.info if result.success else logger.error
            log("推送通道 %s: %s", result.channel, result.detail)
    elif config.push.enabled and not dry_run:
        logger.info("今天没有达到推荐条件的内容，跳过推送")
    return RunResult(
        repositories=picks,
        rss_channels=channel_runs,
        scanned_count=len(repositories),
        report_paths=report_paths,
        history_path=history_path,
        push_results=push_results,
        ran_github=run_github,
        all_repositories=repositories,
        eval_candidates_path=eval_candidates_path,
    )
