"""
v2.2 PreEvaluator 节点 —— 6-3-1 硬核极客权重 + CS 抽象层级对齐

评分权重:
  - JD 匹配度 60% (60 分): 技术栈与业务领域的语义层级匹配
  - STAR 完成度 30% (30 分): 项目经历的 STAR 四要素完整性
  - 动词与指标 10% (10 分): 动词质量和量化数据

核心升级: 计算机科学抽象层级对齐框架，取代字面关键词机械匹配。
"""

import json
import re
from src.state import AgentState
from src.utils.llm import get_flash_client

PRE_EVALUATOR_SYSTEM_PROMPT = """你是一位严格的简历初审官。你的任务是评估一份【原始简历】（未经过任何 AI 优化）与目标 JD 的匹配程度。

══════════════════════════════════
【计算机科学抽象层级对齐框架】
══════════════════════════════════

在进行 JD 匹配度评估前，你必须先对候选人进行抽象层级定位。技术能力存在天然的层级关系：

第 4 层 —— 基础设施 / 系统级 (Infrastructure / Systems)
  特征：分布式系统底座、高性能中间件源码级改造、多活架构、系统级语言(C/Rust/C++)、
       内核/网络协议栈调优、自研存储引擎、大规模集群调度
  标志信号：提到"从零构建"、"源码级"、"分布式一致性"、"百亿级"、"多活"、"定制化优化底层"

第 3 层 —— 架构级 (Architecture)
  特征：微服务拆分与治理、数据库分库分表与读写分离、缓存穿透/击穿/雪崩多级防护、
       消息队列异步解耦与事务最终一致性、全链路压测与监控、云原生容器化编排
  标志信号：提到"架构设计"、"读写分离"、"多级缓存"、"幂等性"、"全链路"、"熔断降级"

第 2 层 —— 应用框架级 (Application / Framework)
  特征：使用主流 Web/ORM/RPC 框架进行业务开发、RESTful API 设计、关系型数据库 CRUD、
       基础缓存与消息队列的使用、Docker 容器化部署、单元测试与 CI/CD 流水线
  标志信号：提到具体框架名(如 FastAPI/Django/Spring)、"CRUD"、"RESTful"、"Docker 部署"

第 1 层 —— 工具使用级 (Tool / Scripting)
  特征：脚本编写、简单网页增删改查、基础 Linux 命令、Excel 数据处理
  标志信号：提到"Word/Excel"、"网页增删改查"、"能跑起来"、"没有报错"

【层级兼容核心规则】：
- 高层级天然向下兼容覆盖低层级。一个处于第 4 层的候选人，即使简历中没有明确列出某个
  第 2 层的具体框架名，也应当判定为其具备该框架的快速掌握能力。
- 评估 JD 匹配时，你必须从语义和底层架构上判断：候选人所展示的技术深度属于哪个层级，
  JD 所要求的核心技术栈属于哪个层级。如果候选人层级 >= JD 要求层级，即使具体关键词
  不完全一致，也应当给予较高的 JD 匹配度分数。
- 严禁机械式的字面关键词强匹配：不要因为候选人写了"分布式一致性协议"而没写"FastAPI"
  就大幅扣分——前者在抽象层级上远高于后者。

══════════════════════════════════
【评分维度及权重 —— 6:3:1 极客模型】
══════════════════════════════════

【维度一】技术栈 JD 匹配度（满分 60 分）
  评估流程:
  1. 先用"抽象层级对齐框架"定位候选人的核心层级
  2. 再用"抽象层级对齐框架"定位 JD 要求的核心层级
  3. 判断层级覆盖关系，给予匹配度评分
     - 候选人层级明显高于 JD 要求: 45-60 分 (向下兼容，快速上手)
     - 候选人层级与 JD 要求同级且关键词对齐: 40-55 分
     - 候选人层级与 JD 要求同级但关键词部分对齐: 25-40 分
     - 候选人层级低于 JD 要求 1 层: 10-25 分 (存在显著技能断层)
     - 候选人层级低于 JD 要求 2 层以上: 0-10 分 (几乎不可跨越)
  4. 业务领域相关性作为辅助加权因子（如供应链、金融、电商等垂直领域经验）

【维度二】STAR 完成度（满分 30 分）
  - 每个项目经历是否包含 S(Situation)/T(Task)/A(Action)/R(Result) 四要素
  - Action 部分是否具备技术深度——写了怎么做、为什么这么做
  - 原始简历通常严重缺失 Situation 和 Result
  - 评分参考: 4 要素完整(25-30), 缺 1 要素(15-25), 缺 2 要素(5-15), 几乎全缺(0-5)

【维度三】动词与指标质量（满分 10 分）
  - 是否使用有影响力的动词（非"负责/参与/做了"）
  - 是否包含任何量化数据
  - 注意：此维度仅占 10%，不应成为决定性的评分因素

══════════════════════════════════
【输出格式】严格 JSON —— 不要任何额外解释
══════════════════════════════════

{{
  "score": <0-100 总分>,
  "dimension_scores": {{
    "jd_match": <0-60>,
    "star_completion": <0-30>,
    "verb_quality": <0-10>
  }},
  "difficulty_flag": <"EXTREME_GAP" | "NORMAL">,
  "candidate_tier": <1-4 候选人的抽象层级>,
  "jd_tier": <1-4 JD 要求的抽象层级>,
  "tier_assessment": "<1句话说明层级判定依据>",
  "feedback": "<列出最关键的 2-3 个问题>"
}}

difficulty_flag 判定规则:
- score < 30: "EXTREME_GAP"（绝望差距，需防幻觉骨架模式）
- score >= 30: "NORMAL"（正常可优化）

重要：不要手软，但也不要做机械式的字面关键词匹配。用抽象层级思维评估候选人。"""


def _parse_pre_eval_json(response_text: str, default_score: int = 20) -> dict:
    """解析 PreEvaluator 返回的 JSON，适配 6-3-1 权重"""
    json_match = re.search(r"\{[\s\S]*\}", response_text)
    if not json_match:
        return {
            "score": default_score,
            "dimension_scores": {"jd_match": 5, "star_completion": 5, "verb_quality": 3},
            "difficulty_flag": "EXTREME_GAP",
            "candidate_tier": 1,
            "jd_tier": 2,
            "tier_assessment": "（解析失败）",
            "feedback": "PreEvaluator 返回格式异常。原始输出：" + response_text[:200],
        }

    json_str = json_match.group(0)
    try:
        data = json.loads(json_str)
        if "dimension_scores" not in data:
            data["dimension_scores"] = {"jd_match": 10, "star_completion": 8, "verb_quality": 3}
        if "difficulty_flag" not in data:
            score = data.get("score", 0)
            data["difficulty_flag"] = "EXTREME_GAP" if score < 30 else "NORMAL"
        if "candidate_tier" not in data:
            data["candidate_tier"] = 0
        if "jd_tier" not in data:
            data["jd_tier"] = 0
        if "tier_assessment" not in data:
            data["tier_assessment"] = ""
        if "feedback" not in data:
            data["feedback"] = "（无详细反馈）"
        return data
    except json.JSONDecodeError:
        return {
            "score": default_score,
            "dimension_scores": {"jd_match": 8, "star_completion": 8, "verb_quality": 3},
            "difficulty_flag": "EXTREME_GAP",
            "candidate_tier": 1,
            "jd_tier": 2,
            "tier_assessment": "（JSON 解析失败）",
            "feedback": f"JSON 解析错误。原始输出: {json_str[:300]}",
        }


def pre_evaluator_node(state: AgentState):
    """
    v2.2 前置分诊节点：6-3-1 权重 + CS 抽象层级对齐

    仅做 difficulty_flag 标记，不进行路由退出。
    所有简历无条件进入 Editor（路由由 graph.pre_eval_routing 决定）。

    输入：resume (原始简历), jd
    输出：score, difficulty_flag, node_status
    """
    resume = state.get("resume", "")
    jd = state.get("jd", "")

    if not resume.strip():
        return {
            "score": 0,
            "difficulty_flag": "EXTREME_GAP",
            "node_status": "原始简历为空，标记为 EXTREME_GAP",
        }

    prompt = f"""【目标岗位 JD】
{jd}

【原始简历（未经过任何优化）】
{resume[:3000]}

请按照 6-3-1 权重和抽象层级框架对这份原始简历进行严格评分，直接输出 JSON："""

    print(f"[pre_evaluator] 开始原始简历初审 (6-3-1 权重 + CS 抽象层级对齐)...")
    print(f"[pre_evaluator] 原始简历 {len(resume)} 字符, JD {len(jd)} 字符")

    try:
        llm = get_flash_client()
        full_prompt = PRE_EVALUATOR_SYSTEM_PROMPT + "\n\n" + prompt
        response = llm.invoke(full_prompt)
        response_text = response.content if hasattr(response, "content") else str(response)

        result = _parse_pre_eval_json(response_text)

        score = result.get("score", 20)
        dims = result.get("dimension_scores", {})
        difficulty_flag = result.get("difficulty_flag", "NORMAL")
        candidate_tier = result.get("candidate_tier", 0)
        jd_tier = result.get("jd_tier", 0)
        tier_assessment = result.get("tier_assessment", "")
        feedback = result.get("feedback", "")

        print(f"[pre_evaluator] 初审评分: {score}/100 "
              f"(JD匹配: {dims.get('jd_match', '?')}/60, "
              f"STAR: {dims.get('star_completion', '?')}/30, "
              f"动词: {dims.get('verb_quality', '?')}/10)")
        print(f"[pre_evaluator] 抽象层级: 候选人 L{candidate_tier} vs JD L{jd_tier} "
              f"({tier_assessment[:80] if tier_assessment else 'N/A'})")

        if difficulty_flag == "EXTREME_GAP":
            print(f"[pre_evaluator] 分诊: EXTREME_GAP (score={score} < 30) -> 防幻觉骨架模式")
        else:
            print(f"[pre_evaluator] 分诊: NORMAL (score={score} >= 30) -> 正常精修模式")

        return {
            "score": score,
            "difficulty_flag": difficulty_flag,
            "node_status": tier_assessment or f"L{candidate_tier} vs JD L{jd_tier}, 评分 {score}/100",
            "evaluation_feedback": feedback,
        }

    except Exception as e:
        print(f"[pre_evaluator] 初审失败: {type(e).__name__}: {e}")
        return {
            "score": 0,
            "difficulty_flag": "EXTREME_GAP",
            "node_status": f"PreEvaluator 异常: {type(e).__name__}",
            "evaluation_feedback": "",
        }
