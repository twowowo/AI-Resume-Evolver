import os
from langgraph.graph import StateGraph, END
from src.state import AgentState
from src.nodes.retriever import retriever_node
from src.nodes.editor import editor_node
from src.tools.search import tavily_search_node, _detect_company, _extract_tech_keywords

_web_search_always = os.getenv("FORCE_WEB_SEARCH", "false").lower() == "true"


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


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("retriever", retriever_node)
    workflow.add_node("tavily_search", tavily_search_node)
    workflow.add_node("editor", editor_node)

    workflow.set_entry_point("retriever")

    workflow.add_conditional_edges(
        "retriever",
        tools_condition,
        {
            "tavily_search": "tavily_search",
            "editor": "editor",
        },
    )

    workflow.add_edge("tavily_search", "editor")

    workflow.add_edge("editor", END)

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
    }

    final = None
    for output in app.stream(initial, stream_mode="values"):
        final = output
    return final
