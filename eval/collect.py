"""Phase 0 收集器：把分散的候选池快照聚合成单一分析就绪文件。

来源：
- reports/*/eval_candidates.json —— 需开启 report.eval_dump（或 REPO_COURIER_EVAL_DUMP=on），
  提供 GitHub 全量打分项目 + 各 RSS/微信频道的已打分候选（含近邻负例）。
- data/history/*.json —— 每次运行都落盘，提供 GitHub 全量打分候选池的广覆盖。

输出 eval/data/candidates.jsonl：按日唯一的候选记录（item_id 去重）。
后续 recall 计算依赖"按日完整候选池"，故此处不做跨日内容去重（内容去重在标注采样阶段做）。

用法：
    python -m eval.collect \
        --reports-dir reports --history-dir data/history \
        --out eval/data/candidates.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # 允许 `python eval/collect.py` 直接运行
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.schema import Candidate, load_eval_dump, load_history, write_jsonl


def collect(reports_dir: Path, history_dir: Path) -> list[Candidate]:
    seen: dict[str, Candidate] = {}

    def add(candidates: list[Candidate]) -> None:
        for candidate in candidates:
            # 优先保留 eval_dump 的记录（更完整）；history 仅补没有 eval_dump 的日期。
            seen.setdefault(candidate.item_id, candidate)

    for dump in sorted(reports_dir.glob("*/eval_candidates.json")):
        add(load_eval_dump(dump))
    for history in sorted(history_dir.glob("*.json")):
        add(load_history(history))

    ordered = sorted(seen.values(), key=lambda c: (c.date, c.kind, -(c.final_score)))
    return ordered


def main() -> None:
    parser = argparse.ArgumentParser(description="聚合候选池快照为 candidates.jsonl")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--history-dir", default="data/history")
    parser.add_argument("--out", default="eval/data/candidates.jsonl")
    args = parser.parse_args()

    candidates = collect(Path(args.reports_dir), Path(args.history_dir))
    write_jsonl(candidates, args.out)

    counts: dict[str, int] = {}
    picked: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate.kind] = counts.get(candidate.kind, 0) + 1
        if candidate.picked:
            picked[candidate.kind] = picked.get(candidate.kind, 0) + 1
    print(f"已写入 {len(candidates)} 条候选 → {args.out}")
    for kind in sorted(counts):
        print(f"  {kind:10s} 候选 {counts[kind]:4d} · 入选 {picked.get(kind, 0):4d}")


if __name__ == "__main__":
    main()
