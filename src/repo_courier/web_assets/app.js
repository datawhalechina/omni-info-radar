const form = document.querySelector("#preview-form");
const submitButton = document.querySelector("#submit-button");
const sourceGrid = document.querySelector("#source-grid");
const selectedSourceCount = document.querySelector("#selected-source-count");
const loading = document.querySelector("#loading");
const results = document.querySelector("#results");
const githubResults = document.querySelector("#github-results");
const resultList = document.querySelector("#result-list");
const channelResults = document.querySelector("#channel-results");
const emptyResult = document.querySelector("#empty-result");
const emptyResultTitle = document.querySelector("#empty-result-title");
const emptyResultDescription = document.querySelector("#empty-result-description");
const scanSummary = document.querySelector("#scan-summary");
const formError = document.querySelector("#form-error");
const keyList = document.querySelector(".key-list");
const wechatKeyPanel = document.querySelector("#wechat-key-panel");
const wechatKeyInput = document.querySelector("#wechat-auth-key");
const wechatKeySummary = document.querySelector("#wechat-key-summary");
const wechatKeyAction = document.querySelector("#wechat-key-action");
const wechatKeyNote = document.querySelector("#wechat-key-note");
const aiProviderSelect = document.querySelector("#ai-provider");
const aiBaseUrlInput = document.querySelector("#ai-base-url");
const aiModelInput = document.querySelector("#ai-model");
const aiCompatibilityNote = document.querySelector("#ai-compatibility-note");
const progressTitle = document.querySelector("#progress-title");
const progressSummary = document.querySelector("#progress-summary");
const channelProgress = document.querySelector("#channel-progress");
const languageToggle = document.querySelector("#language-toggle");
const sourceCatalog = new Map();
const renderedChannels = new Map();
let renderedRepositories = [];
let currentLanguage = localStorage.getItem("repo-courier-language") === "en" ? "en" : "zh";

const I18N = {
  zh: {
    pageTitle: "RepoCourier · 你的每日技术情报员",
    metaDescription: "RepoCourier 从 GitHub、微信公众号、大厂博客、学术论文、科技新闻、产品更新和安全资讯中挑出今日最相关的技术信号。",
    brandAria: "RepoCourier 首页",
    toggleLabel: "Switch to English",
    heroEyebrow: "PERSONAL TECH BRIEFING",
    heroTitleLead: "七个技术频道，只留",
    heroTitleAccent: "今天值得看的",
    heroCopy: "选频道、写关注词，RepoCourier 自动抓取、去噪并生成一份个人技术日报。",
    deskTitle: "定制今日情报",
    noKeyDefault: "默认无需 Key",
    channelsLegend: "内容频道",
    multiSelect: "可多选",
    loadingChannels: "正在读取频道…",
    interestsLegend: "关注方向",
    commaSeparated: "使用逗号分隔",
    interestsLabel: "关注词",
    githubLanguageLabel: "GitHub 语言筛选",
    allLanguages: "全部语言",
    credentialsLegend: "访问凭证",
    credentialsHint: "按所选频道填写",
    githubTokenHint: "提高限额与补全信息",
    add: "添加",
    optional: "可选",
    show: "显示",
    hide: "隐藏",
    githubTokenNote: "公开仓库只需 Metadata 和 Contents 的只读权限。",
    wechatApi: "微信公众号 API",
    wechatMark: "微",
    wechatKeyPlaceholder: "微信公众号抓取服务 API Key",
    compatibleAi: "OpenAI 兼容 AI",
    compatibleAiHint: "接入兼容 Chat Completions 的模型",
    modelProvider: "模型服务商",
    customProvider: "自定义兼容服务",
    zhipuProvider: "智谱 GLM",
    stepfunProvider: "阶跃星辰",
    apiBaseUrl: "API 根地址或 Chat Completions 地址",
    modelName: "模型名称",
    privacyNote: "密钥只保留在当前页面，不会保存到服务端；刷新后清除",
    selectedPrefix: "已选",
    selectedSuffix: "个频道 · 每个精选 3 条",
    generate: "生成我的今日情报",
    preparing: "正在准备今日情报……",
    streamHint: "完成一个频道，就立即展示一个频道",
    progressAria: "频道处理进度",
    signalsEyebrow: "YOUR DAILY SIGNALS",
    resultsTitle: "今天值得看的",
    emptyTitle: "今天没有足够相关的信号",
    emptyDescription: "可以放宽关注词，或选择更多频道后重试。",
    footerCopy: "信息可以很多，今天值得看的只需几条。",
    sourceGithub: "GitHub Trending",
    sourceNews: "科技新闻",
    sourceBlogs: "大厂博客",
    sourceAcademic: "学术论文",
    sourceProducts: "产品更新",
    sourceSecurity: "安全资讯",
    sourceWechat: "微信公众号",
    sourceGithubDescription: "热门项目、Topics、README 与 Star 增长",
    sourceNewsDescription: "MIT Tech Review、The Verge、WIRED 等",
    sourceBlogsDescription: "OpenAI、Google DeepMind、Hugging Face 等",
    sourceAcademicDescription: "arXiv AI、NLP、CV 与机器学习论文",
    sourceProductsDescription: "Codex、Claude Code、Gemini CLI 等发布日志",
    sourceSecurityDescription: "Krebs、The Hacker News、Google Security 等",
    sourceWechatDescription: "机器之心、量子位、新智元等公众号文章",
    fallbackSourceDescription: "{count} 个 RSS / Atom 信息源",
    needsApiKey: "需要 API Key",
    sourceUnavailable: "上游接口已失效，暂不可用",
    unavailable: "不可用",
    channelConfigError: "频道配置读取失败",
    wechatDefaultKey: "已有默认 Key，可选填覆盖",
    wechatPreset: "读取预设公众号文章",
    wechatServerNote: "服务端已配置默认 Key；留空即可使用，也可填入你自己的 Key 仅覆盖本次请求。",
    wechatRequestNote: '选择微信公众号频道时使用。可前往 <a href="https://down.mptext.top/dashboard/api" target="_blank" rel="noreferrer">mptext API 控制台 ↗</a> 获取。',
    aiCompatibleNote: "已适配 {provider} 的 Chat Completions 接口；仍可修改模型名称。",
    aiCustomNote: "自定义地址需在启动时加入 REPO_COURIER_ALLOWED_AI_BASE_URLS；页面会自动补全 /chat/completions。",
    highlights: "值得关注",
    useCases: "适合用在",
    adoptionRisk: "采用前留意",
    deepAnalysis: "深度分析",
    contentSummary: "内容摘要",
    authors: "作者",
    starsToday: "今日新增",
    license: "许可证",
    aiPick: "AI 精选",
    rulePick: "规则精选",
    wechatBadge: "公众号",
    scan: "扫描 {count} 条",
    sourceErrors: "{count} 个源异常",
    waiting: "等待中",
    streamUnsupported: "当前浏览器不支持流式结果读取。",
    noSource: "请至少选择一个情报频道。",
    noInterest: "请至少填写一个关注词。",
    wechatNeedsKey: "微信公众号频道需要 API Key，请在可选增强中填写。",
    genericFailure: "暂时无法生成情报。",
    requestKeyFetching: "页面 Key · 抓取中",
    fetching: "抓取中",
    itemCount: "{count} 条",
    processing: "正在处理 {done} / {total} 个频道",
    scanProgress: "已完成 {done} / {total} · 扫描 {count} 条候选",
    requestKeyUsed: "已使用页面填写的 Key；",
    channelUnavailable: "该频道暂时不可用",
    networkBlocked: "网络已拦截",
    accessDenied: "403 · 访问被拒",
    fetchFailed: "抓取失败",
    completeWithFailure: "已完成，{count} 个频道暂不可用",
    briefingReady: "今日情报已生成",
    scanComplete: "已扫描 {count} 条候选 · {analysis}{failures}",
    aiAnalysis: "AI 增强分析",
    localAnalysis: "本地规则分析",
    failedChannels: " · {count} 个频道异常",
    streamEnded: "流式连接提前结束，请重试。",
    allSourcesFailed: "所选频道暂时无法抓取",
    someSourcesFailed: "部分频道抓取失败",
  },
  en: {
    pageTitle: "RepoCourier · Your Daily Tech Intelligence",
    metaDescription: "RepoCourier finds the most relevant signals from GitHub, WeChat, engineering blogs, papers, tech news, product releases, and security feeds.",
    brandAria: "RepoCourier home",
    toggleLabel: "切换到中文",
    heroEyebrow: "PERSONAL TECH BRIEFING",
    heroTitleLead: "Seven tech channels. Only",
    heroTitleAccent: "today's essential reads",
    heroCopy: "Choose channels and interests. RepoCourier collects, filters, and turns them into your personal daily tech briefing.",
    deskTitle: "Customize today's briefing",
    noKeyDefault: "No keys required by default",
    channelsLegend: "Content channels",
    multiSelect: "Select multiple",
    loadingChannels: "Loading channels…",
    interestsLegend: "Your interests",
    commaSeparated: "Comma separated",
    interestsLabel: "Interests",
    githubLanguageLabel: "GitHub language filter",
    allLanguages: "All languages",
    credentialsLegend: "Access credentials",
    credentialsHint: "Only for selected channels",
    githubTokenHint: "Raise limits and enrich metadata",
    add: "Add",
    optional: "Optional",
    show: "Show",
    hide: "Hide",
    githubTokenNote: "Public repositories only need read-only Metadata and Contents access.",
    wechatApi: "WeChat Official Accounts API",
    wechatMark: "WX",
    wechatKeyPlaceholder: "WeChat content API key",
    compatibleAi: "OpenAI-compatible AI",
    compatibleAiHint: "Use any Chat Completions-compatible model",
    modelProvider: "Model provider",
    customProvider: "Custom compatible service",
    zhipuProvider: "Zhipu AI GLM",
    stepfunProvider: "StepFun",
    apiBaseUrl: "API base URL or Chat Completions endpoint",
    modelName: "Model name",
    privacyNote: "Keys stay in this page, are never saved by the server, and are cleared on refresh",
    selectedPrefix: "Selected",
    selectedSuffix: "channels · 3 picks per channel",
    generate: "Generate my daily briefing",
    preparing: "Preparing your briefing…",
    streamHint: "Each channel appears as soon as it is ready",
    progressAria: "Channel processing progress",
    signalsEyebrow: "YOUR DAILY SIGNALS",
    resultsTitle: "Worth reading today",
    emptyTitle: "Not enough relevant signals today",
    emptyDescription: "Try broader interests or select more channels.",
    footerCopy: "There is always more information. Only a few signals matter today.",
    sourceGithub: "GitHub Trending",
    sourceNews: "Tech News",
    sourceBlogs: "Engineering Blogs",
    sourceAcademic: "Research Papers",
    sourceProducts: "Product Releases",
    sourceSecurity: "Security",
    sourceWechat: "WeChat",
    sourceGithubDescription: "Trending repositories, Topics, READMEs, and Star growth",
    sourceNewsDescription: "MIT Tech Review, The Verge, WIRED, and more",
    sourceBlogsDescription: "OpenAI, Google DeepMind, Hugging Face, and more",
    sourceAcademicDescription: "arXiv papers in AI, NLP, CV, and machine learning",
    sourceProductsDescription: "Release notes from Codex, Claude Code, Gemini CLI, and more",
    sourceSecurityDescription: "Krebs, The Hacker News, Google Security, and more",
    sourceWechatDescription: "Selected Chinese AI and technology publications",
    fallbackSourceDescription: "{count} RSS / Atom feeds",
    needsApiKey: "API key required",
    sourceUnavailable: "Upstream API is no longer available",
    unavailable: "Unavailable",
    channelConfigError: "Could not load channel configuration",
    wechatDefaultKey: "Default key available; optionally override it",
    wechatPreset: "Read selected WeChat publications",
    wechatServerNote: "A default server key is configured. Leave this blank to use it, or override it for this request.",
    wechatRequestNote: 'Required for the WeChat channel. Get one from the <a href="https://down.mptext.top/dashboard/api" target="_blank" rel="noreferrer">mptext API console ↗</a>.',
    aiCompatibleNote: "{provider} Chat Completions is supported; you can still change the model name.",
    aiCustomNote: "Add custom URLs to REPO_COURIER_ALLOWED_AI_BASE_URLS at startup; /chat/completions is appended automatically.",
    highlights: "Highlights",
    useCases: "Good for",
    adoptionRisk: "Before adopting",
    deepAnalysis: "Deep analysis",
    contentSummary: "Content summary",
    authors: "Authors",
    starsToday: "Today",
    license: "License",
    aiPick: "AI PICK",
    rulePick: "RULE PICK",
    wechatBadge: "WeChat",
    scan: "Scanned {count}",
    sourceErrors: "{count} source errors",
    waiting: "Waiting",
    streamUnsupported: "This browser does not support streaming results.",
    noSource: "Select at least one intelligence channel.",
    noInterest: "Enter at least one interest.",
    wechatNeedsKey: "The WeChat channel requires an API key. Add it under access credentials.",
    genericFailure: "Could not generate the briefing.",
    requestKeyFetching: "Page key · Fetching",
    fetching: "Fetching",
    itemCount: "{count} items",
    processing: "Processing {done} / {total} channels",
    scanProgress: "Completed {done} / {total} · Scanned {count} candidates",
    requestKeyUsed: "The key entered on this page was used; ",
    channelUnavailable: "This channel is temporarily unavailable",
    networkBlocked: "Network blocked",
    accessDenied: "403 · Access denied",
    fetchFailed: "Fetch failed",
    completeWithFailure: "Complete; {count} channels unavailable",
    briefingReady: "Today's briefing is ready",
    scanComplete: "Scanned {count} candidates · {analysis}{failures}",
    aiAnalysis: "AI-enhanced analysis",
    localAnalysis: "Local rule-based analysis",
    failedChannels: " · {count} channel errors",
    streamEnded: "The stream ended early. Please try again.",
    allSourcesFailed: "The selected channels could not be fetched",
    someSourcesFailed: "Some channels failed",
  },
};

function t(key, values = {}) {
  const template = I18N[currentLanguage][key] ?? I18N.zh[key] ?? key;
  return Object.entries(values).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
    template,
  );
}

function localizedBackendMessage(message) {
  if (currentLanguage === "zh") return message;
  const text = String(message || "");
  if (text.includes("处理超时")) return "This channel timed out";
  if (text.includes("网络") && (text.includes("拦截") || text.includes("放行"))) {
    return "The network blocked this channel's upstream service";
  }
  if (text.includes("拒绝访问") || text.includes("401") || text.includes("403")) {
    return "The upstream service denied access";
  }
  if (text.includes("API Key")) return "This channel requires a valid API key";
  if (text.includes("未被当前站点允许")) return "This model service URL is not allowed by this site";
  if (text.includes("未知内容频道")) return "Unknown content channel";
  if (text.includes("暂时不可用") || text.includes("上游来源")) return t("channelUnavailable");
  return text || t("channelUnavailable");
}

const SOURCE_PRESENTATION = {
  github: { icon: "GH", titleKey: "sourceGithub", descriptionKey: "sourceGithubDescription" },
  news: { icon: "N", titleKey: "sourceNews", descriptionKey: "sourceNewsDescription" },
  blogs: { icon: "B", titleKey: "sourceBlogs", descriptionKey: "sourceBlogsDescription" },
  academic: { icon: "aχ", titleKey: "sourceAcademic", descriptionKey: "sourceAcademicDescription" },
  products: { icon: "P", titleKey: "sourceProducts", descriptionKey: "sourceProductsDescription" },
  security: { icon: "S", titleKey: "sourceSecurity", descriptionKey: "sourceSecurityDescription" },
  wechat: { icon: "微", titleKey: "sourceWechat", descriptionKey: "sourceWechatDescription" },
};

// 上游抓取接口已失效，界面上置灰而非移除，便于后续恢复。
const DISABLED_SOURCES = new Set(["wechat"]);

const AI_PROVIDERS = {
  openai: { label: "OpenAI", baseUrl: "https://api.openai.com/v1", model: "" },
  claude: { label: "Claude", baseUrl: "https://api.anthropic.com/v1", model: "claude-sonnet-4-6" },
  zhipu: { label: "Zhipu AI GLM", baseUrl: "https://open.bigmodel.cn/api/paas/v4", model: "glm-5.2" },
  kimi: { label: "Kimi", baseUrl: "https://api.moonshot.cn/v1", model: "kimi-k2.6" },
  minimax: { label: "MiniMax", baseUrl: "https://api.minimaxi.com/v1", model: "MiniMax-M2.7" },
  stepfun: { label: "StepFun", baseUrl: "https://api.stepfun.com/v1", model: "step-3.5-flash" },
  dmxapi: { label: "DMXAPI", baseUrl: "https://www.dmxapi.cn/v1", model: "gpt-5.6-sol" },
};

const FALLBACK_SOURCES = [
  { id: "wechat", title: "微信公众号", source_count: 6, default: false, requires_key: true },
  { id: "github", title: "GitHub Trending", source_count: 1, default: true },
  { id: "news", title: "科技新闻", source_count: 4, default: false },
  { id: "blogs", title: "大厂博客", source_count: 4, default: false },
  { id: "academic", title: "学术论文", source_count: 1, default: false },
  { id: "products", title: "产品更新", source_count: 4, default: false },
  { id: "security", title: "安全资讯", source_count: 4, default: false },
];

const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const number = (value) =>
  new Intl.NumberFormat(currentLanguage === "en" ? "en-US" : "zh-CN").format(Number(value || 0));

function localizedSourceTitle(source) {
  const presentation = SOURCE_PRESENTATION[source.id];
  return presentation?.titleKey ? t(presentation.titleKey) : source.title;
}

function parseInterests(value) {
  return [...new Set(value.split(/[,\n，]/).map((item) => item.trim()).filter(Boolean))];
}

function selectedSources() {
  return [...document.querySelectorAll('input[name="sources"]:checked')].map(
    (input) => input.value,
  );
}

function comparableAiBaseUrl(value) {
  return value.trim().replace(/\/+$/, "").replace(/\/chat\/completions$/, "");
}

function updateAiProviderNote() {
  const provider = AI_PROVIDERS[aiProviderSelect.value];
  aiCompatibilityNote.textContent = provider
    ? t("aiCompatibleNote", { provider: provider.label })
    : t("aiCustomNote");
}

aiProviderSelect.addEventListener("change", () => {
  const provider = AI_PROVIDERS[aiProviderSelect.value];
  if (provider) {
    aiBaseUrlInput.value = provider.baseUrl;
    aiModelInput.value = provider.model;
  } else {
    aiBaseUrlInput.focus();
  }
  updateAiProviderNote();
});

aiBaseUrlInput.addEventListener("input", () => {
  const current = comparableAiBaseUrl(aiBaseUrlInput.value);
  const matched = Object.entries(AI_PROVIDERS).find(
    ([, provider]) => comparableAiBaseUrl(provider.baseUrl) === current,
  );
  aiProviderSelect.value = matched?.[0] || "custom";
  updateAiProviderNote();
});

function updateSourceCount() {
  selectedSourceCount.textContent = String(selectedSources().length);
}

function sourceCard(source, checkedSources) {
  const presentation = SOURCE_PRESENTATION[source.id] || {};
  const title = localizedSourceTitle(source);
  const description = presentation.descriptionKey
    ? t(presentation.descriptionKey)
    : t("fallbackSourceDescription", { count: source.source_count || 0 });
  const disabled = DISABLED_SOURCES.has(source.id);
  const hint = disabled ? `${description}（${t("sourceUnavailable")}）` : description;
  const sourceLabel = `${title}，${hint}`;
  const keyHint = source.requires_key
    ? `<small class="source-key-hint" title="${escapeHtml(t("needsApiKey"))}">KEY</small>`
    : "";
  const checked = disabled
    ? false
    : checkedSources
      ? checkedSources.has(source.id)
      : source.default;
  return `
    <label class="source-option${disabled ? " is-disabled" : ""}" title="${escapeHtml(hint)}">
      <input type="checkbox" name="sources" value="${escapeHtml(source.id)}" aria-label="${escapeHtml(sourceLabel)}" ${checked ? "checked" : ""} ${disabled ? "disabled" : ""} />
      <span class="source-checkbox" aria-hidden="true">✓</span>
      <span class="source-title">${escapeHtml(title)}</span>${keyHint}
    </label>`;
}

function renderSources(sources, checkedSources = null) {
  sourceCatalog.clear();
  sources.forEach((source) => sourceCatalog.set(source.id, source));
  const wechatSource = sources.find((source) => source.id === "wechat");
  const hasServerWechatKey = Boolean(wechatSource && !wechatSource.requires_key);
  const wechatDisabled = DISABLED_SOURCES.has("wechat");
  wechatKeyPanel.hidden = !wechatSource;
  wechatKeyPanel.open = false;
  wechatKeyPanel.classList.toggle("is-disabled", wechatDisabled);
  wechatKeyPanel.querySelector("summary").tabIndex = wechatDisabled ? -1 : 0;
  wechatKeyInput.disabled = wechatDisabled;
  wechatKeyPanel.querySelector(".reveal-key").disabled = wechatDisabled;
  keyList.classList.toggle("without-wechat", !wechatSource);
  if (wechatDisabled) {
    wechatKeySummary.textContent = t("sourceUnavailable");
    wechatKeyAction.querySelector("[data-key-action-label]").textContent = t("unavailable");
    wechatKeyNote.textContent = t("sourceUnavailable");
  } else {
    wechatKeySummary.textContent = hasServerWechatKey
      ? t("wechatDefaultKey")
      : t("wechatPreset");
    wechatKeyAction.querySelector("[data-key-action-label]").textContent = hasServerWechatKey
      ? t("optional")
      : t("add");
    wechatKeyNote.innerHTML = hasServerWechatKey
      ? t("wechatServerNote")
      : t("wechatRequestNote");
  }
  sourceGrid.innerHTML = sources.map((source) => sourceCard(source, checkedSources)).join("");
  sourceGrid.querySelectorAll('input[name="sources"]').forEach((input) => {
    input.addEventListener("change", updateSourceCount);
  });
  updateSourceCount();
}

async function loadSources() {
  try {
    const response = await fetch("/api/options", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(t("channelConfigError"));
    const data = await response.json();
    renderSources(data.sources?.length ? data.sources : FALLBACK_SOURCES);
  } catch (_error) {
    renderSources(FALLBACK_SOURCES);
  }
}

function shortDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(currentLanguage === "en" ? "en-US" : "zh-CN", {
    month: "short",
    day: "numeric",
  }).format(date);
}

function insightList(title, items) {
  const content = (items || [])
    .filter(Boolean)
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  if (!content) return "";
  return `<div class="ai-insight"><strong>${title}</strong><ul>${content}</ul></div>`;
}

function repoAiDetails(repository) {
  if (repository.analysis_status !== "ai") return "";
  const summary = repository.summary
    ? `<p class="ai-summary">${escapeHtml(repository.summary)}</p>`
    : "";
  const highlights = insightList(t("highlights"), repository.highlights);
  const useCases = insightList(t("useCases"), repository.use_cases);
  const risk = repository.risk_note
    ? `<p class="ai-risk"><strong>${escapeHtml(t("adoptionRisk"))}</strong>${escapeHtml(repository.risk_note)}</p>`
    : "";
  return `
    <details class="ai-details">
      <summary><span><i>AI</i> ${escapeHtml(t("deepAnalysis"))}</span><b aria-hidden="true"></b></summary>
      <div class="ai-details-body">
        ${summary}
        ${highlights || useCases ? `<div class="ai-insight-grid">${highlights}${useCases}</div>` : ""}
        ${risk}
      </div>
    </details>`;
}

function repoCard(repository) {
  const tags = (repository.matched_interests || [])
    .map((item) => `<span>${escapeHtml(item)}</span>`)
    .join("");
  const language = String(repository.language || "").trim();
  const license = String(repository.license || "").trim();
  const metrics = [
    Number(repository.stars) > 0 ? `<span><b>★ ${number(repository.stars)}</b> Stars</span>` : "",
    Number(repository.stars_today) > 0 ? `<span><b>+${number(repository.stars_today)}</b> ${escapeHtml(t("starsToday"))}</span>` : "",
    language && language.toLowerCase() !== "unknown" ? `<span><b>${escapeHtml(language)}</b></span>` : "",
    license && !["unknown", "noassertion", "other"].includes(license.toLowerCase())
      ? `<span><b>${escapeHtml(license)}</b> ${escapeHtml(t("license"))}</span>`
      : "",
  ].filter(Boolean).join("");
  return `
    <article class="signal-card repo-card">
      <div class="signal-content">
        <div class="signal-topline"><span class="pick-index">${String(repository.rank || 0).padStart(2, "0")}</span><span class="recommendation">${escapeHtml(repository.recommendation)}</span><span class="source-rank">Trending #${escapeHtml(repository.trending_rank)}</span></div>
        <h4><a href="${escapeHtml(repository.url)}" target="_blank" rel="noreferrer">${escapeHtml(repository.full_name)} <span>↗</span></a></h4>
        <p class="why">${escapeHtml(repository.why_for_you)}</p>
        <p class="summary">${escapeHtml(repository.description || repository.summary)}</p>
        ${metrics ? `<div class="metric-row">${metrics}</div>` : ""}
        ${tags ? `<div class="tag-list">${tags}</div>` : ""}
        ${repoAiDetails(repository)}
      </div>
    </article>`;
}

function rssAiDetails(item) {
  if (item.analysis_status !== "ai") return "";
  const authors = (item.authors || [])
    .filter(Boolean)
    .map(escapeHtml)
    .join(currentLanguage === "en" ? ", " : "、");
  return `
    <details class="ai-details">
      <summary><span><i>AI</i> ${escapeHtml(t("contentSummary"))}</span><b aria-hidden="true"></b></summary>
      <div class="ai-details-body">
        <p class="ai-summary">${escapeHtml(item.summary)}</p>
        ${authors ? `<p class="ai-authors"><strong>${escapeHtml(t("authors"))}</strong>${authors}</p>` : ""}
      </div>
    </details>`;
}

function productName(sourceName) {
  return String(sourceName || "").replace(/\s+Releases?$/i, "").trim() || sourceName;
}

function rssCard(item, channelId) {
  const tags = (item.matched_keywords || [])
    .map((keyword) => `<span>${escapeHtml(keyword)}</span>`)
    .join("");
  const status = item.analysis_status === "ai" ? t("aiPick") : t("rulePick");
  const inlineSummary = item.analysis_status === "ai" ? "" : `<p class="summary">${escapeHtml(item.summary)}</p>`;
  const date = shortDate(item.published_at);
  const isWechat = channelId === "wechat";
  const isProduct = channelId === "products";
  const displayTitle = isProduct ? item.product_name || productName(item.source_name) : item.title;
  let sourceMeta = `<span class="source-rank">${escapeHtml(item.source_name)}${date ? ` · ${escapeHtml(date)}` : ""}</span>`;
  if (isWechat) {
    sourceMeta = `<span class="wechat-source"><i>${escapeHtml(t("wechatBadge"))}</i><strong>${escapeHtml(item.source_name)}</strong>${date ? `<small>${escapeHtml(date)}</small>` : ""}</span>`;
  } else if (isProduct) {
    sourceMeta = `<span class="source-rank product-version"><strong>${escapeHtml(item.version || item.title)}</strong>${date ? ` · ${escapeHtml(date)}` : ""}</span>`;
  }
  return `
    <article class="signal-card rss-card${isWechat ? " wechat-card" : ""}">
      <div class="signal-content">
        <div class="signal-topline"><span class="pick-index paper-index">${String(item.rank || 0).padStart(2, "0")}</span><span class="recommendation paper-status">${status}</span>${sourceMeta}</div>
        <h4><a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(displayTitle)} <span>↗</span></a></h4>
        <p class="why">${escapeHtml(item.recommendation_reason)}</p>
        ${inlineSummary}
        ${tags ? `<div class="tag-list">${tags}</div>` : ""}
        ${rssAiDetails(item)}
      </div>
    </article>`;
}

function channelSection(channel) {
  if (!channel.items?.length) return "";
  const presentation = SOURCE_PRESENTATION[channel.id] || { icon: "RSS" };
  const icon = channel.id === "wechat" && currentLanguage === "en" ? "WX" : presentation.icon;
  const channelTitle = localizedSourceTitle(channel);
  const scanText = t("scan", { count: number(channel.scanned_count) });
  const errorText = channel.errors_count
    ? ` · ${t("sourceErrors", { count: number(channel.errors_count) })}`
    : "";
  return `
    <div class="result-channel${channel.id === "wechat" ? " wechat-channel" : ""}">
      <div class="channel-title"><span class="channel-icon">${escapeHtml(icon)}</span><h3>${escapeHtml(channelTitle)}</h3><span class="channel-scan">${escapeHtml(scanText + errorText)}</span><i></i></div>
      <div class="result-list">${channel.items.map((item) => rssCard(item, channel.id)).join("")}</div>
    </div>`;
}

function prioritizeSources(sources) {
  const priority = { wechat: 0, github: 1 };
  return sources
    .map((source, index) => ({ source, index }))
    .sort((left, right) =>
      (priority[left.source.id] ?? 2) - (priority[right.source.id] ?? 2) || left.index - right.index,
    )
    .map(({ source }) => source);
}

function resetProgress(sources) {
  const orderedSources = prioritizeSources(sources);
  progressTitle.textContent = t("processing", { done: 0, total: orderedSources.length });
  progressSummary.textContent = `0 / ${orderedSources.length}`;
  channelProgress.innerHTML = orderedSources
    .map((source) => {
      const catalogSource = sourceCatalog.get(source.id);
      const title = localizedSourceTitle(catalogSource || source);
      return `<span id="progress-${escapeHtml(source.id)}" class="progress-chip"><i></i><b>${escapeHtml(title)}</b><small class="progress-status">${escapeHtml(t("waiting"))}</small></span>`;
    })
    .join("");
  channelResults.innerHTML = orderedSources
    .map((source) => `<div id="channel-slot-${escapeHtml(source.id)}"></div>`)
    .join("");
  const githubSlot = document.getElementById("channel-slot-github");
  if (githubSlot) githubSlot.append(githubResults);
}

function updateProgress(source, state, label) {
  const chip = document.getElementById(`progress-${source}`);
  if (!chip) return;
  chip.className = `progress-chip is-${state}`;
  chip.title = state === "error" ? label : "";
  const status = chip.querySelector(".progress-status");
  if (status) status.textContent = label;
}

function renderChannelResult(source, data) {
  let itemCount = 0;
  if (source === "github" && data.repositories?.length) {
    renderedRepositories = data.repositories;
    resultList.innerHTML = data.repositories.map(repoCard).join("");
    githubResults.hidden = false;
    itemCount += data.repositories.length;
  }
  (data.channels || []).forEach((channel) => {
    renderedChannels.set(channel.id, channel);
    const slot = document.getElementById(`channel-slot-${channel.id}`);
    if (slot) slot.innerHTML = channelSection(channel);
    itemCount += channel.items?.length || 0;
  });
  return itemCount;
}

async function readNdjson(response, onEvent) {
  if (!response.body) throw new Error(t("streamUnsupported"));
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (line.trim()) onEvent(JSON.parse(line));
    }
    if (done) break;
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer));
}

document.querySelectorAll(".reveal-key").forEach((button) => {
  button.addEventListener("click", () => {
    const input = document.getElementById(button.dataset.target);
    const showing = input.type === "text";
    input.type = showing ? "password" : "text";
    button.textContent = showing ? t("show") : t("hide");
  });
});

function applyLanguage(language, { persist = true } = {}) {
  const checkedSources = new Set(selectedSources());
  currentLanguage = language === "en" ? "en" : "zh";
  document.documentElement.lang = currentLanguage === "en" ? "en" : "zh-CN";
  document.title = t("pageTitle");
  document.querySelector('meta[name="description"]').content = t("metaDescription");

  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    element.placeholder = t(element.dataset.i18nPlaceholder);
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
    element.setAttribute("aria-label", t(element.dataset.i18nAriaLabel));
  });

  languageToggle.querySelector("span").textContent = currentLanguage === "zh" ? "文" : "A";
  languageToggle.querySelector("strong").textContent = currentLanguage === "zh" ? "EN" : "中文";
  languageToggle.setAttribute("aria-label", t("toggleLabel"));
  languageToggle.title = t("toggleLabel");

  document.querySelectorAll(".reveal-key").forEach((button) => {
    const input = document.getElementById(button.dataset.target);
    button.textContent = input.type === "text" ? t("hide") : t("show");
  });
  updateAiProviderNote();

  const sources = [...sourceCatalog.values()];
  if (sources.length) renderSources(sources, checkedSources);
  if (renderedRepositories.length) {
    resultList.innerHTML = renderedRepositories.map(repoCard).join("");
  }
  renderedChannels.forEach((channel) => {
    const slot = document.getElementById(`channel-slot-${channel.id}`);
    if (slot) slot.innerHTML = channelSection(channel);
  });

  if (persist) localStorage.setItem("repo-courier-language", currentLanguage);
}

languageToggle.addEventListener("click", () => {
  applyLanguage(currentLanguage === "zh" ? "en" : "zh");
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.hidden = true;
  results.hidden = true;
  githubResults.hidden = true;
  emptyResult.hidden = true;
  emptyResultTitle.textContent = t("emptyTitle");
  emptyResultDescription.textContent = t("emptyDescription");
  resultList.innerHTML = "";
  channelResults.innerHTML = "";
  renderedRepositories = [];
  renderedChannels.clear();

  const sources = selectedSources();
  const interests = parseInterests(document.querySelector("#interests").value);
  if (!sources.length) {
    formError.textContent = t("noSource");
    formError.hidden = false;
    return;
  }
  if (!interests.length) {
    formError.textContent = t("noInterest");
    formError.hidden = false;
    return;
  }
  const wechatNeedsKey = sources.includes("wechat") && sourceCatalog.get("wechat")?.requires_key;
  if (wechatNeedsKey && !wechatKeyInput.value.trim()) {
    document.querySelector("#wechat-key-panel").open = true;
    formError.textContent = t("wechatNeedsKey");
    formError.hidden = false;
    wechatKeyInput.focus();
    return;
  }

  const payload = {
    interests,
    sources,
    language: document.querySelector("#language").value,
    github_token: document.querySelector("#github-token").value.trim() || null,
    wechat_auth_key: wechatKeyInput.value.trim() || null,
    ai_base_url: aiBaseUrlInput.value.trim(),
    ai_model: aiModelInput.value.trim(),
    ai_api_key: document.querySelector("#ai-api-key").value.trim() || null,
    ui_language: currentLanguage,
  };

  submitButton.disabled = true;
  languageToggle.disabled = true;
  loading.hidden = false;
  resetProgress(
    sources.map((source) => ({ id: source, title: sourceCatalog.get(source)?.title || source })),
  );
  loading.scrollIntoView({ behavior: "smooth", block: "center" });

  try {
    const response = await fetch("/api/preview/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const data = await response.json();
      const detail = Array.isArray(data.detail)
        ? data.detail.map((item) => localizedBackendMessage(item.msg)).join(currentLanguage === "en" ? "; " : "；")
        : data.detail;
      throw new Error(localizedBackendMessage(detail) || t("genericFailure"));
    }

    let processed = 0;
    let failed = 0;
    let total = sources.length;
    let totalScanned = 0;
    let usedAi = false;
    let hasItems = false;
    let revealedResults = false;
    let streamCompleted = false;
    const failureMessages = [];

    await readNdjson(response, (streamEvent) => {
      if (streamEvent.type === "start") {
        total = Number(streamEvent.total || total);
        resetProgress(streamEvent.sources || []);
        return;
      }
      if (streamEvent.type === "channel_started") {
        const status = streamEvent.source === "wechat" && streamEvent.credential_source === "request"
          ? t("requestKeyFetching")
          : t("fetching");
        updateProgress(streamEvent.source, "running", status);
        return;
      }
      if (streamEvent.type === "channel_complete") {
        processed += 1;
        const data = streamEvent.result || {};
        const itemCount = renderChannelResult(streamEvent.source, data);
        hasItems = hasItems || itemCount > 0;
        totalScanned += Number(data.scanned_count || 0) + Number(data.rss_scanned_count || 0);
        usedAi = usedAi || Boolean(data.used_ai);
        updateProgress(streamEvent.source, "done", t("itemCount", { count: itemCount }));
        progressTitle.textContent = t("processing", { done: processed, total });
        progressSummary.textContent = `${processed} / ${total}`;
        scanSummary.textContent = t("scanProgress", {
          done: processed,
          total,
          count: number(totalScanned),
        });
        if (itemCount > 0) {
          results.hidden = false;
          if (!revealedResults) {
            revealedResults = true;
            results.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        }
        return;
      }
      if (streamEvent.type === "channel_error") {
        processed += 1;
        failed += 1;
        const credentialNote = streamEvent.source === "wechat" && streamEvent.credential_source === "request"
          ? t("requestKeyUsed")
          : "";
        const rawFailureMessage = streamEvent.message || "";
        const failureMessage = localizedBackendMessage(rawFailureMessage);
        failureMessages.push(`${credentialNote}${failureMessage}`);
        const failureLabel = rawFailureMessage.includes("网络拦截")
          ? t("networkBlocked")
          : rawFailureMessage.includes("拒绝访问")
            ? t("accessDenied")
            : t("fetchFailed");
        updateProgress(streamEvent.source, "error", failureLabel);
        progressTitle.textContent = t("processing", { done: processed, total });
        progressSummary.textContent = `${processed} / ${total}`;
        return;
      }
      if (streamEvent.type === "complete") {
        streamCompleted = true;
        failed = Number(streamEvent.failed || failed);
        progressTitle.textContent = failed
          ? t("completeWithFailure", { count: failed })
          : t("briefingReady");
        scanSummary.textContent = t("scanComplete", {
          count: number(totalScanned),
          analysis: usedAi ? t("aiAnalysis") : t("localAnalysis"),
          failures: failed ? t("failedChannels", { count: failed }) : "",
        });
      }
    });

    if (!streamCompleted) throw new Error(t("streamEnded"));
    if (!hasItems) {
      if (failed) {
        emptyResultTitle.textContent = failed === total ? t("allSourcesFailed") : t("someSourcesFailed");
        emptyResultDescription.textContent = [...new Set(failureMessages)].join(currentLanguage === "en" ? "; " : "；");
      }
      emptyResult.hidden = false;
      results.hidden = false;
    }
    document.querySelector("#github-token").value = "";
    document.querySelector("#ai-api-key").value = "";
  } catch (error) {
    formError.textContent = error.message || t("genericFailure");
    formError.hidden = false;
    form.scrollIntoView({ behavior: "smooth", block: "start" });
  } finally {
    loading.hidden = true;
    submitButton.disabled = false;
    languageToggle.disabled = false;
  }
});

applyLanguage(currentLanguage, { persist: false });
loadSources();
