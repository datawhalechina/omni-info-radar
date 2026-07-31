from __future__ import annotations

import re
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from .config import GitHubConfig
from .models import Repository

TRENDING_URL = "https://github.com/trending"
USER_AGENT = "RepoCourier/0.1 (+https://github.com/datawhalechina/omni-info-radar)"


def _count(value: str) -> int:
    compact = value.strip().replace(",", "").lower()
    match = re.search(r"([\d.]+)\s*([km]?)", compact)
    if not match:
        return 0
    number = float(match.group(1))
    multiplier = {"k": 1_000, "m": 1_000_000}.get(match.group(2), 1)
    return int(number * multiplier)


def parse_trending_html(html: str, limit: int = 10) -> list[Repository]:
    soup = BeautifulSoup(html, "html.parser")
    repositories: list[Repository] = []
    for rank, article in enumerate(soup.select("article.Box-row"), start=1):
        link = article.select_one("h2 a")
        if link is None:
            continue
        path = link.get("href", "").strip("/")
        parts = path.split("/")
        if len(parts) < 2:
            continue
        owner, name = parts[0], parts[1]
        description_node = article.select_one("p")
        language_node = article.select_one('[itemprop="programmingLanguage"]')
        star_node = article.select_one(f'a[href="/{owner}/{name}/stargazers"]')
        fork_node = article.select_one(f'a[href="/{owner}/{name}/forks"]')
        today_node = article.select_one("span.d-inline-block.float-sm-right")
        repositories.append(
            Repository(
                rank=rank,
                owner=owner,
                name=name,
                url=f"https://github.com/{owner}/{name}",
                description=description_node.get_text(" ", strip=True) if description_node else "",
                language=language_node.get_text(strip=True) if language_node else "Unknown",
                stars=_count(star_node.get_text(" ", strip=True)) if star_node else 0,
                forks=_count(fork_node.get_text(" ", strip=True)) if fork_node else 0,
                stars_today=_count(today_node.get_text(" ", strip=True)) if today_node else 0,
            )
        )
        if len(repositories) >= limit:
            break
    return repositories


class TrendingClient:
    def __init__(self, config: GitHubConfig, client: httpx.Client | None = None) -> None:
        self.config = config
        self.client = client or httpx.Client(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
        )

    def fetch(self) -> list[Repository]:
        query = {"since": self.config.since}
        if self.config.spoken_language_code:
            query["spoken_language_code"] = self.config.spoken_language_code
        language_path = f"/{self.config.language}" if self.config.language else ""
        url = f"{TRENDING_URL}{language_path}?{urlencode(query)}"
        response = self.client.get(url)
        response.raise_for_status()
        repositories = parse_trending_html(response.text, self.config.limit)
        if not repositories:
            raise RuntimeError("GitHub Trending 页面解析结果为空，页面结构可能已变化")
        return repositories
