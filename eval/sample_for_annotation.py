"""Phase 1 标注采样器：从候选池抽取高诊断力的标注样本。

采样原则（依据 docs/research/去噪质量评测基准.md）：
1. 近邻难负例优先：每个"竞争池"(同 date+kind) 内，为每个入选项配对一个
   分数最高的落选项（系统判它最该被拒的对手）。元评测研究指出，指标只在
   质量接近的候选之间才有区分力，因此这类近邻对是基准的诊断核心。
2. 分数分层覆盖：剩余名额按 final_score 三分位（高/中/低）分层抽取，
   避免样本只集中在高分段。
3. 内容去重：同一文章（dedup_key）只让人标注一次。

用法：
    python -m eval.sample_for_annotation \
        --candidates eval/data/candidates.jsonl \
        --out eval/data/annotation_sheet.jsonl \
        --md eval/data/annotation_sheet.md \
        --per-kind 30 --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.schema import GOLD_FIELDS, Candidate, read_jsonl


def _pool_key(candidate: Candidate) -> tuple[str, str]:
    return (candidate.date, candidate.kind)


def near_miss_pairs(pool: list[Candidate]) -> list[Candidate]:
    """每个竞争池内，为每个入选项配一个分数最高的落选项作难负例，**交错返回**。

    返回顺序为 [入选1, 难负例1, 入选2, 难负例2, ...]，保证按序截断到配额时，
    优先保留完整的"入选+难负例"对，而不是先把入选项占满、把难负例挤掉。
    """
    picked = [c for c in pool if c.picked]
    rejected = sorted((c for c in pool if not c.picked), key=lambda c: -c.final_score)
    used: set[str] = set()
    forced: list[Candidate] = []
    for pick in picked:
        forced.append(pick)
        for candidate in rejected:
            if candidate.dedup_key not in used:
                forced.append(candidate)
                used.add(candidate.dedup_key)
                break
    return forced


def _tercile(values: list[float]) -> tuple[float, float]:
    ordered = sorted(values)
    n = len(ordered)
    if n < 3:
        mid = ordered[n // 2] if n else 0.0
        return (mid, mid)
    return (ordered[n // 3], ordered[(2 * n) // 3])


def stratified_fill(
    pool: list[Candidate], budget: int, rng: random.Random, taken: set[str]
) -> list[Candidate]:
    """按分数三分位分层、尽量平衡入选/落选，补足剩余名额。

    budget 是本频道还需补足的名额（已由调用方按 per_kind - 已选 计算）；
    taken 仅用于跨频道/跨池去重，不重复扣减名额。
    """
    remaining = budget
    low, high = _tercile([c.final_score for c in pool])
    buckets: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in pool:
        if candidate.dedup_key in taken:
            continue  # 已被强制集或其他频道占用，跳过
        if candidate.final_score <= low:
            band = "low"
        elif candidate.final_score >= high:
            band = "high"
        else:
            band = "mid"
        buckets[f"{band}:{'picked' if candidate.picked else 'reject'}"].append(candidate)
    for items in buckets.values():
        rng.shuffle(items)

    picked_out: list[Candidate] = []
    keys = sorted(buckets)
    while remaining > 0 and any(buckets[k] for k in keys):
        for key in keys:  # 轮转各层，保证覆盖
            if remaining <= 0:
                break
            if buckets[key]:
                chosen = buckets[key].pop()
                picked_out.append(chosen)
                taken.add(chosen.dedup_key)
                remaining -= 1
    return picked_out


def sample(candidates: list[Candidate], per_kind: int, seed: int) -> list[Candidate]:
    rng = random.Random(seed)
    pools: dict[tuple[str, str], list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        pools[_pool_key(candidate)].append(candidate)

    # 1) 每个竞争池产出的强制集：入选项与其近邻难负例**交错排列**，
    #    保证即使配额紧张，每个入选项的难负例对也能整体进入（不被截掉）。
    by_kind_forced: dict[str, list[Candidate]] = defaultdict(list)
    for pool in pools.values():
        for candidate in near_miss_pairs(pool):
            by_kind_forced[candidate.kind].append(candidate)

    selected: list[Candidate] = []
    taken: set[str] = set()
    for kind in sorted(by_kind_forced):
        forced: list[Candidate] = []
        for candidate in by_kind_forced[kind]:  # 交错去重，难负例随入选项保留
            if candidate.dedup_key not in taken:
                forced.append(candidate)
                taken.add(candidate.dedup_key)
        forced = forced[:per_kind]
        selected.extend(forced)

        # 2) 剩余名额仅按本频道独立计算，不串用此前频道的选择，
        #    避免后续频道拿不到配额。
        budget = per_kind - len(forced)
        if budget > 0:
            kind_pool = [c for c in candidates if c.kind == kind]
            selected.extend(stratified_fill(kind_pool, budget, rng, taken))

    rng.shuffle(selected)
    return selected


_RUBRIC_HEADER = """# 去噪质量标注表

> 对每条候选独立判断。标注口径详见 docs/research/去噪质量评测基准.md。
> - worth_pushing：如果把它转发到同事/同行群，你是否愿意？(true/false) —— 主标签
> - relevance：与你的关注方向(agent/llm/mcp/ai)相关程度 0=无关 1=边缘 2=强相关
> - usefulness：对该方向的实际决策/工作有用程度 0=无 1=一般 2=高
> - novelty_surprise：相对你已知信息的新颖/惊喜程度 0=已知 1=略有新意 2=明显新知
> - summary_faithful：系统摘要是否忠实于正文、无臆造 (true/false)
> - summary_informative：系统摘要的信息含量 0=空泛 1=一般 2=抓到要点

"""


def _card(index: int, candidate: Candidate) -> str:
    picked = f"是(第{candidate.pick_rank}名)" if candidate.picked else "否"
    gold_lines = "\n".join(f"  - {name} (_{kind}_): " for name, kind in GOLD_FIELDS.items())
    return f"""## [{index}] ({candidate.kind}) {candidate.title}
- item_id: {candidate.item_id}
- url: {candidate.url}
- 来源/日期: {candidate.source} · {candidate.date} · status={candidate.analysis_status}
- 命中词: {"、".join(candidate.matched) or "无"} | 排除词: {"、".join(candidate.excluded) or "无"}
- 打分: rule={candidate.rule_score:g} relevance={candidate.relevance_score:g} \
innovation={candidate.innovation_score:g} final={candidate.final_score:g} | 入选: {picked}
- 系统摘要: {candidate.summary or "（无）"}
- 系统推荐理由: {candidate.recommendation_reason or "（无）"}
- 正文节选: {candidate.content_excerpt or "（无）"}
- 标注（请填写）:
{gold_lines}
"""


def write_outputs(selected: list[Candidate], out_jsonl: Path, out_md: Path) -> None:
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8") as handle:
        for candidate in selected:
            handle.write(json.dumps(candidate.gold_blank(), ensure_ascii=False) + "\n")
    cards = "\n".join(_card(i, c) for i, c in enumerate(selected, start=1))
    out_md.write_text(_RUBRIC_HEADER + cards, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="分层采样 + 近邻难负例，产出标注表")
    parser.add_argument("--candidates", default="eval/data/candidates.jsonl")
    parser.add_argument("--out", default="eval/data/annotation_sheet.jsonl")
    parser.add_argument("--md", default="eval/data/annotation_sheet.md")
    parser.add_argument("--per-kind", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    candidates = read_jsonl(args.candidates)
    selected = sample(candidates, args.per_kind, args.seed)
    write_outputs(selected, Path(args.out), Path(args.md))
    kinds = sorted({c.kind for c in selected})
    print(f"已采样 {len(selected)} 条 → {args.out} / {args.md}")
    for kind in kinds:
        n = sum(1 for c in selected if c.kind == kind)
        print(f"  {kind:10s} {n:3d} 条")


if __name__ == "__main__":
    main()
