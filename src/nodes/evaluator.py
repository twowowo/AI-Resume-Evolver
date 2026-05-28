"""
v2.0-alpha Evaluator 节点 —— 面试官 + 猎头评审团

三维评分：
- JD 匹配度 (40%): 简历覆盖了多少 JD 核心要求
- STAR 完成度 (30%): 每个项目是否完整包含 S/T/A/R
- 动词与指标 (30%): 是否杜绝平庸动词，是否有量化数据

输出严格 JSON，包含 score / dimension_scores / feedback。
"""

import json
import re
from src.state import AgentState
from src.utils.llm import get_flash_client

EVALUATOR_SYSTEM_PROMPT = """你是一个由 3 位资深面试官组成的评审团：
- 评审A：字节跳动商业化 AI 中台 P9 架构师，专注技术深度评估
- 评审B：年薪 200 万的猎头合伙人，专注简历话术和竞争力评估
- 评审C：前阿里 P8 面试官，专注 STAR 法则完整性和量化指标评估

你的任务是对一份【优化后简历】进行严格评分。评分维度及权重：

══════════════════════════════════
【维度一】JD 匹配度（满分 40 分）
══════════════════════════════════
衡量标准：
- 简历中是否覆盖了 JD 中的核心技术栈？
- 项目经验是否针对性地回应了 JD 的核心要求？
- 是否体现了 JD 所要求的"技术深度"而非表面的关键词堆砌？

扣分规则：
- 每缺失 1 个 JD 核心要求：扣 5-8 分
- 关键词出现但缺乏深层描述：扣 3 分
- 简历方向与 JD 明显不匹配：扣 15 分

══════════════════════════════════
【维度二】STAR 完成度（满分 30 分）
══════════════════════════════════
衡量标准：
- 每个项目是否包含 S (Situation 情景)、T (Task 任务)、A (Action 行动)、R (Result 结果)
- 各部分是否具备技术深度——"情景"是否量化了痛点？"行动"是否写了具体技术方案？"结果"是否有数据支撑？

扣分规则：
- 缺失任一部分：扣 5 分
- 描述空洞（如"做了优化"但没有写怎么优化）：扣 3 分
- 全部项目都没有 STAR 结构：扣 20 分

══════════════════════════════════
【维度三】动词与指标质量（满分 30 分）
══════════════════════════════════
禁用平庸动词：负责、参与、做了、写了、用过、维护、处理、开发
必须升级为大厂级动词：主导、构建、攻克、重塑、架构、压榨、调优、消除、标准化、精细化

衡量标准：
- 是否所有项目描述都使用了大厂级动词？
- 是否有可量化的数据指标支撑（即使标注"估算"也算通过）？

扣分规则：
- 每发现 1 个禁用动词：扣 3 分
- 项目完全缺少量化数据：扣 5 分
- 量化数据明显不合理（如"QPS 提升 9999%"）：扣 2 分

══════════════════════════════════
【输出格式】严格 JSON —— 不要任何额外解释
══════════════════════════════════

返回格式：
{{
  "score": <0-100 总分>,
  "dimension_scores": {{
    "jd_match": <0-40>,
    "star_completion": <0-30>,
    "verb_quality": <0-30>
  }},
  "passed": <true 表示 score >= 70，false 表示需要修改>,
  "strengths": "<1-2 句话总结本次优化的亮点>",
  "feedback": "<逐条列出需要修改的具体问题，每条必须包含：哪个项目/段落 → 什么问题 → 具体的修改建议。如果 passed=true，写'无需修改'>"
}}

重要：
1. 严格评分，不要放水。70 分意味着可以投大厂，50 分以下意味着核心能力缺失。
2. feedback 必须是"可执行的修改指令"，不要说"项目描述不够深入"这种废话。
   正确示范："项目一 Action 部分缺少缓存雪崩的具体技术解法，请补充：你使用了互斥锁（SETNX）还是逻辑过期方案？是否加了布隆过滤器？请写出至少 2 个具体的技术措施。"
3. feedback 中要引用简历的原文来指出问题位置。
"""


def _parse_evaluator_json(response_text: str, default_score: int = 50) -> dict:
    """解析 Evaluator 返回的 JSON，带容错回退"""
    # 尝试提取 JSON 块
    json_match = re.search(r"\{[\s\S]*\}", response_text)
    if not json_match:
        return {
            "score": default_score,
            "dimension_scores": {"jd_match": 15, "star_completion": 15, "verb_quality": 15},
            "passed": False,
            "strengths": "（解析失败）",
            "feedback": "Evaluator 返回格式异常，请人工检查。原始输出：" + response_text[:200],
        }

    json_str = json_match.group(0)
    try:
        data = json.loads(json_str)
        # 容错：补全缺失字段
        if "dimension_scores" not in data:
            data["dimension_scores"] = {"jd_match": 15, "star_completion": 15, "verb_quality": 15}
        if "passed" not in data:
            data["passed"] = data.get("score", 0) >= 70
        if "strengths" not in data:
            data["strengths"] = ""
        if "feedback" not in data:
            data["feedback"] = "（无详细反馈）"
        return data
    except json.JSONDecodeError as e:
        return {
            "score": default_score,
            "dimension_scores": {"jd_match": 15, "star_completion": 15, "verb_quality": 15},
            "passed": False,
            "strengths": "（JSON 解析失败）",
            "feedback": f"JSON 解析错误: {e}。原始输出: {json_str[:300]}",
        }


def evaluator_node(state: AgentState):
    """评分裁判节点：对优化后简历进行三维评分"""
    revised_resume = state.get("revised_resume", "")
    jd = state.get("jd", "")
    original_resume = state.get("resume", "")
    iteration_count = state.get("iteration_count", 0)

    if not revised_resume.strip():
        return {
            "score": 0,
            "evaluation_feedback": "[evaluator] 优化后简历为空，无法评分。",
            "iteration_count": iteration_count,
        }

    prompt = f"""【目标岗位 JD】
{jd}

【原始简历】
{original_resume[:2000]}

【优化后简历】
{revised_resume[:4000]}

请按照评审标准进行三维评分，直接输出 JSON："""

    print(f"[evaluator] 开始评审... (第 {iteration_count + 1} 轮)")
    print(f"[evaluator] 评审内容: 简历 {len(revised_resume)} 字符, JD {len(jd)} 字符")

    try:
        llm = get_flash_client()
        full_prompt = EVALUATOR_SYSTEM_PROMPT + "\n\n" + prompt
        response = llm.invoke(full_prompt)
        response_text = response.content if hasattr(response, "content") else str(response)

        result = _parse_evaluator_json(response_text)

        score = result.get("score", 50)
        passed = result.get("passed", False)
        dims = result.get("dimension_scores", {})

        print(f"[evaluator] 评分结果: {score}/100 "
              f"(JD匹配: {dims.get('jd_match', '?')}/40, "
              f"STAR: {dims.get('star_completion', '?')}/30, "
              f"动词: {dims.get('verb_quality', '?')}/30) "
              f"{'✓ 通过' if passed else '✗ 需修改'}")

        if not passed and result.get("feedback"):
            feedback_preview = result["feedback"][:300]
            print(f"[evaluator] 反馈摘要: {feedback_preview}...")

        return {
            "score": score,
            "evaluation_feedback": result.get("feedback", ""),
            "iteration_count": iteration_count,
        }

    except Exception as e:
        print(f"[evaluator] 评审失败: {type(e).__name__}: {e}")
        return {
            "score": 0,
            "evaluation_feedback": f"[evaluator] 评分系统异常: {type(e).__name__}: {e}",
            "iteration_count": iteration_count,
        }
