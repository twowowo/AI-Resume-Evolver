"""
v5.2 文本清洗器 —— LLM 废话防火墙

双重保险的第二层：即使 Prompt 没能 100% 压制 LLM 的客套话惯性，
本模块在所有输出管道中做最终拦截，确保前端收到的文本纯净无污染。

设计原则:
  - 所有函数幂等：多次调用结果一致
  - 不修改正文内容：只删除"包裹层"垃圾
  - 中英文混合覆盖：同时处理中英文常见废话模板
"""

import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 第一道：AI 客套话前缀 / 后缀 模式库
# ═══════════════════════════════════════════════════════════════

# 前缀模式 —— 命中则整段砍掉（从开头到匹配结束）
_PREFIX_PATTERNS: list[Tuple[re.Pattern, str]] = [
    # ── 中文客套话 ──
    (re.compile(r"^(好的[，,]?\s*)?(以下是|以下为|已经)根据您(的|提供)[^。\n]*?(：|:\s*)", re.MULTILINE), "客套前缀"),
    (re.compile(r"^(好的[，,]?\s*)?(已经|已)为您(优化|重写|生成|准备|打造|整理)[^。\n]*?(：|:\s*)", re.MULTILINE), "服务声明"),
    (re.compile(r"^(好的[，,]?\s*)?(这是|此为|如下是|下面是)(优化后|重写后|生成)?[^。\n]{0,30}(简历|内容|版本|终稿|文档)[^。\n]*?(：|:\s*)", re.MULTILINE), "交付声明"),
    (re.compile(r"^(好的[，,]?\s*)?(我将|我会|让我|现在)(来)?(为您|帮你|给)?(优化|重写|分析|评估|生成|输出)[^。\n]*?(：|:\s*)", re.MULTILINE), "动作预告"),
    # ── 英文客套话 ──
    (re.compile(r"^(Okay[,!]?\s*)?Here\s+is\s+(the|your|an?)\s+(optimized|revised|rewritten|polished|updated)\s+(resume|version|content)[^.\n]*?[:\n]", re.IGNORECASE | re.MULTILINE), "英文交付声明"),
    (re.compile(r"^(Sure[,!]?\s*)?(I('ll| will)|Let me)\s+(optimize|rewrite|revise|generate|create|polish)\s+(the|your|this)\s+(resume|content)[^.\n]*?[:\n]", re.IGNORECASE | re.MULTILINE), "英文动作预告"),
    (re.compile(r"^(Certainly[,!]?\s*)?(Below|Following)\s+is\s+(the|your|an?)\s+(optimized|revised|rewritten|polished)\s+(resume|version)[^.\n]*?[:\n]", re.IGNORECASE | re.MULTILINE), "英文Below声明"),
]

# 后缀模式 —— 命中则从匹配位置砍到尾
_SUFFIX_PATTERNS: list[Tuple[re.Pattern, str]] = [
    # ── 中文祝福/结语 ──
    (re.compile(r"(\n\s*)+希望(这份|以上|这).{0,30}(简历|内容|修改|优化).{0,30}(能|可以)[^。\n]*[。\n]", re.MULTILINE), "祝福语"),
    (re.compile(r"(\n\s*)+祝(你|您|面试|求职|工作|拿到|顺利).{0,40}[！!]?\s*$", re.MULTILINE), "祝愿语"),
    (re.compile(r"(\n\s*)+(以上|以上就是|这就是)(优化后|重写后|为您|我)?(的|这份)?[^。\n]{0,30}(简历|内容|修改|优化|版本)[^。\n]*[。]?\s*$", re.MULTILINE), "结语声明"),
    (re.compile(r"(\n\s*)+(如果|若有|如有)(任何|其他|更多|需要|问题).{0,50}[。！!]?\s*$", re.MULTILINE), "兜底服务声明"),
    (re.compile(r"(\n\s*)+期待(您的)?(反馈|回复|确认|指正).{0,20}[。！!]?\s*$", re.MULTILINE), "期待反馈"),
    # ── 英文祝福/结语 ──
    (re.compile(r"(\n\s*)+(I\s+)?(hope|wish)\s+(you|this|the)\s+.{0,60}[.!]?\s*$", re.IGNORECASE | re.MULTILINE), "英文祝福"),
    (re.compile(r"(\n\s*)+(Good\s+)?[Ll]uck\s+(with|on|in)\s+.{0,40}[.!]?\s*$", re.IGNORECASE | re.MULTILINE), "英文Good Luck"),
    (re.compile(r"(\n\s*)+(Please\s+)?(let\s+me\s+know|feel\s+free|reach\s+out).{0,50}[.!]?\s*$", re.IGNORECASE | re.MULTILINE), "英文follow-up"),
    (re.compile(r"(\n\s*)+(Best\s+regards|Sincerely|Cheers|Warmly|Yours).{0,20}[,!]?\s*$", re.IGNORECASE | re.MULTILINE), "英文签名"),
    # ── 元评论/占位符指导语 ──
    (re.compile(r"(\n\s*)+待通过实践积累[^。\n]*[。\n]", re.MULTILINE), "元评论-待积累"),
    (re.compile(r"(\n\s*)+没有对应经历就不填[^。\n]*[。\n]", re.MULTILINE), "元评论-留白指令"),
]

# 单独行匹配的废话行 —— 整行删除
_STANDALONE_TRASH_LINES: list[re.Pattern] = [
    re.compile(r"^\s*(好的|收到|明白了|了解)[，,。！!]?\s*$", re.MULTILINE),
    re.compile(r"^\s*(没问题|马(上|上就)|现在(开始|就)|这就)(给您|为你|来)?[^。\n]{0,10}$", re.MULTILINE),
    # ── v4.6 Ragas 透明化前言污染 ──
    re.compile(r"^>\s*\*\*已基于当前岗位\s*JD\s*需求.*终稿。\s*\*\*\s*$", re.MULTILINE),
]


def strip_ai_pleasantries(text: str) -> Tuple[str, list[str]]:
    """移除 AI 生成的客套话前缀和结语后缀。

    Args:
        text: 原始 LLM 输出文本

    Returns:
        (cleaned_text, removed_items): 清洗后文本 + 被移除内容的描述列表
    """
    removed: list[str] = []
    original = text

    # ── Phase 1: 前缀剔除 ──
    for pattern, label in _PREFIX_PATTERNS:
        match = pattern.match(text)
        if match:
            cut_len = match.end()
            text = text[cut_len:].lstrip()
            removed.append(f"[前缀] {label}: \"{original[cut_len-20:cut_len].strip()}...\"")
            break  # 只砍一次前缀

    # ── Phase 2: 后缀剔除（从尾部向前查找）──
    for pattern, label in _SUFFIX_PATTERNS:
        match = pattern.search(text)
        if match and match.start() > len(text) * 0.5:
            # 只删除文本后半段的结语（避免误删正文中的引用）
            prefix_len = len(match.group(1)) if match.group(1) else 0
            text = text[:match.start() + prefix_len].rstrip()
            removed.append(f"[后缀] {label}")
            break  # 只砍一次后缀

    # ── Phase 3: 独立废话行剔除 ──
    lines = text.split("\n")
    cleaned_lines: list[str] = []
    for line in lines:
        is_trash = False
        for trash_re in _STANDALONE_TRASH_LINES:
            if trash_re.match(line):
                is_trash = True
                break
        if is_trash:
            removed.append(f"[废话行] \"{line.strip()}\"")
            continue
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)

    # ── 最终 trim ──
    text = text.strip()

    return text, removed


# ═══════════════════════════════════════════════════════════════
# 第二道：Markdown 代码块包裹剥离
# ═══════════════════════════════════════════════════════════════

_CODE_FENCE_START = re.compile(
    r"^\s*```\s*(markdown|md|text|html|plaintext|plain)?\s*\n?",
    re.IGNORECASE,
)
_CODE_FENCE_END = re.compile(r"\n?\s*```\s*$")


def strip_markdown_code_fences(text: str) -> Tuple[str, bool]:
    """剥离 LLM 自作聪明添加的 ```markdown ... ``` 代码块包裹。

    Args:
        text: 可能在首尾被 code fence 包裹的文本

    Returns:
        (cleaned_text, was_stripped): 清洗后文本 + 是否真的剥离了代码块
    """
    original = text
    text = text.strip()

    # 检查是否以 ``` 开头并以 ``` 结尾（且首尾的 ``` 是配对的）
    if not text.startswith("```"):
        return text, False

    # 去掉开头的 ```markdown / ```md / ``` 等
    text = _CODE_FENCE_START.sub("", text, count=1)

    # 去掉结尾的 ```
    text = _CODE_FENCE_END.sub("", text, count=1)

    text = text.strip()
    return text, text != original


# ═══════════════════════════════════════════════════════════════
# 第二点五道：空模块物理切除
# ═══════════════════════════════════════════════════════════════

# 模块标题后紧跟"暂无/无"占位内容 → 整块删除
_EMPTY_MODULE_RE = re.compile(
    r"\n*##\s+([^\n]+)\s*\n\s*\n"
    r"\s*(?:暂无|无相关|无(?:获奖|实习|项目|校园|竞赛|证书|语言|法提供|从查证))[^\n]*\s*"
    r"(?=\n*##|\n*\Z)",
    re.MULTILINE,
)

# 残留：单独的 ## 标题行后面全是空行直到文末
_TRAILING_EMPTY_HEADING_RE = re.compile(
    r"\n*##\s+[^\n]+\s*\n\s*\Z",
    re.MULTILINE,
)


def _strip_empty_sections(text: str) -> tuple[str, int]:
    """切除内容为空的简历模块。

    匹配模式：## 模块标题 + 空行 + "暂无/无..."占位文本。
    返回 (清洗后文本, 切除模块数)。
    """
    removed_count = 0

    # Phase 1: 完整空模块（标题 + 暂无内容）
    while True:
        match = _EMPTY_MODULE_RE.search(text)
        if not match:
            break
        removed_count += 1
        section_name = match.group(1).strip()
        # 替换为 \n\n 保持段间距，避免前后模块粘连
        text = text[: match.start()] + "\n\n" + text[match.end() :]
        logger.info(f"[sanitizer] 切除空模块: ## {section_name}")

    # Phase 2: 末尾孤独标题行
    while True:
        match = _TRAILING_EMPTY_HEADING_RE.search(text)
        if not match:
            break
        removed_count += 1
        text = text[: match.start()].rstrip()
        logger.info(f"[sanitizer] 切除末尾空标题")

    return text, removed_count


# ═══════════════════════════════════════════════════════════════
# 第三道：综合清洗 —— 串联所有过滤器
# ═══════════════════════════════════════════════════════════════

# 多行连续的 3+ 空行 → 压缩为单个空行
_RE_MULTI_BLANK = re.compile(r"\n\s*\n\s*\n+")


def sanitize_resume_text(text: str, log_prefix: str = "") -> str:
    """综合清洗管道：代码块剥离 → 客套话剔除 → 空白压缩。

    此函数应在 LLM 输出即将发送到前端之前调用，作为 Prompt 之后的
    第二道物理防线。所有函数幂等，重复调用不会过度修剪。

    Args:
        text: LLM 原始输出文本（已通过 XML 标签提取或直接输出）
        log_prefix: 日志前缀（如 "[editor]"、"[sse]"）

    Returns:
        清洗后的纯净简历文本
    """
    if not text or not text.strip():
        return text

    original_len = len(text)

    # Step 1: 剥离 Markdown 代码块包裹
    text, fence_stripped = strip_markdown_code_fences(text)
    if fence_stripped:
        tag = f"{log_prefix} [sanitizer] 剥离了 Markdown 代码块包裹" if log_prefix else "[sanitizer] 剥离了 Markdown 代码块包裹"
        print(tag)

    # Step 2: 移除 AI 客套话
    text, removed = strip_ai_pleasantries(text)
    if removed:
        tag = f"{log_prefix} [sanitizer]" if log_prefix else "[sanitizer]"
        for item in removed:
            print(f"{tag} {item}")

    # Step 2.5: 切除空模块（## 标题 + 暂无/无 占位内容）
    text, sections_removed = _strip_empty_sections(text)
    if sections_removed:
        tag = f"{log_prefix} [sanitizer] 切除了 {sections_removed} 个空模块" if log_prefix else f"[sanitizer] 切除了 {sections_removed} 个空模块"
        print(tag)

    # Step 3: 压缩连续空行
    text = _RE_MULTI_BLANK.sub("\n\n", text)

    # Step 4: 最终 trim
    text = text.strip()

    if log_prefix and len(text) != original_len:
        print(f"{log_prefix} [sanitizer] 清洗完成: {original_len} → {len(text)} 字符 "
              f"(-{original_len - len(text)})")

    return text
