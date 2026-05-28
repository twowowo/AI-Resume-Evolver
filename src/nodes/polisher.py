"""
v2.0-alpha Polisher 节点 —— 精准外科式简历精修

与 Editor 的区别：
- Editor: 粗优化，从零开始重写整份简历
- Polisher: 精修，只针对 Evaluator 反馈的问题进行靶向修改

使用 DeepSeek-V4-Pro + Thinking 模式，死磕具体问题。
"""

import os
from src.state import AgentState
from src.utils.llm import get_pro_client


POLISHER_SYSTEM_PROMPT = """你是一位年薪 200 万的顶级简历精修师，你的任务不是重写整份简历，
而是【仅针对评审团指出的具体问题】进行精准外科手术式修改。

核心原则：
1. 只改被评审团点名的问题，不要画蛇添足改其他部分
2. 保留原简历中评审团认可的优点
3. 每个修改必须有明确的目的 —— 解决一个具体被扣分的问题
4. 修改后必须让评审团下次打分时找不到同样的问题
5. 【结构铁律】在根据裁判意见补充技术细节时，必须严格保持原有简历整体 STAR 结构的紧凑性与段落逻辑。严禁无限制灌水和盲目堆砌字数——每增加一段文字必须有清晰的"解决哪个扣分点"的对应关系。保持已有技术优势与核心骨架不变，只做靶向修补。

【评审团的反馈 —— 这是你必须修复的问题清单】：
{evaluation_feedback}

修改要求：
- 如果评审说"缺少 STAR 某一部分" → 补全该部分，详细到具体技术方案
- 如果评审说"动词平庸" → 替换全部禁用动词为大厂级动词
- 如果评审说"缺少量化指标" → 基于技术场景合理估算并标"（估算）"
- 如果评审说"技术深度不足" → 补充 2-3 层技术细节（不要只写做了什么，要写怎么做的、为什么这么做、踩了什么坑）

【目标 JD —— 用于对齐需求】：
{jd}

【原优化后简历 —— 这是你的修改基础】：
{revised_resume}

【原始简历 —— 用于核实信息不编造】：
{original_resume}

请直接输出修改后的完整简历（保持原有结构，只修改被点名的问题部分）："""


def polisher_node(state: AgentState):
    """精修节点：只针对 Evaluator 反馈的问题进行靶向修改"""
    revised_resume = state.get("revised_resume", "")
    jd = state.get("jd", "")
    original_resume = state.get("resume", "")
    feedback = state.get("evaluation_feedback", "")
    iteration_count = state.get("iteration_count", 0)

    if not revised_resume.strip():
        return {
            "revised_resume": revised_resume,
            "internal_monologue": "[polisher] 无内容可精修。",
            "iteration_count": iteration_count + 1,
        }

    if not feedback.strip():
        return {
            "revised_resume": revised_resume,
            "internal_monologue": "[polisher] 无评审反馈，无需精修。",
            "iteration_count": iteration_count + 1,
        }

    prompt = POLISHER_SYSTEM_PROMPT.format(
        evaluation_feedback=feedback,
        jd=jd,
        revised_resume=revised_resume,
        original_resume=original_resume[:3000],
    )

    print(f"[polisher] 开始精修... (第 {iteration_count + 1} 轮)")
    print(f"[polisher] 修复目标: {feedback[:200]}...")

    try:
        llm = get_pro_client()
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        polished = content.strip()

        # 提取 thinking（如果有）
        thinking = ""
        if hasattr(response, "additional_kwargs") and response.additional_kwargs:
            thinking = response.additional_kwargs.get("thinking", "")
        elif hasattr(response, "response_metadata") and response.response_metadata:
            thinking = response.response_metadata.get("thinking", "")

        if thinking:
            print(f"[polisher] Thinking ({len(thinking)} 字符): {thinking[:300]}...")

        print(f"[polisher] 精修完成，输出 {len(polished)} 字符")

        return {
            "revised_resume": polished,
            "internal_monologue": f"[polisher 第{iteration_count + 1}轮] 针对评审反馈进行了精修。\n反馈要点: {feedback[:300]}",
            "iteration_count": iteration_count + 1,
        }

    except Exception as e:
        print(f"[polisher] 精修失败: {type(e).__name__}: {e}")
        return {
            "revised_resume": revised_resume,
            "internal_monologue": f"[polisher] 精修异常 ({type(e).__name__})，保留上一版本。",
            "iteration_count": iteration_count + 1,
        }
