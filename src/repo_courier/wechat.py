from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import httpx
from bs4 import BeautifulSoup

from .config import (
    ProfileConfig,
    RepoLlmConfig,
    RssDefaultsConfig,
    WechatAccountConfig,
    WechatConfig,
)
from .feeds import (
    BEIJING,
    RssAnalyzer,
    SearchWindow,
    analyze_channel_items,
    load_prompt_builder,
    score_item,
)
from .models import ChannelRun, RssItem

logger = logging.getLogger(__name__)

CHANNEL_ID = "wechat"
PAGE_SIZE = 20
MAX_FETCH_WORKERS = 10
MAX_CONTENT_FETCH_WORKERS = 3
MAX_DOWNLOAD_ATTEMPTS = 3
USER_AGENT = "RepoCourier/0.1 (WeChat article reader)"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36"
)


class WechatResponse(Protocol):
    @property
    def text(self) -> str: ...

    def raise_for_status(self) -> None: ...

    def json(self) -> object: ...


class WechatHttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        params: dict[str, object],
        headers: dict[str, str] | None = None,
    ) -> WechatResponse: ...


@dataclass(frozen=True, slots=True)
class WechatArticle:
    account: WechatAccountConfig
    title: str
    url: str
    published_at: datetime


class WechatPipeline:
    def __init__(
        self,
        config: WechatConfig,
        defaults: RssDefaultsConfig,
        llm: RepoLlmConfig,
        *,
        client: WechatHttpClient | None = None,
        analyzer: RssAnalyzer | None = None,
        llm_client: Any | None = None,
    ) -> None:
        self.config = config
        self.defaults = defaults
        self.client = client or httpx.Client(
            timeout=30,
            follow_redirects=True,
            verify=config.verify_ssl,
            headers={"User-Agent": USER_AGENT},
        )
        builder = load_prompt_builder(config.prompt)
        self.analyzer = analyzer or RssAnalyzer(llm, defaults, builder, llm_client)

    def run(self, profile: ProfileConfig, window: SearchWindow) -> ChannelRun:
        if not self.config.enabled:
            return ChannelRun(CHANNEL_ID, self.config.title, [], 0, 0)
        if not self.config.accounts:
            return ChannelRun(CHANNEL_ID, self.config.title, [], 0, 0)
        if not self.config.auth_key:
            raise RuntimeError("微信公众号频道需要环境变量 WECHAT_AUTH_KEY")

        articles, errors = self._fetch_articles(window)
        items = self._fetch_contents(articles, profile, errors)
        return analyze_channel_items(
            CHANNEL_ID,
            self.config.title,
            items,
            errors,
            profile,
            self.defaults,
            self.analyzer,
        )

    def _fetch_articles(
        self, window: SearchWindow
    ) -> tuple[list[WechatArticle], dict[str, str]]:
        collected: list[WechatArticle] = []
        errors: dict[str, str] = {}
        workers = max(1, min(len(self.config.accounts) or 1, MAX_FETCH_WORKERS))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._fetch_account_articles, account, window): account
                for account in self.config.accounts
            }
            for future in as_completed(futures):
                account = futures[future]
                try:
                    collected.extend(future.result())
                except Exception as exc:  # Isolate every configured account.
                    errors[account.fakeid] = str(exc)
                    logger.warning("[wechat/%s] 文章列表获取失败：%s", account.name, exc)

        unique: dict[str, WechatArticle] = {}
        for article in collected:
            unique.setdefault(article.url, article)
        return list(unique.values()), errors

    def _fetch_account_articles(
        self, account: WechatAccountConfig, window: SearchWindow
    ) -> list[WechatArticle]:
        begin = 0
        result: list[WechatArticle] = []
        seen_pages: set[tuple[tuple[str, str], ...]] = set()
        while True:
            response = self.client.get(
                f"{self.config.api_base_url}/article",
                params={"fakeid": account.fakeid, "begin": begin, "size": PAGE_SIZE},
                headers={"X-Auth-Key": self.config.auth_key},
            )
            _raise_for_status(response)
            raw_articles = _article_objects(response.json())
            if not raw_articles:
                break
            signature = tuple(
                (str(raw.get("link") or ""), str(raw.get("create_time") or ""))
                for raw in raw_articles
            )
            if signature in seen_pages:
                raise ValueError(f"公众号 {account.name} 返回了重复分页")
            seen_pages.add(signature)

            page_times: list[datetime] = []
            for raw in raw_articles:
                article = _parse_article(raw, account)
                if article is None:
                    continue
                page_times.append(article.published_at)
                if window.contains(article.published_at):
                    result.append(article)

            if len(raw_articles) < PAGE_SIZE:
                break
            if page_times and min(page_times) < window.start:
                break
            begin += PAGE_SIZE
        return result

    def _fetch_contents(
        self,
        articles: list[WechatArticle],
        profile: ProfileConfig,
        errors: dict[str, str],
    ) -> list[RssItem]:
        items: list[RssItem] = []
        workers = max(1, min(len(articles) or 1, MAX_CONTENT_FETCH_WORKERS))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._download_content, article): (index, article)
                for index, article in enumerate(articles, start=1)
            }
            for future in as_completed(futures):
                index, article = futures[future]
                try:
                    content = future.result()
                    if not content:
                        raise ValueError("正文为空")
                except Exception as exc:  # Isolate every article download.
                    errors[f"{article.account.fakeid}:article:{index}"] = str(exc)
                    logger.warning(
                        "[wechat/%s] 正文获取失败 %s：%s",
                        article.account.name,
                        article.url,
                        exc,
                    )
                    continue
                item = RssItem(
                    channel_id=CHANNEL_ID,
                    source_id=article.account.fakeid,
                    source_name=article.account.name,
                    entry_id=article.url,
                    title=article.title,
                    url=article.url,
                    content_excerpt=f"{article.title}\n\n{content}",
                    published_at=article.published_at,
                )
                if score_item(item, profile):
                    items.append(item)
        return items

    def _download_content(self, article: WechatArticle) -> str:
        try:
            response = self.client.get(
                article.url,
                params={},
                headers={"User-Agent": BROWSER_USER_AGENT},
            )
            _raise_for_status(response)
            content = _extract_article_text(response.text)
            if content:
                return content[: self.config.content_max_chars]
        except httpx.HTTPError as exc:
            logger.debug("[wechat] 直接读取正文失败 %s：%s", article.url, exc)

        if not self.config.content_api_fallback_enabled:
            return ""
        logger.debug("[wechat] 改用正文下载 API：%s", article.url)

        for attempt in range(MAX_DOWNLOAD_ATTEMPTS):
            response = self.client.get(
                f"{self.config.api_base_url}/download",
                params={"url": article.url, "format": "html"},
            )
            try:
                _raise_for_status(response)
            except httpx.HTTPStatusError as exc:
                if (
                    exc.response.status_code != httpx.codes.TOO_MANY_REQUESTS
                    or attempt == MAX_DOWNLOAD_ATTEMPTS - 1
                ):
                    raise
                retry_after = exc.response.headers.get("Retry-After", "")
                try:
                    delay = float(retry_after)
                except ValueError:
                    delay = 2**attempt
                time.sleep(max(0.5, min(delay, 5.0)))
                continue
            return _extract_article_text(response.text)[: self.config.content_max_chars]
        raise RuntimeError("微信公众号正文下载重试次数已耗尽")


def _extract_article_text(document: str) -> str:
    soup = BeautifulSoup(document, "html.parser")
    content = soup.select_one("#js_content")
    if content is None:
        if soup.find(("html", "body")) is not None:
            return ""
        return soup.get_text("\n", strip=True)
    for node in content.select("script, style, noscript"):
        node.decompose()
    return "\n".join(content.stripped_strings)


def _raise_for_status(response: WechatResponse) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text
        if "域名不在安全策略" in body or "域名拦截" in body:
            raise RuntimeError("当前网络安全策略拦截 down.mptext.top") from exc
        raise


def _article_objects(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("微信公众号文章响应必须是对象")
    top_level = payload.get("articles")
    if isinstance(top_level, list):
        return [item for item in top_level if isinstance(item, dict)]

    data = payload.get("data")
    containers: object = (
        data.get("list", []) if isinstance(data, dict) else payload.get("list", data)
    )
    if not isinstance(containers, list):
        return []
    articles: list[dict[str, Any]] = []
    for container in containers:
        if not isinstance(container, dict) or not isinstance(container.get("articles"), list):
            continue
        articles.extend(item for item in container["articles"] if isinstance(item, dict))
    return articles


def _parse_article(
    payload: dict[str, Any], account: WechatAccountConfig
) -> WechatArticle | None:
    title = str(payload.get("title") or "").strip()
    url = str(payload.get("link") or "").strip()
    raw_timestamp = payload.get("create_time")
    if not title or not url or isinstance(raw_timestamp, bool):
        return None
    try:
        published_at = datetime.fromtimestamp(float(raw_timestamp), tz=BEIJING)
    except (OSError, OverflowError, TypeError, ValueError):
        return None
    return WechatArticle(account, title, url, published_at)
