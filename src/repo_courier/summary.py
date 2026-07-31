from __future__ import annotations

import json
import logging
import re

import httpx

from .config import RepoLlmConfig
from .models import Repository

logger = logging.getLogger(__name__)


class Summarizer:
    def __init__(self, config: RepoLlmConfig, client: httpx.Client | None = None) -> None:
        self.config = config
        self.client = client or httpx.Client(
            timeout=config.timeout_seconds,
            verify=config.verify_ssl,
        )

    def summarize(self, repositories: list[Repository]) -> list[Repository]:
        if self.config.enabled and self.config.api_key and self.config.model:
            try:
                self._ai_summarize(repositories)
                return repositories
            except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                logger.warning("AI 摘要失败，将使用本地规则摘要: %s", exc)
        for repository in repositories:
            self._fallback(repository)
        return repositories

    def _ai_summarize(self, repositories: list[Repository]) -> None:
        inputs = [
            {
                "full_name": item.full_name,
                "description": item.description,
                "language": item.language,
                "topics": item.topics,
                "stars": item.stars,
                "stars_today": item.stars_today,
                "license": item.license,
                "readme_excerpt": item.readme_excerpt,
            }
            for item in repositories
        ]
        output_rule = (
            "Use concise English for every natural-language value."
            if self.config.output_language == "en"
            else "所有自然语言字段使用简洁中文。"
        )
        system = (
            "你是资深开源项目分析师。根据给定事实做简洁、克制的分析，不得臆造。"
            f"{output_rule}"
            "只返回 JSON 数组。每项字段必须为 full_name, summary, highlights, use_cases, "
            "category, risk_note；highlights 和 use_cases 是各 1-3 条的字符串数组。"
            "risk_note 只填写明确、具体且会影响采用决策的风险，没有则返回空字符串；"
            "不要把未识别到许可证元数据本身作为风险。"
        )
        response = self.client.post(
            self.config.base_url,
            headers={"Authorization": f"Bearer {self.config.api_key}"},
            json={
                "model": self.config.model,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": "分析以下项目。返回对象格式 {\"repositories\": [...]}：\n"
                        + json.dumps(inputs, ensure_ascii=False),
                    },
                ],
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        payload = self._parse_json(content)
        items = payload.get("repositories", payload) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ValueError("AI 返回内容不是项目数组")
        results = {item.get("full_name"): item for item in items if isinstance(item, dict)}
        for repository in repositories:
            item = results.get(repository.full_name)
            if not item:
                self._fallback(repository)
                continue
            repository.summary = str(item.get("summary") or repository.description)
            repository.highlights = _strings(item.get("highlights"))
            repository.use_cases = _strings(item.get("use_cases"))
            repository.category = str(item.get("category") or "其他")
            repository.risk_note = str(item.get("risk_note") or "")
            repository.analysis_status = "ai"

    @staticmethod
    def _parse_json(content: str) -> object:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        return json.loads(cleaned)

    def _fallback(self, repository: Repository) -> None:
        english = self.config.output_language == "en"
        topic_text = (", " if english else "、").join(repository.topics[:4])
        description = repository.description.strip().rstrip("。.")
        repository.summary = description or (
            f"An open-source project primarily written in {repository.language}"
            if english
            else f"一个以 {repository.language} 为主的开源项目"
        )
        repository.highlights = (
            [
                f"About {repository.stars_today:,} new Stars today",
                f"Primary language: {repository.language}",
            ]
            if english
            else [
                f"今日新增约 {repository.stars_today:,} Stars",
                f"主要语言：{repository.language}",
            ]
        )
        if topic_text:
            repository.highlights.append(
                f"Topics: {topic_text}" if english else f"关键词：{topic_text}"
            )
        repository.use_cases = _infer_use_cases(repository, english=english)
        repository.category = _infer_category(repository, english=english)
        repository.risk_note = ""
        repository.analysis_status = "fallback"


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:3]


def _infer_category(repository: Repository, *, english: bool = False) -> str:
    text = " ".join(
        [repository.name, repository.description, repository.language, *repository.topics]
    ).lower()
    categories = [
        ("AI / 机器学习", ("ai", "llm", "machine-learning", "agent", "model")),
        ("开发工具", ("developer", "cli", "tool", "sdk", "ide", "terminal")),
        ("Web / 应用", ("web", "frontend", "backend", "react", "vue", "app")),
        ("数据 / 基础设施", ("database", "data", "cloud", "kubernetes", "infra")),
        ("安全", ("security", "privacy", "vulnerability", "pentest")),
        ("学习资源", ("tutorial", "awesome", "learn", "course", "book")),
    ]
    for category, keywords in categories:
        if any(keyword in text for keyword in keywords):
            if not english:
                return category
            return {
                "AI / 机器学习": "AI / Machine Learning",
                "开发工具": "Developer Tools",
                "Web / 应用": "Web / Applications",
                "数据 / 基础设施": "Data / Infrastructure",
                "安全": "Security",
                "学习资源": "Learning Resources",
            }[category]
    return "Other" if english else "其他"


def _infer_use_cases(repository: Repository, *, english: bool = False) -> list[str]:
    category = _infer_category(repository)
    mapping = {
        "AI / 机器学习": ["AI 原型验证与能力集成"],
        "开发工具": ["提升开发、调试或自动化效率"],
        "Web / 应用": ["Web 产品开发与技术选型参考"],
        "数据 / 基础设施": ["数据处理或基础设施建设"],
        "安全": ["安全研究与防护能力建设"],
        "学习资源": ["系统学习与团队知识库建设"],
        "其他": ["技术调研与开源方案选型"],
    }
    if not english:
        return mapping[category]
    return {
        "AI / 机器学习": ["AI prototyping and capability integration"],
        "开发工具": ["Improve development, debugging, or automation workflows"],
        "Web / 应用": ["Web product development and technology evaluation"],
        "数据 / 基础设施": ["Data processing or infrastructure engineering"],
        "安全": ["Security research and defensive engineering"],
        "学习资源": ["Structured learning and team knowledge bases"],
        "其他": ["Technology research and open-source evaluation"],
    }[category]
