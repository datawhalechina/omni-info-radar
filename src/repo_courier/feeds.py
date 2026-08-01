from __future__ import annotations

import importlib
import json
import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import httpx
import tiktoken
from bs4 import BeautifulSoup
from json_repair import repair_json

from .config import (
    ProfileConfig,
    RepoLlmConfig,
    RssChannelConfig,
    RssDefaultsConfig,
    RssSourceConfig,
)
from .matching import contains, interest_terms, normalize
from .models import ChannelRun, RssItem

logger = logging.getLogger(__name__)

BEIJING = ZoneInfo("Asia/Shanghai")
USER_AGENT = "RepoCourier/0.1 (unified RSS reader)"
MESSAGE_OVERHEAD_TOKENS = 32
PromptBuilder = Callable[[RssItem, ProfileConfig], list[dict[str, str]]]


@dataclass(frozen=True, slots=True)
class SearchWindow:
    start: datetime
    end: datetime

    @classmethod
    def for_beijing_day(cls, day: date) -> SearchWindow:
        return cls(
            datetime.combine(day, time.min, tzinfo=BEIJING),
            datetime.combine(day, time.max.replace(microsecond=0), tzinfo=BEIJING),
        )

    @property
    def start_utc(self) -> datetime:
        return self.start.astimezone(timezone.utc)

    @property
    def end_utc(self) -> datetime:
        return self.end.astimezone(timezone.utc)

    def contains(self, value: datetime) -> bool:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return self.start_utc <= value.astimezone(timezone.utc) <= self.end_utc

    def to_dict(self) -> dict[str, str]:
        return {
            "timezone": "Asia/Shanghai",
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
        }


class LlmResponse(Protocol):
    def raise_for_status(self) -> None: ...

    def json(self) -> object: ...


class LlmClient(Protocol):
    def post(
        self, url: str, *, headers: dict[str, str], json: dict[str, object]
    ) -> LlmResponse: ...


@dataclass(slots=True)
class _MockResponse:
    payload: dict[str, object]

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class MockLlmClient:
    """Deterministic Chat Completions-compatible client for tests and local validation."""

    def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> _MockResponse:
        messages = json.get("messages", [])
        text = json_module_dumps(messages)
        relevance = 9 if '"rule_score":' in text else 7
        content = json_module_dumps(
            {
                "relevance_score": relevance,
                "innovation_score": 8,
                "summary": "模拟分析：该内容概述了专题中的主要进展与关键信息。",
                "recommendation_reason": "模拟分析认为该内容与关注方向相关，值得进一步阅读。",
            }
        )
        return _MockResponse({"choices": [{"message": {"content": content}}]})


class TokenLimiter:
    def __init__(self, encoding_name: str, max_tokens: int) -> None:
        self.encoding = tiktoken.get_encoding(encoding_name)
        self.max_tokens = max_tokens

    def count_messages(self, messages: list[dict[str, str]]) -> int:
        return MESSAGE_OVERHEAD_TOKENS + sum(
            len(self.encoding.encode(message.get("role", "")))
            + len(self.encoding.encode(message.get("content", "")))
            for message in messages
        )

    def fit(
        self, builder: PromptBuilder, item: RssItem, profile: ProfileConfig
    ) -> list[dict[str, str]]:
        fixed_item = replace(item, content_excerpt="")
        fixed_messages = builder(fixed_item, profile)
        if self.count_messages(fixed_messages) > self.max_tokens:
            raise ValueError(
                f"专题 {item.channel_id} 的固定 Prompt 超过 {self.max_tokens} Token"
            )
        content_tokens = self.encoding.encode(item.content_excerpt)
        low, high = 0, len(content_tokens)
        best_messages = fixed_messages
        best_content = ""
        while low <= high:
            middle = (low + high) // 2
            content = self.encoding.decode(content_tokens[:middle])
            messages = builder(replace(item, content_excerpt=content), profile)
            if self.count_messages(messages) <= self.max_tokens:
                best_messages = messages
                best_content = content
                low = middle + 1
            else:
                high = middle - 1
        item.content_excerpt = best_content
        return best_messages


class RssAnalyzer:
    def __init__(
        self,
        llm: RepoLlmConfig,
        defaults: RssDefaultsConfig,
        prompt_builder: PromptBuilder,
        client: LlmClient | None = None,
    ) -> None:
        self.llm = llm
        self.prompt_builder = prompt_builder
        self.token_limiter = TokenLimiter(defaults.token_encoding, defaults.max_input_tokens)
        self.client = client or httpx.Client(
            timeout=llm.timeout_seconds,
            verify=llm.verify_ssl,
        )

    def analyze(self, item: RssItem, profile: ProfileConfig) -> None:
        try:
            messages = self.token_limiter.fit(self.prompt_builder, item, profile)
        except ValueError:
            raise
        if not (self.llm.enabled and self.llm.api_key and self.llm.model):
            self.fallback(item, profile)
            return
        try:
            response = self.client.post(
                self.llm.base_url,
                headers={"Authorization": f"Bearer {self.llm.api_key}"},
                json={
                    "model": self.llm.model,
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                    "messages": messages,
                },
            )
            response.raise_for_status()
            content = _message_content(response.json())
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
            payload = json.loads(repair_json(cleaned))
            if not isinstance(payload, dict):
                raise ValueError("LLM 返回 JSON 的顶层必须是对象")
            item.relevance_score = _score(payload.get("relevance_score"))
            item.innovation_score = _score(payload.get("innovation_score"))
            summary = str(payload.get("summary") or "").strip()
            reason = str(payload.get("recommendation_reason") or "").strip()
            if not summary or not reason:
                raise ValueError("LLM 必须返回内容概要和推荐理由")
            if profile.output_language == "zh" and (
                not _contains_chinese(summary) or not _contains_chinese(reason)
            ):
                raise ValueError("LLM 必须返回中文内容概要和推荐理由")
            item.summary = _truncate(summary, 200)
            item.recommendation_reason = _truncate(reason, 200)
            item.analysis_status = "ai"
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("[RSS/LLM] %s 分析失败，使用规则回退：%s", item.entry_id, exc)
            self.fallback(item, profile)

    @staticmethod
    def fallback(item: RssItem, profile: ProfileConfig) -> None:
        item.analysis_status = "fallback"
        item.relevance_score = max(0, min(10, round(item.rule_score / 10)))
        item.innovation_score = 0
        separator = ", " if profile.output_language == "en" else "、"
        matched = separator.join(item.matched_keywords[:3])
        if profile.output_language == "en":
            item.recommendation_reason = (
                f"Matched interests: {matched}."
                if matched
                else "Selected by local relevance rules."
            )
        else:
            item.recommendation_reason = (
                f"命中关注词：{matched}。" if matched else "根据规则排序入选。"
            )
        item.summary = _truncate(item.feed_summary or item.content_excerpt or item.title, 200)


class RssPipeline:
    def __init__(
        self,
        channel: RssChannelConfig,
        defaults: RssDefaultsConfig,
        llm: RepoLlmConfig,
        *,
        client: httpx.Client | None = None,
        analyzer: RssAnalyzer | None = None,
        llm_client: LlmClient | None = None,
    ) -> None:
        self.channel = channel
        self.defaults = defaults
        self.client = client or httpx.Client(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        builder = load_prompt_builder(channel.prompt)
        self.analyzer = analyzer or RssAnalyzer(llm, defaults, builder, llm_client)

    def run(self, profile: ProfileConfig, window: SearchWindow) -> ChannelRun:
        if not self.channel.enabled:
            return ChannelRun(self.channel.channel_id, self.channel.title, [], 0, 0)
        items, errors = self._fetch_sources(window, profile)
        return analyze_channel_items(
            self.channel.channel_id,
            self.channel.title,
            items,
            errors,
            profile,
            self.defaults,
            self.analyzer,
        )

    def _fetch_sources(
        self, window: SearchWindow, profile: ProfileConfig
    ) -> tuple[list[RssItem], dict[str, str]]:
        collected: list[RssItem] = []
        errors: dict[str, str] = {}

        def fetch(source: RssSourceConfig) -> list[RssItem]:
            with self.client.stream("GET", source.url) as response:
                response.raise_for_status()
                entries = parse_feed_chunks(
                    response.iter_bytes(),
                    window,
                    self.defaults.max_items_per_source,
                    self.defaults.max_input_tokens,
                    self.defaults.token_encoding,
                    profile,
                )
            return [
                RssItem(
                    channel_id=self.channel.channel_id,
                    source_id=source.source_id,
                    source_name=source.name,
                    entry_id=entry.entry_id,
                    title=entry.title,
                    url=entry.url,
                    feed_summary=entry.summary,
                    content_excerpt=entry.content,
                    authors=entry.authors,
                    tags=entry.tags,
                    published_at=entry.published_at,
                    matched_keywords=entry.matched_keywords,
                    rule_score=entry.rule_score,
                )
                for entry in entries
                if entry.title and entry.url
            ]

        workers = max(1, min(len(self.channel.sources) or 1, 10))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(fetch, source): source for source in self.channel.sources}
            for future in as_completed(futures):
                source = futures[future]
                try:
                    collected.extend(future.result())
                except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
                    errors[source.source_id] = str(exc)
                    logger.warning(
                        "[%s/%s] RSS 获取失败：%s",
                        self.channel.channel_id,
                        source.name,
                        exc,
                    )
        return collected, errors


def analyze_channel_items(
    channel_id: str,
    title: str,
    items: list[RssItem],
    errors: dict[str, str],
    profile: ProfileConfig,
    defaults: RssDefaultsConfig,
    analyzer: RssAnalyzer,
) -> ChannelRun:
    shortlist = _select_with_keyword_coverage(
        items,
        profile.interests,
        defaults.llm_candidates,
        _rule_sort_key,
    )
    workers = max(1, min(defaults.max_analysis_workers, len(shortlist) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(lambda item: analyzer.analyze(item, profile), shortlist))
    for item in shortlist:
        item.final_score = combined_score(item)
    picks = _select_with_keyword_coverage(
        shortlist,
        profile.interests,
        defaults.top_k,
        _final_sort_key,
    )
    for rank, item in enumerate(picks, start=1):
        item.pick_rank = rank
    logger.info(
        "[%s] 日期内保留 %d 条，LLM 候选 %d 条，最终入选 %d 条",
        channel_id,
        len(items),
        len(shortlist),
        len(picks),
    )
    # shortlist 是完整已打分候选池：picks 是其中被选中的对象引用（已写回 pick_rank），
    # 其余为被淘汰的近邻负例。整体导出供离线评测计算 precision/recall 与难负例。
    return ChannelRun(
        channel_id,
        title,
        picks,
        len(items),
        len(shortlist),
        errors,
        candidates=list(shortlist),
    )


def _select_with_keyword_coverage(
    items: list[RssItem],
    interests: list[str],
    limit: int,
    sort_key: Callable[[RssItem], tuple[float, float, str]],
) -> list[RssItem]:
    ordered = sorted(items, key=sort_key)
    selected: list[RssItem] = []
    covered: set[str] = set()
    for interest in interests:
        if interest in covered:
            continue
        candidate = next(
            (
                item
                for item in ordered
                if item not in selected and interest in item.matched_keywords
            ),
            None,
        )
        if candidate is None:
            continue
        selected.append(candidate)
        covered.update(candidate.matched_keywords)
        if len(selected) >= limit:
            return selected
    selected.extend(item for item in ordered if item not in selected)
    return selected[:limit]


@dataclass(slots=True)
class FeedEntry:
    entry_id: str
    title: str
    url: str
    summary: str
    content: str
    authors: list[str]
    tags: list[str]
    published_at: datetime
    matched_keywords: list[str] = field(default_factory=list)
    rule_score: int = 0


def parse_feed(
    content: str,
    window: SearchWindow,
    limit: int = 10,
    content_token_limit: int = 1000,
    token_encoding: str = "cl100k_base",
    profile: ProfileConfig | None = None,
) -> list[FeedEntry]:
    return parse_feed_chunks(
        [content.encode("utf-8")],
        window,
        limit,
        content_token_limit,
        token_encoding,
        profile,
    )


def parse_feed_chunks(
    chunks: Iterable[bytes],
    window: SearchWindow,
    limit: int = 10,
    content_token_limit: int = 1000,
    token_encoding: str = "cl100k_base",
    profile: ProfileConfig | None = None,
) -> list[FeedEntry]:
    parser = ET.XMLPullParser(events=("end",))
    encoding = tiktoken.get_encoding(token_encoding)
    best: list[FeedEntry] = []
    for chunk in chunks:
        parser.feed(chunk)
        for _, node in parser.read_events():
            if _local_name(node.tag) not in {"item", "entry"}:
                continue
            published_at = _parse_datetime(
                _first_text(node, {"pubDate", "published", "updated", "date"})
            )
            if published_at is not None and window.contains(published_at):
                entry = _parse_entry(node, published_at, encoding, content_token_limit)
                if entry.title and entry.url:
                    candidate = RssItem(
                        channel_id="",
                        source_id="",
                        source_name="",
                        entry_id=entry.entry_id,
                        title=entry.title,
                        url=entry.url,
                        feed_summary=entry.summary,
                        content_excerpt=entry.content,
                        authors=entry.authors,
                        tags=entry.tags,
                        published_at=entry.published_at,
                    )
                    if profile is None or score_item(candidate, profile):
                        entry.matched_keywords = candidate.matched_keywords
                        entry.rule_score = candidate.rule_score
                        best.append(entry)
                        best.sort(key=_feed_rule_sort_key)
                        del best[limit:]
            node.clear()
    parser.close()
    return best


def score_item(item: RssItem, profile: ProfileConfig) -> bool:
    title = normalize(item.title)
    tags = normalize(" ".join(item.tags))
    body = normalize(" ".join([item.feed_summary, item.content_excerpt]))
    all_text = " ".join([title, tags, body])
    item.excluded_keywords = [
        keyword for keyword in profile.exclude_keywords if contains(all_text, normalize(keyword))
    ]
    if item.excluded_keywords:
        return False
    score = 0
    matched: list[str] = []
    for interest in profile.interests:
        terms = interest_terms(interest)
        if any(contains(title, term) for term in terms):
            score += 30
        elif any(contains(tags, term) for term in terms):
            score += 20
        elif any(contains(body, term) for term in terms):
            score += 10
        else:
            continue
        matched.append(interest)
    item.matched_keywords = list(dict.fromkeys(matched))
    item.rule_score = min(100, score)
    return True


def combined_score(item: RssItem) -> float:
    if item.analysis_status != "ai":
        return float(item.rule_score)
    llm_score = (item.relevance_score * 0.6 + item.innovation_score * 0.4) * 10
    return round(item.rule_score * 0.4 + llm_score * 0.6, 2)


def load_prompt_builder(path: str) -> PromptBuilder:
    module_name, _, function_name = path.partition(":")
    builder = getattr(importlib.import_module(module_name), function_name)
    if not callable(builder):
        raise ValueError(f"Prompt 不是可调用函数: {path}")
    return builder


def _parse_entry(
    node: ET.Element,
    published_at: datetime,
    encoding: tiktoken.Encoding,
    content_token_limit: int,
) -> FeedEntry:
    title = _clean_html(_first_text(node, {"title"}))
    summary_html = _first_text(node, {"description", "summary"})
    content_html = _first_text(node, {"encoded", "content"})
    url = _entry_url(node)
    entry_id = _first_text(node, {"guid", "id"}) or url
    authors = _unique(_all_text(node, {"author", "creator", "name"}))
    tags = _unique(
        _all_text(node, {"category"})
        + [child.get("term", "") for child in node.iter() if _local_name(child.tag) == "category"]
    )
    summary = _clean_html(summary_html)
    content = "\n\n".join(_unique([summary, _clean_html(content_html)]))
    content_tokens = encoding.encode(content)
    if len(content_tokens) > content_token_limit:
        content = encoding.decode(content_tokens[:content_token_limit])
    return FeedEntry(entry_id, title, url, summary, content, authors, tags, published_at)


def _entry_url(node: ET.Element) -> str:
    for child in node.iter():
        if _local_name(child.tag) != "link":
            continue
        href = child.get("href", "").strip()
        if href and child.get("rel", "alternate") == "alternate":
            return href
        if child.text and child.text.strip():
            return child.text.strip()
    return ""


def _first_text(node: ET.Element, names: set[str]) -> str:
    for child in node.iter():
        if _local_name(child.tag) in names and child.text:
            return child.text.strip()
    return ""


def _all_text(node: ET.Element, names: set[str]) -> list[str]:
    return [
        child.text.strip()
        for child in node.iter()
        if _local_name(child.tag) in names and child.text and child.text.strip()
    ]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _clean_html(value: str) -> str:
    if "<" not in value and "&" not in value:
        return re.sub(r"\s+", " ", value).strip()
    return re.sub(r"\s+", " ", BeautifulSoup(value or "", "html.parser").get_text(" ")).strip()


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value and value.strip()))


def _score(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("评分必须是数字")
    score = int(value)
    if score != value or not 0 <= score <= 10:
        raise ValueError("评分必须是 0 到 10 的整数")
    return score


def _message_content(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ValueError("LLM HTTP 响应必须是对象")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("LLM HTTP 响应缺少 choices")
    first = choices[0]
    if not isinstance(first, dict) or not isinstance(first.get("message"), dict):
        raise ValueError("LLM choices[0].message 格式错误")
    content = first["message"].get("content")
    if not isinstance(content, str):
        raise ValueError("LLM message.content 必须是字符串")
    return content


def _contains_chinese(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", value))


def _truncate(value: str, limit: int) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _rule_sort_key(item: RssItem) -> tuple[float, float, str]:
    timestamp = item.published_at.timestamp() if item.published_at else 0
    return (-item.rule_score, -timestamp, item.title.lower())


def _feed_rule_sort_key(item: FeedEntry) -> tuple[float, float, str]:
    return (-item.rule_score, -item.published_at.timestamp(), item.title.lower())


def _final_sort_key(item: RssItem) -> tuple[float, float, str]:
    timestamp = item.published_at.timestamp() if item.published_at else 0
    return (-item.final_score, -timestamp, item.title.lower())


def json_module_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
