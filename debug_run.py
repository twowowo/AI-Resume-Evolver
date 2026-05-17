import os
import sys
import time
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)

sys.path.insert(0, os.path.abspath("."))

from src.state import GraphState
from src.nodes.analyzer import jd_analyzer_node
from src.nodes.refiner import resume_refiner_node
from src.utils.loader import load_docx

LOG_FILE = os.path.join(os.path.dirname(__file__), "debug_result.txt")


def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
        f.flush()


def create_test_jd():
    return """职位：高级后端开发工程师 (Python/FastAPI方向)
薪资：30k-45k

职责：
1. 负责公司核心业务系统的后端架构设计与开发
2. 使用 Python (FastAPI/Flask) 构建高性能异步 API 服务
3. 设计和实现 RAG 向量数据库检索系统，支撑大模型应用
4. 优化数据库性能，处理高并发场景下的数据读写

要求：
1. 精通 Python 编程，熟悉 FastAPI 框架及其异步特性
2. 具备 RAG 项目实战经验，熟悉向量数据库原理和应用
3. 熟悉 SQL/NoSQL 数据库，有数据库优化经验
4. 了解 Docker、Kubernetes 等容器化技术
5. 有大规模分布式系统开发经验者优先
6. 良好的沟通能力和团队协作精神

加分项：
1. 有大模型应用开发经验
2. 熟悉微服务架构
3. 有技术团队管理经验"""


def _extract_project_section(text: str, max_chars: int = 600) -> str:
    lines = text.split("\n")
    project_lines = []
    in_project = False
    for line in lines:
        lower = line.strip().lower()
        if any(kw in lower for kw in ["项目", "project", "经历", "experience", "工作"]):
            in_project = True
        if in_project:
            project_lines.append(line)
            if sum(len(l) for l in project_lines) > max_chars:
                break
    if not project_lines:
        return text[:max_chars] + "..."
    return "\n".join(project_lines)


def main():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")

    log(">>> AI-Resume-Evolver 全链路测试开始")
    log("=" * 60)

    log("\n[1] 准备测试数据...")

    resume_path = os.path.join("data", "resumes", "测试简历1.docx")
    if os.path.exists(resume_path):
        raw_resume = load_docx(resume_path)
        log(f"[OK] 简历加载成功，长度: {len(raw_resume)} 字符")
    else:
        raw_resume = "测试简历内容 - 张三，3年Python开发经验，熟悉FastAPI和数据库优化"
        log("[WARN] 使用模拟简历数据")

    target_jd = create_test_jd()
    log(f"[OK] JD 创建成功，长度: {len(target_jd)} 字符")

    state = GraphState(
        raw_resume=raw_resume,
        target_jd=target_jd,
        gap_list=[],
        rich_context_list=[],
        rag_context="",
        refined_resume="",
        feedback="",
        revision_count=0,
    )

    log("\n[2] 初始状态:")
    log(f"   - raw_resume: {len(state['raw_resume'])} 字符")
    log(f"   - target_jd: {len(state['target_jd'])} 字符")
    log(f"   - gap_list: {len(state['gap_list'])} 项")

    log("\n[3] 开始执行 jd_analyzer_node...")
    start_time = time.time()

    try:
        state = jd_analyzer_node(state)
        analyzer_time = time.time() - start_time
        log(f"\n[TIME] 分析节点执行耗时: {analyzer_time:.2f} 秒")

        log("\n[4] 分析结果:")
        log(f"   - gap_list 项数: {len(state['gap_list'])}")

        if state["gap_list"]:
            log("\n[GAP_LIST] 内容 (前 15 项):")
            for i, term in enumerate(state["gap_list"][:15], 1):
                log(f"   {i:2d}. {term}")

        log("\n[5] 开始执行 resume_refiner_node (DeepSeek-V4-Pro Thinking)...")
        refiner_start = time.time()

        state = resume_refiner_node(state)
        refiner_time = time.time() - refiner_start
        log(f"\n[TIME] 优化节点执行耗时: {refiner_time:.2f} 秒")

        log("\n[6] 优化结果:")
        log(f"   - refined_resume 长度: {len(state['refined_resume'])} 字符")
        log(f"   - revision_count: {state['revision_count']}")

        log("\n" + "=" * 60)
        log("[COMPARE] 优化前 vs 优化后 (项目片段对比)")
        log("=" * 60)

        before_snippet = _extract_project_section(state["raw_resume"])
        after_snippet = _extract_project_section(state["refined_resume"], max_chars=800)

        log("\n--- 优化前 ---")
        log(before_snippet)

        log("\n--- 优化后 ---")
        log(after_snippet)

        log("\n" + "=" * 60)
        log(f"[TIME] 总耗时: {analyzer_time + refiner_time:.2f} 秒 (分析: {analyzer_time:.2f}s + 优化: {refiner_time:.2f}s)")
        log("[DONE] 全链路测试完成！")

    except Exception as e:
        log(f"\n[ERROR] 测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            traceback.print_exc(file=f)


if __name__ == "__main__":
    main()
