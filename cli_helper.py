import os
import subprocess


def interactive_run():
    print("=" * 30)
    print("🚀 AI-Resume-Evolver 交互助手")
    print("=" * 30)

    # 1. 选择简历
    resume = input("\n1. 请输入简历文件名 (需放在 data/resumes 文件夹下，例如: 测试简历1.docx):\n> ").strip()
    resume_path = os.path.join("data", "resumes", resume)
    
    while not os.path.exists(resume_path):
        print(f"❌ 找不到文件: {resume_path}")
        resume = input("请重新输入简历文件名:\n> ").strip()
        resume_path = os.path.join("data", "resumes", resume)

    # 2. 选择 JD (可选)
    jd = input("\n2. 请输入目标岗位(JD)文件名 (直接回车则使用默认 JD):\n> ").strip()
    jd_arg = f"-j data/jds/{jd}" if jd else ""

    # 3. 选择导出格式
    format_choice = input("\n3. 请选择导出格式 (1: Word / 2: PDF / 回车: 仅预览):\n> ").strip()
    format_map = {"1": "docx", "2": "pdf"}
    export_format = format_map.get(format_choice, "")
    export_arg = f"-e {export_format}" if export_format else ""

    # 4. 指定输出名称
    output_name = input("\n4. 给优化后的文件起个名字 (直接回车则自动命名):\n> ").strip()
    output_arg = f"-o output/{output_name}" if output_name else ""

    # 拼接命令
    cmd = f"python main.py -r {resume_path} {jd_arg} {export_arg} {output_arg}"
    
    print("\n" + "=" * 30)
    print(f"⚙️  正在启动优化任务...")
    print(f"📝 执行命令: {cmd}")
    print("=" * 30 + "\n")

    # 执行命令
    subprocess.run(cmd, shell=True)


if __name__ == "__main__":
    interactive_run()