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
    max_terms = 40
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
    max_cases = 12
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
    """从 LLM 响应中提取 <clean_resume>...</clean_resume> 内的纯净 Markdown，
    并通过 text_sanitizer 做最终清洗。"""
    from src.utils.text_sanitizer import sanitize_resume_text

    match = _CLEAN_RESUME_RE.search(response_text)
    if match:
        extracted = match.group(1).strip()
        return sanitize_resume_text(extracted, log_prefix="[editor]")
    # 回退: 如果没找到标签，走全文本清洗管道
    fallback = sanitize_resume_text(response_text, log_prefix="[editor]")
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
【铁律一】全量保留死命令 — 有内容的模块一个不删，空模块直接跳过
══════════════════════════════════════════════════════════
你必须全量保留原简历中每个【有实质内容】的模块及其含金量数据。包括但不限于：
  - 教育背景
  - 实习经历（对在校生/应届生，严禁将"实习经历"改称"工作经历"！）
  - 项目经历
  - 校园经历（社团、学生会、志愿者等）
  - 获奖情况
  - 技能特长

每个模块的量化数据（GPA、排名、奖项级别、项目成果数字）必须原样保留。

⚠️ 空模块跳过规则（与全量保留同等优先级）：
如果原始简历中某个模块【完全没有实质内容】——判断标准：正文为空、仅写"无"、"暂无"、"无相关经历"、"无获奖记录"等占位文本——则直接跳过该模块。不要输出 ## 模块标题，不要补"暂无"，不要补任何占位文本。HR 看到干净的简历比看到"暂无实习经历"更专业，空模块不是简历的必要组成部分。

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
【铁律六】技能特长深度结构化格式 —— 绝对禁止扁平标签
══════════════════════════════════════════════════════════

⛔ 绝对禁止的写法（违反此格式的输出将被物理拦截）:
  ❌ Java (熟练), Python (熟练), MySQL (熟悉)                   ← 扁平括号熟练度
  ❌ **编程语言:** Java, Python, Go, C++                        ← 纯名词罗列
  ❌ - 熟练掌握 Spring Boot、MyBatis、Redis                      ← 无粗体锚点的标签堆砌
  ❌ - **Java**: 熟练使用 Spring Boot 进行后端开发                 ← 粗体后直接冒号截断，无场景描述

✅ 唯一合法的技能模块格式 —— 必须严格复制以下 Markdown 结构:

### 核心技术栈

* **AI 与大模型工程**
  - 熟练掌握 **LangGraph / LangChain 框架**，熟悉 React、Plan-and-Execute 等设计范式，可独立完成复杂 Agent 状态机架构设计与实现。
  - 熟悉 **RAG 全链路设计与优化**，能够结合具体业务场景对召回效果、响应质量与向量库（ChromaDB）系统性能进行针对性优化。
  - 熟练使用 **Claude Code、OpenClaw** 等先进 Agent 辅助工具，了解其底层的代码理解、修改与任务拆解工程原理。

* **后端开发与数据工程**
  - 熟悉 **FastAPI / Spring Boot 等 Web 框架**，精通 RESTful API 设计与多线程异步编程，能够独立完成高性能接口开发。
  - 熟练使用 **MySQL、Redis 等数据库**，深入理解索引底层 B+ 树原理，具备高频访问场景下的数据建模与 SQL 慢查询治理能力。

* **开发运维与工程素养**
  - 熟练掌握 **Docker 容器化与服务编排**，能独立编写多阶段构建 Dockerfile，完成全栈分布式服务的反向代理与反向路由配置。
  - 熟练使用 **Git 进行版本控制**，深刻理解多人协同、Git Flow 分支管理机制，具备极强的代码规范与工业级工程化意识。

══════════════════════════════════════════════════════════
【格式死锁检查表】—— 你的输出必须逐条通过以下校验:
══════════════════════════════════════════════════════════

🔒 死锁 1 — 行首粗体关键词死锁:
   每个 `- ` 列表项的"第一个 Markdown 粗体块"（即第一对 ** 之间的文字）
   必须是一个具体的技术硬指标（4-10 个字），例如：
     ✅ **LangGraph / LangChain 框架**
     ✅ **MySQL、Redis 等数据库**
     ✅ **Docker 容器化与服务编排**
     ❌ **AI 与大模型工程** ← 太宽泛，这是大类名不是硬指标
     ❌ **熟练掌握 Java** ← 动词不要进入粗体
     ❌ **Java** ← 太短，需要有场景锚定词

🔒 死锁 2 — 能力边界与场景对齐死锁:
   粗体关键词后面的文字（逗号之后），必须立即展开为：
   - 工程落地场景（如：异步编程、流程编排、索引优化、容器化部署）
   - 可量化的技术边界（如：慢查询治理、性能调优、反向代理配置、数据建模）
   严禁输出纯教科书式概念解释（如"Java 是一种面向对象的编程语言"）。
   必须使用"能够/可独立完成/具备/深入理解/精通/熟悉"等能力锚定词。

🔒 死锁 3 — 层级结构死锁:
   一级大类标题: * **大类名称**（单星号 + 粗体，2-4 个大类）
   二级技能条目:   - <动词> **<4-10字硬指标>**<逗号><工程场景描述>
   缩进严格为 2 空格（即 `  - `），大类与条目之间的缩进层级必须清晰可辨。

🔒 死锁 4 — 禁止残余污染:
   - 大类名称中禁止出现括号熟练度
   - 技能描述中禁止出现 (熟练)、(精通)、(熟悉) 等括号标注
   - 每个大类下 2-4 条技能描述，不得少于 2 条也不得多于 4 条
   - 全模块 3-4 个大类，不得少于 3 个也不得多于 4 个

分层原则:
- 将简历中所有技能归纳为 3-4 个与目标 JD 强对齐的专业大类
- 每个大类的命名必须体现工程深度，禁用"编程语言""开发工具"等浅层分类
- 每个技能词的描述必须与下方项目经历中的术语保持精确联动
- 剔除非核心竞争力标签：Git 基础操作、Office、Photoshop、打字速度等

══════════════════════════════════════════════════════════
【铁律七】技术深度 + 量化 + 降维打击叙事
══════════════════════════════════════════════════════════
基于已有技术栈合理推导技术细节。每条要点必须具备:
  - 技术原理（用了什么 + 怎么用的 + 为什么）
  - 量化成果（性能提升 % / 延迟变化 / 成本降低等，直接写数字）

术语联动铁律:
  - 项目经历中使用的技术词汇必须与【核心技术栈】分层标签高度一致
  - 提到 FastAPI 时必须体现"异步并发"，提到 Docker 时必须体现"工程交付/部署"
  - 禁用纯粹的工具罗列，转为工程化叙事：
    ✅ "基于 LangGraph 拓扑编排实现多 Agent 协作链路，通过异步并发优化吞吐至 120 QPS"
    ❌ "使用了 LangGraph、FastAPI、Docker"

降维打击叙事词库（优先使用）:
  - 设计模式、链路编排、性能基准（Benchmark）、异步并发管线
  - 推理部署、Token 预算压缩、语义检索召回率、RAG 证据链
  - 微创手术式修改、拓扑收敛、状态机持久化

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

══════════════════════════════════════════════════════════
【铁律十】绝对输出禁语令 —— 违反此律者输出将被物理截断
══════════════════════════════════════════════════════════
你的 <clean_resume> 标签内是直接投递给 HR 的正式文档。以下内容被【绝对禁止】出现在输出中的任何位置（包括标签内外）：

⛔ 禁止寒暄与问候:
   - ❌ "好的"、"收到"、"明白了"、"没问题"
   - ❌ "以下是优化后的简历"、"已经为您生成"、"请查收"
   - ❌ "希望这份简历能帮到您"、"祝您求职顺利"、"期待您的反馈"
   - ❌ "如果有任何问题"、"如需进一步修改"、"随时联系"
   - ❌ "OK"、"Sure"、"Here is"、"Below is"、"I hope"、"Good luck"

⛔ 禁止 Markdown 代码块包裹:
   - ❌ 严禁在 <clean_resume> 内外输出 ``` 或 ```markdown 或 ```md 标记
   - 你输出的内容就是最终文档本身，不是"代码示例"
   - 简历是 Markdown 正文，不需要用代码块包裹

⛔ 禁止角色扮演与元评论:
   - ❌ "作为资深猎头"、"根据我的经验"、"我注意到"
   - ❌ "你的简历存在以下问题"、"建议你"、"你应该"
   - ❌ 任何对简历内容的评价、分析、或修改说明
   - 标签外的分析思考会被物理丢弃，不要浪费 Token

⛔ 禁止署名与签名:
   - ❌ 不要在你的输出末尾署名或写结语
   - 简历以最后一个模块的最后一条要点为终点，之后不要有任何额外文字

⛔ 标签格式死锁:
   - 必须使用 <clean_resume> 和 </clean_resume>，不允许写成 <clean resume> 或其他变体
   - 标签必须独立成行（前后可以有空白字符，但不应与其他内容挤在同一行）

违反以上任何一条，你的输出将在物理层面被截断清洗，导致简历不完整。
请把你所有的"服务意识"收敛为唯一一种表达：写出一份质量极高的纯净 Markdown 简历正文。

══════════════════════════════════════════════════════════
【铁律十一】RAG 动态检索上下文冷酷审计与拒绝机制
══════════════════════════════════════════════════════════
以下是系统从 JD 中提取的 15 个核心技术锚点，代表目标岗位的真实技术要求。
你在撰写简历时必须遵守以下审计规则：

1. 【技术新增审计】任何你想添加到简历中的新技术栈/框架/工具/中间件，
   必须满足以下两个条件之一：
   (a) 该技术出现在下方的「JD 核心技术锚点清单」中，或
   (b) 该技术已存在于原始简历中

2. 【幻觉拦截】如果你打算使用的技术既不在锚点清单也不在原始简历中 →
   这是幻觉信号，立即放弃该技术，不得写入简历

3. 【技术预算约束】锚点清单是你的"技术预算上限"——你只能在此范围内
   做 STAR 技术深度的合理延伸。严禁因清单包含了某个技术，就在候选人
   根本没有相关经验的模块中凭空编造该技术的项目经历

4. 【编造熔断】若锚点清单要求的技术（如 K8s、多活架构）候选人完全不具备，
   宁可让对应模块留白或用占位符标记，也不允许编造虚假经历去匹配

5. 【正向引导】锚点清单同时是技术深度的"安全区"——清单内的技术词
   可以放心做深度展开（原理推导/性能调优/工程落地），因为这些
   技术已经过 JD 对齐审计

JD 核心技术锚点清单:
{jd_keywords}

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
【铁律五】全量保留 + 空模块跳过
══════════════════════════════════════════════════════════
原简历中每个【有实质内容】的模块必须保留。如果某模块完全没有实质内容（正文为空或仅"无/暂无"字样），直接跳过该模块，不输出标题和占位文本。

══════════════════════════════════════════════════════════
【铁律六】绝对输出禁语令
══════════════════════════════════════════════════════════
绝对禁止输出：寒暄问候（"好的"、"以下是"、"希望这份简历能帮到您"）、
Markdown 代码块包裹（``` 标记）、角色扮演评论、署名结语、祝福语。
<clean_resume> 标签内必须是可直接投递的纯净简历正文。

══════════════════════════════════════════════════════════
【铁律七】RAG 动态检索上下文冷酷审计 — 防幻觉熔断
══════════════════════════════════════════════════════════
以下是系统从 JD 中提取的 15 个核心技术锚点。在骨架搭建模式下：
1. 任何新增技术必须出现在锚点清单中或已存在于原始简历 — 否则是幻觉，禁止写入
2. 若锚点要求的技术候选人完全不具备 → 用方括号占位符留白，严禁编造
3. 锚点清单是你的"技术安全区"——仅在清单范围内做合理深度延伸

JD 核心技术锚点清单:
{jd_keywords}

【术语注入库（匹配平替词汇，仅用于启发，严禁照抄）】:
{term_injection}

【金牌案例（深度利用其技术方案和量化数字作为参考基线）】:
{golden_cases}

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
    # ── v5.9 None 安全兜底：state.get() 键存在值=None 时默认值失效，改用 or ──
    resume = state.get("resume") or ""
    jd = state.get("jd") or ""
    rag_context = state.get("rag_context") or ""
    tool_outputs = state.get("tool_outputs") or []
    difficulty_flag = state.get("difficulty_flag") or ""
    jd_keywords = state.get("jd_keywords") or "（未提取 JD 锚点，请基于 JD 原文自行判断核心技术栈）"
    retriever_metrics = state.get("retriever_metrics") or ""

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

    # ── RAG 上下文预处理（正常模式 + EXTREME_GAP 模式共用）──
    rag_items = _split_rag_items(rag_context)
    term_injection = _build_term_injection(rag_items)
    golden_cases = _build_golden_cases(rag_items)

    if not rag_context.strip():
        golden_cases = "（未检索到相关金牌案例，请基于通用大厂标准进行优化）"
        term_injection = "（暂无专属术语库，请基于通用大厂标准进行动词升级）"

    # ── 防幻觉骨架模式 ──
    if difficulty_flag == "EXTREME_GAP":
        prompt = EDITOR_EXTREME_GAP_PROMPT.format(
            term_injection=term_injection,
            golden_cases=golden_cases,
            jd_keywords=jd_keywords,
            web_search_context=web_search_context,
            jd=jd,
            resume=resume,
        )
        print(f"[editor] 触发防幻觉骨架模式 (EXTREME_GAP), Prompt {len(prompt)} 字符, "
              f"RAG {len(rag_items)} 条")

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
            f"[editor 防幻觉骨架模式] EXTREME_GAP，RAG 增强已注入 ({len(rag_items)} 条参考)。\n"
            f"输出 {len(clean_md)} 字符，{placeholder_count} 处占位符留白。\n"
            f"JD 锚点审计: {jd_keywords[:300]}\n"
            f"[Editor Metrics v6.0] mode=EXTREME_GAP | "
            f"rag_items={len(rag_items)} | "
            f"output_chars={len(clean_md)} | "
            f"placeholders={placeholder_count} | "
            f"retriever_metrics={retriever_metrics}"
        )

        return {
            "revised_resume": clean_md,
            "internal_monologue": monologue,
            "optimization_summary": "",
            "clean_resume_json": {},
        }

    # ── 正常模式 ──
    prompt = EDITOR_SYSTEM_PROMPT.format(
        term_injection=term_injection,
        golden_cases=golden_cases,
        jd_keywords=jd_keywords,
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
    # ── 遥测指标注入 ──
    rag_keyword_count = len([k for k in jd_keywords.split("\n") if k.strip().startswith(("1","2","3","4","5","6","7","8","9","10","11","12","13","14","15"))])
    if rag_keyword_count == 0:
        rag_keyword_count = 15  # fallback 估算
    editor_metrics = (
        f"[Editor Metrics v6.0] mode=NORMAL | "
        f"model={model_label} | "
        f"rag_items={len(rag_items)} | "
        f"jd_anchors={rag_keyword_count} | "
        f"thinking_chars={len(thinking_text)} | "
        f"output_chars={len(clean_md)} | "
        f"h2_modules={h2_count} | "
        f"pipe_separators={pipe_count} | "
        f"retriever={retriever_metrics}"
    )
    monologue = monologue + "\n" + editor_metrics

    print(f"[editor] v3.0 Markdown 优化完成: {len(clean_md)} 字符, {h2_count} 个 ## 模块, "
          f"{pipe_count} 处 | 分隔符, summary {len(optimization_summary)} 字符")
    print(f"[editor] {editor_metrics}")

    return {
        "revised_resume": clean_md,
        "internal_monologue": monologue,
        "optimization_summary": optimization_summary,
        "clean_resume_json": {},
    }
