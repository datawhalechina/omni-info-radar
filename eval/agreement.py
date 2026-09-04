"""Phase 1 评分者一致性校验：对同一批样本的两份人工标注计算 Cohen's κ 与一致率。

依据：标注协议可信度用 κ 衡量（Databricks 公开的 LLM 评判器 κ≈0.64-0.65 为现实参照）。
经验门槛：κ≥0.7 良好；0.6-0.7 可用；<0.6 说明构念定义不清，应先修订标注规范再扩标。
注意：此处对 0-2 有序字段按名义 κ 计算（保守）；如需更敏感可用加权 κ（线性/二次权重）。

用法：
    python -m eval.agreement --a gold_anna.jsonl --b gold_ben.jsonl            # 默认 worth_pushing
    python -m eval.agreement --a gold_anna.jsonl --b gold_ben.jsonl --all      # 全部字段
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.schema import GOLD_FIELDS


def _load_gold(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            item_id = record.get("item_id")
            gold = record.get("gold")
            if item_id and isinstance(gold, dict):
                out[item_id] = gold
    return out


def cohen_kappa(labels_a: list, labels_b: list) -> tuple[float, float, int]:
    """返回 (kappa, percent_agreement, n)。名义尺度 κ。"""
    n = len(labels_a)
    if n == 0:
        return (float("nan"), float("nan"), 0)
    agree = sum(1 for x, y in zip(labels_a, labels_b, strict=True) if x == y)
    po = agree / n
    counts_a = Counter(labels_a)
    counts_b = Counter(labels_b)
    categories = set(counts_a) | set(counts_b)
    pe = sum((counts_a[c] / n) * (counts_b[c] / n) for c in categories)
    if pe >= 1.0:
        return (1.0, po, n)
    return ((po - pe) / (1 - pe), po, n)


def _interpret(kappa: float) -> str:
    if kappa != kappa:  # NaN
        return "无可比较样本"
    if kappa >= 0.7:
        return "良好（可扩标）"
    if kappa >= 0.6:
        return "可用（建议校准边界样例）"
    return "偏低（先修订标注规范）"


def compare(a: dict[str, dict], b: dict[str, dict], field: str) -> None:
    shared = sorted(set(a) & set(b))
    labels_a, labels_b = [], []
    for item_id in shared:
        va, vb = a[item_id].get(field), b[item_id].get(field)
        if va is None or vb is None:
            continue
        labels_a.append(va)
        labels_b.append(vb)
    kappa, po, n = cohen_kappa(labels_a, labels_b)
    print(
        f"{field:22s} n={n:4d}  一致率={po:.3f}  κ={kappa:.3f}  → {_interpret(kappa)}"
        if n
        else f"{field:22s} n=   0  （两位标注者均无有效标注）"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="两份人工标注的评分者一致性")
    parser.add_argument("--a", required=True)
    parser.add_argument("--b", required=True)
    parser.add_argument("--field", default="worth_pushing")
    parser.add_argument("--all", action="store_true", help="对全部标注字段计算")
    args = parser.parse_args()

    a = _load_gold(Path(args.a))
    b = _load_gold(Path(args.b))
    fields = list(GOLD_FIELDS) if args.all else [args.field]
    print(f"共同样本 item_id 数：{len(set(a) & set(b))}")
    for field in fields:
        compare(a, b, field)


if __name__ == "__main__":
    main()
