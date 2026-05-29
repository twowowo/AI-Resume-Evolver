"""
v2.2 LangGraph 多智能体工作流 —— 前置分诊 + 路由解耦

图结构:
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
        END         [eval_condition]
                    │           │
                 polisher      END
                    │
               [eval_condition]
                    │           │
                evaluator      END

  流程锁死: 所有简历必须至少经过一轮 Editor 优化, 无条件进入 evaluator 终审。
"""

import os
from langgraph.graph import StateGraph, END
from src.state import AgentState
from src.nodes.retriever import retriever_node
from src.nodes.editor import editor_node
from src.nodes.evaluator import evaluator_node
from src.nodes.polisher import polisher_node
from src.nodes.pre_evaluator import pre_evaluator_node
from src.tools.search import tavily_search_node, _detect_company, _extract_tech_keywords

_web_search_always = os.getenv("FORCE_WEB_SEARCH", "false").lower() == "true"

MAX_ITERATIONS = 3
PASS_THRESHOLD = 70
CRITICAL_LOW_THRESHOLD = 30


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
    v2.2 Evaluator 之后的路由（对优化后简历评分）：

    - EXTREME_GAP: 防幻觉骨架模式完成，单轮放行 -> END
    - score >= 70: 闪电战通关 -> END
    - 40 <= score < 70: 进入 polisher 精细博弈（最多 MAX_ITERATIONS 轮）
    - score < 40 (安全网): 硬核重组 -> polisher -> END
    """
    score = state.get("score", 0)
    iteration = state.get("iteration_count", 0)
    difficulty = state.get("difficulty_flag", "")

    # 熔断路径：防幻觉骨架模式执行完，直接放行
    if difficulty == "EXTREME_GAP":
        print(f"[graph] 防幻觉骨架模式完成 (difficulty_flag=EXTREME_GAP)，直接放行 -> END")
        return END

    if score >= PASS_THRESHOLD:
        print(f"[graph] 闪电战通关: 评分 {score} >= {PASS_THRESHOLD} -> END")
        return END

    if score >= CRITICAL_LOW_THRESHOLD:
        if iteration < MAX_ITERATIONS:
            print(f"[graph] 中度差距: 评分 {score} 在 [{CRITICAL_LOW_THRESHOLD}, {PASS_THRESHOLD}) 区间，"
                  f"第 {iteration + 1}/{MAX_ITERATIONS} 轮 -> 精细博弈 (Polisher)")
            return "polisher"
        else:
            print(f"[graph] 精细博弈已达上限: {iteration}/{MAX_ITERATIONS} 轮，评分 {score}，强制放行 -> END")
            return END
    else:
        # v2.1: 理论上不会走到这里（EXTREME_GAP 由 pre_evaluator 提前拦截）
        # 但保留作为安全网
        print(f"[graph] 意外低分: 评分 {score} < {CRITICAL_LOW_THRESHOLD}，"
              f"触发硬核单轮重组 -> Polisher (全力一击后直接 END)")
        return "polisher"


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("retriever", retriever_node)
    workflow.add_node("tavily_search", tavily_search_node)
    workflow.add_node("pre_evaluator", pre_evaluator_node)
    workflow.add_node("editor", editor_node)
    workflow.add_node("evaluator", evaluator_node)
    workflow.add_node("polisher", polisher_node)

    workflow.set_entry_point("retriever")

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

    # evaluator -> 分诊路由 (polisher 或 END)
    workflow.add_conditional_edges(
        "evaluator",
        eval_condition,
        {
            "polisher": "polisher",
            END: END,
        },
    )

    # polisher -> 分诊路由 (回到 evaluator 或 END)
    workflow.add_conditional_edges(
        "polisher",
        eval_condition,
        {
            "polisher": "polisher",
            END: END,
        },
    )

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
        "difficulty_flag": "",
        "node_status": "",
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
    }

    final = None
    for output in app.stream(initial, stream_mode="values"):
        final = output
    return final
