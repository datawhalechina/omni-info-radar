# 📮 RepoCourier

> 从 微信公众号、GitHub、科技新闻、大厂博客、学术论文、产品更新和安全资讯中，挑出今天真正与你相关的技术信号。

<p align="center">
  <img src="assets/Repo-readme-v2.png" alt="RepoCourier 个性化技术情报" width="82%">
</p>

RepoCourier 不是又一个大而全的信息搜集器。它先从多个公开信息源收集候选内容，再根据你的关注词去噪、重新排序，每个频道只保留最值得打开的几条。

- **7 个情报频道**：微信公众号、GitHub、科技新闻、大厂博客、学术论文、产品更新和安全资讯。
- **24 个上游信息源**：默认配置 Arxiv、机器之心、Google Security、Claude Code Release等信息源。
- **个性化精选**：先用关键词筛选，再可选使用 AI 分析相关性与创新性。
- **没有 AI Key 也能运行**：自动回退到本地规则摘要和排序。
- **报告与推送**：输出 Markdown、HTML、JSON，可推送到飞书、企业微信、个人微信和 QQ。

## 情报来源

| 频道 | 默认信息源 | 挑选方式 |
| --- | --- | --- |
| 🔥 GitHub Trending | GitHub Trending 页面、仓库元数据、Topics 与 README | 关注词 + Star 增长 + Trending 排名 |
| 📰 科技新闻 | MIT Technology Review、The Verge、WIRED、Ars Technica | 新闻价值、相关性与时效性 |
| 🏢 大厂博客 | OpenAI、Google DeepMind、Google AI、Hugging Face | 技术贡献、工程实践与影响范围 |
| 🎓 学术论文 | arXiv AI、NLP、CV 与 Machine Learning | 研究相关性与方法创新性 |
| 🚀 产品更新 | Gemini CLI、OpenAI Codex、Claude Code、OpenClaw Releases | 功能变化、兼容性与实用影响 |
| 🛡️ 安全资讯 | Krebs on Security、The Hacker News、Google Security、安全客 | 风险等级、受影响范围与可操作性 |
| 💬 微信公众号 | 机器之心、量子位、新智元、阿里云开发者、腾讯云开发者、Datawhale | 关注词、信息密度、技术深度与时效价值 |

信息源不写死在程序中。可以在 [`config/config.yaml`](config/config.yaml) 增删 RSS / Atom Feed，也可以添加新的专题频道。

## 快速开始

需要 Python 3.10+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/datawhalechina/omni-info-radar.git
cd repo-courier
uv sync
uv run repo-courier --channels all --dry-run
```

`--dry-run` 会生成报告，但不发送消息。不传 `--date` 时，GitHub 获取实时 Daily Trending，微信公众号和 RSS 频道检索北京时间今天的内容。

报告会写入：

```text
reports/YYYY-MM-DD/daily.md
reports/YYYY-MM-DD/daily.html
reports/YYYY-MM-DD/daily.json
```

## 配置你的关注方向

编辑 [`config/config.yaml`](config/config.yaml)：

```yaml
profile:
  interests: [agent, llm, mcp, ai]
  exclude_keywords: [awesome list, interview, tutorial collection]
  daily_picks: 3
```

推荐使用仓库 Topics、论文关键词和技术新闻中常见的英文词组。也可以临时覆盖：

```bash
export REPO_COURIER_INTERESTS="rust,database,self-hosted,security"
```

如果需要微信公众号源，需要访问 [https://down.mptext.top/dashboard/api](https://down.mptext.top/dashboard/api) 获取 apiKey，并填入：

```bash
export WECHAT_AUTH_KEY="your-api-key"
```

## 可选：使用 AI 增强分析

GitHub 摘要和所有 RSS 频道共用一套 OpenAI Chat Completions 兼容配置，可使用 OpenAI 或其它实现相同请求与响应格式的模型服务：

```bash
export REPO_LLM_API_KEY="your-key"
export REPO_LLM_BASE_URL="https://api.openai.com/v1/chat/completions"
export REPO_LLM_MODEL="your-model"
```

API Key 只通过环境变量或 Web 页面传入，不要写进 YAML 或提交到 Git。未配置 Key 时，项目会继续使用透明的关键词规则运行。

### 接入其他 OpenAI 兼容 API

Web 页面已预设 OpenAI、Claude、智谱 GLM、Kimi、MiniMax 和阶跃星辰的官方 Chat Completions 端点，选择服务商后会自动填入 API 根地址和模型示例。模型 ID 会随厂商更新，请以各平台控制台中当前可用的 ID 为准。

| 服务商 | API 根地址 | 模型示例 |
| --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | 按账户可用模型填写 |
| [Claude](https://platform.claude.com/docs/zh-CN/cli-sdks-libraries/libraries/openai-sdk) | `https://api.anthropic.com/v1` | `claude-sonnet-4-6` |
| [智谱 GLM](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction) | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.2` |
| [Kimi](https://platform.kimi.com/docs/api/overview) | `https://api.moonshot.cn/v1` | `kimi-k2.6` |
| [MiniMax](https://platform.minimaxi.com/docs/api-reference/text-chat-openai) | `https://api.minimaxi.com/v1` | `MiniMax-M2.7` |
| [阶跃星辰](https://platform.stepfun.com/docs/zh/guides/developer/openai) | `https://api.stepfun.com/v1` | `step-3.5-flash` |

Claude 通过 Anthropic 官方的 OpenAI SDK 兼容层接入，可用于 RepoCourier 所需的基础 Chat Completions 分析。如果需要 Claude 的完整高级能力，Anthropic 更推荐使用原生 Messages API。

为防止公共 Web 服务被用来访问任意网址，官方预设以外的聚合网关或自建服务需由部署者显式放行。例如使用 DMXAPI：

```bash
REPO_COURIER_ALLOWED_AI_BASE_URLS=https://www.dmxapi.cn/v1 uv run repo-courier-web
```

同时放行多个自定义地址时使用逗号分隔：

```bash
REPO_COURIER_ALLOWED_AI_BASE_URLS="https://www.dmxapi.cn/v1,https://your-gateway.example/v1" uv run repo-courier-web
```

环境变量只在进程启动时读取；修改后需要重启 Web 服务。允许列表只放行目标地址，用户仍需在页面填入自己的模型 ID 和 API Key。

GitHub Token 也是可选的，用于提高 API 限额和补全仓库信息：

```bash
export GITHUB_TOKEN="your-fine-grained-token"
```

只分析公开仓库时，Fine-grained Token 使用 `Metadata: Read-only` 和 `Contents: Read-only` 即可。

## Web Beta

Web Beta 提供一个简约的单次情报页面：

- 动态读取 GitHub、微信公众号和 `config.yaml` 中的 RSS 频道。
- 多选情报频道，每个频道最多精选 3 条。
- 所选频道有限并行处理，并通过流式响应逐个展示已完成的频道。
- 可按需填写自己的 GitHub Token、微信公众号 API Key，以及 OpenAI 兼容服务的 API 地址、模型名称与 API Key。
- Web 页面可填写 API 根地址（如 `https://api.openai.com/v1`）或完整的 `chat/completions` 地址。
- 页面填写的密钥只保留到当前页面刷新，不写入报告、日志、数据库或浏览器存储。
- 公共 Web 实例只生成预览，不代替用户发送飞书、微信或 QQ 消息。

本地启动：

```bash
uv sync --extra web
uv run repo-courier-web
# 打开 http://127.0.0.1:8000
```

部署到 Render 时可以使用仓库根目录的 [`render.yaml`](render.yaml)。公开实例必须通过 `REPO_COURIER_ALLOWED_AI_BASE_URLS` 限制允许请求的模型服务，多个 API 根地址或完整端点使用逗号分隔，避免任意网址访问。

Web 默认最多同时处理 3 个频道、单频道最多等待 60 秒；自部署时可以通过 `REPO_COURIER_WEB_CHANNEL_CONCURRENCY` 和 `REPO_COURIER_WEB_CHANNEL_TIMEOUT_SECONDS` 调整，但不建议把并发设置过高，以免对上游来源造成突发请求。

## 选择频道

```bash
# 只看 GitHub、科技新闻和安全资讯
uv run repo-courier --channels github,news,security --dry-run

# 运行全部频道
uv run repo-courier --channels all --dry-run

# 指定 RSS 检索日期
uv run repo-courier --channels news,blogs --date 2026-07-15 --dry-run
```

不传 `--channels` 时，按 `config.yaml` 中每个频道的 `enabled` 开关运行。可用值为：

```text
github, wechat, news, blogs, academic, products, security, all
```

## 每天自动生成和推送

仓库内置 [GitHub Actions 工作流](.github/workflows/daily.yml)。Fork 项目后，在 `Settings → Secrets and variables → Actions` 中添加所需的 Secrets，即可每天生成报告。

| 能力 | Secret |
| --- | --- |
| GitHub 仓库元数据 | `GITHUB_TOKEN` |
| 微信公众号文章 | `WECHAT_AUTH_KEY` |
| AI 分析 | `REPO_LLM_API_KEY`、`REPO_LLM_BASE_URL`、`REPO_LLM_MODEL` |
| 飞书群机器人 | `FEISHU_WEBHOOK` |
| 企业微信群机器人 | `WECOM_WEBHOOK` |
| 个人微信 Server酱 | `SERVERCHAN_SENDKEY` |
| 个人 QQ OneBot | `ONEBOT_URL`、`ONEBOT_USER_ID`，可选 `ONEBOT_TOKEN` |

公共 Web 页面不接收这些推送凭证。需要长期自动推送时，应将凭证保存在用户自己的 GitHub Actions Secrets 或自托管环境中。

## 工作流程

```text
微信公众号 / GitHub Trending / RSS / Atom
              ↓
    日期窗口与关键词去噪
              ↓
      频道内候选排序
              ↓
   可选 AI 相关性分析
              ↓
 Markdown / HTML / JSON 报告
              ↓
 飞书 / 企微 / 微信 / QQ
```

RSS 信息源的某一站失败不会中断其他频道；AI 请求失败也会自动回退到本地规则结果。

## 开发

```bash
uv sync --extra dev --extra web
uv run pytest
uv run ruff check .
```

项目结构：

```text
src/repo_courier/
├── trending.py       # GitHub Trending 抓取
├── github.py         # GitHub 元数据与 README
├── feeds.py          # 统一 RSS / Atom 抓取、分析与排序
├── wechat.py         # 微信公众号文章抓取与分析
├── prompts/          # 各频道 AI 分析提示词
├── personalize.py    # GitHub 个性化排序
├── report.py         # Markdown / HTML / JSON 报告
├── pushers/          # 飞书、企微、Server酱、OneBot
├── web.py            # Web Beta API
└── runner.py         # 全流程编排
```

贡献前请阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

## 安全与平台说明

- 不要将 Token、API Key、Webhook 或 SendKey 提交到 Git。
- 开启 AI 后，公开仓库 README 片段与 RSS 候选内容会发送给所配置的模型服务。
- 个人微信没有通用官方机器人接口，Server酱属于第三方服务。
- QQ 推送依赖 OneBot 实现，请遵守对应平台规则。

## License

[MIT](LICENSE)
