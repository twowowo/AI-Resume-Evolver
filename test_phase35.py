"""
Phase 3.5 单体压测脚本 —— 测试简历 1（张兵）
打印 PreEvaluator -> Editor -> Evaluator 的完整分数曲线
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath("."))

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__) or ".", ".env"))

from src.utils.loader import load_docx, load_txt


def merge_state(old, new):
    """模拟 LangGraph 的状态合并"""
    merged = dict(old)
    merged.update(new)
    return merged


# ── 加载测试数据 ──
resume_path = "data/resumes/测试简历1.docx"
jd_path = "data/jds/jd1.txt"

raw_resume = load_docx(resume_path)
target_jd = load_txt(jd_path)

print("=" * 65)
print("  Phase 3.5 单体压测 -- 测试简历 1 (张兵)")
print("  v2.3 硬工具保底双轨制 + 6-3-1 死锁 + 反幻觉平滑")
print("=" * 65)
print(f"\n[INPUT] 简历: {resume_path} ({len(raw_resume)} 字符)")
print(f"[INPUT] JD: {jd_path} ({len(target_jd)} 字符)")
print(f"\n[简历摘要]")
print(raw_resume[:500])
print(f"\n[JD 摘要]")
print(target_jd[:400])

# ── 初始化状态 ──
state = {
    "resume": raw_resume,
    "jd": target_jd,
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

t0 = time.time()

# ── Step 1: Retriever ──
print("\n" + "-" * 65)
print("  Step 1: Retriever (RAG 混合检索)")
print("-" * 65)

from src.nodes.retriever import retriever_node
ret_output = retriever_node(state)
state = merge_state(state, ret_output)
rag_len = len(state.get("rag_context", ""))
print(f"[retriever] RAG 上下文: {rag_len} 字符")

# Check if web search needed
from src.graph import _needs_web_search
if _needs_web_search(state):
    print("[graph] 触发联网搜索...")
    from src.tools.search import tavily_search_node
    tavily_output = tavily_search_node(state)
    state = merge_state(state, tavily_output)
    tools_len = len(state.get("tool_outputs", []))
    print(f"[tavily_search] 搜索完成，工具输出: {tools_len} 条")

# ── Step 2: PreEvaluator ──
print(f"\n" + "-" * 65)
print("  Step 2: PreEvaluator (v2.3 硬工具保底双轨制)")
print("-" * 65)

from src.nodes.pre_evaluator import pre_evaluator_node
pre_eval_output = pre_evaluator_node(state)
state = merge_state(state, pre_eval_output)

pre_score = state.get("score", 0)
pre_flag = state.get("difficulty_flag", "")
pre_status = state.get("node_status", "")

print(f"\n  >>> PreEvaluator 初筛结论 <<<")
print(f"  总分: {pre_score}/100")
print(f"  分诊标记: {pre_flag}")
print(f"  状态: {pre_status}")

if pre_score >= 30:
    print(f"  [PASS] 初筛通过: 总分 {pre_score} >= 30 熔断线，正常进入精修模式")
else:
    print(f"  [FAIL] 初筛未过: 总分 {pre_score} < 30 熔断线，进入防幻觉骨架模式")

# ── Step 3: Editor ──
print(f"\n" + "-" * 65)
print("  Step 3: Editor (简历优化)")
print("-" * 65)

from src.nodes.editor import editor_node
editor_output = editor_node(state)
state = merge_state(state, editor_output)

revised_len = len(state.get("revised_resume", ""))
monologue = state.get("internal_monologue", "")
print(f"[editor] 优化后简历: {revised_len} 字符")
if monologue:
    # Truncate to first few lines
    mono_lines = monologue.split("\n")[:5]
    for line in mono_lines:
        print(f"  | {line[:120]}")

# ── Step 4: Evaluator ──
print(f"\n" + "-" * 65)
print("  Step 4: Evaluator (v2.3 6-3-1 死锁 + 反幻觉平滑)")
print("-" * 65)

from src.nodes.evaluator import evaluator_node
eval_output = evaluator_node(state)
state = merge_state(state, eval_output)

eval_score = state.get("score", 0)
eval_flag = state.get("difficulty_flag", "")
eval_fb = state.get("evaluation_feedback", "")
iteration = state.get("iteration_count", 0)

print(f"\n  >>> Evaluator 终评审结论 <<<")
print(f"  终评总分: {eval_score}/100")
print(f"  分诊标记: {eval_flag or '(继承 pre_evaluator)'}")
print(f"  迭代轮次: {iteration}")

# 判断是否进入精修循环
polish_rounds = 0
if eval_flag == "EXTREME_GAP":
    print(f"  [SKIP] 防幻觉骨架模式: 单轮放行，不进入精修循环")
elif eval_score >= 70:
    print(f"  [PASS] 闪电战通关: 评分 {eval_score} >= 70，直接结束")
elif eval_score >= 30:
    print(f"  [POLISH] 进入精修博弈: 评分 {eval_score} 在 [30, 70) 区间")
    polish_rounds = 3
else:
    print(f"  [POLISH] 低分安全网: 评分 {eval_score} < 30，触发硬核重组")

# ── 精修循环 ──
if eval_flag != "EXTREME_GAP" and eval_score < 70:
    from src.nodes.polisher import polisher_node

    for round_num in range(3):
        if eval_score >= 70:
            break
        if state.get("difficulty_flag") == "EXTREME_GAP":
            break

        print(f"\n" + "-" * 65)
        print(f"  Step 5.{round_num + 1}: Polisher 精修 (第 {round_num + 1} 轮)")
        print("-" * 65)

        state["iteration_count"] = round_num
        polish_output = polisher_node(state)
        state = merge_state(state, polish_output)

        polished_len = len(state.get("revised_resume", ""))
        print(f"[polisher] 精修后简历: {polished_len} 字符")

        print(f"\n" + "-" * 65)
        print(f"  Step 6.{round_num + 1}: Evaluator 复评 (第 {round_num + 2} 轮)")
        print("-" * 65)

        eval_output = evaluator_node(state)
        state = merge_state(state, eval_output)
        eval_score = state.get("score", 0)
        eval_flag = state.get("difficulty_flag", "")

        print(f"\n  >>> 第 {round_num + 2} 轮复评结论 <<<")
        print(f"  评分: {eval_score}/100")

        if eval_score >= 70:
            print(f"  [PASS] 通过! 评分 {eval_score} >= 70")
        elif eval_flag == "EXTREME_GAP":
            print(f"  [TRIGGER] 触发 EXTREME_GAP，终止循环")
            break

elapsed = time.time() - t0

# ── 最终报告 ──
print("\n" + "=" * 65)
print("  压测最终报告")
print("=" * 65)

final_score = eval_score if 'eval_score' in dir() else pre_score
final_flag = state.get("difficulty_flag", "")

print(f"""
  ┌─────────────────────────────────────────┐
  │  简历: 测试简历1 (张兵)                  │
  │  JD:   高级Python后端 (仓储物流方向)       │
  │                                          │
  │  PreEvaluator 初筛:  {pre_score:>3d}/100       │
  │  Evaluator 终评:     {final_score:>3d}/100       │
  │                                          │
  │  分诊标记: {final_flag:<30s} │
  │  耗时:     {elapsed:.1f} 秒                    │
  │                                          │
  │  工具链: FastAPI/MySQL/Redis/RabbitMQ/Docker │
  │  预期初筛: >= 30 分 (硬工具保底应生效)       │
  └─────────────────────────────────────────┘
""")

# ── 校验 ──
print("-" * 65)
print("  校验项")
print("-" * 65)

all_pass = True

# Check 1: PreEvaluator score >= 30
if pre_score >= 30:
    print(f"  [PASS] 初筛分 {pre_score} >= 30 熔断线")
else:
    print(f"  [FAIL] 初筛分 {pre_score} < 30 熔断线 -- 硬工具保底可能未生效!")
    all_pass = False

# Check 2: difficulty flag
if pre_flag == "NORMAL":
    print(f"  [PASS] 分诊标记为 NORMAL，正常进入精修")
elif pre_score >= 30:
    print(f"  [WARN] 分诊标记为 {pre_flag} 但分数 >= 30")

# Check 3: Final score stability
if final_score >= 30:
    print(f"  [PASS] 终评分 {final_score} >= 30")
else:
    print(f"  [FAIL] 终评分 {final_score} < 30")
    all_pass = False

# Check 4: Score not in extreme range
if 30 <= final_score <= 95:
    print(f"  [PASS] 终评分 {final_score} 在合理区间 [30, 95]")
else:
    print(f"  [WARN] 终评分 {final_score} 在极端区间")

if all_pass:
    print(f"\n  [SUCCESS] 全部校验通过！硬工具保底双轨制生效，张兵简历评分合理回归。")
else:
    print(f"\n  [FAIL] 部分校验未通过，需要进一步调优。")

print("\n" + "=" * 65)
print("  压测完成")
print("=" * 65)
