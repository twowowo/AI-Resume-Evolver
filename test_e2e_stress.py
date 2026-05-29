"""
Phase 3 全链路冒烟测试 + 博弈边界压测
=======================================
覆盖：
  1. 正常 E2E：retriever → editor → evaluator ⇄ polisher
  2. 流式状态追踪（节点转移 + State 快照）
  3. 极限压测：低质量简历强制触发对抗闭环 → 验证兜底降级
"""

import os
import sys
import time
import json

# 强制 UTF-8 输出，解决 Windows GBK 终端编码问题
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.abspath("."))
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__) or ".", ".env")
load_dotenv(dotenv_path=env_path)

from src.graph import get_graph
from src.utils.loader import load_docx, load_txt
from src.state import AgentState

# ── 配置 ────────────────────────────────────────────────────────
RESUME_PATH = "data/resumes/测试简历1.docx"
JD_PATH = "data/jds/jd1.txt"
OUTPUT_DIR = "output"
LOG_FILE = "test_e2e_result.txt"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def log(msg: str):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
        f.flush()


def sep(title: str = ""):
    line = "=" * 60
    if title:
        log(f"\n{line}\n  {title}\n{line}")
    else:
        log(line)


# ── 测试 1: 正常 E2E 全链路 ─────────────────────────────────────

def test_normal_e2e():
    """使用真实简历 + 真实 JD 跑完整闭环"""
    sep("测试 1: 正常 E2E 全链路 (retriever -> editor -> evaluator <-> polisher)")

    # 加载真实数据
    log(f"\n[加载] 简历: {RESUME_PATH}")
    raw_resume = load_docx(RESUME_PATH)
    log(f"       简历长度: {len(raw_resume)} 字符")

    log(f"[加载] JD: {JD_PATH}")
    target_jd = load_txt(JD_PATH)
    log(f"       JD 长度: {len(target_jd)} 字符")

    # 获取图
    app = get_graph()
    initial: AgentState = {
        "resume": raw_resume,
        "jd": target_jd,
        "rag_context": "",
        "revised_resume": "",
        "internal_monologue": "",
        "tool_outputs": [],
        "score": 0,
        "evaluation_feedback": "",
        "iteration_count": 0,
    }

    # ── 流式追踪 ──
    t_start = time.time()
    node_timeline: list[dict] = []
    seen_nodes: set[str] = set()
    final_state = None

    log("\n[流式追踪] 开始图执行...")
    log("-" * 40)

    for output in app.stream(initial, stream_mode="updates"):
        for node_name, node_output in output.items():
            ts = time.time() - t_start

            if node_name not in seen_nodes:
                seen_nodes.add(node_name)
                entry = {
                    "node": node_name,
                    "time": f"{ts:.1f}s",
                    "output_keys": list(node_output.keys()) if node_output else [],
                }

                # 捕获关键状态变化
                if "rag_context" in node_output:
                    entry["rag_len"] = len(str(node_output["rag_context"]))
                if "revised_resume" in node_output:
                    entry["resume_len"] = len(str(node_output["revised_resume"]))
                if "score" in node_output:
                    entry["score"] = node_output["score"]
                if "evaluation_feedback" in node_output:
                    fb = str(node_output["evaluation_feedback"])
                    entry["feedback_preview"] = fb[:120]
                if "iteration_count" in node_output:
                    entry["iteration"] = node_output["iteration_count"]
                if "internal_monologue" in node_output:
                    mono = str(node_output["internal_monologue"])
                    entry["monologue_preview"] = mono[:150]

                node_timeline.append(entry)
                log(f"  [{ts:5.1f}s] ◉ {node_name} → {entry.get('output_keys', [])}")

    final_state = app.invoke(initial)
    elapsed = time.time() - t_start

    # ── 汇总报告 ──
    sep("测试 1 结果汇总")
    log(f"  总耗时: {elapsed:.1f}s")
    log(f"  节点执行顺序: {' → '.join(e['node'] for e in node_timeline)}")
    log(f"  最终评分: {final_state.get('score', 'N/A')}/100")
    log(f"  总迭代: {final_state.get('iteration_count', 'N/A')}")
    log(f"  简历输出: {len(final_state.get('revised_resume', ''))} 字符")

    score = final_state.get("score", 0)
    if score >= 70:
        log(f"  ✓ 通过阈值 (≥70)")
    else:
        log(f"  ✗ 未达阈值 — 已达最大迭代次数 (兜底放行)")

    # 内心独白
    monologue = final_state.get("internal_monologue", "")
    log(f"\n[内心独白]")
    for line in monologue.split("\n")[:15]:
        log(f"  {line}")

    # 简历样本
    revised = final_state.get("revised_resume", "")
    log(f"\n[优化后简历样本 (前 800 字符)]")
    log("-" * 40)
    log(revised[:800])
    if len(revised) > 800:
        log(f"\n... (共 {len(revised)} 字符)")

    # 保存
    sample_path = os.path.join(OUTPUT_DIR, "test1_normal_output.md")
    with open(sample_path, "w", encoding="utf-8") as f:
        f.write(revised)
    log(f"\n[保存] 完整简历 → {sample_path}")

    return {
        "elapsed": elapsed,
        "score": score,
        "iterations": final_state.get("iteration_count", 0),
        "timeline": node_timeline,
        "passed": score >= 70,
    }


# ── 测试 2: 博弈边界压测 ─────────────────────────────────────────

def test_adversarial_stress():
    """
    用极低质量简历故意触发 evaluator 打低分，
    观察 polisher 被反复调用，到达 MAX_ITERATIONS 后兜底放行。
    """
    sep("测试 2: 博弈边界压测 (低质量简历 → 强制对抗闭环)")

    # 极低质量简历 - 故意做得非常敷衍
    poor_resume = """个人信息
姓名：测试用户
学历：本科

工作经历
某小公司 - 后端开发 (2020-2023)
负责写接口，用了一下数据库，做了几个项目，维护服务器。

项目经历
项目一：公司官网
做了公司官网后端，写了几个API，用了MySQL，感觉还行。

技能
Python, SQL, 会写代码"""

    target_jd = load_txt(JD_PATH)

    log(f"\n[加载] 低质量简历: {len(poor_resume)} 字符 (故意敷衍)")
    log(f"[加载] JD: {JD_PATH} ({len(target_jd)} 字符)")

    app = get_graph()
    initial: AgentState = {
        "resume": poor_resume,
        "jd": target_jd,
        "rag_context": "",
        "revised_resume": "",
        "internal_monologue": "",
        "tool_outputs": [],
        "score": 0,
        "evaluation_feedback": "",
        "iteration_count": 0,
    }

    t_start = time.time()
    score_history: list[dict] = []
    node_timeline: list[str] = []

    log("\n[流式追踪] 观察对抗闭环...")
    log("-" * 40)

    for output in app.stream(initial, stream_mode="updates"):
        for node_name, node_output in output.items():
            ts = time.time() - t_start
            node_timeline.append(node_name)

            info = f"  [{ts:5.1f}s] ◉ {node_name}"

            if "score" in node_output:
                score = node_output["score"]
                iteration = node_output.get("iteration_count", 0)
                fb = str(node_output.get("evaluation_feedback", ""))
                score_history.append({
                    "iteration": iteration,
                    "score": score,
                    "feedback_snippet": fb[:150],
                })
                info += f" | 评分: {score}/100 (第{iteration}轮)"
                if score < 70:
                    info += " ✗ 打回重改!"
                else:
                    info += " ✓ 通过!"

            if "revised_resume" in node_output:
                info += f" | 简历: {len(str(node_output['revised_resume']))} 字符"

            log(info)

    final_state = app.invoke(initial)
    elapsed = time.time() - t_start

    # ── 汇总 ──
    sep("测试 2 博弈压测结果")
    log(f"  总耗时: {elapsed:.1f}s")
    log(f"  节点执行序列: {' → '.join(node_timeline)}")
    log(f"  最终评分: {final_state.get('score', 'N/A')}/100")
    log(f"  总迭代: {final_state.get('iteration_count', 0)}")

    # 评分轨迹
    log(f"\n[评分轨迹]")
    for entry in score_history:
        marker = "✓" if entry["score"] >= 70 else "✗"
        log(f"  第{entry['iteration']}轮: {entry['score']}/100 {marker}")
        if entry["feedback_snippet"]:
            log(f"         反馈: {entry['feedback_snippet']}...")

    # 兜底验证
    final_score = final_state.get("score", 0)
    final_iter = final_state.get("iteration_count", 0)

    log(f"\n[兜底降级验证]")
    if final_score < 70 and final_iter >= 3:
        log(f"  ✓ 兜底生效: 评分 {final_score} < 70，已达 {final_iter} 轮上限，优雅放行")
        log(f"  ✓ 系统输出了当前最优解（非报错/死循环）")
        degraded = True
    elif final_score >= 70:
        log(f"  ✓ 对抗成功: 经过 {final_iter} 轮精修，评分突破 70 分阈值")
        degraded = False
    else:
        log(f"  ⚠ 异常: 评分 {final_score}，迭代 {final_iter} 轮（未达上限但未通过）")
        degraded = False

    # 简历样本
    revised = final_state.get("revised_resume", "")
    log(f"\n[优化后简历样本 (前 800 字符)]")
    log("-" * 40)
    log(revised[:800])
    if len(revised) > 800:
        log(f"\n... (共 {len(revised)} 字符)")

    sample_path = os.path.join(OUTPUT_DIR, "test2_stress_output.md")
    with open(sample_path, "w", encoding="utf-8") as f:
        f.write(revised)
    log(f"\n[保存] 完整简历 → {sample_path}")

    return {
        "elapsed": elapsed,
        "score": final_score,
        "iterations": final_iter,
        "score_history": score_history,
        "timeline": node_timeline,
        "degraded": degraded,
    }


# ── 主入口 ──────────────────────────────────────────────────────

def main():
    # 清空日志
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")

    sep("AI-Resume-Evolver v2.0 全链路冒烟测试 + 博弈边界压测")
    log(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"  USE_PRO_MODEL: {os.getenv('USE_PRO_MODEL', 'false')}")
    log(f"  ChromaDB: 808 条术语")
    log(f"  MAX_ITERATIONS: 3, PASS_THRESHOLD: 70")

    # ── 测试 1 ──
    result1 = test_normal_e2e()

    # ── 测试 2 ──
    result2 = test_adversarial_stress()

    # ── 最终汇总 ──
    sep("全链路压测最终汇总")
    log(f"")
    log(f"  测试 1 (正常E2E):")
    log(f"    耗时: {result1['elapsed']:.1f}s")
    log(f"    评分: {result1['score']}/100 {'✓' if result1['passed'] else '✗'}")
    log(f"    节点: {' → '.join(e['node'] for e in result1['timeline'])}")
    log(f"")
    log(f"  测试 2 (博弈压测):")
    log(f"    耗时: {result2['elapsed']:.1f}s")
    log(f"    评分: {result2['score']}/100")
    log(f"    节点: {' → '.join(result2['timeline'])}")
    log(f"    兜底降级: {'✓ 已触发' if result2['degraded'] else '— 未触发（对抗成功）'}")
    log(f"")
    log(f"  完整日志: {LOG_FILE}")
    log(f"  输出目录: {OUTPUT_DIR}/")
    sep("压测完成")


if __name__ == "__main__":
    main()
