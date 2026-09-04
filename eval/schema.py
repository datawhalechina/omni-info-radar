"""统一候选记录模型与归一化：把 eval_candidates.json / data/history 拍平成可评测记录。

设计依据（见 docs/research/去噪质量评测基准.md）：
- 去噪基准需要"完整候选池"而非仅入选项，才能计算 precision/recall 与难负例；
- 记录同时保留系统各阶段打分（rule/relevance/innovation/final）与是否入选，
  以便分别评测去噪层、排序层与摘要层。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# 存入评测记录时正文截断长度（标注与指标都不需要全文，够判断即可）。
CONTENT_CAP = 1200

# Gold Set 标注字段及其取值类型（标注规范的程序化表达）。
GOLD_FIELDS: dict[str, str] = {
    "worth_pushing": "bool",  # 主标签：是否值得推送（群聊/Slack 转发测试）
    "relevance": "0-2",  # 对关注词画像的相关性
    "usefulness": "0-2",  # 决策有用性（技术受众加权，Berger 实用价值）
    "novelty_surprise": "0-2",  # 新颖性/惊喜度（超越准确性 / Berger surprise）
    "summary_faithful": "bool",  # 摘要是否忠实于源文（G-Eval consistency）
    "summary_informative": "0-2",  # 摘要信息量（G-Eval relevance/completeness）
}


def _cap(value: str) -> str:
    value = (value or "").strip()
    return value if len(value) <= CONTENT_CAP else value[: CONTENT_CAP - 1].rstrip() + "…"


@dataclass(slots=True)
class Candidate:
    """一条可评测/可标注的候选记录（跨频道统一）。"""

    item_id: str  # 按日唯一：{date}::{dedup_key}，用于 precision/recall
    dedup_key: str  # 内容唯一键（url / full_name），用于标注去重
    date: str
    kind: str  # "github" 或 rss 频道 id（news/blogs/.../wechat）
    channel: str  # 展示名
    source: str
    title: str
    url: str
    published_at: str | None
    content_excerpt: str
    matched: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    rule_score: float = 0.0
    relevance_score: float = 0.0
    innovation_score: float = 0.0
    final_score: float = 0.0
    analysis_status: str = ""
    picked: bool = False
    pick_rank: int | None = None
    summary: str = ""
    recommendation_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Candidate:
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value for key, value in data.items() if key in allowed})

    def gold_blank(self) -> dict:
        """在候选记录基础上附加空白标注字段，供人工填写。"""
        record = self.to_dict()
        record["gold"] = {name: None for name in GOLD_FIELDS}
        return record


def normalize_github(repo: dict, date: str) -> Candidate:
    full_name = repo.get("full_name") or f"{repo.get('owner')}/{repo.get('name')}"
    dedup_key = f"github::{full_name}"
    relevance = float(repo.get("relevance_score") or 0)
    return Candidate(
        item_id=f"{date}::{dedup_key}",
        dedup_key=dedup_key,
        date=date,
        kind="github",
        channel="GitHub Trending",
        source="GitHub Trending",
        title=full_name,
        url=repo.get("url", ""),
        published_at=repo.get("updated_at") or None,
        content_excerpt=_cap(
            "\n".join(
                part for part in [repo.get("description"), repo.get("readme_excerpt")] if part
            )
        ),
        matched=list(repo.get("matched_interests") or []),
        excluded=[],
        rule_score=relevance,  # GitHub 用 Personalizer 的 0-100 分作为规则分
        relevance_score=relevance,
        innovation_score=0.0,
        final_score=relevance,
        analysis_status=repo.get("analysis_status", ""),
        picked=repo.get("pick_rank") is not None,
        pick_rank=repo.get("pick_rank"),
        summary=repo.get("summary", ""),
        recommendation_reason=repo.get("why_for_you", ""),
    )


def normalize_rss(item: dict, channel_id: str, channel_title: str, date: str) -> Candidate:
    url = item.get("url") or item.get("entry_id") or ""
    dedup_key = f"{channel_id}::{url}"
    return Candidate(
        item_id=f"{date}::{dedup_key}",
        dedup_key=dedup_key,
        date=date,
        kind=channel_id,
        channel=channel_title,
        source=item.get("source_name", ""),
        title=item.get("title", ""),
        url=item.get("url", ""),
        published_at=item.get("published_at"),
        content_excerpt=_cap(
            "\n".join(
                part for part in [item.get("feed_summary"), item.get("content_excerpt")] if part
            )
        ),
        matched=list(item.get("matched_keywords") or []),
        excluded=list(item.get("excluded_keywords") or []),
        rule_score=float(item.get("rule_score") or 0),
        relevance_score=float(item.get("relevance_score") or 0),
        innovation_score=float(item.get("innovation_score") or 0),
        final_score=float(item.get("final_score") or 0),
        analysis_status=item.get("analysis_status", ""),
        picked=item.get("pick_rank") is not None,
        pick_rank=item.get("pick_rank"),
        summary=item.get("summary", ""),
        recommendation_reason=item.get("recommendation_reason", ""),
    )


def load_eval_dump(path: str | Path) -> list[Candidate]:
    """读取 reports/{date}/eval_candidates.json，返回全部候选（GitHub + 各频道）。"""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    date = payload.get("date", "")
    out: list[Candidate] = []
    github = payload.get("github") or {}
    for repo in github.get("candidates", []):
        out.append(normalize_github(repo, date))
    for channel_id, channel in (payload.get("rss_channels") or {}).items():
        for item in channel.get("candidates", []):
            out.append(normalize_rss(item, channel_id, channel.get("title", channel_id), date))
    return out


def load_history(path: str | Path) -> list[Candidate]:
    """读取 data/history/{date}.json，返回 GitHub 全量打分候选池。

    history 每次运行都会落盘（不依赖 eval_dump），因此是 GitHub 侧候选池的广覆盖来源。
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    date = payload.get("date", Path(path).stem)
    return [normalize_github(repo, date) for repo in payload.get("repositories", [])]


def write_jsonl(candidates: list[Candidate], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for candidate in candidates:
            handle.write(json.dumps(candidate.to_dict(), ensure_ascii=False) + "\n")


def read_jsonl(path: str | Path) -> list[Candidate]:
    out: list[Candidate] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                out.append(Candidate.from_dict(json.loads(line)))
    return out
