"""
v2.0 Editor 节点 —— 粗/中粒度完整重写 + RAG 术语无缝灌注

融合了原 v1.0 refiner.py 的全部 Prompt 工程资产：
- 术语注入库：从 RAG 上下文中自动提取短术语，构建动词升级平替词汇表
- 金牌案例融合：带编号的完整案例段落，含深度利用指令
- DeepSeek-V4-Pro Thinking 思维链提取
- 结构化毒舌批评 (internal_monologue)

在 v2.0 管线中作为首道优化关卡：retriever → editor → evaluator ⇄ polisher
"""

import os
import re
from src.state import AgentState
from src.utils.llm import get_flash_client, get_pro_client

# ── RAG 上下文拆分 ──────────────────────────────────────────────

_HEADER_LINE = re.compile(r"^\s*\[.+?\]\s*(案例内容|：)", re.IGNORECASE)


def _split_rag_items(rag_context: str) -> list[str]:
    """将 RAG 上下文按双换行拆分为独立条目，过滤空项和纯标签行"""
    if not rag_context or not rag_context.strip():
        return []

    raw_items = rag_context.split("\n\n")
    items: list[str] = []
    for item in raw_items:
        item = item.strip()
        if not item:
            continue
        # 去掉 [tag] 案例内容： 这个头
        item = _HEADER_LINE.sub("", item, count=1).strip()
        if item and len(item) >= 6:
            items.append(item)
    return items


def _build_term_injection(items: list[str]) -> str:
    """
    从 RAG 条目中提取短文本作为「术语注入库」。
    短条目（<150 字符）视为可平替的动词/术语；
    长条目也提取首句作为术语参考。
    """
    terms: list[str] = []
    seen: set[str] = set()

    for item in items:
        # 短条目直接作为术语
        if len(item) < 150:
            clean = item.strip().rstrip("。，；,.;")
            if clean and len(clean) >= 4 and clean not in seen:
                terms.append(clean)
                seen.add(clean)
        else:
            # 长条目取首句（以 。或 ； 或 \n 为界）
            first_sentence = re.split(r"[。；\n]", item, maxsplit=1)[0].strip()
            if first_sentence and len(first_sentence) >= 8 and first_sentence not in seen:
                terms.append(first_sentence)
                seen.add(first_sentence)

    if not terms:
        return "（暂无专属术语库，请基于通用大厂标准进行动词升级）"

    # 去重后限制 25 条
    max_terms = 25
    if len(terms) > max_terms:
        terms = terms[:max_terms]

    lines = [f"  {i}. {t}" for i, t in enumerate(terms, 1)]
    return "\n".join(lines)


def _build_golden_cases(items: list[str]) -> str:
    """将 RAG 条目格式化为带编号的金牌案例库"""
    if not items:
        return "（暂无金牌案例素材，请基于通用大厂标准进行技术深度延伸）"

    # 优先取长条目作为案例，不足则用全部
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
    """从 DeepSeek Pro 响应中提取 thinking 思维链"""
    if hasattr(response, "additional_kwargs") and response.additional_kwargs:
        thinking = response.additional_kwargs.get("thinking", "")
        if thinking:
            return thinking
    if hasattr(response, "response_metadata") and response.response_metadata:
        thinking = response.response_metadata.get("thinking", "")
        if thinking:
            return thinking
    return ""


# ── 融合版 System Prompt ────────────────────────────────────────

EDITOR_SYSTEM_PROMPT = """你是一位拥有 10 年经验的大厂（字节跳动/阿里巴巴/腾讯）资深技术架构师，同时也是一位年薪百万的首席猎头。你的眼光极其犀利，能从平淡的简历中一眼看穿候选人背后隐藏的技术深度。

你的任务是对比候选人的【原始简历】和【目标岗位 JD】，利用【术语注入库】和【金牌案例素材】中的话术、技术方案和量化指标，对原始简历进行"整容级"重构。

你必须严格遵守以下规则：

══════════════════════════════════
【规则一】STAR 法则强制重构
══════════════════════════════════
每个项目经历必须按照 Situation（情景）、Task（任务）、Action（行动）、Result（结果）的结构重新组织。各部分必须包含：
- 情景：量化痛点或业务背景（如"日均 50 万次请求下"、"千万级数据表"）
- 任务：明确的技术目标（如"将 P99 延迟从 2s 降至 200ms 以内"）
- 行动：具体技术方案，至少展开 2-3 层技术细节（用了什么 → 怎么用的 → 为什么这么用 → 踩了什么坑）
- 结果：量化数据支撑（即使标注"估算"也算通过）

══════════════════════════════════
【规则二】动词升级 —— 术语平替
══════════════════════════════════
严禁使用以下平庸动词——"负责、参与、做了、写了、用过、维护、处理、开发"。
必须替换为大厂级动词——"主导、构建、攻克、重塑、逆向、渗透、压榨、调优、消除、攻克、工程化、标准化、精细化"。

你必须深度参考下方【术语注入库】中的词汇，将它们作为动词平替的素材库。
术语库中的每一行都是一个可选的高价值术语/动词/技术名词，请将其合理融入简历：
{term_injection}

══════════════════════════════════
【规则三】技术深度挖掘
══════════════════════════════════
基于候选人已有的项目经历，深入挖掘其背后的技术挑战和架构决策。例如：
- "负责接口开发" → "主导设计了基于 FastAPI 异步非阻塞模型的高并发 RESTful API 服务，通过依赖注入拦截器实现了统一的认证鉴权与限流熔断机制"
- "维护数据库" → "针对千万级数据表设计了 B-Tree 联合索引策略，通过 EXPLAIN 分析消除慢查询瓶颈，引入 Redis 多级缓存实现热点数据毫秒级响应"
- "用了缓存" → "针对缓存穿透/击穿/雪崩三类经典问题，分别采用布隆过滤器前置拦截、互斥锁（SETNX）防止热点 key 失效击穿、以及 TTL 随机抖动避免集中过期"

禁止只写表面行为——必须写出技术选型的考量、踩过的坑、以及为什么选择这个方案而不是那个。

══════════════════════════════════
【规则四】指标量化
══════════════════════════════════
所有成果必须有可量化的数据支撑。如果原始简历没有具体数据，你必须基于技术场景进行合理推测，但必须标注为"（估算）"或"（待确认指标）"。例如：
- QPS 提升 40%（估算）
- 响应时间从 2s 降至 200ms（待确认指标）
- 支撑日均 50 万次并发请求（估算）
- 内存占用降低 35%（待确认指标）

══════════════════════════════════
【规则五】金牌案例素材深度利用
══════════════════════════════════
你必须深度参考下方【金牌案例素材】中的具体技术方案和量化数字：
- 将素材中的具体量化数字（如"延迟从 12s 降至 0.8s"、"QPS 提升 40%"）应用到候选人相应的技术描述中
- 将素材中的技术方案（如"异步非阻塞模型"、"B-Tree 联合索引"、"布隆过滤器"）深度融入候选人的同类项目经历
- 禁止只看关键词不看上下文：素材是完整的技术段落，不是孤立的词汇列表
- 每条案例都是一份完整的技术方案，要理解其中的技术逻辑链，而非生硬照搬

{golden_cases}

══════════════════════════════════
【规则六】严禁编造
══════════════════════════════════
绝对不允许编造候选人不具备的技术栈或未参与的项目。但允许基于已有经验进行合理的技术深度延伸。

══════════════════════════════════
【规则七】输出格式
══════════════════════════════════
直接输出优化后的完整简历内容，包含：个人信息、个人优势/自我评价（3-5条，每条用加粗关键词开头）、工作经历（含 STAR 项目描述）、教育背景。

──────────────────────────────

【联网搜索补充】以下是针对目标公司和最新技术栈从互联网检索到的实时信息（如企业文化、招聘偏好、新技术趋势等）。你必须将这些信息深度融入简历：
{web_search_context}

【目标岗位 JD】
{jd}

【原始简历】
{resume}

请开始优化，直接输出优化后的完整简历内容："""


# ── EXTREME_GAP 防幻觉骨架模式 Prompt ─────────────────────────────

EDITOR_EXTREME_GAP_PROMPT = """你是一位诚实的职业规划顾问。当前场景：候选人的原始简历与目标 JD 之间存在【极端差距】(EXTREME_GAP)。

核心约束：候选人的原始简历内容非常薄弱（可能只有几十个字的简单描述），与目标中厂 JD 差距巨大。

你必须遵守以下【铁律】：

══════════════════════════════════
【铁律一】严禁编造虚假项目经验
══════════════════════════════════
- 绝对不允许凭空编造"分布式系统"、"高并发"、"千万级吞吐"、"多活架构"等候选人显然不具备的经验
- 绝对不允许编造候选人不具备的技术栈
- 绝对不允许把一个"个人博客"包装成"企业级微服务平台"

══════════════════════════════════
【铁律二】转为【标准骨架搭建模式】
══════════════════════════════════
你的任务是帮候选人梳理一份【真实的、规范的中厂简历骨架】，而不是虚构一份完美的简历：
- 用 STAR 结构重新组织候选人已有的项目经历
- 将平庸动词升级为中等水平动词（如"实现/设计/构建/优化"，不必强求"主导/攻克/重塑"）
- 补充技术描述时只写到候选人实际能做的深度
- 对于无法填充的量化指标和技术细节，使用显眼的占位符留白

══════════════════════════════════
【铁律三】占位符规范
══════════════════════════════════
对于候选人简历中缺失的关键信息，使用以下占位符格式：
- 量化指标缺失: `[请在此处实事求是填入您的日均订单量]`
- 技术细节缺失: `[请描述您在此项目中使用的具体缓存策略，如 Redis key 设计]`
- 业务场景缺失: `[请补充该项目的业务背景和数据规模]`
- 成果缺失: `[请填入可验证的项目成果，如性能提升百分比]`

占位符必须用【方括号】包裹，内容用中文写明需要填入什么。

══════════════════════════════════
【铁律四】保留真实可用的基础优化
══════════════════════════════════
虽然不能编造，但你仍然应该：
- 帮助候选人规范简历格式和 STAR 结构
- 将技术描述写得更加清晰、专业
- 基于候选人已有知识进行合理的深度延伸（如已知 Python，可以合理推断了解 FastAPI 基础）
- 补充行业通用的基础技术实践建议（如 Git 使用、单元测试、代码规范）

【联网搜索补充】:
{web_search_context}

【目标岗位 JD】:
{jd}

【原始简历】:
{resume}

请直接输出骨架优化后的完整简历（包含占位符）："""


# ── 毒舌批评 ────────────────────────────────────────────────────

def _build_critique(original: str, revised: str, thinking_text: str = "") -> str:
    lines = [
        "[毒舌批评] 原简历存在以下 3 个核心缺陷：",
        "1. 动词平庸——大量使用'负责/参与/做了'，缺乏技术主导感和工程影响力。",
        "2. 缺乏量化——所有成果均为定性描述，无法让面试官评估实际贡献量级。",
        "3. 技术深度不足——只描述了表面行为，未体现架构决策、性能优化、异常处理等技术深水区。",
        "",
        "[本次修改侧重点]",
        "- 将所有平庸动词替换为术语注入库中的大厂级词汇（主导/构建/攻克）。",
        "- 为每个项目经历注入 STAR 结构，并补充分层技术细节。",
        "- 参考金牌案例中的量化模式，为关键指标标注'（估算）'或'（待确认指标）'供候选人核对。",
        f"- 优化后简历长度：{len(revised)} 字符（原文 {len(original)} 字符）。",
    ]

    if thinking_text:
        lines.append("")
        lines.append(f"[模型思考链] {len(thinking_text)} 字符思维链已记录，可用于审计优化决策。")

    return "\n".join(lines)


# ── 主节点 ──────────────────────────────────────────────────────

def editor_node(state: AgentState):
    """
    v2.1 核心优化节点 —— 双模式切换

    正常模式: 大厂级动词升级 + STAR 重构 + 金牌案例 + 量化指标
    防幻觉骨架模式 (EXTREME_GAP): 规范结构 + 占位符留白 + 禁止编造

    输入：resume, jd, rag_context, tool_outputs, difficulty_flag
    输出：revised_resume, internal_monologue
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
        }

    # ── 构建联网搜索上下文 ──
    if tool_outputs:
        web_search_context = "\n\n".join(tool_outputs)
    else:
        web_search_context = "（未启用联网搜索，可设置 TAVILY_API_KEY 获取实时企业信息）"

    # ── 防幻觉骨架模式：跳过 RAG 注入，直接使用 EXTREME_GAP 约束 Prompt ──
    if difficulty_flag == "EXTREME_GAP":
        prompt = EDITOR_EXTREME_GAP_PROMPT.format(
            web_search_context=web_search_context,
            jd=jd,
            resume=resume,
        )
        mode_label = "防幻觉骨架模式 (EXTREME_GAP)"
        use_pro = False  # 骨架模式用 Flash 即可

        print(f"[editor] 触发防幻觉骨架模式！")
        print(f"[editor] Prompt 长度: {len(prompt)} 字符")

        try:
            llm = get_flash_client()
            response = llm.invoke(prompt)
            revised = response.content if hasattr(response, "content") else str(response)
            revised = revised.strip()

            placeholder_count = revised.count("[请")
            print(f"[editor] 骨架模式完成，输出 {len(revised)} 字符，占位符 {placeholder_count} 处")

            monologue = (
                f"[editor 防幻觉骨架模式] 检测到 EXTREME_GAP，原始简历与 JD 差距过大。\n"
                f"已禁用大厂级动词升级和量化指标编造，转为标准骨架搭建。\n"
                f"输出 {len(revised)} 字符，包含 {placeholder_count} 处占位符留白。\n"
                f"候选人需自行填充占位符中的真实数据。"
            )

            return {
                "revised_resume": revised,
                "internal_monologue": monologue,
            }

        except Exception as e:
            print(f"[editor] 骨架模式失败: {type(e).__name__}: {e}")
            return {
                "revised_resume": resume,
                "internal_monologue": f"[editor] 骨架模式异常 ({type(e).__name__})，已回退为原始简历。",
            }

    # ── 正常模式：RAG 双通道注入 + 大厂级优化 ──
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

    print(f"[editor] 正在调用 {model_label} (正常模式)...")
    print(f"[editor] Prompt 长度: {len(prompt)} 字符")
    print(f"[editor] RAG 条目: {len(rag_items)} 条 -> 术语 {term_injection.count(chr(10)) + 1 if term_injection else 0} 条, 案例 {golden_cases.count('案例')} 条")
    print(f"[editor] 联网搜索: {len(web_search_context)} 字符")

    try:
        llm = get_pro_client() if use_pro else get_flash_client()
        response = llm.invoke(prompt)

        thinking_text = _extract_thinking(response)
        revised = response.content if hasattr(response, "content") else str(response)
        revised = revised.strip()

    except Exception as e:
        print(f"[editor] 模型调用失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {
            "revised_resume": resume,
            "internal_monologue": f"[editor] 优化失败 ({type(e).__name__})，已回退为原始简历。",
        }

    # 输出 thinking（如果有）
    if thinking_text:
        print(f"[editor] 模型思考链 ({len(thinking_text)} 字符):")
        print("-" * 40)
        print(thinking_text[:1500])
        print("-" * 40)

    monologue = _build_critique(resume, revised, thinking_text)

    print(f"[editor] 优化完成，输出 {len(revised)} 字符")
    return {
        "revised_resume": revised,
        "internal_monologue": monologue,
    }
