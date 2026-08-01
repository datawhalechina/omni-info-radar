# 去噪质量评测基准（Phase 0–1）

为 Omni Info Radar 建立"去噪/排序/摘要质量"的离线评测标尺。方法论与构念定义见
[`docs/research/去噪质量评测基准.md`](../docs/research/去噪质量评测基准.md)。

## 为什么需要它

系统当前只输出"入选了什么"，但无法回答"选得对不对、漏没漏、摘要忠不忠实"。
文献表明这类策展系统的风险恰恰是**自身成为新的信息过载源**（全球已有 40% 用户回避新闻），
而项目普遍**缺少质量度量**。谁先建立标尺，谁就掌握迭代的判据。

评测分三层，各有指标：
| 层 | 系统动作 | 指标 |
|---|---|---|
| 去噪/筛选 | `feeds.score_item` + 关键词覆盖 | precision@k / recall / 误推率 |
| 排序 | `combined_score` | nDCG@k / MRR / 多样性(ILD) / 新颖性 |
| 摘要/理由 | `RssAnalyzer` / `Summarizer` | G-Eval 四维（忠实/相关/连贯/流畅） |

## 数据流

```
运行(开 eval_dump) ──► reports/{date}/eval_candidates.json ─┐
运行(总是) ─────────► data/history/{date}.json ────────────┤  eval/collect.py
                                                            ▼
                                              eval/data/candidates.jsonl
                                                            │  eval/sample_for_annotation.py
                                                            ▼
                              eval/data/annotation_sheet.{jsonl,md}  ──► 人工标注 ──► gold.jsonl
                                                            │  eval/agreement.py
                                                            ▼
                                              Cohen's κ 校验（≥0.6 才可用）
```

## 使用步骤

```bash
# Phase 0：开启候选池导出后运行（候选池含被淘汰的近邻负例）
REPO_COURIER_EVAL_DUMP=on uv run repo-courier --channels all --dry-run
#   或在 config.yaml 的 report 段设 eval_dump: true

# Phase 0：聚合所有历史快照为分析就绪文件
python -m eval.collect --out eval/data/candidates.jsonl

# Phase 1：分层采样 + 近邻难负例，产出标注表
python -m eval.sample_for_annotation \
    --candidates eval/data/candidates.jsonl \
    --per-kind 30 --seed 42

# Phase 1：人工标注 annotation_sheet.md/jsonl（口径见 docs/research/去噪质量评测基准.md）

# Phase 1：两位标注者一致性校验
python -m eval.agreement --a gold_anna.jsonl --b gold_ben.jsonl --all
```

标注格式参考 [`gold.example.jsonl`](gold.example.jsonl)。

## 目录

| 文件 | 作用 |
|---|---|
| `schema.py` | 统一候选记录模型 + 归一化（eval_candidates.json / history → Candidate） |
| `collect.py` | 聚合候选池快照 → `candidates.jsonl`（按日去重，保留完整池供 recall） |
| `sample_for_annotation.py` | 分层采样 + 近邻难负例 → 标注表（jsonl + md） |
| `agreement.py` | 两份标注的 Cohen's κ / 一致率 |
| `gold.example.jsonl` | 标注文件格式示例 |

## 后续（Phase 2+，未含在本次改动）

- `metrics.py`：precision@k / recall / nDCG / ILD / G-Eval，对 Gold Set 跑回归；
- 接入 CI：任一维度相对基线显著退化即报警；
- IM 反馈回路（👍/👎）做小规模在线校验，弥补"离线≠在线"鸿沟。

## 注意

- `eval/data/` 为生成产物，已在 `.gitignore` 排除；`gold.example.jsonl` 随库版本化。
- 本工具包独立于主程序，`python -m eval.*` 在仓库根目录运行。
