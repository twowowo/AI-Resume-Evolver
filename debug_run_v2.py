"""
v2.0-alpha 全链路测试脚本
使用 LangGraph 多智能体图: retriever → editor → evaluator → (polisher loop) → END
"""
import os
import sys
import time
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)

sys.path.insert(0, os.path.abspath("."))

from src.graph import get_graph
from src.utils.loader import load_txt

LOG_FILE = os.path.join(os.path.dirname(__file__), "debug_result_v2.txt")


def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
        f.flush()


def main():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")

    log(">>> AI-Resume-Evolver v2.0-alpha 全链路测试")
    log("   图结构: retriever -> editor -> evaluator -> (polisher -> evaluator) -> END")
    log("   测试场景: 张大壮 3年Python后端 → 字节跳动 AI基础设施架构师")
    log("=" * 60)

    # 加载材料
    resume_path = os.path.join("mock_resume.md")
    raw_resume = load_txt(resume_path)
    log(f"\n[LOAD] 简历: {resume_path} ({len(raw_resume)} 字符)")

    jd_path = os.path.join("debug_jd.txt")
    if not os.path.exists(jd_path):
        # 把硬核 JD 写进去
        from debug_run import create_test_jd
        jd_text = create_test_jd()
        with open(jd_path, "w", encoding="utf-8") as f:
            f.write(jd_text)
    else:
        jd_text = load_txt(jd_path)
    log(f"[LOAD] JD: {jd_path} ({len(jd_text)} 字符)")

    # 构造初始状态
    initial = {
        "resume": raw_resume,
        "jd": jd_text,
        "rag_context": "",
        "revised_resume": "",
        "internal_monologue": "",
        "tool_outputs": [],
        "score": 0,
        "evaluation_feedback": "",
        "iteration_count": 0,
    }

    log("\n" + "=" * 60)
    log("开始全链路执行...")
    log("=" * 60)

    app = get_graph()
    seen_nodes = []
    t_start = time.time()

    # 累积最终状态：stream 过程中逐节点 merge 增量，避免 invoke() 重复执行管线
    final = dict(initial)

    for output in app.stream(initial, stream_mode="updates"):
        for node_name, node_output in output.items():
            # 累积状态增量到 final
            final.update(node_output)

            if node_name not in seen_nodes:
                seen_nodes.append(node_name)

            if node_name == "retriever":
                log(f"\n[NODE {len(seen_nodes)}] retriever — RAG 检索完成")
            elif node_name == "tavily_search":
                log(f"\n[NODE {len(seen_nodes)}] tavily_search — 联网搜索完成")
            elif node_name == "editor":
                revised_len = node_output.get("revised_resume", "")
                revised_len = len(revised_len) if revised_len else 0
                log(f"\n[NODE {len(seen_nodes)}] editor — 粗优化完成 ({revised_len} 字符)")
            elif node_name == "evaluator":
                score = node_output.get("score", 0)
                fb = node_output.get("evaluation_feedback", "")
                iter_cnt = node_output.get("iteration_count", 0)
                log(f"\n[NODE {len(seen_nodes)}] evaluator — 评分: {score}/100 (第 {iter_cnt + 1} 轮)")
                if fb:
                    log(f"  [反馈] {fb[:400]}")
                if score >= 70:
                    log(f"  [结果] ✓ 通过！放行导出。")
                else:
                    log(f"  [结果] ✗ 未通过 (<70)，进入 Polisher 精修...")
            elif node_name == "polisher":
                iter_cnt = node_output.get("iteration_count", 0) - 1
                log(f"\n[NODE {len(seen_nodes)}] polisher — 第 {iter_cnt} 轮精修完成")

    elapsed = time.time() - t_start
    # final 已通过 stream 累积完成，无需再 invoke

    log("\n" + "=" * 60)
    log("最终结果")
    log("=" * 60)

    score = final.get("score", 0)
    iteration = final.get("iteration_count", 0)
    revised = final.get("revised_resume", "")
    monologue = final.get("internal_monologue", "")

    log(f"\n  最终评分: {score}/100")
    log(f"  总迭代轮次: {iteration}")
    log(f"  优化后简历长度: {len(revised)} 字符")
    log(f"  总耗时: {elapsed:.1f} 秒")

    if monologue:
        log(f"\n  [Agent 内心独白]")
        for line in monologue.split("\n")[:20]:
            log(f"    {line}")

    log(f"\n  [优化后简历预览 (前 800 字符)]")
    log("-" * 50)
    log(revised[:800])
    if len(revised) > 800:
        log(f"\n... (共 {len(revised)} 字符)")

    # 将完整优化简历写入独立文件
    resume_out = os.path.join(os.path.dirname(__file__), "output", "final_resume_v2.md")
    os.makedirs(os.path.dirname(resume_out), exist_ok=True)
    with open(resume_out, "w", encoding="utf-8") as f:
        f.write(revised)
    log(f"\n[EXPORT] 完整优化简历已写入: {resume_out}")

    log("\n" + "=" * 60)
    log("[FINISH] v2.0-alpha 全链路测试完成")
    log("=" * 60)


if __name__ == "__main__":
    main()
