"""
Agent 模式 LangGraph 有向图 — ReAct 闭环大脑点火

拓扑结构:
    START
      │
      ▼
  agent_brain ──(has tool_calls?)──▶ tools_executor ──┐
      │                                                │
      │ (no tool_calls)                                │
      ▼                                                │
     END ◀─────────────────────────────────────────────┘

核心闭环:
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
from langgraph.checkpoint.memory import MemorySaver

# 导入步骤1中通过20项压测的完全体武器库
from src.tools.agent_tools import AGENT_TOOLS


# ==========================================
# 📊 1. 定义有向图的全局状态机（AgentState）
# ==========================================

class AgentState(TypedDict):
    # add_messages 是 LangGraph 的核心内聚算法，用于自动将新产生的
    # Thought/Observation 追加到历史对话树中
    messages: Annotated[List[BaseMessage], add_messages]

    # 工业级状态并网：锁定当前会话操作的原始简历底座，作为只读上下文，防止模型跑飞
    current_resume_markdown: str


# ==========================================
# 🧠 2. 编写 Agent 大脑节点逻辑
# ==========================================

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
        "立刻调用 `save_user_profile_tool` 冰冻特征。"
    ))

    # 组装当前的完整输入链
    full_messages = [system_prompt] + messages

    # v4.1 双模供给器：云端 DeepSeek 主线 (timeout=30s) + 自动降级本地 gemma3:1b
    from src.utils.llm import get_resilient_llm
    llm = get_resilient_llm(temperature=0.3, max_tokens=8192)

    # 核心动作：云端绑工具链，本地备胎纯文本模式（gemma3:1b 不支持 Function Calling）
    if getattr(llm, "_is_fallback", False):
        llm_with_tools = llm  # 本地备胎：禁止 bind_tools，纯文本轻装上阵
    else:
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

# 注册节点：大脑节点 + 官方的高级 ToolNode 节点
# （自动消费并执行大模型吐出的 Function Calling JSON）
workflow.add_node("agent_brain", call_agent_brain)
workflow.add_node("tools_executor", ToolNode(AGENT_TOOLS))

# 连线：指定 START 起点直达大脑
workflow.add_edge(START, "agent_brain")


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

# ── v4.1 MemorySaver 状态机持久化：强制注入 Checkpointer 内存持久化锁 ──
memory = MemorySaver()
agent_compiled_graph = workflow.compile(checkpointer=memory)
