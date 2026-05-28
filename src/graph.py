"""
v2.0-alpha LangGraph 多智能体工作流

图结构:
    retriever
       │
       ▼
    [条件: 是否需要联网搜索?]
       │              │
    tavily_search    editor
       │              │
       └──────┬───────┘
              ▼
          evaluator  ←────────────────┐
              │                       │
       [条件: score<70 & iter<3?]     │
         │              │             │
      polisher      (放行→END)        │
         │                            │
         └────────────────────────────┘
"""

import os
from langgraph.graph import StateGraph, END
from src.state import AgentState
from src.nodes.retriever import retriever_node
from src.nodes.editor import editor_node
from src.nodes.evaluator import evaluator_node
from src.nodes.polisher import polisher_node
from src.tools.search import tavily_search_node, _detect_company, _extract_tech_keywords

_web_search_always = os.getenv("FORCE_WEB_SEARCH", "false").lower() == "true"

MAX_ITERATIONS = 3
PASS_THRESHOLD = 70


def _needs_web_search(state: AgentState) -> bool:
    if _web_search_always:
        return True

    jd = state.get("jd", "")
    rag_context = state.get("rag_context", "")

    if not rag_context or len(rag_context) < 80:
        return True

    company = _detect_company(jd)
    new_tech = _extract_tech_keywords(jd)

    if company:
        return True

    if new_tech:
        return True

    return False


def tools_condition(state: AgentState) -> str:
    if _needs_web_search(state):
        print("[graph] 本地 RAG 不足以覆盖 JD 中的公司背景或新技术 — 触发联网搜索")
        return "tavily_search"
    else:
        print("[graph] 本地 RAG 已充分覆盖，跳过联网搜索 — 直接进入优化")
        return "editor"


def eval_condition(state: AgentState) -> str:
    """Evaluator 之后的条件路由：通过还是打回重改？"""
    score = state.get("score", 0)
    iteration = state.get("iteration_count", 0)

    if score >= PASS_THRESHOLD:
        print(f"[graph] 评分 {score} ≥ {PASS_THRESHOLD}，通过！放行导出。")
        return END
    elif iteration < MAX_ITERATIONS:
        print(f"[graph] 评分 {score} < {PASS_THRESHOLD}，第 {iteration + 1}/{MAX_ITERATIONS} 轮 → 打回 Polisher 精修")
        return "polisher"
    else:
        print(f"[graph] 已迭代 {iteration} 轮（最大 {MAX_ITERATIONS}），评分 {score}，强制放行。")
        return END


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("retriever", retriever_node)
    workflow.add_node("tavily_search", tavily_search_node)
    workflow.add_node("editor", editor_node)
    workflow.add_node("evaluator", evaluator_node)
    workflow.add_node("polisher", polisher_node)

    workflow.set_entry_point("retriever")

    # retriever → 条件分支
    workflow.add_conditional_edges(
        "retriever",
        tools_condition,
        {
            "tavily_search": "tavily_search",
            "editor": "editor",
        },
    )

    workflow.add_edge("tavily_search", "editor")

    # editor → evaluator（新增）
    workflow.add_edge("editor", "evaluator")

    # evaluator → 条件分支（通过放行 / 打回重改）
    workflow.add_conditional_edges(
        "evaluator",
        eval_condition,
        {
            "polisher": "polisher",
            END: END,
        },
    )

    # polisher → evaluator（闭环：精修后重新评分）
    workflow.add_edge("polisher", "evaluator")

    return workflow.compile()


_graph_app = None


def get_graph():
    global _graph_app
    if _graph_app is None:
        _graph_app = build_graph()
    return _graph_app


def run_pipeline(resume: str, jd: str) -> AgentState:
    app = get_graph()
    initial: AgentState = {
        "resume": resume,
        "jd": jd,
        "rag_context": "",
        "revised_resume": "",
        "internal_monologue": "",
        "tool_outputs": [],
        "score": 0,
        "evaluation_feedback": "",
        "iteration_count": 0,
    }
    result = app.invoke(initial)
    return result


def run_pipeline_stream(resume: str, jd: str):
    app = get_graph()
    initial: AgentState = {
        "resume": resume,
        "jd": jd,
        "rag_context": "",
        "revised_resume": "",
        "internal_monologue": "",
        "tool_outputs": [],
        "score": 0,
        "evaluation_feedback": "",
        "iteration_count": 0,
    }

    final = None
    for output in app.stream(initial, stream_mode="values"):
        final = output
    return final
