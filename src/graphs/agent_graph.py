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

    # 初始化大模型并绑定武器库协议（Function Calling 关键动作）
    llm = ChatOpenAI(
        model=os.getenv("MODEL_FLASH", "deepseek-v4-flash"),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0.3,  # 低温确保工具调用的高度确定性
    )

    # 核心动作：将大模型与强约束工具链通过协议绑定
    llm_with_tools = llm.bind_tools(AGENT_TOOLS)

    # 触发模型推理
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

# 编译点火：产出最终的生产级可运行图单例
agent_compiled_graph = workflow.compile()
