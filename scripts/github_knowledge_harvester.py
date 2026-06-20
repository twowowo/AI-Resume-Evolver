"""
v1.1 GitHub 技术情报自动采集管道 — 双模 Prompt + URL 校验

工作流:
  1. URL 清洗 + 校验（检测粘连/非法格式）
  2. 遍历 TARGET_URLS，抓取 GitHub raw Markdown
  3. DeepSeek Flash 双模脱水:
     Mode A (个人案例): 提取个人项目经历中的 STAR 案例
     Mode B (知识合成): 将架构/设计方案转化为工程实践心得
  4. 标题去重后追加写入 data/reference/github_harvested_cases.txt
  5. 配合 scripts/ingest_data.py → ChromaDB + BM25 索引重建

用法:
  python scripts/github_knowledge_harvester.py

Docker / Cron 自动化:
  docker compose exec backend python scripts/github_knowledge_harvester.py
  docker compose exec backend python scripts/ingest_data.py
"""
import os
import re
import sys
import time
import hashlib
import logging
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

from src.utils.llm import get_flash_client

# ═══════════════════════════════════════════════════════════════
# 配置区
# ═══════════════════════════════════════════════════════════════

TARGET_URLS: list[str] = [
    # ── 系统设计: 指向具体解决方案页面（README 是 ToC，无实质内容）──
    "https://raw.githubusercontent.com/donnemartin/system-design-primer/master/solutions/system_design/scaling_aws/README.md",
    "https://raw.githubusercontent.com/donnemartin/system-design-primer/master/solutions/system_design/pastebin/README.md",
    "https://raw.githubusercontent.com/donnemartin/system-design-primer/master/solutions/system_design/twitter/README.md",

    # ── AI Agent / LLM 工程 ──
    # "https://raw.githubusercontent.com/langchain-ai/langgraph/main/README.md",
]

OUTPUT_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "reference", "github_harvested_cases.txt"
)
OUTPUT_FILE = os.path.abspath(OUTPUT_FILE)

LOG_FILE = os.path.join(
    os.path.dirname(__file__), "..", "harvest_result.txt"
)
LOG_FILE = os.path.abspath(LOG_FILE)

# 单次抓取最大字符数（防止巨型 README 塞爆 LLM 上下文）
MAX_FETCH_CHARS = 30_000

# HTTP 请求超时（秒）
FETCH_TIMEOUT = 30

# LLM 调用最大重试
MAX_LLM_RETRIES = 3

# 去重标题的最小匹配长度
DEDUP_TITLE_MIN_LEN = 6

# 知识合成模式：每个 URL 最多产出的案例数上限（防止 LLM 过量生成）
KNOWLEDGE_MAX_CASES_PER_URL = 8

# 内容密度阈值：前 N 字符中 Markdown 链接占比超过此值 → 判定为目录页，跳过
CONTENT_DENSITY_CHECK_CHARS = 5000
CONTENT_DENSITY_LINK_RATIO = 0.35

_LINK_PATTERN_RE = re.compile(r"\[([^\]]*?)\]\([^\)]*?\)")

# ═══════════════════════════════════════════════════════════════
# 日志
# ═══════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger("harvester")


# ═══════════════════════════════════════════════════════════════
# LLM 脱水 Prompt（双模）
# ═══════════════════════════════════════════════════════════════

# ── Mode A: 个人项目经历提取（原版 Prompt）──
DEHYDRATION_PROMPT_CASES = """你是一位资深技术猎头与知识库策展人。请从以下 GitHub Markdown 文档中提取所有有价值的【个人技术案例/项目实战/故障排查/性能优化实录】内容。

【输出格式铁律】
每条案例必须严格按照以下 5 行格式输出，不允许任何变形:

[案例标签] 案例一句话标题
- Situation: 一句话描述项目初始状态、面临的核心问题或业务背景
- Task: 一句话描述需要达成的目标或需要解决的技术挑战
- Action: 一句话描述具体采取的技术手段、使用的框架/工具/方法论
- Result: 一句话描述取得的量化成果（若无确切数字，基于技术场景合理估算并标"（估算）"）

【格式示例】
[缓存架构] 社交平台热点数据多级缓存治理
- Situation: 明星突发事件导致 Redis 热点 Key 单分片过载，触发服务熔断
- Task: 构建高可用缓存体系，防御瞬时百万级流量冲击
- Action: 设计 Caffeine 本地缓存 + Redis 分布式缓存多级架构，引入自研热点发现引擎动态下发
- Result: Redis 压力降低 70%，支撑 50w QPS 突发流量，实现业务零感知

【硬核规则】
1. 每条案例的 [标签] 必须是 2-6 个字符的精准技术分类词（如 [多级缓存]、[JVM调优]、[分布式事务]）
2. 每行 STAR 描述必须是一句完整、可直接入库的技术摘要
3. 如果原文包含具体数字（QPS、延迟、内存、成本等），必须原样保留
4. 如果原文无量化数据，基于技术场景合理估算，在数字后标注"（估算）"
5. 只提取真实的个人项目经历/故障复盘/优化实录。若原文是教程/命令参考/面试题/论文清单/纯概念说明 → 输出 EMPTY
6. 每条案例之间用一个空行分隔
7. 不要输出任何案例之外的寒暄或总结

【GitHub 原文】
{raw_markdown}

现在请输出提取的案例（若无真实个人项目经历则输出 EMPTY）:"""

# ── Mode B: 架构/知识 → 工程实践心得合成 ──
DEHYDRATION_PROMPT_KNOWLEDGE = """你是一位拥有 10 年经验的资深架构师，正在为一本《大厂工程实践内参》撰写案例条目。

你的任务不是简单抄写原文，而是【将下面的技术知识/架构方案/设计模式，转化为实战工程实践心得】。
换句话说：假设一位工程师在真实项目中应用了这些知识，他会在简历上怎么用 STAR 格式来描述这段经历？

【输出格式铁律 — 与 Mode A 完全一致】
[技术标签] 工程实践一句话标题
- Situation: 在什么业务场景下遇到了这个问题
- Task: 需要达成的技术目标
- Action: 具体采用什么技术手段解决（基于原文知识）
- Result: 量化的改进效果（基于技术常识合理估算，标注"（估算）"）

【合成示例】
原文描述: "Cache-aside: The application reads from cache first. On cache miss, it reads from database and writes to cache."
合成为:
[缓存策略] Cache-Aside 模式在电商订单查询中的工程落地
- Situation: 订单查询接口数据库读取压力大，热点订单数据导致慢 SQL 频发
- Task: 引入缓存层减少数据库直接读取，P99 延迟控制在 100ms 以内
- Action: 采用 Cache-Aside 模式，应用层先查 Redis，未命中则查 MySQL 并异步回填缓存，设置 30min TTL + 随机抖动防雪崩
- Result: 数据库读取 QPS 下降 85%（估算），P99 延迟从 600ms 降至 45ms（估算）

【硬核规则】
1. [标签] 必须是 2-6 字的精准技术分类词，从原文的核心主题中提炼
2. 每条案例必须像真实简历一样具体——要有虚构但合理的业务场景、技术选型理由、和量化数字
3. 量化数字必须标注"（估算）"
4. 最多提取 {max_cases} 条案例。宁缺毋滥——如果原文知识点太少，少于 3 条也完全可以
5. 如果原文几乎不包含任何可工程化的技术知识 → 输出 EMPTY
6. 每条案例之间用一个空行分隔，不要输出任何案例之外的寒暄或总结

【待合成的技术知识原文】
{raw_markdown}

现在请输出工程实践心得案例（或 EMPTY）:"""


# ═══════════════════════════════════════════════════════════════
# URL 校验与清洗
# ═══════════════════════════════════════════════════════════════

_URL_CONCAT_RE = re.compile(r"https?://[^\s]+https?://")

def _validate_url(url: str) -> tuple[str | None, str | None]:
    """校验并清洗单条 URL

    Returns:
        (cleaned_url, error_message)
        - cleaned_url: 清洗后合法 URL，或 None 表示不可恢复
        - error_message: 校验失败的原因描述
    """
    url = url.strip()
    if not url:
        return None, "空 URL"

    # 检测粘连: 一个字符串里包含多个 https://
    concat_match = _URL_CONCAT_RE.search(url)
    if concat_match:
        return None, (
            f"URL 粘连 — 检测到两个 http(s) 协议头粘连在一起，"
            f"请检查 TARGET_URLS 列表中是否缺少逗号分隔符"
        )

    # 必须以 http(s) 开头
    if not url.startswith(("https://", "http://")):
        return None, f"不是合法 HTTP(S) URL: {url[:80]}"

    return url, None


def _sanitize_url_list(raw_urls: list[str]) -> list[str]:
    """清洗 URL 列表: 去空、去粘连、去重复"""
    seen: set[str] = set()
    clean: list[str] = []
    rejected = 0

    for url in raw_urls:
        cleaned, error = _validate_url(url)
        if error:
            logger.warning(f"[URL校验] 跳过: {error}")
            rejected += 1
            continue
        if cleaned in seen:
            logger.info(f"[URL校验] 跳过重复: {cleaned[:80]}...")
            continue
        seen.add(cleaned)
        clean.append(cleaned)

    if rejected:
        logger.info(f"[URL校验] 共剔除 {rejected} 条无效 URL，有效 {len(clean)} 条")
    return clean


# ═══════════════════════════════════════════════════════════════
# 内容密度预检
# ═══════════════════════════════════════════════════════════════

def _check_content_density(text: str) -> tuple[bool, float]:
    """检测文本是否为目录/索引页（链接密度过高）

    对纯 ToC/awesome-list 类型的页面，LLM 无法提取任何案例，
    提前跳过可节省 LLM Token 消耗。

    Returns:
        (is_substantive, link_ratio)
        - is_substantive: True = 有实质内容，值得送入 LLM
        - link_ratio: Markdown 链接文本占比
    """
    if len(text) < 1000:
        return True, 0.0  # 太短不检测，交给 LLM 判断

    sample = text[:CONTENT_DENSITY_CHECK_CHARS]
    link_chars = sum(len(m.group(0)) for m in _LINK_PATTERN_RE.finditer(sample))
    ratio = link_chars / len(sample) if sample else 0

    return ratio < CONTENT_DENSITY_LINK_RATIO, ratio


# ═══════════════════════════════════════════════════════════════
# HTTP 抓取
# ═══════════════════════════════════════════════════════════════

def _fetch_raw_markdown(url: str) -> tuple[str | None, str | None]:
    """抓取 GitHub raw Markdown URL，返回 (content, error_message)"""
    req = Request(url, headers={
        "User-Agent": "AI-Resume-Evolver/1.1 (knowledge-harvester)",
        "Accept": "text/plain, text/markdown, */*",
    })

    try:
        with urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            # 额外校验: 响应 Content-Type 必须是文本
            ct = resp.headers.get("Content-Type", "")
            if "html" in ct.lower():
                return None, f"响应为 HTML 而非纯文本 (可能不是 raw URL): {url[:80]}"

            raw = resp.read().decode("utf-8", errors="replace")
            if len(raw) > MAX_FETCH_CHARS:
                logger.info(f"截断: {len(raw)} → {MAX_FETCH_CHARS} 字符")
                raw = raw[:MAX_FETCH_CHARS]
            return raw, None
    except HTTPError as e:
        return None, f"HTTP {e.code} — 请确认该 raw URL 确实存在且可公开访问"
    except URLError as e:
        return None, f"网络错误: {e.reason}"
    except Exception as e:
        return None, f"未知错误: {type(e).__name__}: {e}"


# ═══════════════════════════════════════════════════════════════
# LLM 双模脱水
# ═══════════════════════════════════════════════════════════════

def _invoke_llm_dehydrate(prompt: str, mode_label: str) -> str | None:
    """调用 LLM 脱水，返回文本或 None"""
    for attempt in range(1, MAX_LLM_RETRIES + 1):
        try:
            llm = get_flash_client()
            response = llm.invoke(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            text = text.strip()

            if not text or text.upper().strip() == "EMPTY":
                return None

            # 格式校验: 至少包含一个 [tag]
            if "[" not in text or "]" not in text:
                logger.warning(f"[{mode_label}] LLM 输出缺少 [标签] 格式，重试 {attempt}/{MAX_LLM_RETRIES}")
                if attempt < MAX_LLM_RETRIES:
                    time.sleep(2)
                    continue
                return None

            return text

        except Exception as e:
            logger.error(f"[{mode_label}] LLM 调用失败 (attempt {attempt}): {type(e).__name__}: {e}")
            if attempt < MAX_LLM_RETRIES:
                time.sleep(3)
            else:
                return None
    return None


def _dehydrate_markdown(raw_md: str) -> tuple[str | None, str]:
    """双模脱水: Mode A (个人案例) → Mode B (知识合成)

    Returns:
        (dehydrated_text_or_none, mode_used_label)
    """
    truncated = raw_md[:MAX_FETCH_CHARS]

    # ── Mode A: 尝试提取真实个人案例 ──
    logger.info("  [Mode A] 尝试提取个人项目案例...")
    prompt_a = DEHYDRATION_PROMPT_CASES.format(raw_markdown=truncated)
    result = _invoke_llm_dehydrate(prompt_a, "Mode A")
    if result:
        return result, "Mode A (个人案例提取)"

    # ── Mode B: 架构/知识 → 工程实践心得合成 ──
    logger.info("  [Mode A] 无案例，切换到 [Mode B] 知识合成...")
    prompt_b = DEHYDRATION_PROMPT_KNOWLEDGE.format(
        raw_markdown=truncated,
        max_cases=KNOWLEDGE_MAX_CASES_PER_URL,
    )
    result = _invoke_llm_dehydrate(prompt_b, "Mode B")
    if result:
        return result, "Mode B (知识→工程实践合成)"

    return None, "双模均无产出"


# ═══════════════════════════════════════════════════════════════
# 去重逻辑
# ═══════════════════════════════════════════════════════════════

_TITLE_LINE_RE = re.compile(r"^\s*\[(.+?)\]\s*(.+)$")


def _extract_titles(text: str) -> list[str]:
    """从案例文本中提取所有 [标签] 标题行"""
    titles: list[str] = []
    for line in text.split("\n"):
        m = _TITLE_LINE_RE.match(line.strip())
        if m:
            title = f"[{m.group(1)}] {m.group(2)}".strip()
            if len(title) >= DEDUP_TITLE_MIN_LEN:
                titles.append(title)
    return titles


def _load_existing_titles(file_path: str) -> set[str]:
    """从现有文件中加载所有已入库的标题"""
    if not os.path.exists(file_path):
        return set()

    titles: set[str] = set()
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                m = _TITLE_LINE_RE.match(line)
                if m:
                    title = f"[{m.group(1)}] {m.group(2)}".strip()
                    if len(title) >= DEDUP_TITLE_MIN_LEN:
                        titles.add(title.lower())
    except Exception as e:
        logger.warning(f"读取已有文件失败: {e}")

    return titles


def _dedup_and_filter(new_text: str, existing_titles: set[str]) -> tuple[str, int, int]:
    """去重：仅保留标题不在 existing_titles 中的案例块

    案例块以 [标签] 标题行起始，用空行分隔。

    Returns:
        (filtered_text, total_count, new_count)
    """
    existing = {t.lower() for t in existing_titles}

    blocks = new_text.split("\n\n")
    filtered_blocks: list[str] = []
    total = 0
    new = 0

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        first_line = block.split("\n")[0].strip()
        m = _TITLE_LINE_RE.match(first_line)
        if not m:
            # 不以标题起始的块 → 可能是上一个块的延续，保留
            if filtered_blocks:
                filtered_blocks[-1] = filtered_blocks[-1] + "\n\n" + block
            continue

        total += 1
        title = f"[{m.group(1)}] {m.group(2)}".strip()

        if title.lower() in existing:
            logger.info(f"  [跳过重复] {title}")
            continue

        new += 1
        existing.add(title.lower())
        filtered_blocks.append(block)

    return "\n\n".join(filtered_blocks), total, new


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════

def run():
    start_time = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info(f"GitHub 知识采集管道启动 — {start_time.isoformat()}")
    logger.info(f"目标 URL 数: {len(TARGET_URLS)}")
    logger.info(f"输出文件: {OUTPUT_FILE}")
    logger.info("=" * 60)

    # ── URL 清洗 ──
    clean_urls = _sanitize_url_list(TARGET_URLS)

    if not clean_urls:
        logger.warning("TARGET_URLS 经校验后无有效 URL，请编辑脚本顶部的 TARGET_URLS 列表。")
        logger.info("正确格式: https://raw.githubusercontent.com/owner/repo/main/README.md")
        logger.info("常见错误: 两个 URL 之间缺少逗号 → 粘连成一个字符串")
        return

    logger.info(f"有效 URL 数: {len(clean_urls)} (原始 {len(TARGET_URLS)} 条)")

    # ── 确保输出目录存在 ──
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    # ── 加载已有标题 ──
    existing_titles = _load_existing_titles(OUTPUT_FILE)
    logger.info(f"已有案例标题数: {len(existing_titles)}")

    # ── 逐 URL 采集 ──
    total_new_cases = 0
    total_fetched = 0
    total_failed_fetch = 0
    total_empty = 0
    mode_stats = {"Mode A (个人案例提取)": 0, "Mode B (知识→工程实践合成)": 0}

    for i, url in enumerate(clean_urls, 1):
        logger.info(f"\n[{i}/{len(clean_urls)}] 抓取: {url[:100]}...")

        # Step 1: HTTP 抓取
        raw_content, error = _fetch_raw_markdown(url)
        if error:
            logger.error(f"  抓取失败: {error}")
            total_failed_fetch += 1
            continue

        if not raw_content or not raw_content.strip():
            logger.info(f"  空内容，跳过")
            total_empty += 1
            continue

        total_fetched += 1
        content_hash = hashlib.sha256(raw_content.encode()).hexdigest()[:12]
        logger.info(f"  抓取成功: {len(raw_content)} 字符, sha256={content_hash}")

        # Step 1.5: 内容密度预检
        is_substantive, link_ratio = _check_content_density(raw_content)
        if not is_substantive:
            logger.info(f"  跳过: 内容为目录/索引页 (链接密度 {link_ratio:.0%} > {CONTENT_DENSITY_LINK_RATIO:.0%})")
            logger.info(f"  提示: 请将 URL 指向具体内容页，而非 README/awesome-list 索引")
            total_empty += 1
            continue

        # Step 2: LLM 双模脱水
        dehydrated, mode_used = _dehydrate_markdown(raw_content)
        if dehydrated is None:
            logger.info(f"  无可提取案例 ({mode_used})")
            total_empty += 1
            continue

        logger.info(f"  脱水完成: {len(dehydrated)} 字符 ({mode_used})")
        mode_stats[mode_used] = mode_stats.get(mode_used, 0) + 1

        # Step 3: 去重
        filtered, total_in_block, new_in_block = _dedup_and_filter(dehydrated, existing_titles)
        logger.info(f"  去重: {total_in_block} 条案例 → {new_in_block} 条新增")

        if not filtered.strip():
            continue

        # Step 4: 追加写入
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        header = f"\n\n## Harvested from {url} at {timestamp} [via {mode_used}]\n"
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(header)
            f.write(filtered)
            f.write("\n")

        total_new_cases += new_in_block
        logger.info(f"  已写入 {new_in_block} 条新案例")

    # ── 汇总 ──
    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info("\n" + "=" * 60)
    logger.info("采集完成")
    logger.info(f"  URL 总数:         {len(clean_urls)} (原始输入 {len(TARGET_URLS)} 条)")
    logger.info(f"  抓取成功:         {total_fetched}")
    logger.info(f"  抓取失败:         {total_failed_fetch}")
    logger.info(f"  无可提取内容:     {total_empty}")
    logger.info(f"  新增案例:         {total_new_cases}")
    logger.info(f"  脱水模式分布:     Mode A={mode_stats.get('Mode A (个人案例提取)', 0)}, "
                f"Mode B={mode_stats.get('Mode B (知识→工程实践合成)', 0)}")
    logger.info(f"  累计标题数:       {len(existing_titles)}")
    logger.info(f"  总耗时:           {elapsed:.1f}s")
    logger.info(f"  输出文件:         {OUTPUT_FILE}")
    logger.info("=" * 60)

    if total_new_cases > 0:
        logger.info("\n下一步: 运行 python scripts/ingest_data.py 将新案例灌入 ChromaDB")
    else:
        logger.info("\n无新增案例，无需重建索引。")


if __name__ == "__main__":
    run()
