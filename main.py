import os
import sys
import argparse
import time
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)

sys.path.insert(0, os.path.abspath("."))

from fastapi import FastAPI
import uvicorn

app = FastAPI(title="AI Resume Evolver API")


@app.get("/health")
async def health_check():
    return {"status": "online", "port": 8001, "engine": "LangGraph"}


def run_pipeline(resume_path: str, jd_path: str | None = None, export_fmt: str | None = None, output_path: str | None = None):
    from src.state import GraphState
    from src.nodes.analyzer import jd_analyzer_node
    from src.nodes.refiner import resume_refiner_node
    from src.utils.loader import load_docx, load_txt

    print("=" * 60)
    print("AI-Resume-Evolver 全链路优化")
    print("=" * 60)

    print(f"\n[1] 加载简历: {resume_path}")
    if resume_path.endswith(".docx"):
        raw_resume = load_docx(resume_path)
    else:
        raw_resume = load_txt(resume_path)
    print(f"    简历长度: {len(raw_resume)} 字符")

    if jd_path and os.path.exists(jd_path):
        print(f"\n[2] 加载 JD: {jd_path}")
        if jd_path.endswith(".docx"):
            target_jd = load_docx(jd_path)
        else:
            target_jd = load_txt(jd_path)
    else:
        print("\n[2] 使用内置测试 JD")
        target_jd = """职位：高级后端开发工程师 (Python/FastAPI方向)
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
6. 良好的沟通能力和团队协作精神"""

    print(f"    JD 长度: {len(target_jd)} 字符")

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

    print("\n[3] 执行 JD 分析节点...")
    t0 = time.time()
    state = jd_analyzer_node(state)
    print(f"    耗时: {time.time() - t0:.1f}s, gap_list: {len(state['gap_list'])} 项")

    print("\n[4] 执行简历优化节点...")
    t0 = time.time()
    state = resume_refiner_node(state)
    print(f"    耗时: {time.time() - t0:.1f}s, 输出: {len(state['refined_resume'])} 字符")

    if export_fmt:
        print(f"\n[5] 导出为 {export_fmt.upper()}...")
        from src.utils.exporter import export_resume

        if output_path is None:
            base = os.path.splitext(os.path.basename(resume_path))[0]
            output_path = f"output/{base}_optimized"

        final_path = export_resume(state["refined_resume"], output_path, export_fmt)
        print(f"    导出完成: {final_path}")
    else:
        print("\n[5] 优化后简历预览:")
        print("-" * 40)
        print(state["refined_resume"][:2000])
        if len(state["refined_resume"]) > 2000:
            print(f"\n... (共 {len(state['refined_resume'])} 字符，已截断)")

    print("\n" + "=" * 60)
    print("全链路完成!")
    print("=" * 60)

    return state


def main():
    parser = argparse.ArgumentParser(description="AI-Resume-Evolver - 智能简历优化工具")
    parser.add_argument("-r", "--resume", required=True, help="简历文件路径 (.docx 或 .txt)")
    parser.add_argument("-j", "--jd", default=None, help="JD 文件路径 (.docx 或 .txt)，不指定则使用内置测试 JD")
    parser.add_argument("-e", "--export", choices=["docx", "pdf"], default=None, help="导出格式")
    parser.add_argument("-o", "--output", default=None, help="导出文件路径 (不含扩展名)")
    parser.add_argument("--server", action="store_true", help="启动 FastAPI 服务")

    args = parser.parse_args()

    if args.server:
        print("启动 FastAPI 服务: http://127.0.0.1:8001")
        uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)
    else:
        os.makedirs("output", exist_ok=True)
        run_pipeline(
            resume_path=args.resume,
            jd_path=args.jd,
            export_fmt=args.export,
            output_path=args.output,
        )


if __name__ == "__main__":
    main()
