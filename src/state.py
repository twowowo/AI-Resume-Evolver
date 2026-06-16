from typing import TypedDict, Annotated, List, Optional
import operator


class AgentState(TypedDict):
    """v4.2 LangGraph 多智能体状态 —— 三层漏斗隔离沙箱"""

    # ── v4.2 多租户隔离底座：动态 thread_id = f"{user_id}::{resume_id}" ──
    user_id: str               # 用户全局唯一 ID，贯穿全链路隔离
    resume_id: str             # 当前简历文件 Hash 标识，锁死记忆沙箱边界

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
    # 💬 v3.0 交互问答模式新增数据动线
    chat_history: list            # v4.5 降级为 plain list：由 summarize 节点物理瘦身替换
    user_supplement: str          # 用户在左侧输入框最新敲入的补充信息/修改意见
    session_id: str               # 会话 ID (UUID)，对应前端 thread_id
    turn_count: int               # 对话轮数累加计数器
    # ── v4.5 长对话熔断器：高保真记忆脱水缓存 ──
    conversation_summary: str     # summarize_history_node 产出的结构化断点备忘录
    visual_payload: dict          # v4.5 混合解耦载荷 (name/contact/skills[]/main_resume_markdown)
    # ── v4.3 Ragas 影子审计提效计数器 ──
    step_count: int            # LangGraph 节点迭代步数累计
    total_tokens: int          # 累计消耗 Token（估算值）
