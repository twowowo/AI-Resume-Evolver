from typing import TypedDict, Annotated
import operator


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
    # v2.0-beta 分诊熔断
    difficulty_flag: str       # "" | "EXTREME_GAP" — 由 evaluator 在首轮评分 < 40 时设置
    node_status: str           # 当前节点的运行态描述，用于 UI 流式展示
