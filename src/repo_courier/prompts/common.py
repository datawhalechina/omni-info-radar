from __future__ import annotations

import json

from ..config import ProfileConfig
from ..models import RssItem


def build_messages(
    item: RssItem, profile: ProfileConfig, *, role: str, focus: str
) -> list[dict[str, str]]:
    output_rule = (
        "summary 和 recommendation_reason 必须使用英文，且分别不超过 200 个字符。"
        if profile.output_language == "en"
        else "summary 和 recommendation_reason 必须使用中文，且分别不超过 200 字。"
    )
    system = f"""
## Role
你是严谨的{role}。只根据输入内容判断，不得臆造。

## Task
根据用户关键词和 RSS 内容进行筛选与分析。重点判断{focus}。

## Output
只返回合法 JSON 对象，不要返回 Markdown 或额外解释。
relevance_score 和 innovation_score 必须是 0 到 10 的整数。
{output_rule}

输出字段：relevance_score、innovation_score、summary、recommendation_reason。
""".strip()
    user = json.dumps(
        {
            "channel": item.channel_id,
            "keywords": profile.interests,
            "source": item.source_name,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "matched_keywords": item.matched_keywords,
            "rule_score": item.rule_score,
            "content": "\n\n".join(
                [
                    f"Title:\n{item.title}",
                    f"Tags:\n{', '.join(item.tags)}",
                    f"Content:\n{item.content_excerpt}",
                ]
            ),
        },
        ensure_ascii=False,
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
