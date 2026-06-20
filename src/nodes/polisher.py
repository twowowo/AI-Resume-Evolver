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
6. 【空模块跳过规则】如果原简历中某个模块完全没有实质内容（正文为空、"无"、"暂无"等占位字样），直接跳过该模块，不输出 ## 模块标题，不补任何占位文本。
7. 【绝对输出禁语令】直接输出修改后的完整简历正文，绝对禁止附带任何寒暄（"好的"、"以下是"）、Markdown 代码块包裹（```）、祝福语、署名结语、或角色扮演评论。

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


POLISHER_CRITICAL_PROMPT = """你是一位诚实的职业规划顾问。当前场景：候选人的原始简历与目标 JD 之间存在【极端差距】(EXTREME_GAP)。

评审团已经判定这份简历的初版优化稿分数极低（< 35 分），继续微调已无意义。你需要：

核心约束：【严禁凭空编造虚假项目经验】
- 绝对不允许编造"分布式系统"、"高并发"、"千万级吞吐"、"多活架构"等候选人显然不具备的经验
- 绝对不允许编造候选人不具备的技术栈
- 绝对不允许把一个"个人博客"包装成"企业级微服务平台"

你的任务转为【标准骨架搭建模式】：
- 将平庸动词升级为中等水平动词（如"实现/设计/构建/优化"，不必强求"主导/攻克/重塑"）
- 用 STAR 结构重新组织候选人已有的项目经历
- 对于无法填充的量化指标和技术细节，使用占位符留白：
  - 量化指标: `[请在此处实事求是填入您的日均订单量]`
  - 技术细节: `[请描述您在此项目中使用的具体缓存策略]`
  - 业务场景: `[请补充该项目的业务背景和数据规模]`
  - 成果: `[请填入可验证的项目成果，如性能提升百分比]`

占位符必须用【方括号】包裹，内容用中文写明需要填入什么。

虽然不能编造，但仍应帮助候选人规范简历格式、清晰化技术描述、基于已有知识做合理延伸。

【目标 JD —— 用于对齐需求】：
{jd}

【初版优化稿 —— 评分过低，需彻底重构】：
{revised_resume}

【原始简历 —— 用于核实信息不编造】：
{original_resume}

【评分反馈 —— 了解为什么评分低】：
{evaluation_feedback}

【绝对输出禁语令】直接输出完整简历正文，绝对禁止任何寒暄、代码块包裹、祝福语或角色扮演评论。

请直接输出骨架优化后的完整简历（包含占位符，这是唯一一次全力一击，不允许失败）："""


def polisher_node(state: AgentState):
    """精修/硬核重组节点：根据 difficulty_flag 切换行为模式"""
    # ── v5.9 None 安全兜底 ──
    revised_resume = state.get("revised_resume") or ""
    jd = state.get("jd") or ""
    original_resume = state.get("resume") or ""
    feedback = state.get("evaluation_feedback") or ""
    iteration_count = state.get("iteration_count") or 0
    difficulty_flag = state.get("difficulty_flag") or ""

    if not revised_resume.strip():
        return {
            "revised_resume": revised_resume,
            "internal_monologue": "[polisher] 无内容可精修。",
            "iteration_count": iteration_count + 1,
            "difficulty_flag": difficulty_flag,
        }

    # ── 熔断模式：硬核重组 ──
    if difficulty_flag == "EXTREME_GAP":
        prompt = POLISHER_CRITICAL_PROMPT.format(
            jd=jd,
            revised_resume=revised_resume,
            original_resume=original_resume[:3000],
            evaluation_feedback=feedback,
        )
        mode_label = "硬核重组 (EXTREME_GAP)"
    else:
        if not feedback.strip():
            return {
                "revised_resume": revised_resume,
                "internal_monologue": "[polisher] 无评审反馈，无需精修。",
                "iteration_count": iteration_count + 1,
                "difficulty_flag": difficulty_flag,
            }
        prompt = POLISHER_SYSTEM_PROMPT.format(
            evaluation_feedback=feedback,
            jd=jd,
            revised_resume=revised_resume,
            original_resume=original_resume[:3000],
        )
        mode_label = f"精修 (第 {iteration_count + 1} 轮)"

    print(f"[polisher] 开始{mode_label}...")
    print(f"[polisher] 目标: {feedback[:200]}..." if feedback else f"[polisher] 模式: {mode_label}")

    try:
        llm = get_pro_client()
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        from src.utils.text_sanitizer import sanitize_resume_text
        polished = sanitize_resume_text(content.strip(), log_prefix="[polisher]")

        # 提取 thinking（如果有）
        thinking = ""
        if hasattr(response, "additional_kwargs") and response.additional_kwargs:
            thinking = response.additional_kwargs.get("thinking", "")
        elif hasattr(response, "response_metadata") and response.response_metadata:
            thinking = response.response_metadata.get("thinking", "")

        if thinking:
            print(f"[polisher] Thinking ({len(thinking)} 字符): {thinking[:300]}...")

        print(f"[polisher] {mode_label}完成，输出 {len(polished)} 字符")

        if difficulty_flag == "EXTREME_GAP":
            placeholder_count = polished.count("[请")
            monologue = (
                f"[polisher 防幻觉骨架模式] 检测到 EXTREME_GAP，执行防幻觉骨架搭建。\n"
                f"输出 {len(polished)} 字符，包含 {placeholder_count} 处占位符留白。"
            )
        else:
            monologue = (
                f"[polisher 第{iteration_count + 1}轮] 针对评审反馈进行了精修。\n"
                f"反馈要点: {feedback[:300]}"
            )

        return {
            "revised_resume": polished,
            "internal_monologue": monologue,
            "iteration_count": iteration_count + 1,
            "difficulty_flag": difficulty_flag,
        }

    except Exception as e:
        print(f"[polisher] {mode_label}失败: {type(e).__name__}: {e}")
        return {
            "revised_resume": revised_resume,
            "internal_monologue": f"[polisher] {mode_label}异常 ({type(e).__name__})，保留上一版本。",
            "iteration_count": iteration_count + 1,
            "difficulty_flag": difficulty_flag,
        }
