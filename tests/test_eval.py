import json
from datetime import date, datetime

from eval import agreement, collect, sample_for_annotation, schema
from repo_courier.config import (
    AppConfig,
    ProfileConfig,
    PushConfig,
    ReportConfig,
    RssChannelConfig,
    RssConfig,
    RssDefaultsConfig,
    load_config,
)
from repo_courier.feeds import RssPipeline, analyze_channel_items
from repo_courier.github import GitHubClient
from repo_courier.models import ChannelRun, DailyReport, Repository, RssItem
from repo_courier.report import ReportWriter
from repo_courier.runner import run
from repo_courier.summary import Summarizer
from repo_courier.trending import TrendingClient


class _NoopAnalyzer:
    """不改动条目（analysis_status 保持 pending → combined_score 回退到 rule_score）。"""

    def analyze(self, item, profile) -> None:  # noqa: ARG002
        return None


def _rss_item(entry_id: str, score: int) -> RssItem:
    return RssItem(
        channel_id="news",
        source_id="the-verge",
        source_name="The Verge",
        entry_id=entry_id,
        title=f"title {entry_id}",
        url=f"https://example.com/{entry_id}",
        matched_keywords=["agent"],
        rule_score=score,
    )


# --------------------------------------------------------------------------- #
# 生产侧：候选池捕获
# --------------------------------------------------------------------------- #
def test_analyze_channel_items_captures_full_candidate_pool() -> None:
    items = [_rss_item(str(i), score) for i, score in enumerate([50, 40, 30, 20, 10])]
    profile = ProfileConfig(interests=["agent"], exclude_keywords=[], daily_picks=3)
    defaults = RssDefaultsConfig(llm_candidates=4, top_k=2, max_analysis_workers=2)

    result = analyze_channel_items(
        "news", "科技新闻", items, {}, profile, defaults, _NoopAnalyzer()
    )

    # 入选项只有 top_k=2；候选池保留全部 4 条已打分候选（含 2 条近邻负例）。
    assert len(result.items) == 2
    assert len(result.candidates) == 4
    rejected = [c for c in result.candidates if c.pick_rank is None]
    assert len(rejected) == 2
    # to_dict() 不受影响：daily.json 仍只含入选项。
    assert len(result.to_dict()["items"]) == 2
    assert "candidates" not in result.to_dict()


def test_write_eval_dump_includes_rejected_candidates(tmp_path) -> None:
    picked_repo = Repository(
        rank=1, owner="a", name="agent", url="https://x/agent", relevance_score=60, pick_rank=1
    )
    rejected_repo = Repository(
        rank=2, owner="a", name="misc", url="https://x/misc", relevance_score=5
    )
    picked_item = _rss_item("p", 60)
    picked_item.pick_rank = 1
    rejected_item = _rss_item("r", 55)  # 近邻负例：分数接近但落选
    channel = ChannelRun(
        "news", "科技新闻", [picked_item], 10, 4, candidates=[picked_item, rejected_item]
    )
    report = DailyReport(
        repositories=[picked_repo],
        rss_channels={"news": channel},
        rss_window={"timezone": "Asia/Shanghai", "start": "s", "end": "e"},
    )
    writer = ReportWriter(ReportConfig(output_dir=str(tmp_path)))

    path = writer.write_eval_dump(report, [picked_repo, rejected_repo], date(2026, 8, 1))

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "eval_candidates.json"
    assert len(payload["github"]["candidates"]) == 2  # 含未入选项目
    news = payload["rss_channels"]["news"]
    assert len(news["candidates"]) == 2
    assert sum(1 for c in news["candidates"] if c["pick_rank"] is None) == 1


def test_config_eval_dump_env_override(tmp_path, monkeypatch) -> None:
    missing = tmp_path / "nope.yaml"
    assert load_config(missing).report.eval_dump is False  # 默认关闭

    monkeypatch.setenv("REPO_COURIER_EVAL_DUMP", "on")
    assert load_config(missing).report.eval_dump is True

    monkeypatch.setenv("REPO_COURIER_EVAL_DUMP", "off")
    assert load_config(missing).report.eval_dump is False


def test_runner_writes_eval_dump_when_enabled(tmp_path, monkeypatch) -> None:
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 8, 1, 9, 0, tzinfo=tz)

    repositories = [
        Repository(rank=1, owner="acme", name="css", url="https://x/css"),
        Repository(rank=8, owner="acme", name="agent", url="https://x/agent", topics=["agent"]),
    ]
    monkeypatch.setattr(TrendingClient, "fetch", lambda self: repositories)
    monkeypatch.setattr(GitHubClient, "enrich", lambda self, items: items)
    monkeypatch.setattr(GitHubClient, "enrich_readmes", lambda self, items: items)
    monkeypatch.setattr(Summarizer, "summarize", lambda self, items: items)
    monkeypatch.setattr("repo_courier.runner.datetime", FixedDateTime)
    monkeypatch.setattr(
        RssPipeline,
        "run",
        lambda self, profile, window: ChannelRun(
            self.channel.channel_id,
            self.channel.title,
            [],
            0,
            0,
            candidates=[_rss_item("e1", 30)],
        ),
    )
    config = AppConfig(
        profile=ProfileConfig(interests=["agent"], exclude_keywords=[], daily_picks=1),
        rss=RssConfig(
            channels={
                "news": RssChannelConfig(
                    "news", "科技新闻", "repo_courier.prompts.news:build_messages", True
                )
            }
        ),
        report=ReportConfig(
            output_dir=str(tmp_path / "reports"),
            data_dir=str(tmp_path / "history"),
            eval_dump=True,
        ),
        push=PushConfig(enabled=False),
    )

    result = run(config, day=date(2026, 7, 10), dry_run=True)

    assert result.eval_candidates_path is not None
    assert result.eval_candidates_path.exists()
    payload = json.loads(result.eval_candidates_path.read_text(encoding="utf-8"))
    # GitHub 候选池含未入选的 acme/css（picks 只有 acme/agent）。
    names = {c["full_name"] for c in payload["github"]["candidates"]}
    assert names == {"acme/css", "acme/agent"}
    assert len(payload["rss_channels"]["news"]["candidates"]) == 1


# --------------------------------------------------------------------------- #
# 独立侧：eval 工具包
# --------------------------------------------------------------------------- #
def test_normalize_github_and_rss() -> None:
    repo = {
        "full_name": "a/b",
        "url": "https://x/b",
        "description": "desc",
        "readme_excerpt": "readme",
        "matched_interests": ["agent"],
        "relevance_score": 60,
        "analysis_status": "ai",
        "pick_rank": 1,
        "summary": "s",
        "why_for_you": "w",
    }
    github = schema.normalize_github(repo, "2026-08-01")
    assert github.kind == "github"
    assert github.dedup_key == "github::a/b"
    assert github.rule_score == 60 and github.final_score == 60
    assert github.picked and github.matched == ["agent"]
    assert "desc" in github.content_excerpt and "readme" in github.content_excerpt

    item = {
        "source_name": "The Verge",
        "title": "t",
        "url": "https://x/n",
        "feed_summary": "fs",
        "content_excerpt": "ce",
        "matched_keywords": ["llm"],
        "excluded_keywords": [],
        "rule_score": 30,
        "relevance_score": 8,
        "innovation_score": 7,
        "final_score": 42.0,
        "pick_rank": None,
        "summary": "sum",
        "recommendation_reason": "rr",
    }
    rss = schema.normalize_rss(item, "news", "科技新闻", "2026-08-01")
    assert rss.kind == "news" and rss.channel == "科技新闻"
    assert rss.dedup_key == "news::https://x/n"
    assert not rss.picked and rss.final_score == 42.0


def test_gold_blank_has_all_fields() -> None:
    candidate = schema.normalize_github({"full_name": "a/b", "url": "u"}, "2026-08-01")
    record = candidate.gold_blank()
    assert set(record["gold"]) == set(schema.GOLD_FIELDS)
    assert all(value is None for value in record["gold"].values())


def test_collect_aggregates_and_dedups(tmp_path) -> None:
    reports = tmp_path / "reports"
    (reports / "2026-08-01").mkdir(parents=True)
    dump = {
        "date": "2026-08-01",
        "rss_window": {},
        "github": {
            "scanned_count": 1,
            "candidates": [
                {"full_name": "a/b", "url": "u", "relevance_score": 55, "pick_rank": 1}
            ],
        },
        "rss_channels": {
            "news": {
                "title": "科技新闻",
                "scanned_count": 3,
                "llm_candidate_count": 2,
                "candidates": [
                    {"source_name": "S", "title": "t", "url": "http://x", "rule_score": 30,
                     "final_score": 30, "pick_rank": 1, "matched_keywords": ["agent"]}
                ],
                "errors": {},
            }
        },
    }
    (reports / "2026-08-01" / "eval_candidates.json").write_text(
        json.dumps(dump), encoding="utf-8"
    )
    history = tmp_path / "history"
    history.mkdir()
    (history / "2026-08-01.json").write_text(
        json.dumps(
            {"date": "2026-08-01",
             "repositories": [{"full_name": "a/b", "url": "u", "relevance_score": 55,
                               "pick_rank": 1}]}
        ),
        encoding="utf-8",
    )

    candidates = collect.collect(reports, history)

    # GitHub 同日出现在 dump 与 history，按 item_id 去重为 1；外加 1 条 news。
    assert len(candidates) == 2
    assert {c.kind for c in candidates} == {"github", "news"}


def _candidate(dedup: str, final: float, picked: bool, rank=None) -> schema.Candidate:
    return schema.Candidate(
        item_id=f"2026-08-01::{dedup}",
        dedup_key=dedup,
        date="2026-08-01",
        kind="news",
        channel="科技新闻",
        source="S",
        title=dedup,
        url=f"https://x/{dedup}",
        published_at=None,
        content_excerpt="",
        final_score=final,
        picked=picked,
        pick_rank=rank,
    )


def test_sample_forces_near_miss_pair() -> None:
    candidates = [
        _candidate("picked", 30.0, True, 1),
        _candidate("near_miss", 30.0, False),  # 同分落选 → 必须被强制纳入
        _candidate("far", 5.0, False),
    ]
    selected = sample_for_annotation.sample(candidates, per_kind=10, seed=1)
    keys = {c.dedup_key for c in selected}
    assert {"picked", "near_miss"} <= keys


def test_cohen_kappa_known_value() -> None:
    kappa, po, n = agreement.cohen_kappa(
        [True, True, False, False], [True, False, False, False]
    )
    assert n == 4
    assert po == 0.75
    assert abs(kappa - 0.5) < 1e-9

    perfect, _, _ = agreement.cohen_kappa([1, 1, 0], [1, 1, 0])
    assert perfect == 1.0
