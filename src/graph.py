"""
v4.5 LangGraph 双模有向图 —— 一键模式 + 交互模式 + 长对话熔断器

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
       ├─ chat_history > 6 → summarize_history_node (600-800字压缩)
       │                      │
       │                      ▼
       └────────────────→ chat_editor ──→ evaluator ──→ interviewer ──→ END
                          (增量编辑)      (评分)        (压测)

    多轮回环发生跨 HTTP 请求层面，单次请求内一次走完三段式链路。
    长对话熔断器在每次交互入口自动检测，超过 6 条历史即触发压缩脱水。

  流程锁死: 所有简历必须经过 Editor → Evaluator → Interviewer 完整链路
  交互锁死: 所有补充意见必须经过 chat_editor → evaluator 评分闭环
  记忆锁死: chat_history > 6 → summarize_history_node 熔断压缩，永不溢出
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
from src.utils.llm import get_flash_client

_web_search_always = os.getenv("FORCE_WEB_SEARCH", "false").lower() == "true"

MAX_ITERATIONS = 3
MAX_INTERACTIVE_TURNS = 5
PASS_THRESHOLD = 70
CRITICAL_LOW_THRESHOLD = 30

# ═══════════════════════════════════════════════════════════════
# v4.5 长对话熔断器：高保真记忆脱水引擎
# ═══════════════════════════════════════════════════════════════

SUMMARIZE_HISTORY_THRESHOLD = 6  # chat_history 超过此条数触发压缩

SUMMARIZE_PROMPT = """你现在是工业级智能体系统的【高保真记忆脱水引擎】。
请你仔细阅读以下对话历史，将其物理压缩成一段 600-800 字以内的【当前简历优化断点进度与背景备忘录】。

【硬核格式锁死】
你必须严格按以下 4 个章节输出，每个章节用 `###` 标题开头，不得遗漏任何章节：

### 1. 当前演进技术现状 (Current Tech Stack)
简述当前简历已优化的技术栈描述、已强化的核心关键词、已补充的关键项目细节与量化指标。

### 2. 优化断点与达成目标 (Milestones & Targets)
用户上一轮修改到了哪一步，下一步计划达成什么优化目标，当前的大致进度与达成率。

### 3. 历史推翻与雷区限制 (Rejected & Restrictions)
用户明确拒绝过的修改建议、不可触碰的简历章节或表述禁区、已锁定的排版与格式规则。

### 4. 影子审计分数轨迹 (Score Trace)
历次评分走势概述，忠实度 (Faithfulness) 与相关性 (Answer Relevance) 分数变化方向，当前分数瓶颈与扣分主因。

总字数严格控制在 600-800 字之间，输出纯文本，不得包含代码块标记或额外解释。"""


def should_summarize_filter(state: AgentState) -> bool:
    """
    v4.5 长对话熔断过滤器 —— 检查 chat_history 是否超过压缩阈值

    返回值:
      True  → 需要在 chat_editor 前执行 summarize_history_node
      False → 直接进入 chat_editor
    """
    chat_history = state.get("chat_history", [])
    return len(chat_history) > SUMMARIZE_HISTORY_THRESHOLD


def summarize_history_node(state: AgentState) -> dict:
    """
    v4.5 高保真记忆脱水节点 —— 将历史对话物理压缩为结构化备忘录

    核心算法:
      1. 保留 chat_history 最后 2 条（最近一轮对话），保持"触觉记忆"不丢失
      2. 将其余历史对话送入 DeepSeek Flash，按 SUMMARIZE_PROMPT 四章节压缩
      3. 如果已有 conversation_summary（二次压缩），将旧摘要作为"前情提要"链式注入
      4. LLM 调用失败时自动回退为截断文本，确保图拓扑不崩

    输出:
      - conversation_summary: 600-800 字结构化备忘录
      - chat_history: 仅保留最后 2 条
      - node_status: 运行态描述
    """
    chat_history = state.get("chat_history", [])

    if len(chat_history) <= 2:
        return {"node_status": "历史过短，跳过压缩"}

    # ── 切片：保留最后 2 条触觉记忆 ──
    recent = chat_history[-2:]
    old = chat_history[:-2]

    # ── 格式化旧历史为对话文本 ──
    history_parts: list[str] = []
    for i, m in enumerate(old):
        role_label = "用户" if m.get("role") == "user" else "AI 助手"
        snippet = m.get("content", "")[:300]
        history_parts.append(f"[第{i // 2 + 1}轮][{role_label}]: {snippet}")
    history_text = "\n".join(history_parts)

    # ── 链式注入：已有摘要作为前情提要 ──
    existing_summary = state.get("conversation_summary", "")
    if existing_summary:
        full_context = (
            f"## 上一轮压缩备忘录\n{existing_summary}\n\n"
            f"## 本轮新增对话（需合并压缩）\n{history_text}"
        )
    else:
        full_context = f"## 原始对话历史\n{history_text}"

    prompt = SUMMARIZE_PROMPT + "\n\n" + full_context

    # ── 调用 DeepSeek Flash 执行压缩 ──
    try:
        llm = get_flash_client()
        response = llm.invoke(prompt)
        summary = response.content if hasattr(response, "content") else str(response)
        summary = summary.strip()
    except Exception as exc:
        print(f"[summarize_history] LLM 压缩失败: {type(exc).__name__}: {exc}, 触发截断回退")
        # 回退：用旧历史截断文本作为粗粒度摘要
        fallback = history_text[:600] if history_text else "(空历史)"
        summary = (
            f"### 1. 当前演进技术现状\n(压缩引擎降级，原始记录): {fallback}\n\n"
            f"### 2. 优化断点与达成目标\n待恢复\n\n"
            f"### 3. 历史推翻与雷区限制\n待恢复\n\n"
            f"### 4. 影子审计分数轨迹\n待恢复"
        )

    print(f"[summarize_history] 压缩完成: {len(old)} 条历史 → {len(summary)} 字符备忘录, "
          f"保留最近 {len(recent)} 条触觉记忆")

    return {
        "conversation_summary": summary,
        "chat_history": recent,
        "node_status": f"历史压缩完成: {len(old)} 条对话脱水为 {len(summary)} 字符备忘录",
    }


def _entry_router(state: AgentState) -> str:
    """
    v4.5 拓扑入口路由 —— 一键模式 vs 交互模式分流 + 长对话熔断器

    - user_supplement 非空 → 交互模式:
        - chat_history > 6 条 → 先经 summarize_history_node 压缩再进 chat_editor
        - chat_history ≤ 6 条 → 直入 chat_editor 增量编辑
    - user_supplement 为空 → 一键模式，走 RAG 检索全链路
    """
    if state.get("user_supplement", "").strip():
        if should_summarize_filter(state):
            print("[graph] 交互模式 + 长对话熔断触发 -> 先压缩历史再进入 chat_editor")
            return "summarize_history_node"
        print("[graph] 交互模式 -> chat_editor 增量编辑")
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
    v4.5 编译 LangGraph 有向图 —— 三层漏斗 + 长对话熔断器

    拓扑:
      ┌─ user_supplement 非空:
      │    ├─ chat_history > 6 → summarize_history_node → chat_editor ─┐
      │    └─ chat_history ≤ 6 → chat_editor ─────────────────────────┘
      │                                                                  ▼
      ├─ user_supplement 为空 → retriever → [conditional] → tavily_search / pre_evaluator
      │                                                                  │
      │                                                  ┌─────────────────┘
      │                                                  ▼
      │                                               editor
      │                                                  │
      └──────────────────────────────────────────────────┘
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
    交互模式: [summarize_gate] → chat_editor → evaluator → interviewer → END (跨 HTTP 多轮回环)
    长对话熔断: chat_history > 6 → summarize_history_node 压缩至 600-800 字备忘录
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("retriever", retriever_node)
    workflow.add_node("tavily_search", tavily_search_node)
    workflow.add_node("pre_evaluator", pre_evaluator_node)
    workflow.add_node("editor", editor_node)
    workflow.add_node("evaluator", evaluator_node)
    workflow.add_node("polisher", polisher_node)
    workflow.add_node("interviewer", interviewer_node)
    workflow.add_node("summarize_history_node", summarize_history_node)
    workflow.add_node("chat_editor", chat_editor_node)

    # ── v4.5 条件入口: 一键模式 vs 交互模式分流 + 长对话熔断 ──
    workflow.set_conditional_entry_point(
        _entry_router,
        {
            "chat_editor": "chat_editor",
            "retriever": "retriever",
            "summarize_history_node": "summarize_history_node",
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

    # summarize_history_node -> chat_editor (历史压缩后进入增量编辑)
    workflow.add_edge("summarize_history_node", "chat_editor")

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


def run_pipeline(resume: str, jd: str, user_id: str = "default_user", resume_id: str = "default_resume") -> AgentState:
    app = get_graph()
    initial: AgentState = {
        "user_id": user_id,
        "resume_id": resume_id,
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
        "conversation_summary": "",
        "visual_payload": {},
        "step_count": 0,
        "total_tokens": 0,
        "jd_keywords": "",
        "retriever_metrics": "",
    }
    result = app.invoke(initial)
    return result


def run_pipeline_stream(resume: str, jd: str, user_id: str = "default_user", resume_id: str = "default_resume"):
    app = get_graph()
    initial: AgentState = {
        "user_id": user_id,
        "resume_id": resume_id,
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
        "conversation_summary": "",
        "visual_payload": {},
        "step_count": 0,
        "total_tokens": 0,
        "jd_keywords": "",
        "retriever_metrics": "",
    }

    final = None
    for output in app.stream(initial, stream_mode="values"):
        final = output
    return final
