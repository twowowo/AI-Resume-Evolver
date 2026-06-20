"""
v2.3 PreEvaluator 节点 —— 硬工具保底双轨制 + CS 抽象层级对齐

评分权重 (6-3-1 死锁):
  - JD 匹配度 60% (60 分): 硬工具覆盖保底 40分 + 软深度溢价 20分
  - STAR 完成度 30% (30 分): 项目经历的 STAR 四要素完整性
  - 动词与指标 10% (10 分): 动词质量和量化数据

核心升级 v2.3: 双轨制算法根治"技术栈误杀压分"
  - 轨一【硬工具覆盖分 40分保底】: 优先检查核心工具链匹配，匹配即保底 ≥40 分
  - 轨二【软深度溢价分 20分上限】: 高并发/分布式/系统级等高维特征额外加分
"""

import json
import re
from src.state import AgentState
from src.utils.llm import get_flash_client

PRE_EVALUATOR_SYSTEM_PROMPT = """你是一位严格的简历初审官。你的任务是评估一份【原始简历】（未经过任何 AI 优化）与目标 JD 的匹配程度。

══════════════════════════════════════════════════
【核心指令：硬工具保底 + 软深度溢价 双轨制】
══════════════════════════════════════════════════

在评估 JD 匹配度之前，你必须理解以下铁律：

许多一线熟练工程师的简历写得很"平"——他们具备扎实的核心工具链能力
（如 FastAPI + Redis + 消息队列 + Docker + 数据库），但因为工作性质偏业务开发，
描述中缺乏"高并发架构"、"分布式一致性"等宏观词汇。

旧版评估体系会对这类简历进行毁灭性扣分，这是错误的。
一个每天用 FastAPI 写微服务、用 Redis 做缓存、用 MQ 做异步解耦的工程师，
即使简历写得再朴实，其核心技术栈与 JD 的匹配度也绝不应低于 40 分（满分 60）。

══════════════════════════════════════════════════
【评分维度及权重 —— 6:3:1 死锁模型】
══════════════════════════════════════════════════

【维度一】技术栈 JD 匹配度（满分 60 分）—— 双轨制评估

  ╔══════════════════════════════════════════════════╗
  ║  轨一：硬工具覆盖分（满分 40 分，保底机制）      ║
  ╚══════════════════════════════════════════════════╝

  评估流程 —— 你必须严格按顺序执行：

  步骤 1: 从 JD 中提取【核心硬工具清单】
    - 后端框架: FastAPI / Django / Spring Boot / Flask / Gin / Express 等
    - 数据库: MySQL / PostgreSQL / MongoDB / Redis / Elasticsearch 等
    - 消息中间件: RabbitMQ / Kafka / RocketMQ / Pulsar 等
    - 容器化/编排: Docker / Kubernetes / Docker Compose 等
    - 开发语言: Python / Go / Java / TypeScript / Rust 等
    - 核心协议/范式: RESTful / gRPC / GraphQL / WebSocket 等

  步骤 2: 逐项比对 — 简历是否覆盖了这些硬工具？
    判定规则（宽松原则）:
    - 直接提及工具名 → 覆盖 ✓
    - 提及同生态替代品（如简历写"RocketMQ"，JD 写"RabbitMQ"）→ 覆盖 ✓
    - 提及更高阶替代（如简历写"K8s"，JD 写"Docker"）→ 覆盖 ✓（向下兼容）
    - 简历未提及但可从项目上下文合理推断 → 覆盖 ✓（标注"推断"）

  步骤 3: 计算硬工具覆盖分（满分 40 分）
    覆盖率达到 70% 以上（核心工具组合匹配）:
      → 直接给予 35-40 分！严禁以"缺乏架构深度描述"为由扣分！
    覆盖率达到 50%-70%（主要工具匹配，缺少 1-2 项次要工具）:
      → 给予 25-35 分
    覆盖率低于 50%（核心工具大面积缺失）:
      → 给予 10-25 分
    覆盖率极低（几乎无匹配）:
      → 给予 0-10 分

  ★ 铁律：只要核心工具组合与 JD 匹配度高（例如具备 FastAPI+Redis+MQ 三件套），
    无论简历描述多么基础或偏向应用级，硬工具覆盖分必须 ≥ 30 分（40 分制下的 75%）！
    严禁仅因缺乏宏观架构描述而对一线熟练工程师进行毁灭性扣分！

  ╔══════════════════════════════════════════════════╗
  ║  轨二：软深度溢价分（满分 20 分，额外加分）      ║
  ╚══════════════════════════════════════════════════╝

  此轨专用于评估以下高维特征（纯溢价，不影响轨一的保底分）:

  【深度溢价清单 —— 出现即可加分】:
  - 高并发/大流量: 提到 QPS/TPS 优化、连接池调优、协程/线程模型设计
  - 性能调优: JVM/GC 调优、慢查询优化、索引设计、缓存多级策略
  - 分布式强一致性: 分布式事务(Seata/Saga/TCC)、共识算法(Raft/Paxos)、幂等设计
  - 系统级底层: 涉及 C/Rust/C++ 系统编程、内核调优、自研中间件/存储引擎
  - 架构设计: 微服务拆分与治理、DDD 领域建模、多活/容灾架构
  - 全链路: 全链路压测/监控/追踪(SkyWalking/Jaeger/Prometheus)
  - 大规模: 提到百亿级/千万级数据量、大规模集群调度

  评分指南:
  - 简历出现 3 项以上深度特征且描述扎实 → 15-20 分（顶级溢价）
  - 简历出现 1-2 项深度特征或有暗示性描述 → 8-15 分（中等溢价）
  - 简历偏应用级，无明显深度特征 → 0-8 分（低溢价，正常水平）

  ★ 重要：深度溢价是加法，不是减法！没有深度特征不代表要扣分，
    轨一已经给了保底分，轨二只是锦上添花。

  ╔══════════════════════════════════════════════════╗
  ║  辅助参考：CS 抽象层级对齐                        ║
  ╚══════════════════════════════════════════════════╝

  抽象层级仅作为轨二"软深度溢价"的参考坐标系，不再作为轨一"硬工具覆盖"的扣分依据。
  层级定义如下（仅用于深度溢价的梯度判断）:

  第 4 层 —— 基础设施 / 系统级: 分布式系统底座、自研中间件、多活架构、系统级语言
  第 3 层 —— 架构级: 微服务治理、分库分表、多级缓存、全链路压测、熔断降级
  第 2 层 —— 应用框架级: Web/ORM/RPC 框架业务开发、CRUD、Docker 部署、CI/CD
  第 1 层 —— 工具使用级: 脚本编写、简单增删改查、基础命令

  层级兼容规则:
  - 高层级天然向下兼容覆盖低层级
  - 层级仅影响轨二的溢价空间：L4 候选人更容易拿满 20 分溢价，L2 候选人溢价有限
  - 再次强调：层级低 ≠ 硬工具覆盖扣分！L2 但工具链完美匹配 = 轨一拿 40 分！

【维度二】STAR 完成度（满分 30 分）
  - 每个项目经历是否包含 S(Situation)/T(Task)/A(Action)/R(Result) 四要素
  - Action 部分是否具备技术深度——写了怎么做、为什么这么做
  - 原始简历通常严重缺失 Situation 和 Result
  - 评分参考: 4 要素完整(25-30), 缺 1 要素(15-25), 缺 2 要素(5-15), 几乎全缺(0-5)

【维度三】动词与指标质量（满分 10 分）
  - 是否使用有影响力的动词（非"负责/参与/做了"）
  - 是否包含任何量化数据
  - 注意：此维度仅占 10%，不应成为决定性的评分因素

══════════════════════════════════════════════════
【分诊阈值与熔断线】
══════════════════════════════════════════════════

  总分 30 分是核心熔断线:
  - 总得分 ≥ 30 分 → difficulty_flag = "NORMAL" → 正常精修模式
  - 总得分 < 30 分 → difficulty_flag = "EXTREME_GAP" → 防幻觉骨架模式

  评分合理性自检:
  - 如果硬工具覆盖率 > 50% 但技术栈总分 < 30 分 → 你的评分有严重偏差，请重新评估！
  - 如果硬工具覆盖率 > 70% 但技术栈总分 < 40 分 → 你很可能误杀了，请重新检查轨一评分！

══════════════════════════════════════════════════
【输出格式】严格 JSON —— 不要任何额外解释
══════════════════════════════════════════════════

{{
  "score": <0-100 总分>,
  "dimension_scores": {{
    "jd_match": <0-60 (轨一+轨二合计)>,
    "jd_tool_coverage": <0-40 轨一硬工具覆盖分>,
    "jd_depth_premium": <0-20 轨二软深度溢价分>,
    "star_completion": <0-30>,
    "verb_quality": <0-10>
  }},
  "difficulty_flag": <"EXTREME_GAP" | "NORMAL">,
  "candidate_tier": <1-4 候选人的抽象层级（仅用于轨二参考）>,
  "jd_tier": <1-4 JD 要求的抽象层级>,
  "tier_assessment": "<1句话说明层级判定依据>",
  "core_tool_overlap": "<列出简历与JD共同覆盖的核心工具，如'FastAPI/Redis/MySQL/Docker'>",
  "tool_coverage_rate": "<百分比，如'75%'>",
  "jd_matched_skills": ["<JD要求且简历已覆盖的技术栈>", ...],
  "jd_missing_skills": ["<JD要求但简历未体现的技术栈>", ...],
  "star_strengths": ["<原始简历STAR做得好的点>", ...],
  "star_weaknesses": ["<原始简历STAR缺失的点>", ...],
  "weak_verbs_found": ["<简历中弱动词>", ...],
  "feedback": "<列出最关键的 2-3 个问题>"
}}

difficulty_flag 判定规则:
- score >= 30: "NORMAL"（正常可优化，进入精修）
- score < 30: "EXTREME_GAP"（绝望差距，需防幻觉骨架模式）

重要：
1. 工具链匹配是硬道理——不要因为简历写得朴素就压分
2. 使用双轨制：先算轨一保底，再加轨二溢价
3. 评分自检：工具覆盖 >50% 但总分 <30 分 = 你的评估出了严重偏差！"""


def _parse_pre_eval_json(response_text: str, default_score: int = 20) -> dict:
    """解析 PreEvaluator 返回的 JSON，适配 6-3-1 权重 + 双轨制 + 结构化维度字段"""
    json_match = re.search(r"\{[\s\S]*\}", response_text)
    if not json_match:
        return {
            "score": default_score,
            "dimension_scores": {
                "jd_match": 5, "jd_tool_coverage": 3, "jd_depth_premium": 2,
                "star_completion": 5, "verb_quality": 3,
            },
            "difficulty_flag": "EXTREME_GAP",
            "candidate_tier": 1,
            "jd_tier": 2,
            "tier_assessment": "（解析失败）",
            "core_tool_overlap": "",
            "tool_coverage_rate": "0%",
            "feedback": "PreEvaluator 返回格式异常。原始输出：" + response_text[:200],
        }

    json_str = json_match.group(0)
    try:
        data = json.loads(json_str)
        dims = data.get("dimension_scores", {})
        if "jd_match" not in dims:
            dims["jd_match"] = dims.get("jd_tool_coverage", 10) + dims.get("jd_depth_premium", 8)
        if "jd_tool_coverage" not in dims:
            dims["jd_tool_coverage"] = 10
        if "jd_depth_premium" not in dims:
            dims["jd_depth_premium"] = 8
        if "star_completion" not in dims:
            dims["star_completion"] = 8
        if "verb_quality" not in dims:
            dims["verb_quality"] = 3

        # v2.7: 提取结构化维度明细字段，合并进 dimension_scores
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

        data["dimension_scores"] = dims

        if "difficulty_flag" not in data:
            score = data.get("score", 0)
            data["difficulty_flag"] = "EXTREME_GAP" if score < 30 else "NORMAL"
        if "candidate_tier" not in data:
            data["candidate_tier"] = 0
        if "jd_tier" not in data:
            data["jd_tier"] = 0
        if "tier_assessment" not in data:
            data["tier_assessment"] = ""
        if "core_tool_overlap" not in data:
            data["core_tool_overlap"] = ""
        if "tool_coverage_rate" not in data:
            data["tool_coverage_rate"] = ""
        if "feedback" not in data:
            data["feedback"] = "（无详细反馈）"
        return data
    except json.JSONDecodeError:
        return {
            "score": default_score,
            "dimension_scores": {
                "jd_match": 8, "jd_tool_coverage": 5, "jd_depth_premium": 3,
                "star_completion": 8, "verb_quality": 3,
            },
            "difficulty_flag": "EXTREME_GAP",
            "candidate_tier": 1,
            "jd_tier": 2,
            "tier_assessment": "（JSON 解析失败）",
            "core_tool_overlap": "",
            "tool_coverage_rate": "",
            "feedback": f"JSON 解析错误。原始输出: {json_str[:300]}",
        }


def pre_evaluator_node(state: AgentState):
    """
    v2.3 前置分诊节点：硬工具保底双轨制 + 6-3-1 死锁权重

    双轨制算法:
      - 轨一【硬工具覆盖分 0-40】: 核心工具链匹配即保底，杜绝误杀
      - 轨二【软深度溢价分 0-20】: 高维特征额外加分

    仅做 difficulty_flag 标记，不进行路由退出。
    所有简历无条件进入 Editor。

    输入：resume (原始简历), jd
    输出：score, difficulty_flag, dimension_scores, core_tool_overlap, node_status
    """
    # ── v5.9 None 安全兜底 ──
    resume = state.get("resume") or ""
    jd = state.get("jd") or ""

    if not resume.strip():
        return {
            "score": 0,
            "difficulty_flag": "EXTREME_GAP",
            "node_status": "原始简历为空，标记为 EXTREME_GAP",
            "pre_eval_dimensions": {"jd_match": 0, "jd_tool_coverage": 0, "jd_depth_premium": 0, "star_completion": 0, "verb_quality": 0},
        }

    prompt = f"""【目标岗位 JD】
{jd}

【原始简历（未经过任何优化）】
{resume[:3000]}

请按照 6-3-1 死锁权重和双轨制算法对这份原始简历进行严格评分，直接输出 JSON："""

    print(f"[pre_evaluator] 开始原始简历初审 (v2.3 硬工具保底双轨制)...")
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
        core_tool_overlap = result.get("core_tool_overlap", "")
        tool_coverage_rate = result.get("tool_coverage_rate", "")
        feedback = result.get("feedback", "")

        jd_tool_cov = dims.get("jd_tool_coverage", "?")
        jd_depth_prem = dims.get("jd_depth_premium", "?")
        jd_match = dims.get("jd_match", "?")

        print(f"[pre_evaluator] 初审评分: {score}/100 "
              f"(JD匹配: {jd_match}/60 = 工具覆盖{jd_tool_cov}/40 + 深度溢价{jd_depth_prem}/20, "
              f"STAR: {dims.get('star_completion', '?')}/30, "
              f"动词: {dims.get('verb_quality', '?')}/10)")

        if core_tool_overlap:
            print(f"[pre_evaluator] 核心工具覆盖: {core_tool_overlap} (覆盖率 {tool_coverage_rate})")

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
            "pre_eval_dimensions": dims,
        }

    except Exception as e:
        print(f"[pre_evaluator] 初审失败: {type(e).__name__}: {e}")
        return {
            "score": 0,
            "difficulty_flag": "EXTREME_GAP",
            "node_status": f"PreEvaluator 异常: {type(e).__name__}",
            "evaluation_feedback": "",
            "pre_eval_dimensions": {"jd_match": 0, "jd_tool_coverage": 0, "jd_depth_premium": 0, "star_completion": 0, "verb_quality": 0},
        }
