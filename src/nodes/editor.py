"""
v3.0 Editor 节点 —— 纯净 Markdown 流 + XML 物理隔离 + 全量保留

核心升级:
  - 彻底移除 JSON 键值对约束，LLM 输出纯净 Markdown
  - 物理隔离: 思考/废话丢弃，<clean_resume>...</clean_resume> 内为 A4 纸渲染内容
  - 全量保留: 教育背景/实习经历/项目经历/校园经历/获奖情况/技能特长 一个不删
  - 三段式 | 分隔: 时间段 | 机构名称 | 身份或专业
  - 零噪音: 禁止 (估算)/(待确认指标)/项目周期：未注明 等机器垃圾
"""

import os
import re
from src.state import AgentState
from src.utils.llm import get_flash_client, get_pro_client

# ── RAG 上下文拆分 ──────────────────────────────────────────────

_HEADER_LINE = re.compile(r"^\s*\[.+?\]\s*(案例内容|：)", re.IGNORECASE)


def _split_rag_items(rag_context: str) -> list[str]:
    if not rag_context or not rag_context.strip():
        return []
    raw_items = rag_context.split("\n\n")
    items: list[str] = []
    for item in raw_items:
        item = item.strip()
        if not item:
            continue
        item = _HEADER_LINE.sub("", item, count=1).strip()
        if item and len(item) >= 6:
            items.append(item)
    return items


def _build_term_injection(items: list[str]) -> str:
    terms: list[str] = []
    seen: set[str] = set()
    for item in items:
        if len(item) < 150:
            clean = item.strip().rstrip("。，；,.;")
            if clean and len(clean) >= 4 and clean not in seen:
                terms.append(clean)
                seen.add(clean)
        else:
            first_sentence = re.split(r"[。；\n]", item, maxsplit=1)[0].strip()
            if first_sentence and len(first_sentence) >= 8 and first_sentence not in seen:
                terms.append(first_sentence)
                seen.add(first_sentence)
    if not terms:
        return "（暂无专属术语库，请基于通用大厂标准进行动词升级）"
    max_terms = 25
    if len(terms) > max_terms:
        terms = terms[:max_terms]
    lines = [f"  {i}. {t}" for i, t in enumerate(terms, 1)]
    return "\n".join(lines)


def _build_golden_cases(items: list[str]) -> str:
    if not items:
        return "（暂无金牌案例素材，请基于通用大厂标准进行技术深度延伸）"
    long_items = [it for it in items if len(it) >= 80]
    if not long_items:
        long_items = items
    max_cases = 8
    cases = long_items[:max_cases]
    lines: list[str] = []
    for i, case in enumerate(cases, 1):
        lines.append(f"案例{i}. {case}")
    return "\n".join(lines)


def _extract_thinking(response) -> str:
    if hasattr(response, "additional_kwargs") and response.additional_kwargs:
        thinking = response.additional_kwargs.get("thinking", "")
        if thinking:
            return thinking
    if hasattr(response, "response_metadata") and response.response_metadata:
        thinking = response.response_metadata.get("thinking", "")
        if thinking:
            return thinking
    return ""


# ── XML 标签解析 ──────────────────────────────────────────────────

_CLEAN_RESUME_RE = re.compile(
    r"<clean_resume>\s*([\s\S]*?)\s*</clean_resume>",
    re.IGNORECASE,
)


def _extract_clean_markdown(response_text: str) -> str:
    """从 LLM 响应中提取 <clean_resume>...</clean_resume> 内的纯净 Markdown"""
    match = _CLEAN_RESUME_RE.search(response_text)
    if match:
        return match.group(1).strip()
    # 回退: 如果没找到标签，尝试去掉常见前缀废话
    fallback = response_text.strip()
    for marker in ["好的，以下是", "以下是优化后的", "这是优化后的", "```markdown", "```"]:
        idx = fallback.find(marker)
        if idx >= 0:
            fallback = fallback[idx + len(marker):].strip()
    # 去掉尾部 ``` 标记
    if fallback.endswith("```"):
        fallback = fallback[:-3].strip()
    return fallback


# ── v3.0 System Prompt（纯净 Markdown + XML 物理隔离）────────────────

EDITOR_SYSTEM_PROMPT = """你是一位拥有 10 年经验的大厂（字节跳动/阿里巴巴/腾讯）资深技术架构师兼首席猎头。你的任务是将原始简历优化为一份排版精美、内容完整、可直接打印的高质量 Markdown 简历。

══════════════════════════════════════════════════════════
【铁律零】物理隔离 — 思考与输出彻底分离
══════════════════════════════════════════════════════════
你可以在 <clean_resume> 标签之外进行简短的专业分析思考（如动词替换理由、STAR 补全策略），但这部分将被系统丢弃，不会展示给用户。
真正要渲染到 A4 纸上的纯净简历，必须严格包裹在 <clean_resume>...</clean_resume> XML 标签内。

正确格式示例:
<clean_resume>
## 教育背景
...
## 实习经历
...
</clean_resume>

<clean_resume> 标签内必须是纯净的 Markdown，不允许任何闲聊、问候语、或"以下是优化后的简历"之类的废话。
XML 标签必须正确闭合，否则简历无法渲染。

══════════════════════════════════════════════════════════
【铁律一】全量保留死命令 — 一个模块、一个数据都不许删
══════════════════════════════════════════════════════════
你必须全量保留原简历中的每一个模块及其含金量数据，禁止擅自删减。包括但不限于：
  - 教育背景
  - 实习经历（对在校生/应届生，严禁将"实习经历"改称"工作经历"！）
  - 项目经历
  - 校园经历（社团、学生会、志愿者等）
  - 获奖情况
  - 技能特长

每个模块的量化数据（GPA、排名、奖项级别、项目成果数字）必须原样保留。
宁可内容稍多，绝不擅自阉割——HR 比你更清楚什么信息对候选人重要。

══════════════════════════════════════════════════════════
【铁律二】STAR 融合 — 拒绝口水话，拒绝二级标题
══════════════════════════════════════════════════════════
每个项目/实习的每条要点必须将 Situation/Task/Action/Result 融合进一句话。
严禁出现「情景」「任务」「行动」「结果」等二级标题字样。
用强动词直接切入：在什么场景下 → 做了什么 → 取得什么量化成果。

正确示例:
- 针对日均 50 万请求下数据库压力瓶颈，设计 Redis 多级缓存方案，P99 延迟从 2s 降至 200ms

错误示例（禁止）:
- 情景：订单系统日均50万请求，数据库压力大
- 行动：引入 Redis 缓存层

══════════════════════════════════════════════════════════
【铁律三】动词升级 — 禁用平庸词
══════════════════════════════════════════════════════════
严禁使用: 负责、参与、做了、写了、用过、维护、处理、开发
必须使用: 主导、构建、攻克、重塑、调优、消除、标准化、精细化、逆向、渗透、压榨、重构、设计、实现

术语注入库（匹配平替词汇）:
{term_injection}

══════════════════════════════════════════════════════════
【铁律四】禁止机器噪音 — 简历必须严肃专业
══════════════════════════════════════════════════════════
以下词汇及类似表述严禁出现在 <clean_resume> 内的任何位置:
  - （估算）
  - （待确认指标）
  - （待确认）
  - 项目周期：未注明
  - [请填入...]
  - （注：...）
  - （约）
  - 大约、大概、左右

简历必须像一份真实的、可以直接投递的正式文档。任何括号注释都会破坏 HR 的信任感。
如需标注量化数据，直接写数字，不要画蛇添足加括号注释。

══════════════════════════════════════════════════════════
【铁律五】经历行三段式绝对格式 — 必须用 | 分隔
══════════════════════════════════════════════════════════
任何经历（学校、公司、实习单位、校园组织）的第一行描述，必须且只能使用以下格式:

时间段 | 机构名称 | 身份或专业

正确示例:
2020.09 - 2024.06 | 北京大学 | 计算机科学与技术 · 本科
2025.11 - 2026.05 | 腾讯科技（深圳）有限公司 | 实习算法工程师
2023.06 - 2023.09 | 字节跳动 | 后端开发实习生
2020.09 - 2022.06 | 校学生会外联部 | 部长

严禁使用其他分隔符（如逗号、破折号、空格对齐），必须严格使用竖线 | 分隔三段。

══════════════════════════════════════════════════════════
【铁律六】技能特长格式 — 分类硬换行
══════════════════════════════════════════════════════════
技能特长模块必须使用 **类别名：** 格式，每个大类独立一行:

正确格式:
**编程语言：** Python, Java, C++, Go
**AI 工程化：** PyTorch, LangChain, LlamaIndex, vLLM
**数据库与中间件：** MySQL, Redis, Kafka, Elasticsearch
**DevOps：** Docker, Kubernetes, CI/CD, Prometheus

严禁将所有技能揉成一团文字。

══════════════════════════════════════════════════════════
【铁律七】技术深度 + 量化
══════════════════════════════════════════════════════════
基于已有技术栈合理推导技术细节。每条要点必须具备:
  - 技术原理（用了什么 + 怎么用的 + 为什么）
  - 量化成果（性能提升 % / 延迟变化 / 成本降低等，直接写数字）

金牌案例（深度利用其技术方案和量化数字）:
{golden_cases}

══════════════════════════════════════════════════════════
【铁律八】严禁编造
══════════════════════════════════════════════════════════
- 绝对不添加原始简历中不存在的新技术栈
- 绝对不编造未参与过的项目或未担任过的职位
- 允许基于已有经验进行合理的技术深度延伸

══════════════════════════════════════════════════════════
【铁律九】Markdown 排版规范
══════════════════════════════════════════════════════════
- 模块标题（教育背景、实习经历等）使用 ## 二级标题，简洁有力
- 每个 ## 标题前保留一个空行，确保视觉呼吸感
- 经历的第一行使用 | 三段式分隔（时间段 | 机构 | 身份）
- 每条要点使用 - 开头（无序列表），每条占一行
- 技能使用 **类别：** 加粗格式，每个大类独立一行
- 获奖情况使用 - 列表，每项一行

──────────────────────────────

【联网搜索补充】:
{web_search_context}

【目标岗位 JD】:
{jd}

【原始简历】:
{resume}

现在请分析原始简历的不足之处，然后用 <clean_resume> 标签输出优化后的纯净 Markdown 简历。记住: <clean_resume> 之外的内容会被丢弃。"""


# ── EXTREME_GAP 防幻觉骨架模式 Prompt ─────────────────────────────

EDITOR_EXTREME_GAP_PROMPT = """你是一位诚实的职业规划顾问。当前场景：候选人与目标 JD 之间存在极端差距 (EXTREME_GAP)。

你必须遵守以下铁律:

══════════════════════════════════════════════════════════
【铁律一】物理隔离
══════════════════════════════════════════════════════════
最终简历必须包裹在 <clean_resume>...</clean_resume> 标签内。标签外内容会被丢弃。

══════════════════════════════════════════════════════════
【铁律二】严禁编造
══════════════════════════════════════════════════════════
- 绝对不编造虚假项目经验、新技术栈、未参与的架构设计
- 不把"个人博客"包装成"企业级微服务平台"

══════════════════════════════════════════════════════════
【铁律三】标准骨架搭建模式
══════════════════════════════════════════════════════════
- 用 STAR 融合结构组织已有项目
- 平庸动词升级为中等动词（实现/设计/构建/优化）
- 缺失信息用方括号占位符留白：[请填入您的日均订单量]
- 每条要点 ≤ 3 条

══════════════════════════════════════════════════════════
【铁律四】Markdown 格式
══════════════════════════════════════════════════════════
- 模块标题使用 ##
- 经历第一行使用 | 三段式: 时间段 | 机构名称 | 身份或专业
- 要点使用 - 列表
- 技能使用 **类别：** 格式
- 禁止 (估算)、(待确认指标) 等噪音词

══════════════════════════════════════════════════════════
【铁律五】全量保留
══════════════════════════════════════════════════════════
原简历的每个模块必须保留，一个不能删。

【联网搜索补充】: {web_search_context}
【目标岗位 JD】: {jd}
【原始简历】: {resume}

现在请用 <clean_resume> 标签输出骨架搭建后的 Markdown 简历。"""


# ── 毒舌批评 ────────────────────────────────────────────────────

def _build_critique(original: str, revised_text: str, thinking_text: str = "",
                    optimization_summary: str = "") -> str:
    lines = [
        "[毒舌批评] 原简历存在以下 3 个核心缺陷：",
        "1. 动词平庸——大量使用'负责/参与/做了'，缺乏技术主导感和工程影响力。",
        "2. 缺乏量化——所有成果均为定性描述，无法让面试官评估实际贡献量级。",
        "3. 技术深度不足——只描述了表面行为，未体现架构决策、性能优化、异常处理等技术深水区。",
    ]
    if optimization_summary:
        lines.append("")
        lines.append(f"[优化综述] {optimization_summary}")
        lines.append("")
        lines.append(f"[本次修改侧重点]")
    else:
        lines.append("")
        lines.append("[本次修改侧重点]")
    lines.append("- 将所有平庸动词替换为大厂级词汇（主导/构建/攻克/精炼）。")
    lines.append("- 每个项目经历融合 STAR 结构为精简要点，补充分层技术细节。")
    lines.append("- 参考金牌案例中的量化模式，去除所有机器噪音标记。")
    lines.append(f"- 优化后简历长度：{len(revised_text)} 字符（原文 {len(original)} 字符）。")

    if thinking_text:
        lines.append("")
        lines.append(f"[模型思考链] {len(thinking_text)} 字符思维链已记录。")

    return "\n".join(lines)


# ── 主节点 ──────────────────────────────────────────────────────

def editor_node(state: AgentState):
    """
    v3.0 核心优化节点 —— 纯净 Markdown 流 + XML 物理隔离

    输出:
      - revised_resume: <clean_resume> 内的纯净 Markdown 文本（前端 A4 纸渲染）
      - internal_monologue: 毒舌批评 + 优化分析
      - optimization_summary: 标签外的简短策略说明
      - clean_resume_json: {}（v3.0 已弃用 JSON，保留字段兼容）
    """
    resume = state.get("resume", "")
    jd = state.get("jd", "")
    rag_context = state.get("rag_context", "")
    tool_outputs = state.get("tool_outputs", [])
    difficulty_flag = state.get("difficulty_flag", "")

    if not resume.strip():
        return {
            "revised_resume": "",
            "internal_monologue": "[editor] 原始简历为空，跳过优化。",
            "optimization_summary": "",
            "clean_resume_json": {},
        }

    # ── 联网搜索上下文 ──
    if tool_outputs:
        web_search_context = "\n\n".join(tool_outputs)
    else:
        web_search_context = "（未启用联网搜索）"

    # ── 防幻觉骨架模式 ──
    if difficulty_flag == "EXTREME_GAP":
        prompt = EDITOR_EXTREME_GAP_PROMPT.format(
            web_search_context=web_search_context,
            jd=jd,
            resume=resume,
        )
        print(f"[editor] 触发防幻觉骨架模式 (EXTREME_GAP), Prompt {len(prompt)} 字符")

        try:
            llm = get_flash_client()
            response = llm.invoke(prompt)
            response_text = response.content if hasattr(response, "content") else str(response)
            response_text = response_text.strip()
        except Exception as e:
            print(f"[editor] 骨架模式失败: {type(e).__name__}: {e}")
            return {
                "revised_resume": resume,
                "internal_monologue": f"[editor] 骨架模式异常 ({type(e).__name__})，已回退。",
                "optimization_summary": "",
                "clean_resume_json": {},
            }

        clean_md = _extract_clean_markdown(response_text)
        placeholder_count = clean_md.count("[请")

        print(f"[editor] 骨架模式完成, 输出 {len(clean_md)} 字符, 占位符 {placeholder_count} 处")

        monologue = (
            f"[editor 防幻觉骨架模式] EXTREME_GAP，已禁用大厂级动词升级和量化编造。\n"
            f"转为标准骨架搭建。输出 {len(clean_md)} 字符，{placeholder_count} 处占位符留白。\n"
        )

        return {
            "revised_resume": clean_md,
            "internal_monologue": monologue,
            "optimization_summary": "",
            "clean_resume_json": {},
        }

    # ── 正常模式 ──
    rag_items = _split_rag_items(rag_context)
    term_injection = _build_term_injection(rag_items)
    golden_cases = _build_golden_cases(rag_items)

    if not rag_context.strip():
        golden_cases = "（未检索到相关金牌案例，请基于通用大厂标准进行优化）"
        term_injection = "（暂无专属术语库，请基于通用大厂标准进行动词升级）"

    prompt = EDITOR_SYSTEM_PROMPT.format(
        term_injection=term_injection,
        golden_cases=golden_cases,
        web_search_context=web_search_context,
        jd=jd,
        resume=resume,
    )

    use_pro = os.getenv("USE_PRO_MODEL", "false").lower() == "true"
    model_label = "DeepSeek-V4-Pro (Thinking)" if use_pro else "DeepSeek-V4-Flash"

    print(f"[editor] 调用 {model_label} (v3.0 纯净 Markdown 流)...")
    print(f"[editor] Prompt {len(prompt)} 字符, RAG {len(rag_items)} 条")

    try:
        llm = get_pro_client() if use_pro else get_flash_client()
        response = llm.invoke(prompt)
        thinking_text = _extract_thinking(response)
        response_text = response.content if hasattr(response, "content") else str(response)
        response_text = response_text.strip()
    except Exception as e:
        print(f"[editor] 模型调用失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {
            "revised_resume": resume,
            "internal_monologue": f"[editor] 优化失败 ({type(e).__name__})，已回退。",
            "optimization_summary": "",
            "clean_resume_json": {},
        }

    if thinking_text:
        print(f"[editor] 思维链 {len(thinking_text)} 字符")
        print("-" * 40)
        print(thinking_text[:1500])
        print("-" * 40)

    # ── 提取 <clean_resume> 内的纯净 Markdown ──
    clean_md = _extract_clean_markdown(response_text)

    if not clean_md or len(clean_md) < 50:
        print(f"[editor] <clean_resume> 提取失败或内容过短 ({len(clean_md)} 字符)，回退原始输出")
        monologue = _build_critique(resume, response_text, thinking_text)
        return {
            "revised_resume": response_text,
            "internal_monologue": monologue,
            "optimization_summary": "",
            "clean_resume_json": {},
        }

    # ── 构建优化说明 ──
    summary_lines = []
    if thinking_text:
        # 从思维链中提取前两句作为优化说明
        thinking_sentences = re.split(r"[。；\n]", thinking_text, maxsplit=2)
        summary_lines = [s.strip() for s in thinking_sentences[:2] if s.strip() and len(s.strip()) >= 10]
    optimization_summary = "；".join(summary_lines) if summary_lines else ""

    # ── 构建内省 ──
    monologue = _build_critique(resume, clean_md, thinking_text, optimization_summary)

    # ── 统计信息 ──
    h2_count = len(re.findall(r"^##\s", clean_md, re.MULTILINE))
    pipe_count = len(re.findall(r"\|", clean_md))
    print(f"[editor] v3.0 Markdown 优化完成: {len(clean_md)} 字符, {h2_count} 个 ## 模块, "
          f"{pipe_count} 处 | 分隔符, summary {len(optimization_summary)} 字符")

    return {
        "revised_resume": clean_md,
        "internal_monologue": monologue,
        "optimization_summary": optimization_summary,
        "clean_resume_json": {},
    }
