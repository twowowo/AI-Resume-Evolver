"""
v2.5 MockInterviewer 节点 —— 压力测试追问链生成器

角色: 严厉的中厂核心技术架构师
输入: Editor 优化后的精修简历 + 目标 JD
输出: 3 道直击底层第一性原理的刁钻追问链 → stress_test_questions
"""

import json
import re
from src.state import AgentState
from src.utils.llm import get_pro_client

INTERVIEWER_SYSTEM_PROMPT = """你是一位严厉的中厂核心技术架构师，拥有 12 年后端架构经验，
面试过 500+ 候选人。你极端厌恶简历注水和表面功夫。

你现在面对的是一份经过 AI 精修的简历。你的任务不是判断它是否"好看"，
而是拿着这份简历作为靶子，针对里面每一个被包装过的硬核技术声明，
进行毫不留情的深度拷问。

══════════════════════════════════════════════════════
【拷问原则】
══════════════════════════════════════════════════════

1. 【直击第一性原理】
   不要问"你用过 Redis 吗"，而要问：
   "你在简历中说用 Redis Lua 脚本保证原子性——如果 Lua 脚本执行到一半
    Redis 主节点挂了，你的脚本会怎样？已执行的写操作会丢失还是回滚？
    Redis 的事务和 MySQL 的事务在 ACID 保证上有什么本质区别？"

2. 【结合项目故障场景】
   不要问理论问题，要把问题嵌入到候选人简历中描述的具体业务场景：
   "你的 WMS 系统中用 RabbitMQ 做异步库存通知——假设在某次大促期间，
    MQ 突然堆积了 50 万条消息，你的消费者扛不住了，你会怎么处理？
    是按时间优先级丢弃、还是降级到数据库、还是动态扩容消费者？
    你凭什么选择这个方案？"

3. 【追问链路设计】
   每道题必须包含递进深度——从简历表面的声明，追问到候选人必须
   真正动手做过才能回答的层次。题目设计为"追问链"：第一问摸底，
   第二问追问细节，第三问考察 trade-off 判断力。

4. 【精准打击简历软肋】
   仔细扫描简历中以下"高危区域"并重点出题：
   - 任何提到"高并发/高可用/高性能"但未给出具体压测数据的声明
   - 任何使用"设计/架构/构建"但实际可能是"使用/配置"的技术点
   - 任何提到具体中间件(RabbitMQ/Kafka/Redis)但可能只是 API 调用的项目
   - 任何标注"（估算）"或"（待确认指标）"的量化数据
   - 任何提到"优化/调优"但没有写具体手段和效果对比的描述

5. 【三类覆盖】
   - 至少 1 道：技术深度类（追问底层原理和源码实现）
   - 至少 1 道：系统设计类（追问架构决策和 trade-off）
   - 至少 1 道：项目经验/故障场景类（追问真实踩坑和复盘）

══════════════════════════════════════════════════════
【输出格式】严格 JSON
══════════════════════════════════════════════════════

{
  "questions": [
    {
      "question_number": 1,
      "category": "技术深度",
      "question": "你在简历中提到对 MySQL 做了'慢查询优化和索引设计'。请具体说一个你优化过的最复杂的慢查询案例：这条 SQL 原来长什么样、执行计划(EXPLAIN)的哪些字段让你判断出了问题、你具体做了什么（只加索引？还是改了表结构？还是改了查询逻辑？）、最终 RT 从多少降到多少。如果你只是加了索引，那有没有考虑过索引的副作用——比如这个索引对写入性能的影响有多大？",
      "expected_points": [
        "能当场写出 SQL 和执行计划的关键字段(type/rows/Extra)",
        "区分了覆盖索引、联合索引最左前缀、索引下推等概念",
        "提到了索引对写入和锁的影响",
        "有具体的 RT 数据对比"
      ]
    },
    {
      "question_number": 2,
      "category": "系统设计",
      "question": "...",
      "expected_points": ["...", "..."]
    },
    {
      "question_number": 3,
      "category": "项目经验",
      "question": "...",
      "expected_points": ["...", "..."]
    }
  ]
}

重要：
- 题目必须足够长、足够具体，不要问空泛的问题
- 每道题的 expected_points 必须是可验证的技术深度指标
- 如果简历中没有足够的高危打击点，就针对最核心的技术栈出题
- 让候选人感受到：不真正动过手、踩过坑，是不可能答好这些题的"""


def _parse_interviewer_json(response_text: str) -> list[dict]:
    """解析 Interviewer 返回的 JSON"""
    json_match = re.search(r"\{[\s\S]*\}", response_text)
    if not json_match:
        return []

    try:
        data = json.loads(json_match.group(0))
        return data.get("questions", [])
    except json.JSONDecodeError:
        return []


def interviewer_node(state: AgentState):
    """
    v2.5 MockInterviewer 压力测试节点

    在 evaluator 终评通过后执行，针对精修简历中的技术声明
    生成 3 道直击底层原理的刁钻追问链。

    输入：revised_resume (优化后简历), jd (目标岗位)
    输出：stress_test_questions (压测题列表)
    """
    revised_resume = state.get("revised_resume", "")
    jd = state.get("jd", "")
    internal_monologue = state.get("internal_monologue", "")

    if not revised_resume.strip():
        print("[interviewer] 精修简历为空，跳过压测题生成")
        return {"stress_test_questions": []}

    prompt = f"""【目标岗位 JD】
{jd[:1500]}

【AI 精修后的候选人简历 —— 这是你的拷打靶子】
{revised_resume[:4000]}

请仔细扫描上述简历，找出最值得深度拷问的 3 个技术声明，
生成 3 道包含追问链的刁钻面试题。直接输出 JSON："""

    print(f"[interviewer] 启动 MockInterviewer 压力测试 (v2.5 架构师拷问模式)...")
    print(f"[interviewer] 靶子简历 {len(revised_resume)} 字符, JD {len(jd)} 字符")

    try:
        llm = get_pro_client()
        full_prompt = INTERVIEWER_SYSTEM_PROMPT + "\n\n" + prompt
        response = llm.invoke(full_prompt)
        content = response.content if hasattr(response, "content") else str(response)

        questions_data = _parse_interviewer_json(content)

        if not questions_data:
            print("[interviewer] JSON 解析失败，使用回退模式")
            questions_data = _fallback_interviewer_questions(revised_resume)

        # 规范化并补全字段
        result = []
        for i, q in enumerate(questions_data[:3]):
            result.append({
                "question_number": i + 1,
                "category": q.get("category", "技术深度"),
                "question": q.get("question", ""),
                "expected_points": q.get("expected_points", []),
            })

        print(f"[interviewer] 成功生成 {len(result)} 道压力测试追问链:")
        for q in result:
            q_preview = q["question"][:120]
            print(f"  Q{q['question_number']} [{q['category']}]: {q_preview}...")

        return {"stress_test_questions": result}

    except Exception as e:
        print(f"[interviewer] 生成失败: {type(e).__name__}: {e}")
        return {"stress_test_questions": _fallback_interviewer_questions("")}


def _fallback_interviewer_questions(resume: str) -> list[dict]:
    """LLM 不可用时的硬核回退题（针对通用后端简历）"""
    return [
        {
            "question_number": 1,
            "category": "技术深度",
            "question": (
                "你在简历中提到使用 Redis 做缓存。请描述一次缓存方案导致线上问题的真实经历。"
                "具体说明：你用了什么缓存策略（Cache-Aside/Read-Through/Write-Behind）？"
                "缓存和数据库的一致性你是怎么保证的？有没有遇到过缓存雪崩/击穿/穿透？"
                "你具体用了什么方案（互斥锁/逻辑过期/布隆过滤器）？为什么选这个？"
            ),
            "expected_points": [
                "能区分 Cache-Aside 等策略并说明选择理由",
                "对缓存一致性有具体方案描述（先删缓存还是先写DB，为什么）",
                "能区分雪崩/击穿/穿透三种场景并给出不同解法",
                "有真实事故复盘或压测数据"
            ],
        },
        {
            "question_number": 2,
            "category": "系统设计",
            "question": (
                "你在简历中提到了消息队列做异步解耦。假设你的系统从日均 10 万订单"
                "突然要支撑日均 100 万订单（大促场景），你会对现有的消息队列架构做哪些改造？"
                "请具体说明：消息堆积怎么办？消费者扩容有没有上限？需不需要拆分 Topic？"
                "如何保证消息不丢不重？如果 MQ 本身挂了你的系统怎么降级？"
            ),
            "expected_points": [
                "给出了消息堆积的多层处理方案（扩容/限流/降级/优先级）",
                "区分了 at-most-once / at-least-once / exactly-once 语义",
                "有具体的容量规划和压测思路",
                "提到了监控和告警体系"
            ],
        },
        {
            "question_number": 3,
            "category": "项目经验",
            "question": (
                "请描述一次你在项目中做出的技术决策后来被证明是错误的。"
                "具体说明：当时你是怎么做出这个决策的（基于什么信息/假设）？"
                "错误是在什么阶段被发现的（测试/灰度/全量上线）？影响了多少用户/数据？"
                "你是怎么修复的？事后复盘你总结出了什么流程或规范上的改进？"
            ),
            "expected_points": [
                "诚实描述了技术失误的具体细节而非避重就轻",
                "区分了决策时的信息局限和决策本身的逻辑错误",
                "有具体的应急响应时间线和修复方案",
                "从事故中提炼了可落地的工程规范改进"
            ],
        },
    ]
