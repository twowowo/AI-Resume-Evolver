"""
v3.0 LangGraph 双模有向图 —— 一键模式 + 交互模式拓扑缝合

一键模式 (ONE_CLICK):
    retriever
       │
       ▼
    [条件: 是否需要联网搜索?]
       │              │
    tavily_search    pre_evaluator
       │              │
       └──────┬───────┘
              ▼
       [pre_eval_routing: 模式标记, 无退出]
         │                │
    EXTREME_GAP        NORMAL
         │                │
      editor            editor
    (防幻觉骨架)      (正常精修)
         │                │
         ▼                ▼
      evaluator        evaluator
         │                │
         ▼                ▼
    [eval_condition]  [eval_condition]
         │                │
    interviewer       polisher ←──┘
         │                │
         ▼                ▼
        END          [eval_condition]
                     │           │
                evaluator    interviewer
                     │           │
                     ▼           ▼
                [loop...]      END

交互模式 (INTERACTIVE):
    entry_router (user_supplement 非空)
       │
       ▼
    chat_editor ──→ evaluator ──→ interviewer ──→ END
    (增量编辑)      (评分)        (压测)

    多轮回环发生跨 HTTP 请求层面，单次请求内一次走完三段式链路。
    用户可在 final 帧拿到评分后再次 POST /chat 发起新一轮修改。

  流程锁死: 所有简历必须经过 Editor → Evaluator → Interviewer 完整链路
  交互锁死: 所有补充意见必须经过 chat_editor → evaluator 评分闭环
"""

import os
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from src.state import AgentState
from src.nodes.retriever import retriever_node
from src.nodes.editor import editor_node
from src.nodes.evaluator import evaluator_node
from src.nodes.polisher import polisher_node
from src.nodes.pre_evaluator import pre_evaluator_node
from src.nodes.interviewer import interviewer_node
from src.nodes.chat_editor import chat_editor_node
from src.tools.search import tavily_search_node, _detect_company, _extract_tech_keywords

_web_search_always = os.getenv("FORCE_WEB_SEARCH", "false").lower() == "true"

MAX_ITERATIONS = 3
MAX_INTERACTIVE_TURNS = 5
PASS_THRESHOLD = 70
CRITICAL_LOW_THRESHOLD = 30


def _entry_router(state: AgentState) -> str:
    """
    v3.0 拓扑入口路由 —— 一键模式 vs 交互模式分流

    - user_supplement 非空 → 交互模式，直入 chat_editor 增量编辑
    - user_supplement 为空 → 一键模式，走 RAG 检索全链路
    """
    if state.get("user_supplement", "").strip():
        print("[graph] 检测到用户补充信息 -> 交互模式 (chat_editor 增量编辑)")
        return "chat_editor"
    print("[graph] 一键模式 -> RAG 检索全链路 (retriever)")
    return "retriever"


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
        print("[graph] 本地 RAG 不足以覆盖 JD 中的公司背景或新技术 -> 触发联网搜索")
        return "tavily_search"
    else:
        print("[graph] 本地 RAG 已充分覆盖，跳过联网搜索 -> 进入前置分诊")
        return "pre_evaluator"


def pre_eval_routing(state: AgentState) -> str:
    """
    v2.2 PreEvaluator 之后的路由 —— 仅做模式标记，禁止直接退出

    流程锁死规则：
    - PreEvaluator 只负责标记 difficulty_flag (EXTREME_GAP 或 NORMAL)
    - 路由无条件走向 editor, 绝不在此处返回 END
    - 所有简历必须经过至少一轮 Editor 优化
    - 最终评审权交还给后置 evaluator 节点 (eval_condition)
    """
    difficulty = state.get("difficulty_flag", "")
    score = state.get("score", 0)

    if difficulty == "EXTREME_GAP":
        print(f"[graph] 前分诊: EXTREME_GAP (score={score} < {CRITICAL_LOW_THRESHOLD}) -> "
              f"Editor (防幻觉骨架模式)")
    else:
        print(f"[graph] 前分诊: NORMAL (score={score} >= {CRITICAL_LOW_THRESHOLD}) -> "
              f"Editor (正常精修模式)")

    # 流程锁死: 无条件走向 editor, 绝不返回 END
    return "editor"


def eval_condition(state: AgentState) -> str:
    """
    v3.0 Evaluator 之后的路由（对优化后简历评分）：

    一键模式 (ONE_CLICK):
      - EXTREME_GAP: 防幻觉骨架模式完成 → Interviewer (生成压测题后 END)
      - score >= 70: 闪电战通关 → Interviewer → END
      - 30 <= score < 70: 进入 polisher 精细博弈（最多 MAX_ITERATIONS 轮）
      - score < 30 (安全网): 硬核重组 → polisher
      - 迭代耗尽: → Interviewer → END

    交互模式 (INTERACTIVE, session_id 非空):
      - score >= 70 或 turn_count >= MAX_INTERACTIVE_TURNS: → Interviewer → END
      - 否则: → chat_editor (回环，等待用户下一轮补充)

    所有简历必经 MockInterviewer 压力测试后才能结束。
    """
    score = state.get("score", 0)
    iteration = state.get("iteration_count", 0)
    difficulty = state.get("difficulty_flag", "")
    session_id = state.get("session_id", "")
    turn_count = state.get("turn_count", 0)

    # ── 交互模式路由 ──
    # 多轮交互的"回环"发生在跨 HTTP 请求层面，单次请求内 chat_editor → evaluator → interviewer 一次走完
    if session_id:
        print(f"[graph] 交互模式: score={score}, turn={turn_count} -> Interviewer 压测 -> END")
        return "interviewer"

    # ── 一键模式路由 (原逻辑) ──
    # 熔断路径：防幻觉骨架模式执行完 → 压测题 → END
    if difficulty == "EXTREME_GAP":
        print(f"[graph] 防幻觉骨架模式完成 (difficulty_flag=EXTREME_GAP) -> Interviewer 压测 -> END")
        return "interviewer"

    if score >= PASS_THRESHOLD:
        print(f"[graph] 闪电战通关: 评分 {score} >= {PASS_THRESHOLD} -> Interviewer 压测 -> END")
        return "interviewer"

    if score >= CRITICAL_LOW_THRESHOLD:
        if iteration < MAX_ITERATIONS:
            print(f"[graph] 中度差距: 评分 {score} 在 [{CRITICAL_LOW_THRESHOLD}, {PASS_THRESHOLD}) 区间，"
                  f"第 {iteration + 1}/{MAX_ITERATIONS} 轮 -> 精细博弈 (Polisher)")
            return "polisher"
        else:
            print(f"[graph] 精细博弈已达上限: {iteration}/{MAX_ITERATIONS} 轮，评分 {score} -> Interviewer 压测 -> END")
            return "interviewer"
    else:
        # v2.5: 安全网 → polisher 最后一搏（polisher 完成后会再次进入 eval_condition，
        # 届时 iteration >= MAX_ITERATIONS 会走到 interviewer）
        print(f"[graph] 意外低分: 评分 {score} < {CRITICAL_LOW_THRESHOLD}，"
              f"触发硬核单轮重组 -> Polisher (完成后进 Interviewer)")
        return "polisher"


def build_graph(checkpointer=None):
    """
    v3.0 编译 LangGraph 有向图

    拓扑:
      ┌─ user_supplement 非空 → chat_editor ─┐
      │                                        ▼
      ├─ user_supplement 为空 → retriever → [conditional] → tavily_search / pre_evaluator
      │                                                              │
      │                                              ┌─────────────────┘
      │                                              ▼
      │                                           editor
      │                                              │
      └──────────────────────────────────────────────┘
                                                     ▼
                                                 evaluator
                                                     │
                                          ┌──────────┼──────────┐
                                          ▼          ▼          ▼
                                     polisher   chat_editor  interviewer
                                     (一键)     (交互回环)    (压测)
                                          │          │          │
                                          └──────────┴──────────┘
                                                     ▼
                                                   END

    一键模式: retriever → ... → editor → evaluator → polisher ↔ evaluator → interviewer → END
    交互模式: chat_editor → evaluator → interviewer → END (跨 HTTP 多轮回环)
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("retriever", retriever_node)
    workflow.add_node("tavily_search", tavily_search_node)
    workflow.add_node("pre_evaluator", pre_evaluator_node)
    workflow.add_node("editor", editor_node)
    workflow.add_node("evaluator", evaluator_node)
    workflow.add_node("polisher", polisher_node)
    workflow.add_node("interviewer", interviewer_node)
    workflow.add_node("chat_editor", chat_editor_node)

    # ── 条件入口: 一键模式 vs 交互模式分流 ──
    workflow.set_conditional_entry_point(
        _entry_router,
        {
            "chat_editor": "chat_editor",
            "retriever": "retriever",
        },
    )

    # retriever -> 条件分支 (tavily_search 或 pre_evaluator)
    workflow.add_conditional_edges(
        "retriever",
        tools_condition,
        {
            "tavily_search": "tavily_search",
            "pre_evaluator": "pre_evaluator",
        },
    )

    # tavily_search -> pre_evaluator
    workflow.add_edge("tavily_search", "pre_evaluator")

    # pre_evaluator -> editor (无条件，仅做 difficulty_flag 模式标记)
    workflow.add_conditional_edges(
        "pre_evaluator",
        pre_eval_routing,
        {
            "editor": "editor",
        },
    )

    # editor -> evaluator
    workflow.add_edge("editor", "evaluator")

    # chat_editor -> evaluator (交互模式增量编辑后进入评分)
    workflow.add_edge("chat_editor", "evaluator")

    # evaluator -> 分诊路由 (polisher / chat_editor / interviewer)
    workflow.add_conditional_edges(
        "evaluator",
        eval_condition,
        {
            "polisher": "polisher",
            "chat_editor": "chat_editor",
            "interviewer": "interviewer",
            END: END,
        },
    )

    # polisher -> 分诊路由 (回到 evaluator 或 interviewer)
    workflow.add_conditional_edges(
        "polisher",
        eval_condition,
        {
            "polisher": "polisher",
            "chat_editor": "chat_editor",
            "interviewer": "interviewer",
            END: END,
        },
    )

    # interviewer -> END (压测题生成后直接结束)
    workflow.add_edge("interviewer", END)

    return workflow.compile(checkpointer=checkpointer)


_graph_app = None
_graph_checkpointer = None


def get_graph(checkpointer=None):
    global _graph_app, _graph_checkpointer
    if _graph_app is None or checkpointer is not _graph_checkpointer:
        _graph_app = build_graph(checkpointer=checkpointer)
        _graph_checkpointer = checkpointer
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
        "difficulty_flag": "",
        "node_status": "",
        "pre_eval_dimensions": {},
        "eval_dimensions": {},
        "stress_test_questions": [],
        "optimization_summary": "",
        "clean_resume_json": {},
        "chat_history": [],
        "user_supplement": "",
        "session_id": "",
        "turn_count": 0,
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
        "difficulty_flag": "",
        "node_status": "",
        "pre_eval_dimensions": {},
        "eval_dimensions": {},
        "stress_test_questions": [],
        "optimization_summary": "",
        "clean_resume_json": {},
        "chat_history": [],
        "user_supplement": "",
        "session_id": "",
        "turn_count": 0,
    }

    final = None
    for output in app.stream(initial, stream_mode="values"):
        final = output
    return final
