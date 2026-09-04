from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Repository:
    rank: int
    owner: str
    name: str
    url: str
    description: str = ""
    language: str = "Unknown"
    stars: int = 0
    forks: int = 0
    stars_today: int = 0
    topics: list[str] = field(default_factory=list)
    license: str = ""
    homepage: str = ""
    open_issues: int = 0
    updated_at: str = ""
    readme_excerpt: str = ""
    summary: str = ""
    highlights: list[str] = field(default_factory=list)
    use_cases: list[str] = field(default_factory=list)
    category: str = "其他"
    risk_note: str = ""
    analysis_status: str = "pending"
    relevance_score: int = 0
    recommendation: str = "略过"
    why_for_you: str = ""
    matched_interests: list[str] = field(default_factory=list)
    pick_rank: int | None = None
    previous_rank: int | None = None
    is_new: bool = True

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def rank_change(self) -> str:
        if self.is_new or self.previous_rank is None:
            return "NEW"
        delta = self.previous_rank - self.rank
        if delta > 0:
            return f"↑{delta}"
        if delta < 0:
            return f"↓{abs(delta)}"
        return "—"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["full_name"] = self.full_name
        data["rank_change"] = self.rank_change
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Repository:
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value for key, value in data.items() if key in allowed})


@dataclass(slots=True)
class RssItem:
    channel_id: str
    source_id: str
    source_name: str
    entry_id: str
    title: str
    url: str
    feed_summary: str = ""
    content_excerpt: str = ""
    authors: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    published_at: datetime | None = None
    matched_keywords: list[str] = field(default_factory=list)
    excluded_keywords: list[str] = field(default_factory=list)
    rule_score: int = 0
    relevance_score: int = 0
    innovation_score: int = 0
    final_score: float = 0.0
    summary: str = ""
    recommendation_reason: str = ""
    analysis_status: str = "pending"
    pick_rank: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["published_at"] = self.published_at.isoformat() if self.published_at else None
        return data


@dataclass(slots=True)
class ChannelRun:
    channel_id: str
    title: str
    items: list[RssItem]
    scanned_count: int
    llm_candidate_count: int
    errors: dict[str, str] = field(default_factory=dict)
    # 完整已打分候选池（含入选与被淘汰的近邻负例），仅用于离线评测导出，
    # 不参与 to_dict()，因此不影响 daily.json / daily.md / daily.html 与推送。
    candidates: list[RssItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "items": [item.to_dict() for item in self.items],
            "scanned_count": self.scanned_count,
            "llm_candidate_count": self.llm_candidate_count,
            "errors": self.errors,
        }

    def candidates_to_dict(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.candidates]


@dataclass(slots=True)
class DailyReport:
    repositories: list[Repository] = field(default_factory=list)
    rss_channels: dict[str, ChannelRun] = field(default_factory=dict)
    rss_window: dict[str, str] = field(default_factory=dict)
