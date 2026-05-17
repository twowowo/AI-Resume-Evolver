import os
import sys
import time

sys.path.insert(0, os.path.abspath("."))

from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__) or ".", ".env")
load_dotenv(dotenv_path=env_path)

NODE_DISPLAY = {
    "retriever": "检索中...    (从 352 条金牌案例库匹配)",
    "tavily_search": "搜索中...    (联网获取企业/技术最新信息)",
    "editor": "重构中...    (DeepSeek 优化简历)",
}


def check_env():
    missing = []
    if not os.getenv("DEEPSEEK_API_KEY", "").strip():
        missing.append("DEEPSEEK_API_KEY")
    if not os.getenv("TAVILY_API_KEY", "").strip():
        missing.append("TAVILY_API_KEY")
    if missing:
        print(f"\n[ERROR] .env 中缺少必要密钥: {', '.join(missing)}")
        print("请在 .env 文件中配置后再启动，格式:")
        print("  DEEPSEEK_API_KEY=sk-xxxxxxxx")
        print("  TAVILY_API_KEY=tvly-xxxxxxxx")
        sys.exit(1)
    print("[CHECK] .env 密钥检查通过")


def list_files(directory, extensions=(".docx", ".txt")):
    os.makedirs(directory, exist_ok=True)
    return sorted(
        f for f in os.listdir(directory)
        if f.lower().endswith(extensions) and not f.startswith("~")
    )


def choose_file(label, directory):
    files = list_files(directory)
    if not files:
        print(f"\n[INFO] {directory} 中没有文件，请手动输入路径。")
        return input(f"{label}:\n> ").strip()

    print(f"\n{label}:")
    for i, f in enumerate(files, 1):
        print(f"  [{i}] {f}")
    print(f"  [0] 手动输入路径")

    while True:
        choice = input("> ").strip()
        if choice == "0":
            return input("请输入文件路径:\n> ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                path = os.path.join(directory, files[idx])
                print(f"  已选择: {path}")
                return path
        except ValueError:
            pass
        print("  无效选择，请重新输入。")


def load_file(path):
    from src.utils.loader import load_docx, load_txt
    if path.lower().endswith(".docx"):
        return load_docx(path)
    return load_txt(path)


def main():
    print("=" * 50)
    print("  AI-Resume-Evolver  全链路智能体")
    print("=" * 50)

    check_env()

    resume_path = choose_file(
        "选择简历文件 (data/resumes 目录)",
        os.path.join("data", "resumes"),
    )
    if not os.path.exists(resume_path):
        print(f"[ERROR] 文件不存在: {resume_path}")
        sys.exit(1)
    raw_resume = load_file(resume_path)
    print(f"  [OK] 简历加载: {len(raw_resume)} 字符")

    jd_path = choose_file(
        "选择 JD 文件 (data/jds 目录, 回车跳过使用默认)",
        os.path.join("data", "jds"),
    )
    if jd_path and os.path.exists(jd_path):
        target_jd = load_file(jd_path)
        print(f"  [OK] JD 加载: {len(target_jd)} 字符")
    else:
        target_jd = """职位：高级后端开发工程师 (Python/FastAPI方向)
要求：精通 Python FastAPI RAG 向量数据库 Docker Kubernetes
具备大模型应用开发经验，熟悉微服务架构
良好的沟通能力和团队协作精神"""
        print(f"  [OK] 使用默认 JD ({len(target_jd)} 字符)")

    format_choice = input(
        "\n选择导出格式:\n"
        "  [1] Word (.docx)\n"
        "  [2] PDF (.pdf)\n"
        "  [回车] 仅预览不导出\n"
        "> "
    ).strip()
    export_fmt = {"1": "docx", "2": "pdf"}.get(format_choice, None)

    output_base = input(
        "\n输出文件名 (不含扩展名, 回车自动命名):\n> "
    ).strip()
    if not output_base:
        stem = os.path.splitext(os.path.basename(resume_path))[0]
        output_base = f"output/{stem}_optimized"
    elif not output_base.startswith("output"):
        output_base = f"output/{output_base}"

    print("\n" + "=" * 50)
    print("  开始全链路优化")
    print("=" * 50)

    from src.graph import get_graph

    app = get_graph()
    initial = {
        "resume": raw_resume,
        "jd": target_jd,
        "rag_context": "",
        "revised_resume": "",
        "internal_monologue": "",
        "tool_outputs": [],
    }

    seen_nodes = set()
    t_start = time.time()

    print()
    for output in app.stream(initial, stream_mode="updates"):
        for node_name, _node_output in output.items():
            if node_name not in seen_nodes:
                seen_nodes.add(node_name)
                status = NODE_DISPLAY.get(
                    node_name, f"{node_name}..."
                )
                print(f"  [{len(seen_nodes)}/3] {status}")

    elapsed = time.time() - t_start

    final = app.invoke(initial)

    print(f"\n  [TIME] 全链路耗时: {elapsed:.1f} 秒")

    monologue = final.get("internal_monologue", "")

    print()
    print("*" * 55)
    print("*  Agent 内心独白 (internal_monologue)")
    print("*" * 55)
    for line in monologue.split("\n"):
        print(f"*  {line}")
    print("*" * 55)

    revised = final.get("revised_resume", "")
    if not revised.strip():
        print("\n[WARN] 优化输出为空，跳过导出。")
        return

    print(f"\n[RESULT] 优化后简历: {len(revised)} 字符")
    print("-" * 50)
    try:
        print(revised[:600])
    except UnicodeEncodeError:
        print(revised[:600].encode("ascii", errors="replace").decode("ascii"))
    if len(revised) > 600:
        print(f"\n... (共 {len(revised)} 字符)")

    if export_fmt:
        print(f"\n  [导出中...] 正在生成 {export_fmt.upper()} ...")
        from src.utils.exporter import export_resume
        try:
            final_path = export_resume(revised, output_base, export_fmt)
            print(f"  [OK] 导出成功: {os.path.abspath(final_path)}")
        except Exception as e:
            print(f"  [FAIL] 导出失败: {e}")
    else:
        print("\n[INFO] 未选择导出格式，已跳过文件生成。")

    print("\n" + "=" * 50)
    print("  全链路完成!")
    print("=" * 50)


if __name__ == "__main__":
    main()
