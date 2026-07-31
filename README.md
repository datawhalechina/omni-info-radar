<h1 align="center"> Omni Info Radar（⚠️ Alpha 内测版） </h1>

> [!CAUTION]
> ⚠️ Alpha 内测版本警告：此为早期构建版本，功能仍在持续完善，可能存在错误或不兼容变更，欢迎通过 Issue 反馈问题或建议。
>
> 内测链接：🔗https://omni-info-radar.fun-mesa-3136.chatgpt.site
>
> 公众号AK获取链接：🔗https://down.mptext.top/dashboard/api

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

- 📈 **创业者｜抢先捕捉产业风向**：每日追踪 AI 热点、产品动态与行业近况，从海量资讯中快速发现值得关注的技术信号和潜在机会。
- 💻 **技术开发者｜高效掌握前沿技术**：聚合 GitHub Trending、大厂技术博客、安全资讯与热门项目，减少信息检索时间，及时跟进技术生态变化。
- 🎓 **在读学生｜持续获取论文灵感**：精选 arXiv 论文、研究进展与高质量技术内容，为课程学习、科研选题和论文阅读提供线索。
- 🧭 **产品经理｜洞察产品与市场趋势**：集中了解主流 AI 产品更新、开源项目和用户关注方向，为产品规划与创新决策提供参考。
- 🧠 **技术团队｜打造专属情报雷达**：通过关注词过滤噪声，并将每日简报推送至飞书、企业微信、微信或 QQ，让关键信息主动抵达。

## 快速开始：

```bash
git clone https://github.com/datawhalechina/omni-info-radar.git
cd omni-info-radar
uv sync
uv run repo-courier --channels all --dry-run
```
> 本地运行需要 Python 3.10+；使用 AI 增强、微信公众号或消息推送功能时，需要自行配置对应服务的凭证。

## 在线阅读

🚧 **建设中**

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
| Sizhou Chen | 项目负责人，核心贡献者 | [Datawhale 核心成员](https://github.com/jjyaoao) |
| Hanchen Qiu | 项目负责人，核心贡献者 | [在读SE的🏓选手](https://github.com/JOJOCrazy123) |

## 参与贡献

- 如果你发现了一些问题，可以提交 Issue 进行反馈；如果长时间没有回复，可以联系 [Datawhale 保姆团队](https://github.com/datawhalechina/DOPMC/blob/main/OP.md)协助跟进。
- 如果你想参与贡献本项目，可以提交 Pull Request；提交代码前请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。
- 如果你对 Datawhale 感兴趣并希望发起新的开源项目，请参考 [Datawhale 开源项目指南](https://github.com/datawhalechina/DOPMC/blob/main/GUIDE.md)。
- 请勿将 Token、API Key、Webhook 或 SendKey 提交到 Git。

## 关注我们

<div align="center">
  <p>扫描下方二维码，关注公众号：Datawhale</p>
  <img src="https://raw.githubusercontent.com/datawhalechina/pumpkin-book/master/res/qrcode.jpeg" alt="Datawhale 公众号二维码" width="180" height="180">
</div>

## LICENSE

<a rel="license" href="LICENSE"><img alt="MIT License" style="border-width:0" src="https://img.shields.io/badge/license-MIT-green.svg"></a><br>
本项目采用 <a rel="license" href="LICENSE">MIT License</a> 进行许可。
