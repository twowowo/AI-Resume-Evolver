from src.utils.loader import load_docx, load_txt
from src.nodes.analyzer import jd_analyzer_node
from src.state import GraphState


def run_test():
    # 1. 加载素材 (确保你已经把文件放进了对应的 data 文件夹)
    resume_path = "data/resumes/测试简历1.docx"  # 或者换成 A_ZhangJingYing.docx
    jd_path = "data/jds/jd1.txt"

    print("--- 正在加载文件 ---")
    resume_text = load_docx(resume_path)
    jd_text = load_txt(jd_path)

    # 2. 构造初始状态
    initial_state: GraphState = {
        "raw_resume": resume_text,
        "target_jd": jd_text,
        "gap_list": [],
        "refined_resume": "",
        "feedback": "",
        "revision_count": 0
    }

    # 3. 运行第一个节点：分析 JD
    print("--- 运行 JD 分析节点 ---")
    final_state = jd_analyzer_node(initial_state)

    # 4. 打印结果
    print(f"简历内容预览 (前50字): {resume_text[:50]}...")
    print(f"JD 关键词提取结果: {final_state['gap_list']}")
    print(f"当前迭代次数: {final_state['revision_count']}")


if __name__ == "__main__":
    run_test()