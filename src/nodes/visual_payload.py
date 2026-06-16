"""
v4.5 混合解耦载荷编译器 (Hybrid Schema Compiler)
==================================================
纯函数工具 —— 从 revised_resume Markdown 中提取结构化字段 (name/contact/skills[])，
同时保留全量正文 Markdown，供前端 A4 看板实现精美 Pill 标签 + 长文渲染。

核心原则:
  - 零侵入：不修改任何 LLM 文字生成逻辑
  - 物理隔离：结构化字段提取失败时优雅降级，绝不抛异常
  - 星号清洗：确保输出 Markdown 中无裸奔 ** 残留
"""

import re
import logging

logger = logging.getLogger("VisualPayload")
logging.basicConfig(level=logging.INFO)

# ── 姓名提取正则 ──
_NAME_RE = re.compile(
    r"\*\*姓\s*名\s*[：:]\s*\*\*\s*(.+?)(?:\s|$)",
    re.IGNORECASE,
)
_NAME_FALLBACK_RE = re.compile(
    r"(?:姓\s*名|姓名)\s*[：:]\s*(.+?)(?:\s|$)",
    re.IGNORECASE,
)

# ── 联系方式提取 ──
_PHONE_RE = re.compile(
    r"(?:手\s*机|电话|手机号|联系电话)\s*[：:]\s*(.+?)(?:\s*$|\s*\n)",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
)

# ── 技能行解析 ──
# 匹配 **类别：** 值 或 **类别:** 值 或 - **类别：** 值
_SKILL_LINE_RE = re.compile(
    r"(?:^-\s*)?\*\*([^*]+?)\s*[：:]\s*\*\*\s*(.+?)$",
    re.MULTILINE,
)

# ── 模块标题检测 ──
_SECTION_HEADING_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)

# ── 需要从 main_resume_markdown 中移除的模块标题关键词 ──
_STRIP_SECTION_KEYWORDS = [
    "个人基础信息", "个人信息", "基本信息", "个人资料",
    "核心技术栈", "技能特长", "专业技能", "技术能力", "技能",
]

# ── 裸奔 ** 残留清洗 ──
_STRAY_STARS_RE = re.compile(r"(?<!\*)\*\*(?!\*)")  # 匹配孤立的 **


def compile_to_visual_payload(revised_resume: str) -> dict:
    """
    从精修后的简历 Markdown 中提取混合解耦载荷。

    Args:
        revised_resume: editor/chat_editor 产出的纯净 Markdown 简历

    Returns:
        {
            "name": "周健恺",
            "contact": "手机：138-XXXX-XXXX | 邮箱：xxx@xxx.com",
            "skills": ["Python", "LangGraph", "ChromaDB", "FastAPI"],
            "main_resume_markdown": "全量简历 Markdown（已清洗裸奔星号）"
        }
    """
    if not revised_resume or not revised_resume.strip():
        return {
            "name": "",
            "contact": "",
            "skills": [],
            "main_resume_markdown": "",
        }

    text = revised_resume.strip()

    # ── 1. 提取姓名 ──
    name = _extract_name(text)

    # ── 2. 提取联系方式 ──
    contact = _extract_contact(text)

    # ── 3. 提取技能数组 ──
    skills = _extract_skills(text)

    # ── 4. 构建 main_resume_markdown（移除已提取的模块，清洗裸星号）──
    main_md = _strip_extracted_sections(text)
    main_md = _sanitize_stray_stars(main_md)

    logger.info(
        f"[VisualPayload] 编译完成: name={name}, contact_len={len(contact)}, "
        f"skills={len(skills)}项, main_md={len(main_md)}字符"
    )

    return {
        "name": name,
        "contact": contact,
        "skills": skills,
        "main_resume_markdown": main_md,
    }


def _extract_name(text: str) -> str:
    """从简历 Markdown 中提取纯中文姓名"""
    match = _NAME_RE.search(text)
    if match:
        name = match.group(1).strip()
        # 清洗：去掉拼音、英文、多余符号
        name = _clean_chinese_name(name)
        if name:
            return name

    # 回退：尝试无 markdown 格式的姓名行
    match = _NAME_FALLBACK_RE.search(text)
    if match:
        name = match.group(1).strip()
        name = _clean_chinese_name(name)
        if name:
            return name

    return ""


def _clean_chinese_name(name: str) -> str:
    """清洗姓名：仅保留中文字符，去除拼音/英文/数字/括号"""
    # 去掉括号内的拼音 (如 "周健恺(Zhou Jiankai)" → "周健恺")
    name = re.sub(r"\([^)]*\)", "", name)
    name = re.sub(r"（[^）]*）", "", name)
    # 去掉英文字母和数字
    name = re.sub(r"[a-zA-Z0-9]", "", name)
    # 去掉多余空格和标点
    name = re.sub(r"[\s·•,，。、;；:：]+", "", name)
    return name.strip()


def _extract_contact(text: str) -> str:
    """提取联系方式，组合为单行字符串"""
    parts: list[str] = []

    # ── 预处理：去除 Markdown 加粗标记，简化提取 ──
    clean_text = text.replace("**", "")

    # 手机号
    phone_match = _PHONE_RE.search(clean_text)
    if phone_match:
        phone = phone_match.group(1).strip()
        # 清洗残留星号
        phone = phone.replace("*", "").strip()
        if phone:
            parts.append(f"手机：{phone}")

    if not parts:
        # 回退：直接匹配手机号格式
        raw_phone = re.search(r"1[3-9]\d{1,2}[-\s]?\d{4}[-\s]?\d{4}", text)
        if raw_phone:
            parts.append(f"手机：{raw_phone.group(0)}")

    # 邮箱
    email_match = _EMAIL_RE.search(text)
    if email_match:
        parts.append(f"邮箱：{email_match.group(0)}")

    return " | ".join(parts) if parts else ""


def _extract_skills(text: str) -> list[str]:
    """
    从简历 Markdown 的技能模块中提取所有技能关键词。

    解析策略:
      1. 找到 ## 核心技术栈 / ## 技能特长 模块
      2. 解析 **类别：** 值 格式的行
      3. 将每个类别的值按逗号/中文逗号/顿号拆分
      4. 去重、去空白、保留完整技能名
    """
    # 先定位技能模块
    skills_section = _find_skills_section(text)
    if not skills_section:
        return []

    all_skills: list[str] = []
    seen: set[str] = set()

    for match in _SKILL_LINE_RE.finditer(skills_section):
        raw_values = match.group(2).strip()
        # 按中文逗号、英文逗号+空格、顿号、竖线拆分（保留 / 如 CI/CD）
        items = re.split(r"[，、|]|,\s*", raw_values)
        for item in items:
            item = item.strip()
            # 过滤：至少 2 个字符，不含冒号，不含纯标点
            if len(item) >= 2 and "：" not in item and ":" not in item:
                if item.lower() not in seen:
                    all_skills.append(item)
                    seen.add(item.lower())

    return all_skills


def _find_skills_section(text: str) -> str:
    """定位技能模块的文本范围"""
    headings = list(_SECTION_HEADING_RE.finditer(text))

    skill_keywords = ["核心技术栈", "技能特长", "专业技能", "技术能力", "技能", "技术栈"]

    for i, match in enumerate(headings):
        heading_text = match.group(1).strip()
        if any(kw in heading_text for kw in skill_keywords):
            start = match.start()
            # 找到下一个 ## 标题的位置作为结束
            if i + 1 < len(headings):
                end = headings[i + 1].start()
            else:
                end = len(text)
            return text[start:end]

    return ""


def _strip_extracted_sections(text: str) -> str:
    """
    从全量 Markdown 中移除已提取为结构化字段的模块
    (个人基础信息 + 技能模块)，避免前端重复渲染。
    """
    headings = list(_SECTION_HEADING_RE.finditer(text))

    # 找到需要移除的模块索引
    indices_to_strip: set[int] = set()
    for i, match in enumerate(headings):
        heading_text = match.group(1).strip()
        if any(kw in heading_text for kw in _STRIP_SECTION_KEYWORDS):
            indices_to_strip.add(i)

    if not indices_to_strip:
        return text

    # 构建移除后的文本
    result_parts: list[str] = []
    last_end = 0

    for i, match in enumerate(headings):
        if i in indices_to_strip:
            # 如果上一个段落还没追加，先追加
            if last_end < match.start():
                result_parts.append(text[last_end:match.start()])
            # 找到这个模块的结束位置
            if i + 1 < len(headings):
                last_end = headings[i + 1].start()
            else:
                last_end = len(text)
        # 非移除模块：不在这里处理，留给最后一次追加

    # 追加最后一个非移除模块之后的内容
    if last_end < len(text):
        result_parts.append(text[last_end:])

    result = "".join(result_parts).strip()

    # 清理多余的空行（连续 3+ 空行 → 2 空行）
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result


def _sanitize_stray_stars(text: str) -> str:
    """
    清洗残留裸奔星号：确保 markdown 中 ** 标记成对出现。

    背景: DeepSeek 偶尔会输出不配对的 **，导致 react-markdown 渲染时
    星号裸露在 HTML 中。此函数检测并修复此类情况。
    """
    # 统计 ** 出现次数
    count = text.count("**")
    if count % 2 == 0:
        # 偶数个：基本健康，仅清理行首行尾孤立星号
        lines = text.split("\n")
        cleaned: list[str] = []
        for line in lines:
            # 移除行首行尾独立的 **（非加粗语法）
            stripped = line.strip()
            if stripped == "**" or stripped == "** " or stripped == " **":
                continue  # 跳过纯星号行
            cleaned.append(line)
        return "\n".join(cleaned)

    # 奇数个：存在裸奔星号，物理移除所有 **
    logger.warning(f"[VisualPayload] 检测到奇数个 ** 标记 ({count}个)，执行物理清洗")
    return text.replace("**", "")
