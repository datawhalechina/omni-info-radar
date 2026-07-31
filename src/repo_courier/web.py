from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr, field_validator

from .config import AppConfig, ReportConfig, load_config
from .runner import run

logger = logging.getLogger(__name__)

ASSET_DIR = Path(__file__).with_name("web_assets")
DEFAULT_AI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_AI_ENDPOINT = f"{DEFAULT_AI_BASE_URL}/chat/completions"
OFFICIAL_AI_BASE_URLS = (
    DEFAULT_AI_BASE_URL,
    "https://api.anthropic.com/v1",
    "https://open.bigmodel.cn/api/paas/v4",
    "https://api.moonshot.cn/v1",
    "https://api.minimaxi.com/v1",
    "https://api.stepfun.com/v1",
)
SUPPORTED_LANGUAGES = {"", "python", "javascript", "typescript", "go", "rust", "java"}
MAX_REQUEST_BYTES = 16 * 1024
SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


class PreviewRequest(BaseModel):
    interests: list[str] = Field(min_length=1, max_length=12)
    sources: list[str] = Field(default_factory=lambda: ["github"], min_length=1, max_length=12)
    language: str = Field(default="", max_length=20)
    github_token: SecretStr | None = Field(default=None, max_length=500)
    wechat_auth_key: SecretStr | None = Field(default=None, max_length=500)
    ai_base_url: str = Field(default=DEFAULT_AI_BASE_URL, max_length=300)
    ai_model: str = Field(default="", max_length=120)
    ai_api_key: SecretStr | None = Field(default=None, max_length=500)
    ui_language: str = Field(default="zh", max_length=8)

    @field_validator("interests")
    @classmethod
    def clean_interests(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw_value in values:
            value = re.sub(r"\s+", " ", raw_value).strip()
            if not value:
                continue
            if len(value) > 40:
                raise ValueError("单个关注词不能超过 40 个字符")
            if value.lower() not in {item.lower() for item in cleaned}:
                cleaned.append(value)
        if not cleaned:
            raise ValueError("至少填写一个关注词")
        return cleaned

    @field_validator("language")
    @classmethod
    def supported_language(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_LANGUAGES:
            raise ValueError("不支持该语言筛选")
        return normalized

    @field_validator("ui_language")
    @classmethod
    def supported_ui_language(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"zh", "en"}:
            raise ValueError("界面语言仅支持 zh 或 en")
        return normalized

    @field_validator("sources")
    @classmethod
    def clean_sources(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip().lower() for value in values))
        if not cleaned or any(not SOURCE_ID_PATTERN.fullmatch(value) for value in cleaned):
            raise ValueError("请至少选择一个可用的内容频道")
        return cleaned


def load_web_config() -> AppConfig:
    return load_config(os.getenv("REPO_COURIER_CONFIG", "config/config.yaml"))


def source_options(config: AppConfig | None = None) -> list[dict[str, object]]:
    config = config or load_web_config()
    options: list[dict[str, object]] = []
    if config.wechat.accounts:
        options.append(
            {
                "id": "wechat",
                "title": config.wechat.title,
                "source_count": len(config.wechat.accounts),
                "default": False,
                "requires_key": not bool(config.wechat.auth_key.strip()),
            }
        )
    options.append(
        {
            "id": "github",
            "title": "GitHub Trending",
            "source_count": 1,
            "default": True,
        }
    )
    options.extend(
        {
            "id": channel.channel_id,
            "title": channel.title,
            "source_count": len(channel.sources),
            "default": False,
        }
        for channel in config.rss.channels.values()
    )
    return options


def product_display_name(source_name: str) -> str:
    return re.sub(r"\s+Releases?$", "", source_name, flags=re.IGNORECASE).strip() or source_name


def normalize_ai_endpoint(value: str) -> str:
    base_url = value.strip().rstrip("/")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("模型服务地址必须是不包含账号、查询参数的 HTTPS 地址")
    path = parsed.path.rstrip("/")
    if not path.endswith("/chat/completions"):
        path = f"{path}/chat/completions" if path else "/chat/completions"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def allowed_ai_base_urls() -> set[str]:
    configured = os.getenv("REPO_COURIER_ALLOWED_AI_BASE_URLS", "")
    values = {normalize_ai_endpoint(item) for item in OFFICIAL_AI_BASE_URLS}
    for item in configured.split(","):
        if not item.strip():
            continue
        try:
            values.add(normalize_ai_endpoint(item))
        except ValueError:
            continue
    return values


def validate_ai_settings(payload: PreviewRequest) -> tuple[str, str, str]:
    key = payload.ai_api_key.get_secret_value().strip() if payload.ai_api_key else ""
    model = payload.ai_model.strip()
    if bool(key) != bool(model):
        raise ValueError("启用 AI 时需要同时填写 API Key 和模型名称")
    if not key:
        return "", "", ""

    endpoint = normalize_ai_endpoint(payload.ai_base_url)
    if endpoint not in allowed_ai_base_urls():
        raise ValueError(
            "该模型服务地址未被当前站点允许；"
            "自托管时请通过 REPO_COURIER_ALLOWED_AI_BASE_URLS 加入允许列表并重启"
        )
    return endpoint, model, key


def validate_sources(payload: PreviewRequest, config: AppConfig) -> None:
    available = {str(option["id"]) for option in source_options(config)}
    unknown = [source for source in payload.sources if source not in available]
    if unknown:
        raise ValueError(f"未知内容频道: {', '.join(unknown)}")


def validate_wechat_settings(payload: PreviewRequest, config: AppConfig) -> str:
    request_key = (
        payload.wechat_auth_key.get_secret_value().strip() if payload.wechat_auth_key else ""
    )
    auth_key = request_key or config.wechat.auth_key.strip()
    if "wechat" in payload.sources and not auth_key:
        raise ValueError("使用微信公众号频道时，需要填写微信公众号 API Key")
    return auth_key


def generate_preview(payload: PreviewRequest) -> dict[str, object]:
    base_url, model, api_key = validate_ai_settings(payload)
    github_token = payload.github_token.get_secret_value().strip() if payload.github_token else ""
    config = load_web_config()
    validate_sources(payload, config)
    wechat_auth_key = validate_wechat_settings(payload, config)
    config.profile.interests = payload.interests
    config.profile.daily_picks = 3
    config.profile.output_language = payload.ui_language
    config.github.language = payload.language
    if github_token:
        config.github.token = github_token
    if wechat_auth_key:
        config.wechat.auth_key = wechat_auth_key
    config.repo_llm.enabled = bool(api_key and model)
    config.repo_llm.api_key = api_key
    config.repo_llm.base_url = base_url or DEFAULT_AI_ENDPOINT
    config.repo_llm.model = model
    config.repo_llm.output_language = payload.ui_language
    # Keep public previews bounded even when the self-hosted config is more ambitious.
    config.rss.defaults.max_items_per_source = min(config.rss.defaults.max_items_per_source, 4)
    config.rss.defaults.llm_candidates = min(config.rss.defaults.llm_candidates, 4)
    config.rss.defaults.top_k = 3
    config.rss.defaults.max_input_tokens = min(config.rss.defaults.max_input_tokens, 2_000)
    config.rss.defaults.max_analysis_workers = min(config.rss.defaults.max_analysis_workers, 4)
    config.push.enabled = False

    with TemporaryDirectory(prefix="repo-courier-web-") as directory:
        config.report = ReportConfig(
            output_dir=str(Path(directory) / "reports"),
            data_dir=str(Path(directory) / "history"),
            title=config.report.title,
            product_display_names=config.report.product_display_names,
        )
        result = run(config, dry_run=True, channels=payload.sources)

    repositories = [
        {
            "rank": item.pick_rank,
            "trending_rank": item.rank,
            "full_name": item.full_name,
            "url": item.url,
            "description": item.description,
            "summary": item.summary,
            "language": item.language,
            "stars": item.stars,
            "stars_today": item.stars_today,
            "forks": item.forks,
            "license": item.license,
            "relevance_score": item.relevance_score,
            "recommendation": (
                {"深挖": "Explore", "关注": "Watch", "略过": "Skip"}.get(
                    item.recommendation, item.recommendation
                )
                if payload.ui_language == "en"
                else item.recommendation
            ),
            "why_for_you": (
                "Matches your interests: "
                f"{', '.join(item.matched_interests[:3])}; "
                f"about {item.stars_today:,} new Stars today."
                if payload.ui_language == "en" and item.matched_interests
                else item.why_for_you
            ),
            "matched_interests": item.matched_interests,
            "highlights": item.highlights,
            "use_cases": item.use_cases,
            "category": item.category,
            "risk_note": item.risk_note,
            "analysis_status": item.analysis_status,
        }
        for item in result.repositories
    ]
    channels = []
    for channel in result.rss_channels.values():
        if channel.channel_id == "wechat":
            expected_sources = len(config.wechat.accounts)
        else:
            rss_channel = config.rss.channels.get(channel.channel_id)
            expected_sources = len(rss_channel.sources) if rss_channel else 0
        fully_failed = (
            bool(channel.errors)
            and channel.scanned_count == 0
            and len(channel.errors) >= max(expected_sources, 1)
        )
        public_error = ""
        if fully_failed:
            if channel.channel_id == "wechat":
                error_text = " ".join(channel.errors.values()).lower()
                if "网络安全策略拦截" in error_text:
                    public_error = "当前网络拦截公众号数据服务，请放行 down.mptext.top"
                elif "401" in error_text or "403" in error_text:
                    public_error = "公众号接口拒绝访问，请检查网络权限或 API Key"
                else:
                    public_error = "公众号数据服务暂时不可用"
            else:
                public_error = f"{channel.title}的上游来源暂时不可用"
        channels.append(
            {
                "id": channel.channel_id,
                "title": channel.title,
                "scanned_count": channel.scanned_count,
                "errors_count": len(channel.errors),
                "status": "error" if fully_failed else "ok",
                "message": public_error,
                "items": [
                    {
                        "rank": item.pick_rank,
                        "source_id": item.source_id,
                        "source_name": item.source_name,
                        "product_name": (
                            product_display_name(item.source_name)
                            if channel.channel_id == "products"
                            else ""
                        ),
                        "version": item.title if channel.channel_id == "products" else "",
                        "title": item.title,
                        "url": item.url,
                        "summary": item.summary,
                        "authors": item.authors,
                        "published_at": (
                            item.published_at.isoformat() if item.published_at else None
                        ),
                        "relevance_score": item.relevance_score,
                        "innovation_score": item.innovation_score,
                        "recommendation_reason": item.recommendation_reason,
                        "matched_keywords": item.matched_keywords,
                        "analysis_status": item.analysis_status,
                    }
                    for item in channel.items
                ],
            }
        )
    return {
        "scanned_count": result.scanned_count,
        "rss_scanned_count": sum(channel["scanned_count"] for channel in channels),
        "repositories": repositories,
        "channels": channels,
        "sources": payload.sources,
        "used_ai": bool(api_key and model),
    }


def ndjson_event(event: dict[str, object]) -> bytes:
    return (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def preview_failure_message(result: dict[str, object]) -> str:
    channels = result.get("channels")
    if not isinstance(channels, list):
        return ""
    for channel in channels:
        if not isinstance(channel, dict) or channel.get("status") != "error":
            continue
        message = channel.get("message")
        return str(message) if message else "该频道暂时不可用"
    return ""


async def stream_preview_events(
    application: FastAPI,
    payload: PreviewRequest,
    request: Request,
    source_titles: dict[str, str],
) -> AsyncIterator[bytes]:
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    total = len(payload.sources)
    completed = 0
    failed = 0

    yield ndjson_event(
        {
            "type": "start",
            "total": total,
            "sources": [
                {"id": source, "title": source_titles[source]} for source in payload.sources
            ],
        }
    )

    async def process_source(source: str) -> None:
        async with application.state.preview_channel_slots:
            request_wechat_key = bool(
                source == "wechat"
                and payload.wechat_auth_key
                and payload.wechat_auth_key.get_secret_value().strip()
            )
            await queue.put(
                {
                    "type": "channel_started",
                    "source": source,
                    "title": source_titles[source],
                    "credential_source": ("request" if request_wechat_key else "server")
                    if source == "wechat"
                    else None,
                }
            )
            try:
                source_payload = payload.model_copy(deep=True, update={"sources": [source]})
                result = await asyncio.wait_for(
                    run_in_threadpool(generate_preview, source_payload),
                    timeout=application.state.preview_channel_timeout,
                )
                failure_message = preview_failure_message(result)
                if failure_message:
                    await queue.put(
                        {
                            "type": "channel_error",
                            "source": source,
                            "title": source_titles[source],
                            "message": failure_message,
                            "credential_source": ("request" if request_wechat_key else "server")
                            if source == "wechat"
                            else None,
                        }
                    )
                    return
                await queue.put(
                    {
                        "type": "channel_complete",
                        "source": source,
                        "title": source_titles[source],
                        "result": result,
                    }
                )
            except TimeoutError:
                logger.warning("Web 流式预览频道 %s 处理超时", source)
                await queue.put(
                    {
                        "type": "channel_error",
                        "source": source,
                        "title": source_titles[source],
                        "message": "该频道处理超时",
                    }
                )
            except Exception:
                logger.exception("Web 流式预览频道 %s 处理失败", source)
                await queue.put(
                    {
                        "type": "channel_error",
                        "source": source,
                        "title": source_titles[source],
                        "message": "该频道暂时不可用",
                    }
                )

    async with application.state.preview_slots:
        tasks = [asyncio.create_task(process_source(source)) for source in payload.sources]
        try:
            while completed + failed < total:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1)
                except TimeoutError:
                    continue
                if event["type"] == "channel_complete":
                    completed += 1
                elif event["type"] == "channel_error":
                    failed += 1
                yield ndjson_event(event)
            if completed + failed == total:
                yield ndjson_event(
                    {
                        "type": "complete",
                        "total": total,
                        "completed": completed,
                        "failed": failed,
                    }
                )
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


def create_app() -> FastAPI:
    application = FastAPI(
        title="RepoCourier Web",
        description="从 GitHub 与科技 RSS 频道中选出今天最值得打开的内容。",
        version="0.2.0-beta",
        docs_url=None,
        redoc_url=None,
    )
    application.state.preview_slots = asyncio.Semaphore(
        max(1, int(os.getenv("REPO_COURIER_WEB_CONCURRENCY", "2")))
    )
    application.state.preview_channel_slots = asyncio.Semaphore(
        max(1, int(os.getenv("REPO_COURIER_WEB_CHANNEL_CONCURRENCY", "3")))
    )
    application.state.preview_channel_timeout = max(
        10, int(os.getenv("REPO_COURIER_WEB_CHANNEL_TIMEOUT_SECONDS", "60"))
    )
    application.mount("/assets", StaticFiles(directory=ASSET_DIR), name="assets")

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del request
        errors = [
            {key: value for key, value in error.items() if key not in {"input", "ctx"}}
            for error in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": errors})

    @application.middleware("http")
    async def security_headers(request: Request, call_next):
        try:
            content_length = int(request.headers.get("content-length", "0"))
        except ValueError:
            content_length = 0
        if content_length > MAX_REQUEST_BYTES:
            response = JSONResponse(status_code=413, content={"detail": "请求内容过大"})
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    @application.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(ASSET_DIR / "index.html")

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/api/options")
    async def options() -> dict[str, object]:
        return {"sources": source_options()}

    @application.post("/api/preview")
    async def preview(payload: PreviewRequest) -> dict[str, object]:
        try:
            async with application.state.preview_slots:
                return await run_in_threadpool(generate_preview, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Web 预览生成失败")
            raise HTTPException(status_code=502, detail="暂时无法生成预览，请稍后再试") from exc

    @application.post("/api/preview/stream", response_class=StreamingResponse)
    async def preview_stream(payload: PreviewRequest, request: Request) -> StreamingResponse:
        try:
            config = load_web_config()
            validate_sources(payload, config)
            validate_ai_settings(payload)
            validate_wechat_settings(payload, config)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        titles = {str(option["id"]): str(option["title"]) for option in source_options(config)}
        return StreamingResponse(
            stream_preview_events(application, payload, request, titles),
            media_type="application/x-ndjson",
            headers={"X-Accel-Buffering": "no"},
        )

    return application


app = create_app()


def main() -> None:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("请先安装 Web 依赖: pip install 'repo-courier[web]'") from exc
    uvicorn.run(
        "repo_courier.web:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=True,
    )
