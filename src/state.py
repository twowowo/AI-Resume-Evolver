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
    # v2.4 API 层：维度分数持久化
    pre_eval_dimensions: dict  # pre_evaluator 返回的维度细分 (jd_match/jd_tool_coverage/jd_depth_premium/star_completion/verb_quality)
    eval_dimensions: dict      # evaluator 返回的维度细分 (jd_match/star_completion/verb_quality)
    # v2.5 MockInterviewer 压力测试
    stress_test_questions: list  # interviewer 节点生成的压测面试题
    # v2.7 Editor JSON 输出 + 物理隔离
    optimization_summary: str   # editor 生成的简历优化说明综述（前端看板消费）
    clean_resume_json: dict     # editor 生成的结构化简历数据（前端 A4 纸消费）
