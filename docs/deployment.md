# 部署与定时运行

下面三种方式都使用同一份 [`config/config.yaml`](../config/config.yaml)。第一次运行建议先加 `--dry-run`，确认内容和配置符合预期后，再开启推送或定时任务。

## 本地运行

需要 Python 3.10+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/datawhalechina/omni-info-radar.git
cd omni-info-radar
uv sync
uv run repo-courier --channels all --dry-run
```

根据需要修改 `config/config.yaml` 中的关注词、频道和推送开关。AI、推送等凭证通过环境变量传入；变量名称可参考 [`.env.example`](../.env.example)。例如在 macOS/Linux 中：

```bash
export REPO_LLM_API_KEY="your-api-key"
export REPO_LLM_MODEL="your-model"
uv run repo-courier --channels all
```

报告默认写入 `reports/<日期>/`，GitHub Trending 历史数据写入 `data/history/`。

## Docker

Docker 适合已有容器环境的单次运行。先构建镜像：

```bash
docker build -t omni-info-radar .
```

准备好本地 `config/` 与环境变量文件后运行。`--env-file` 可以直接使用按 `.env.example` 填写的文件。

```bash
docker run --rm \
  --env-file .env \
  -v "$PWD/config:/app/config:ro" \
  -v "$PWD/reports:/app/reports" \
  -v "$PWD/data:/app/data" \
  omni-info-radar --dry-run
```

去掉 `--dry-run` 即可生成正式报告并执行已配置的推送。容器默认只运行一次；如需每天执行，请由宿主机 cron、容器平台的定时任务或 GitHub Actions 触发。

## GitHub Actions

仓库内置 [每日任务](../.github/workflows/daily.yml)，默认每天北京时间 09:00 运行，也可以在 Actions 页面手动触发。

使用自己的 fork 时：

1. 在 fork 的 **Settings → Secrets and variables → Actions** 中添加需要的凭证。常用的是 `REPO_LLM_API_KEY`、`REPO_LLM_MODEL`，以及选用的推送凭证（如 `FEISHU_WEBHOOK`、`WECOM_WEBHOOK` 或邮件 SMTP 变量）。
2. 按需修改 fork 中的 `config/config.yaml`，例如关注词、频道和推送开关。
3. 在 Actions 页面手动运行一次 `Daily RepoCourier`，确认推送和内容正确。

当前工作流会生成报告并发送到已配置的推送渠道，但不会把 `reports/` 上传为 artifact、提交回仓库或部署成网站。如果希望长期查看报告，请另行增加 artifact、外部存储或站点部署步骤。
