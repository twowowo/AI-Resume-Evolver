"""
v2.7 Editor 节点 —— 纯 JSON 输出 + 物理隔离 + 长话短说约束

核心升级:
  - LLM 必须且只能输出纯净 JSON，禁止自由 Markdown
  - optimization_summary → 前端看板消费
  - clean_resume_json → 前端 A4 纸视口渲染
  - 每个项目 Action ≤ 3 条，每条 ≤ 2 行，HR 10 秒阅完
"""

import os
import json as json_mod
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


# ── JSON 解析 ──────────────────────────────────────────────────

def _parse_editor_json(response_text: str) -> dict:
    """从 LLM 响应中提取 JSON，带容错回退"""
    json_match = re.search(r"\{[\s\S]*\}", response_text)
    if not json_match:
        return {"error": "no_json_found", "raw": response_text[:500]}
    try:
        data = json_mod.loads(json_match.group(0))
        if "clean_resume_json" not in data:
            return {"error": "missing_clean_resume_json", "raw": response_text[:500]}
        return data
    except json_mod.JSONDecodeError:
        return {"error": "json_parse_error", "raw": json_match.group(0)[:500]}


def _json_to_text(data: dict) -> str:
    """将 clean_resume_json 转换为可读纯文本（用于流式打字机展示）"""
    lines = []
    name = data.get("name", "")
    title = data.get("title", "")
    if name:
        header = name if not title else f"{name} · {title}"
        lines.append(header)
        lines.append("")

    summary = data.get("summary", "")
    if summary:
        lines.append("个人总结")
        lines.append(summary)
        lines.append("")

    skills = data.get("skills", [])
    if skills:
        lines.append("核心技能")
        lines.append(" / ".join(skills))
        lines.append("")

    experience = data.get("experience", [])
    if experience:
        lines.append("工作经历")
        lines.append("")
        for exp in experience:
            company = exp.get("company", "")
            role = exp.get("role", "")
            period = exp.get("period", "")
            header_parts = [p for p in [company, role, period] if p]
            lines.append(" · ".join(header_parts))
            for action in exp.get("actions", []):
                lines.append(f"- {action}")
            lines.append("")

    education = data.get("education")
    if education:
        lines.append("教育背景")
        parts = [education.get(k, "") for k in ["school", "degree", "period"] if education.get(k, "")]
        lines.append(" · ".join(parts))

    return "\n".join(lines)


# ── v2.7 System Prompt（纯 JSON 输出）────────────────────────────

EDITOR_SYSTEM_PROMPT = """你是一位拥有 10 年经验的大厂（字节跳动/阿里巴巴/腾讯）资深技术架构师兼首席猎头。你的任务是优化简历。你必须严格遵守以下规则，**绝对不允许输出任何闲聊、问候语或 Markdown 格式**。

══════════════════════════════════════════════════
【铁律零】仅输出 JSON，禁止任何额外文字
══════════════════════════════════════════════════
你的整个响应必须是合法的 JSON 对象，不能有任何前缀或后缀文字。
严禁输出诸如"好的，以下是优化后的简历"、"这是 JSON 格式"之类的废话。
如果无法完成任务，JSON 中的字段用空值填充。

══════════════════════════════════════════════════
【铁律一】STAR 融合 — 禁止二级标题
══════════════════════════════════════════════════
每个项目的每条 action 必须将 Situation/Task/Action/Result 融合进一句话中。
严禁出现「情景」「任务」「行动」「结果」等二级标题字样。
用强动词直接切入：在什么场景下 → 做了什么 → 取得什么量化成果。

示例 ─ 错误写法（禁止）:
  "情景：订单系统日均50万请求，数据库压力大"
  "行动：引入 Redis 缓存层"

示例 ─ 正确写法（仅此格式）:
  "针对日均 50 万请求下数据库压力瓶颈，设计 Redis 多级缓存方案，P99 延迟从 2s 降至 200ms（估算）"

══════════════════════════════════════════════════
【铁律二】Action 字数死锁
══════════════════════════════════════════════════
- 每个项目的 actions 数组最多 3 条，每项不超过 2 行（约 80 字）
- 超过 3 条直接截断！只保留最有冲击力的 3 条
- 每条必须包含可量化数据（标注"估算"或"待确认指标"均可）
- 拒绝口水话：禁止"摒弃了传统的..."、"充分考虑了..."等废话开头，直接切动词

══════════════════════════════════════════════════
【铁律三】动词升级 — 禁用平庸词
══════════════════════════════════════════════════
严禁：负责、参与、做了、写了、用过、维护、处理、开发
必须：主导、构建、攻克、重塑、调优、消除、标准化、精细化、逆向、渗透、压榨

术语注入库（匹配平替词汇）：
{term_injection}

══════════════════════════════════════════════════
【铁律四】技术深度 + 量化
══════════════════════════════════════════════════
基于已有技术栈合理推导技术细节并标注。每条 action 必须具备：
- 技术原理（用了什么 + 怎么用的 + 为什么）
- 量化成果（性能提升 % / 延迟变化 / 成本降低等，标注"估算"或"待确认指标"）

金牌案例（深度利用其技术方案和量化数字）：
{golden_cases}

══════════════════════════════════════════════════
【铁律五】严禁编造
══════════════════════════════════════════════════
- 绝对不添加原始简历中不存在的新技术栈
- 绝对不编造未参与过的项目或未担任过的职位
- 允许基于已有经验进行合理的技术深度延伸

══════════════════════════════════════════════════
【铁律六】只输出以下 JSON 结构
══════════════════════════════════════════════════

{{
  "optimization_summary": "<2-3 句话，简述核心优化手段：动词升级了哪些、STAR 补全了什么、量化提升了什么>",
  "clean_resume_json": {{
    "name": "<姓名>",
    "title": "<目标职位>",
    "summary": "<2-3 句自我评价，强动词开头，关键数字突出>",
    "skills": ["<技术栈1>", "<技术栈2>", "..."],
    "experience": [
      {{
        "company": "<公司名>",
        "role": "<职位>",
        "period": "<时间范围>",
        "actions": [
          "<S+T+A+R 融合描述，含量化指标（估算）>",
          "..."
        ]
      }}
    ],
    "education": {{
      "school": "<学校名>",
      "degree": "<学位 · 专业方向>",
      "period": "<就读时间>"
    }}
  }}
}}

actions 最多 3 条！必须融合 STAR，禁止二级标题。每条量化标注"（估算）"或"（待确认指标）"。

──────────────────────────────

【联网搜索补充】：
{web_search_context}

【目标岗位 JD】：
{jd}

【原始简历】：
{resume}

仅输出 JSON："""


# ── EXTREME_GAP 防幻觉骨架模式 Prompt ─────────────────────────────

EDITOR_EXTREME_GAP_PROMPT = """你是一位诚实的职业规划顾问。当前场景：候选人与目标 JD 之间存在极端差距 (EXTREME_GAP)。

你必须遵守以下铁律，**且只能输出 JSON，禁止任何额外文字**。

══════════════════════════════════════════════════
【铁律一】严禁编造
══════════════════════════════════════════════════
- 绝对不编造虚假项目经验、新技术栈、未参与的架构设计
- 不把"个人博客"包装成"企业级微服务平台"

══════════════════════════════════════════════════
【铁律二】标准骨架搭建模式
══════════════════════════════════════════════════
- 用 STAR 融合结构组织已有项目
- 平庸动词升级为中等动词（实现/设计/构建/优化）
- 缺失信息用方括号占位符留白：[请填入您的日均订单量]
- 每个项目 actions ≤ 3 条

══════════════════════════════════════════════════
【铁律三】仅输出 JSON
══════════════════════════════════════════════════

{{
  "optimization_summary": "<1-2 句说明骨架搭建策略和占位符数量>",
  "clean_resume_json": {{
    "name": "<姓名>",
    "title": "<目标职位>",
    "summary": "<自我评价，缺失信息用占位符>",
    "skills": ["<已有技术栈>", "..."],
    "experience": [
      {{
        "company": "<公司名>",
        "role": "<职位>",
        "period": "<时间>",
        "actions": ["<S+T+A+R 融合，缺失处用 [请填入...] >"]
      }}
    ],
    "education": {{"school": "...", "degree": "...", "period": "..."}}
  }}
}}

【联网搜索补充】：{web_search_context}
【目标岗位 JD】：{jd}
【原始简历】：{resume}

仅输出 JSON："""


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
    lines.append("- 每个项目经历融合 STAR 结构为精简 action 条目，补充分层技术细节。")
    lines.append("- 参考金牌案例中的量化模式，为关键指标标注'（估算）'或'（待确认指标）'。")
    lines.append(f"- 优化后简历长度：{len(revised_text)} 字符（原文 {len(original)} 字符）。")

    if thinking_text:
        lines.append("")
        lines.append(f"[模型思考链] {len(thinking_text)} 字符思维链已记录。")

    return "\n".join(lines)


# ── 主节点 ──────────────────────────────────────────────────────

def editor_node(state: AgentState):
    """
    v2.7 核心优化节点 —— 纯 JSON 输出 + 物理隔离

    输出 JSON 结构:
      - optimization_summary → 前端优化说明看板
      - clean_resume_json → 前端 A4 纸视口

    双模式: NORMAL (大厂级优化) / EXTREME_GAP (防幻觉骨架)
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
        mode_label = "防幻觉骨架模式 (EXTREME_GAP)"
        use_pro = False
        print(f"[editor] 触发防幻觉骨架模式！Prompt {len(prompt)} 字符")

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

        parsed = _parse_editor_json(response_text)
        if "error" in parsed:
            print(f"[editor] JSON 解析失败 ({parsed['error']})，回退原始文本")
            return {
                "revised_resume": response_text,
                "internal_monologue": f"[editor] 骨架模式 JSON 解析失败 ({parsed['error']})，回退为原始输出。",
                "optimization_summary": "",
                "clean_resume_json": {},
            }

        clean_json = parsed.get("clean_resume_json", {})
        opt_summary = parsed.get("optimization_summary", "")
        revised_text = _json_to_text(clean_json)
        placeholder_count = revised_text.count("[请")

        print(f"[editor] 骨架模式完成, 输出 {len(revised_text)} 字符, 占位符 {placeholder_count} 处")

        monologue = (
            f"[editor 防幻觉骨架模式] EXTREME_GAP，已禁用大厂级动词升级和量化编造。\n"
            f"转为标准骨架搭建。输出 {len(revised_text)} 字符，{placeholder_count} 处占位符留白。\n"
            f"{opt_summary}"
        )

        return {
            "revised_resume": revised_text,
            "internal_monologue": monologue,
            "optimization_summary": opt_summary,
            "clean_resume_json": clean_json,
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

    print(f"[editor] 调用 {model_label} (v2.7 纯 JSON 模式)...")
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

    # ── 解析 JSON 响应 ──
    parsed = _parse_editor_json(response_text)

    if "error" in parsed:
        print(f"[editor] JSON 解析失败 ({parsed['error']})，回退原始文本为 revised_resume")
        monologue = _build_critique(resume, response_text, thinking_text)
        return {
            "revised_resume": response_text,
            "internal_monologue": monologue,
            "optimization_summary": "",
            "clean_resume_json": {},
        }

    clean_json = parsed.get("clean_resume_json", {})
    opt_summary = parsed.get("optimization_summary", "")

    # 将结构化 JSON 转为可读文本（供流式打字机展示）
    revised_text = _json_to_text(clean_json)

    # 构建内省
    monologue = _build_critique(resume, revised_text, thinking_text, opt_summary)

    exp_count = len(clean_json.get("experience", []))
    action_count = sum(len(exp.get("actions", [])) for exp in clean_json.get("experience", []))
    print(f"[editor] v2.7 JSON 优化完成: {exp_count} 段经历, {action_count} 条 action, "
          f"文本 {len(revised_text)} 字符, summary {len(opt_summary)} 字符")

    return {
        "revised_resume": revised_text,
        "internal_monologue": monologue,
        "optimization_summary": opt_summary,
        "clean_resume_json": clean_json,
    }
