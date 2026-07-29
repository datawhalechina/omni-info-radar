<h1 align="center"> Omni Info Radar（⚠️ Alpha 内测版） </h1>

> [!CAUTION]
> ⚠️ Alpha 内测版本警告：此为早期构建版本，功能仍在持续完善，可能存在错误或不兼容变更，欢迎通过 Issue 反馈问题或建议。

Omni Info Radar 是一个个性化技术情报雷达。它从微信公众号、GitHub、科技新闻、大厂博客、学术论文、产品更新和安全资讯等公开来源收集候选内容，再根据关注词进行去噪与排序，生成每日精选报告。

- 支持 GitHub、微信公众号、新闻、博客、论文、产品更新和安全资讯 7 个频道。
- 支持通过关键词筛选，并可选使用 OpenAI Chat Completions 兼容接口增强分析。
- 未配置 AI API Key 时，自动使用本地规则完成摘要和排序。
- 支持生成 Markdown、HTML 和 JSON 报告。
- 支持推送到飞书、企业微信、个人微信和 QQ。
- 提供命令行工具和 Web Beta 页面。

<p align="center">
  <img src="assets/Repo-readme-v2.png" alt="Omni Info Radar 个性化技术情报" width="82%">
</p>

## 项目受众

- 希望减少信息噪声、快速获取每日技术动态的开发者和技术从业者。
- 需要持续跟踪 GitHub、AI、学术论文、产品更新或安全资讯的研究者与团队。
- 希望通过飞书、企业微信、微信或 QQ 自动接收技术简报的用户。
- 本地运行需要 Python 3.10+；使用 AI 增强、微信公众号或消息推送时，需要自行配置相应服务的凭证。

快速开始：

```bash
git clone https://github.com/JOJOCrazy123/omni-info-radar.git
cd omni-info-radar
uv sync
uv run repo-courier --channels all --dry-run
```

## 在线阅读


## 目录

| 模块 | 简介 | 状态 |
| ---- | ---- | ---- |
| [情报采集](src/repo_courier) | 聚合 GitHub Trending、微信公众号以及 RSS / Atom 信息源 | ✅ |
| [个性化分析](src/repo_courier/personalize.py) | 按关注词筛选、去噪和排序，并支持可选的 AI 增强分析 | ✅ |
| [报告生成](src/repo_courier/report.py) | 生成 Markdown、HTML 和 JSON 格式的每日简报 | ✅ |
| [消息推送](src/repo_courier/pushers) | 支持飞书、企业微信、Server酱和 OneBot | ✅ |
| [Web Beta](src/repo_courier/web.py) | 提供多频道选择、流式展示和自定义模型配置页面 | 🧪 |
| [自动化任务](.github/workflows/daily.yml) | 通过 GitHub Actions 定时生成并推送报告 | ✅ |
| [配置文件](config/config.yaml) | 管理关注方向、频道开关和 RSS / Atom 信息源 | ✅ |
| [测试](tests) | 覆盖配置、采集、摘要、报告、推送与 Web 等核心能力 | ✅ |

## 贡献者名单

| 姓名 | 职责 | 简介 |
| :---- | :---- | :---- |
| jjyaoao | 项目作者 |  |
| JOJOCrazy123 | 贡献者 |  |
| Sizhou Chen | 贡献者 |  |
| Hanchen Qiu | 贡献者 |  |
| 翰晨 | 贡献者 |  |

## 参与贡献

- 如果发现问题或有功能建议，欢迎提交 Issue。
- 如果希望参与项目开发，欢迎提交 Pull Request。
- 提交代码前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。
- 请勿将 Token、API Key、Webhook 或 SendKey 提交到 Git。

## 关注我们


## LICENSE

[MIT License](LICENSE)
