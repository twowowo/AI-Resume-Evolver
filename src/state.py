from typing import TypedDict, List, Annotated
import operator


class GraphState(TypedDict):
    """v1.0 简单管线状态（main.py / debug_run.py 使用）"""
    raw_resume: str
    target_jd: str
    gap_list: List[str]
    rich_context_list: List[str]
    rag_context: str
    refined_resume: str
    feedback: str
    revision_count: int


class AgentState(TypedDict):
    """v2.0 LangGraph 多智能体状态（run_app.py / graph.py 使用）"""
    resume: str
    jd: str
    rag_context: str
    revised_resume: str
    internal_monologue: str
    tool_outputs: Annotated[list, operator.add]
    # v2.0-alpha 新增：Evaluator + Polisher 闭环
    score: int
    evaluation_feedback: str
    iteration_count: int
