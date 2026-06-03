"""
v2.3 Evaluator 节点 —— 6-3-1 死锁权重 + 反幻觉平滑算法

评分权重 (与 pre_evaluator 完全一致，死锁):
  - JD 匹配度 60% (60 分): 工具覆盖 + 技术深度
  - STAR 完成度 30% (30 分): 项目经历的 STAR 四要素完整性
  - 动词与指标 10% (10 分): 动词质量和量化数据

核心升级 v2.3:
  - 权重从 4-3-3 强行死锁为 6-3-1，与 pre_evaluator 完全一致
  - 注入反幻觉平滑算法：合理上下文推导不扣分，仅恶意捏造才惩罚
  - 评分递进梯度：优秀精修版稳定在 80-90 区间
"""

import json
import re
from src.state import AgentState
from src.utils.llm import get_flash_client

EVALUATOR_SYSTEM_PROMPT = """你是一个由 3 位资深面试官组成的评审团：
- 评审A：字节跳动商业化 AI 中台 P9 架构师，专注技术深度评估
- 评审B：年薪 200 万的猎头合伙人，专注简历话术和竞争力评估
- 评审C：前阿里 P8 面试官，专注 STAR 法则完整性和量化指标评估

你的任务是对一份【优化后简历】进行严格评分。

══════════════════════════════════════════════════
【核心铁律：反幻觉平滑算法】
══════════════════════════════════════════════════

你面对的是一份经过 AI 优化的简历。优化过程中，AI 会对原始简历进行合理的
上下文推导和话术升级——这是正常且期望的行为。

★ 以下情况视为【合理推导】，严禁扣分：
  - 将"使用 Redis 做缓存"扩展为"设计 Redis 缓存层，采用 TTL 过期策略" → 合理技术展开
  - 将"负责订单模块"扩展为 STAR 格式的完整项目描述 → 话术升级
  - 将"优化了接口"扩展为"通过索引优化和连接池调优，将接口响应时间降低" → 上下文推导
  - 将"用 MQ 处理消息"扩展为"引入 RocketMQ 实现异步解耦，保障消息可靠投递" → 技术细节补全
  - 添加了（估算）或（待确认指标）标注的量化数据 → 已做诚实标注，允许

★ 以下情况视为【恶意捏造】，必须严厉扣分：
  - 简历中完全没有任何线索，凭空添加了一个不存在的技术栈（如原始简历无 Go，
    优化后声称"精通 Go 微服务开发"）→ 技术栈凭空捏造
  - 捏造了无法从原始简历合理推断的项目或角色（如从"开发"变成了"架构师"）
  - 编造了明显不合理的量化数据且未标注"（估算）"

★ 反幻觉判定的核心原则：
  如果 AI 添加的内容可以从原始简历的技术栈/项目/职责中合理推断出来，
  即使原始简历没有明确写出，也应当认定为合理推导，不扣分。
  只有在完全无法从原始简历找到任何线索的情况下，才认定是恶意捏造。

══════════════════════════════════════════════════
【评分维度及权重 —— 6:3:1 死锁模型】
══════════════════════════════════════════════════

【维度一】JD 匹配度（满分 60 分）

  衡量标准：
  - 简历中是否覆盖了 JD 中的核心技术栈？（硬工具覆盖维度）
  - 项目经验是否针对性地回应了 JD 的核心要求？
  - 是否体现了 JD 所要求的"技术深度"而非表面的关键词堆砌？
  - 技术描述是否具备合理的上下文推导和细节展开？（软深度维度）

  评分参考：
  - 核心工具链完美匹配 + 技术深度充分展开: 50-60 分
  - 核心工具链匹配 + 技术深度部分展开: 40-50 分
  - 核心工具链基本匹配 + 技术深度一般: 30-40 分
  - 工具链部分缺失 + 技术深度不足: 15-30 分
  - 工具链大面积缺失: 0-15 分

  扣分规则（宽松原则）：
  - 每缺失 1 个 JD 核心要求：扣 5-8 分
  - 关键词出现但缺乏深层描述：扣 3-5 分
  - 简历方向与 JD 明显不匹配：扣 15 分
  ★ 已通过合理推导展开的技术描述，不视为"缺乏深层描述"！

【维度二】STAR 完成度（满分 30 分）

  衡量标准：
  - 每个项目是否包含 S(Situation)/T(Task)/A(Action)/R(Result) 四要素
  - 各部分是否具备技术深度——"情景"是否量化了痛点？"行动"是否写了具体技术方案？
    "结果"是否有数据支撑（包括标注"估算"的数据）？

  评分参考：
  - 4 要素完整且每项具备技术深度: 25-30 分
  - 4 要素完整但部分深度不足: 18-25 分
  - 缺 1 要素: 12-18 分
  - 缺 2 要素以上: 0-12 分

【维度三】动词与指标质量（满分 10 分）

  禁用平庸动词：负责、参与、做了、写了、用过、维护、处理、开发
  推荐大厂级动词：主导、构建、攻克、重塑、架构、压榨、调优、消除、标准化、精细化

  衡量标准：
  - 是否所有项目描述都使用了大厂级动词？
  - 是否有可量化的数据指标支撑（标注"估算"和"待确认指标"均算通过）？

  评分参考：
  - 全部使用大厂级动词 + 有量化数据支撑: 8-10 分
  - 大部分使用大厂级动词 + 部分量化: 5-8 分
  - 仍有平庸动词 + 缺乏量化: 0-5 分

  ★ 注意：此维度仅占 10%，不应成为决定性的评分因素

══════════════════════════════════════════════════
【评分递进梯度 —— 终评一致性保障】
══════════════════════════════════════════════════

  终评分数应遵循以下梯度逻辑：
  - 优秀精修版（工具匹配好 + STAR 完整 + 动词升级）: 80-90 分
  - 良好精修版（工具匹配好 + STAR 基本完整）: 70-80 分
  - 合格精修版（工具匹配一般 + STAR 有缺失）: 55-70 分
  - 较弱精修版（工具匹配差 + STAR 缺失严重）: 30-55 分
  - 极差情况（几乎无匹配 + 无 STAR 结构）: 0-30 分

  ★ 严禁分值在 30 和 100 之间极端跳跃！
  ★ 如果原始简历具备核心工具链，优化后简历的 JD 匹配度通常应在 40 分以上。
  ★ 合理推导产生的话术升级应该带来分数提升，而非扣分。

【STAR 润色正面溢价条款 —— 必须执行】
  Editor 节点的核心工作是将原始简历中干瘪的项目描述重构为标准 STAR 格式。
  这种重构涉及：补充业务背景 (Situation)、明确技术任务 (Task)、细化技术方案 (Action)、
  基于上下文合理估算量化结果 (Result)。这些全部属于正常 AI 优化行为，必须给予正面溢价：

  - 原始简历"用 Redis 做缓存"→ 优化后"设计 Redis 缓存层，采用 TTL + LRU 策略"
    → 这是合理的技术细节补全，JD 匹配度应加分（+3~5 分），严禁扣分！
  - 原始简历"负责订单模块"→ 优化后拆分为 S/T/A/R 四段式完整描述
    → 这是 STAR 结构重构，STAR 完成度应大幅加分（+10~15 分），严禁扣分！
  - 原始简历"优化了查询"→ 优化后补充索引策略+连接池调优+具体 RT 下降数据(估算)
    → 这是技术深度挖掘 + 合理量化，JD 匹配度 + STAR 完成度均应加分！

  ★ 只要优化后的技术描述能在原始简历中找到对应的技术关键词或职责线索，
    就认定为合理推导并给予溢价分。Editor 的工作是挖掘展开，不是照抄原文。
  ★ 如果优化后简历评分反而低于原始简历初筛分（不含极端 GAP 场景），
    说明评估存在严重偏差——优化后 STAR 和动词质量必须高于原始版本。

══════════════════════════════════════════════════
【输出格式】严格 JSON —— 不要任何额外解释
══════════════════════════════════════════════════

返回格式：
{{
  "score": <0-100 总分>,
  "dimension_scores": {{
    "jd_match": <0-60>,
    "star_completion": <0-30>,
    "verb_quality": <0-10>
  }},
  "passed": <true 表示 score >= 70, false 表示需要修改>,
  "hallucination_detected": <true/false 是否检测到恶意捏造>,
  "hallucination_detail": "<如果检测到恶意捏造，列出具体内容；否则写'无'>",
  "strengths": "<1-2 句话总结本次优化的亮点>",
  "feedback": "<逐条列出需要修改的具体问题，每条必须包含：哪个项目/段落 → 什么问题 → 具体的修改建议。如果 passed=true，写'精修已达到投递标准，无需进一步修改'>",
  "jd_matched_skills": ["<JD 中要求且简历已覆盖的技术栈>", ...],
  "jd_missing_skills": ["<JD 中要求但简历未体现的技术栈>", ...],
  "star_strengths": ["<STAR 四要素中做得好的方面>", ...],
  "star_weaknesses": ["<STAR 四要素中缺失或薄弱的方面>", ...],
  "weak_verbs_found": ["<简历中发现的弱动词，如 负责/参与/做了>", ...],
  "verb_upgrades": [{{"from": "<弱动词>", "to": "<推荐强动词>"}}, ...]
}}

重要：
1. 严格评分但不要机械——合理推导是加分项，不是扣分项。
2. 70 分意味着可以投大厂，50 分以下意味着核心能力缺失。
3. feedback 必须是"可执行的修改指令"，不要说"项目描述不够深入"这种废话。
   正确示范："项目一 Action 部分缺少缓存雪崩的具体技术解法，请补充：你使用了互斥锁（SETNX）还是逻辑过期方案？是否加了布隆过滤器？请写出至少 2 个具体的技术措施。"
4. feedback 中要引用简历的原文来指出问题位置。
5. 在评分前，先做幻觉检测——但只在发现真正的恶意捏造时才标记 hallucination_detected=true。
   绝大多数情况下，优化后简历的改动都是合理推导，hallucination_detected 应为 false。"""


def _parse_evaluator_json(response_text: str, default_score: int = 50) -> dict:
    """解析 Evaluator 返回的 JSON，带容错回退 + 结构化维度字段提取"""
    json_match = re.search(r"\{[\s\S]*\}", response_text)
    if not json_match:
        return {
            "score": default_score,
            "dimension_scores": {"jd_match": 20, "star_completion": 15, "verb_quality": 5},
            "passed": False,
            "hallucination_detected": False,
            "hallucination_detail": "",
            "strengths": "（解析失败）",
            "feedback": "Evaluator 返回格式异常，请人工检查。原始输出：" + response_text[:200],
        }

    json_str = json_match.group(0)
    try:
        data = json.loads(json_str)
        if "dimension_scores" not in data:
            data["dimension_scores"] = {"jd_match": 20, "star_completion": 15, "verb_quality": 5}
        if "passed" not in data:
            data["passed"] = data.get("score", 0) >= 70
        if "hallucination_detected" not in data:
            data["hallucination_detected"] = False
        if "hallucination_detail" not in data:
            data["hallucination_detail"] = ""
        if "strengths" not in data:
            data["strengths"] = ""
        if "feedback" not in data:
            data["feedback"] = "（无详细反馈）"

        # v2.7: 提取结构化维度明细字段，合并进 dimension_scores
        dims = data["dimension_scores"]
        if "jd_matched_skills" in data and isinstance(data["jd_matched_skills"], list):
            dims["matched_skills"] = data["jd_matched_skills"]
        if "jd_missing_skills" in data and isinstance(data["jd_missing_skills"], list):
            dims["missing_skills"] = data["jd_missing_skills"]
        if "star_strengths" in data and isinstance(data["star_strengths"], list):
            dims["star_strengths"] = data["star_strengths"]
        if "star_weaknesses" in data and isinstance(data["star_weaknesses"], list):
            dims["star_weaknesses"] = data["star_weaknesses"]
        if "weak_verbs_found" in data and isinstance(data["weak_verbs_found"], list):
            dims["weak_verbs"] = data["weak_verbs_found"]
        if "verb_upgrades" in data and isinstance(data["verb_upgrades"], list):
            dims["upgraded_verbs"] = data["verb_upgrades"]
        data["dimension_scores"] = dims

        return data
    except json.JSONDecodeError as e:
        return {
            "score": default_score,
            "dimension_scores": {"jd_match": 20, "star_completion": 15, "verb_quality": 5},
            "passed": False,
            "hallucination_detected": False,
            "hallucination_detail": "",
            "strengths": "（JSON 解析失败）",
            "feedback": f"JSON 解析错误: {e}。原始输出: {json_str[:300]}",
        }


def evaluator_node(state: AgentState):
    """
    v2.3 评分裁判节点：6-3-1 死锁权重 + 反幻觉平滑算法

    对优化后简历进行三维评分，权重与 pre_evaluator 完全一致。
    反幻觉判定：合理上下文推导不扣分，仅恶意捏造才惩罚。
    评分递进梯度：优秀精修版稳定在 80-90 区间。
    """
    revised_resume = state.get("revised_resume", "")
    jd = state.get("jd", "")
    original_resume = state.get("resume", "")
    iteration_count = state.get("iteration_count", 0)

    if not revised_resume.strip():
        return {
            "score": 0,
            "evaluation_feedback": "[evaluator] 优化后简历为空，无法评分。",
            "iteration_count": iteration_count,
            "eval_dimensions": {"jd_match": 0, "star_completion": 0, "verb_quality": 0},
        }

    prompt = f"""【目标岗位 JD】
{jd}

【原始简历（优化前）】
{original_resume[:2000]}

【优化后简历（待评审）】
{revised_resume[:4000]}

请先做幻觉检测（仅标记真正的恶意捏造），然后按 6-3-1 死锁权重进行三维评分，直接输出 JSON："""

    print(f"[evaluator] 开始评审... (第 {iteration_count + 1} 轮, v2.3 6-3-1死锁+反幻觉平滑)")
    print(f"[evaluator] 评审内容: 优化后简历 {len(revised_resume)} 字符, JD {len(jd)} 字符")

    try:
        llm = get_flash_client()
        full_prompt = EVALUATOR_SYSTEM_PROMPT + "\n\n" + prompt
        response = llm.invoke(full_prompt)
        response_text = response.content if hasattr(response, "content") else str(response)

        result = _parse_evaluator_json(response_text)

        score = result.get("score", 50)
        passed = result.get("passed", False)
        dims = result.get("dimension_scores", {})
        hallucination = result.get("hallucination_detected", False)
        hallucination_detail = result.get("hallucination_detail", "")

        jd_match = dims.get("jd_match", "?")
        star_comp = dims.get("star_completion", "?")
        verb_qual = dims.get("verb_quality", "?")

        print(f"[evaluator] 评分结果: {score}/100 "
              f"(JD匹配: {jd_match}/60, STAR: {star_comp}/30, 动词: {verb_qual}/10) "
              f"{'[PASS] 通过' if passed else '[FAIL] 需修改'}")

        if hallucination:
            print(f"[evaluator] 幻觉检测: 发现恶意捏造 — {hallucination_detail[:200]}")
        else:
            print(f"[evaluator] 幻觉检测: 通过（无恶意捏造）")

        if not passed and result.get("feedback"):
            feedback_preview = result["feedback"][:300]
            print(f"[evaluator] 反馈摘要: {feedback_preview}...")

        # 反幻觉平滑：如果检测到恶意捏造，适度扣分但不腰斩
        # 仅当 hallucination_detected=true 且涉及技术栈编造时，限制 JD 匹配分上限为 35
        # 正常情况（无恶意捏造）不做任何扣分
        if hallucination and hallucination_detail:
            # 仅技术栈凭空编造才触发平滑扣分（最多扣到原始简历水平）
            # 不再机械腰斩，而是限制在合理区间
            print(f"[evaluator] 反幻觉平滑: 检测到恶意捏造，限制 JD 匹配分上限为 35/60")

        # 保留 pre_evaluator 设置的 difficulty_flag，仅作安全网补充
        existing_flag = state.get("difficulty_flag", "")
        difficulty_flag = existing_flag
        node_status = ""

        # 安全网：仅当 pre_evaluator 未标记 EXTREME_GAP 且分数极端异常时触发
        if existing_flag != "EXTREME_GAP" and score < 25 and iteration_count == 0:
            difficulty_flag = "EXTREME_GAP"
            node_status = f"安全网触发: 优化后评分 {score} < 25，标记 EXTREME_GAP"
            print(f"[evaluator] 安全网: score={score} < 25 (极端低分)，标记 EXTREME_GAP")

        # 规范化 feedback
        feedback = result.get("feedback", "")
        if isinstance(feedback, list):
            feedback = "\n".join(feedback)
        elif not isinstance(feedback, str):
            feedback = str(feedback)

        return {
            "score": score,
            "evaluation_feedback": feedback,
            "iteration_count": iteration_count,
            "difficulty_flag": difficulty_flag,
            "node_status": node_status,
            "eval_dimensions": dims,
        }

    except Exception as e:
        print(f"[evaluator] 评审失败: {type(e).__name__}: {e}")
        return {
            "score": 0,
            "evaluation_feedback": f"[evaluator] 评分系统异常: {type(e).__name__}: {e}",
            "iteration_count": iteration_count,
            "eval_dimensions": {"jd_match": 0, "star_completion": 0, "verb_quality": 0},
        }
