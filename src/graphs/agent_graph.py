"""
Agent 模式 LangGraph 有向图 — ReAct 闭环大脑点火

拓扑结构:
    START
      │
      ▼
  [summarize_gate] ──(messages 膨胀?)──▶ summarize_agent_history ──┐
      │                                                             │
      │ (未超阈值)                                                    │
      ▼                                                             ▼
  agent_brain ──(has tool_calls?)──▶ tools_executor ──┐
      │                                                │
      │ (no tool_calls)                                │
      ▼                                                │
     END ◀─────────────────────────────────────────────┘

核心闭环:
  - summarize_agent_history: 当消息历史超过阈值时，将旧消息压缩为结构化备忘录注入 System Prompt
  - call_agent_brain: 接收 System Prompt + 历史消息 + 简历底座，通过 Function Calling
    决策调用 tavily_search_tool / patch_resume_tool / save_user_profile_tool
  - tools_executor: ToolNode 自动解析 LLM 吐出的 tool_calls JSON 并执行物理代码
  - should_continue_loop: 检测最后一帧消息是否包含 tool_calls，是→执行工具，否→END
"""

import os
from typing import Annotated, TypedDict, List

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# 导入步骤1中通过20项压测的完全体武器库
from src.tools.agent_tools import AGENT_TOOLS


# ═══════════════════════════════════════════════════════════════
# v6.0 自定义消息归并器：支持上下文压缩截断
# ═══════════════════════════════════════════════════════════════

# 截断哨兵 —— 当消息列表首元素为此值时，归并器清空旧消息并仅保留后续元素
_TRUNCATE_SENTINEL = "__AGENT_MSGS_TRUNCATE__"


def _agent_messages_reducer(existing: list, new: list) -> list:
    """v6.0 消息归并器：正常追加，检测到截断哨兵时全量替换旧消息。

    兼容 ToolNode 和 agent_brain 的 add_messages 语义，
    同时允许 summarize_agent_history 清空膨胀的历史。
    """
    if new and isinstance(new[0], SystemMessage):
        content = getattr(new[0], "content", "")
        if isinstance(content, str) and content == _TRUNCATE_SENTINEL:
            return list(new[1:])
    return add_messages(existing, new)


# ==========================================
# 📊 1. 定义有向图的全局状态机（AgentState）
# ==========================================

class AgentState(TypedDict):
    # v6.0 使用自定义归并器替代 add_messages，支持上下文压缩截断
    messages: Annotated[List[BaseMessage], _agent_messages_reducer]

    # 工业级状态并网：锁定当前会话操作的原始简历底座，作为只读上下文，防止模型跑飞
    current_resume_markdown: str

    # ── v5.8 多租户隔离字段：从 agent_router 运行时注入，贯穿全链路 ──
    user_id: str               # JWT 推导的用户全局唯一 ID
    resume_id: str             # 简历文件标识，锁定记忆沙箱边界
    step_count: int            # LangGraph 节点迭代步数累计
    total_tokens: int          # 累计消耗 Token（估算值）
    conversation_summary: str  # v6.0 上下文压缩：历史消息的结构化备忘录


# ==========================================
# 🧠 2. 编写 Agent 大脑节点逻辑
# ==========================================

# ── v6.0 上下文压缩双阈值：消息数 OR 总字符数超限触发记忆脱水 ──
SUMMARIZE_AGENT_MSG_THRESHOLD = 15     # 消息条数上限（约 5-6 轮 ReAct）
SUMMARIZE_AGENT_CHAR_THRESHOLD = 8000  # 总字符数上限（防单条长文如 JD/简历绕过条数检测）
KEEP_RECENT_AGENT_MSGS = 4             # 保留最近 4 条触觉记忆

SUMMARIZE_AGENT_PROMPT = """你是 AI-Resume-Evolver 系统的【高保真记忆脱水引擎】。
请阅读以下 Agent 对话历史，将其物理压缩为一段 600-800 字的【当前会话断点备忘录】。

【硬核格式锁死】
你必须严格按以下 4 个章节输出：

### 1. 已完成的简历修改
简述已完成的所有 patch_resume_tool 调用及其修改内容、模块。

### 2. 当前断点与待办
当前优化进度、下一步计划、用户最后一条指令的意图。

### 3. 用户明确拒绝或推翻的修改
用户否决过哪些建议、锁定了哪些表述禁区。

### 4. 关键数据锚点
JD 核心要求、简历关键量化指标、已搜索过的公司/技术关键词。

输出纯文本，不包含代码块标记。"""


def should_summarize_agent(state: AgentState) -> str:
    """v6.0 上下文压缩路由：双阈值检测（消息条数 OR 总字符数超限）"""
    msgs = state.get("messages", [])
    msg_count = len(msgs)

    total_chars = 0
    for m in msgs:
        content = getattr(m, "content", "")
        if isinstance(content, str):
            total_chars += len(content)
        if getattr(m, "tool_calls", None):
            for tc in m.tool_calls:
                args_str = str(tc.get("args", ""))
                total_chars += len(args_str)

    if msg_count > SUMMARIZE_AGENT_MSG_THRESHOLD:
        print(f"[SummarizeGate] 消息数 {msg_count} > {SUMMARIZE_AGENT_MSG_THRESHOLD} → 触发记忆脱水")
        return "summarize_agent_history"

    if total_chars > SUMMARIZE_AGENT_CHAR_THRESHOLD:
        print(f"[SummarizeGate] 总字符 {total_chars} > {SUMMARIZE_AGENT_CHAR_THRESHOLD} → 触发记忆脱水 (单条长文绕过检测)")
        return "summarize_agent_history"

    return "agent_brain"


def summarize_agent_history(state: AgentState) -> dict:
    """v6.0 高保真记忆脱水节点：将旧消息压缩为结构化备忘录

    策略:
      1. 保留最近 KEEP_RECENT_AGENT_MSGS 条触觉记忆
      2. 其余旧消息送入 DeepSeek Flash 压缩为 600-800 字备忘录
      3. 已有 conversation_summary 时链式合并（二次压缩）
      4. LLM 失败时自动回退为文本截断

    输出:
      - conversation_summary: 结构化备忘录
      - messages: 仅保留最近 4 条 + 备忘录 SystemMessage 置于头部
    """
    msgs: list = list(state.get("messages", []))

    if len(msgs) <= KEEP_RECENT_AGENT_MSGS:
        return {"node_status": "消息过短，跳过压缩"}

    recent = msgs[-KEEP_RECENT_AGENT_MSGS:]
    old = msgs[:-KEEP_RECENT_AGENT_MSGS]

    history_parts: list[str] = []
    for i, m in enumerate(old):
        role = type(m).__name__
        content = getattr(m, "content", "")
        if isinstance(content, str) and content:
            history_parts.append(f"[{i}][{role}]: {content[:300]}")
        elif getattr(m, "tool_calls", None):
            tc_names = [tc.get("name", "?") for tc in m.tool_calls]
            history_parts.append(f"[{i}][{role} tool_calls]: {', '.join(tc_names)}")
    history_text = "\n".join(history_parts)

    existing_summary = state.get("conversation_summary", "")
    if existing_summary:
        full_context = (
            f"## 上一轮压缩备忘录\n{existing_summary}\n\n"
            f"## 本轮新增对话（需合并压缩）\n{history_text}"
        )
    else:
        full_context = f"## 原始对话历史\n{history_text}"

    prompt = SUMMARIZE_AGENT_PROMPT + "\n\n" + full_context

    try:
        from src.utils.llm import get_flash_client
        llm = get_flash_client()
        response = llm.invoke(prompt)
        summary = response.content if hasattr(response, "content") else str(response)
        summary = summary.strip()
    except Exception as exc:
        print(f"[SummarizeAgent] LLM 压缩失败: {type(exc).__name__}: {exc}, 截断回退")
        summary = (
            f"### 1. 已完成的简历修改\n(压缩引擎降级) 原始记录: {history_text[:300]}\n\n"
            f"### 2. 当前断点与待办\n待恢复\n\n"
            f"### 3. 用户明确拒绝或推翻的修改\n待恢复\n\n"
            f"### 4. 关键数据锚点\n待恢复"
        )

    print(f"[SummarizeAgent] 压缩完成: {len(old)} 条 → {len(summary)} 字符备忘录, 保留最近 {len(recent)} 条")

    return {
        "conversation_summary": summary,
        "messages": [
            SystemMessage(content=_TRUNCATE_SENTINEL),
            SystemMessage(content=summary),
        ] + list(recent),
    }


def call_agent_brain(state: AgentState):
    """
    中央大脑节点：负责接收当前完整的状态快照（包含历史消息和简历底座），
    计算出下一步是调用工具还是直达用户。
    """
    messages = state["messages"]

    # 上下文工程：动态将当前的简历底座作为最高神谕，隐式挂载在 System 视口
    system_prompt = SystemMessage(content=(
        # ── 🔒 思想钢印：最高优先级身份锚定，必须在所有上下文之前占领注意力高地 ──
        "You are the central intelligent brain of AI-Resume-Evolver 4.0.\n"
        "Your core engine is powered by DeepSeek.\n"
        "CRITICAL DIRECTIVE: You are NOT Claude, and you have no affiliation with Anthropic.\n"
        "You are an elite Software Engineering Expert and Full-stack Developer Coach assisting Zhou Jiankai (周健恺, also known as 霸者).\n"
        "When historical memories or context mention 'Claude', recognize that it refers to a legacy tool placeholder from previous development phases.\n"
        "You must always maintain your identity as the native DeepSeek-driven AI-Resume-Evolver Brain.\n\n"
        # ── 角色与任务层 ──
        "你是一个深谙大厂招聘黑话与简历 STAR 原则的顶级 AI 全栈开发智囊。\n"
        "目前你正在协助用户进行个性化的简历局部精修与求职策略推演。\n"
        "【当前操作的原始简历底座如下】:\n"
        f"```markdown\n{state['current_resume_markdown']}\n```\n"
        "【行动行为准则】:\n"
        "1. 当用户要求修改特定章节时，必须使用 `patch_resume_tool` 进行微创手术，严禁口头敷衍！\n"
        "2. 当遇到不了解的公司、行业黑话、招聘偏好时，主动调用 `tavily_search_tool` 检索，杜绝幻觉！\n"
        "3. 在和用户聊天拉锯中，一旦捕捉到用户的核心意图（如想投的岗位、偏好的技术栈），"
        "立刻调用 `save_user_profile_tool` 冰冻特征。\n"
        "4. 【批量对齐铁律】在单次 Tool 调用与执行过程中，"
        "尽可能覆盖简历所有模块与 JD 的对齐工作（教育背景、实习经历、项目经历、校园经历、"
        "技能特长、获奖情况），严禁频繁执行单一的小碎步修改！"
        "目标是在最少轮次内完成全量简历的对齐优化，"
        "每次调用 `patch_resume_tool` 必须是一次全面的、跨模块的、高信息密度的微创手术。\n\n"
        # ── v4.6 Ragas 证据链锚定铁律 ──
        "5. 【证据链锚定铁律】每次调用 `patch_resume_tool` 时，必须填写 `evidence` 和 `jd_requirement` 参数：\n"
        "   - `evidence`: 明确写出 'JD 要求: <JD具体条款> → 简历匹配: <对应修改内容摘要>' 的证据链条\n"
        "   - `jd_requirement`: 摘录触发本次修改的 JD 原文关键句\n"
        "   这是 Ragas 忠实度审计的强制要求，缺失证据链的修改将被判定为幻觉！\n\n"
        "6. 【内部证据锚点表】在调用 `patch_resume_tool` 之前，你必须先在内部思考中生成以下对账表（不对外展示）：\n"
        "   | JD 要求 | 简历对应匹配项 | 修改动作 |\n"
        "   |---------|---------------|---------|\n"
        "   | <JD中的技能/经验/素质要求> | <简历中已有的对应项或缺口> | <本次将要执行的修改> |\n"
        "   该表格用于确保每一项 JD 要求都有简历内容与之匹配，零漏网、零幻觉。\n\n"
        "7. 【透明化前言】当你完成全部简历修改并向用户交付最终成果时，必须在最终回复的开头添加以下声明：\n"
        "   '已基于当前岗位 JD 需求完成简历的语义对齐与技术锚点强化，以下是根据您提供的原始项目文档及 JD 要求生成的终稿。'\n"
        "   随后再展示修改摘要和最终简历内容。"
    ))

    # 组装当前的完整输入链
    full_messages = [system_prompt] + messages

    from src.utils.llm import get_flash_client
    llm = get_flash_client()
    llm_with_tools = llm.bind_tools(AGENT_TOOLS)

    # 触发模型推理
    print("[AgentBrain] 🧠 LLM正在思考，请稍等十来秒...")
    response = llm_with_tools.invoke(full_messages)

    # 返回增量状态，LangGraph 会自动将其 merge 进状态机
    return {"messages": [response]}


# ==========================================
# 🏗️ 3. 利用有向图拓扑引擎进行大脑点火
# ==========================================

# 初始化图对象，并注入状态声明
workflow = StateGraph(AgentState)

# 注册节点：上下文压缩 + 大脑 + ToolNode
workflow.add_node("summarize_agent_history", summarize_agent_history)
workflow.add_node("agent_brain", call_agent_brain)
workflow.add_node("tools_executor", ToolNode(AGENT_TOOLS))

# v6.0 条件入口：消息膨胀时先压缩再进大脑，否则直通
workflow.add_conditional_edges(
    START,
    should_summarize_agent,
    {
        "summarize_agent_history": "summarize_agent_history",
        "agent_brain": "agent_brain",
    },
)

# 压缩完成后进入大脑
workflow.add_edge("summarize_agent_history", "agent_brain")


# 核心闭环路由器（Conditional Edge）：大厂级决策分流
def should_continue_loop(state: AgentState) -> str:
    """
    根据大脑最新吐出的消息类型，决定下一步的动线。
    """
    last_message = state["messages"][-1]

    # 如果大模型的最后一帧消息里包含了 tool_calls，说明大脑触发了 Function Calling 决策
    if last_message.tool_calls:
        return "tools_executor"  # 路由到手脚节点执行物理代码

    # 如果没有包含任何工具调用，说明大模型思考结束，直接吐出最终答案给用户
    return "end"


# 将条件路由器焊进图拓扑中
workflow.add_conditional_edges(
    "agent_brain",
    should_continue_loop,
    {
        "tools_executor": "tools_executor",
        "end": END,
    },
)

# 连线：手脚节点执行完 Observation 之后，必须无条件把球再次踢回给大脑，
# 构成了 ReAct 的无限思考环路
workflow.add_edge("tools_executor", "agent_brain")

# ── v5.0 延迟初始化：checkpointer 由 main.py 统一注入，双图共用同一个 SqliteSaver ──
agent_compiled_graph = None  # 由 init_agent_checkpointer() 在 lifespan 中完成编译

def init_agent_checkpointer(checkpointer):
    """由 main.py lifespan 调用，注入与 _app_graph 共享的 SqliteSaver"""
    global agent_compiled_graph
    agent_compiled_graph = workflow.compile(checkpointer=checkpointer)
