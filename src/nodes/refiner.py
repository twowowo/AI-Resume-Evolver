import os
import re
from src.state import GraphState
from src.utils.llm import get_flash_client, get_pro_client

REFINER_SYSTEM_PROMPT = """你是一位顶级互联网公司（如字节跳动、阿里巴巴、腾讯）的资深架构师，同时也是一位年薪百万的资深猎头顾问。你的任务是将一份平淡的简历优化为具备"大厂深度"的简历。

你必须严格遵守以下规则：

1. STAR 法则重构：每个项目经历必须按照 Situation（情景）、Task（任务）、Action（行动）、Result（结果）的结构重新组织。

2. 术语平替：严禁使用"写了"、"做了"、"用过"、"负责"等平庸动词。必须使用以下金牌术语库中的词汇进行替换：
{gap_terms}

3. 技术深度挖掘：基于候选人已有的项目经历，深入挖掘其背后的技术挑战和架构决策。例如：
   - "写了 API 接口" → "设计并实现了基于 FastAPI 异步特性的高并发 RESTful API 服务，通过依赖注入和中间件拦截器实现了统一的认证鉴权与限流熔断机制"
   - "用了数据库" → "针对千万级数据表设计了 B-Tree 联合索引策略，通过 EXPLAIN 分析优化慢查询，引入 Redis 缓存层实现热点数据毫秒级响应"

4. 指标量化：所有成果必须有可量化的数据支撑。如果原始简历没有数据，你可以基于技术场景进行合理估算，但必须标注为"估算"。
   - 例如：QPS 提升 40%（估算）、响应时间从 2s 降至 200ms（估算）、支撑日均 50 万次并发请求（估算）

5. 严禁编造：绝对不允许编造候选人没有做过的项目或没有使用过的技术栈。但允许基于已有项目进行合理的技术深度延伸。

6. 输出格式：直接输出优化后的完整简历内容。简历应包含：个人信息、个人优势/自我评价、工作经历（含项目描述）、教育背景。

目标 JD 要求：
{target_jd}

原始简历：
{raw_resume}

请开始优化，直接输出优化后的完整简历："""


def _extract_thinking(response) -> str:
    content = response.content if hasattr(response, "content") else str(response)
    if hasattr(response, "additional_kwargs") and response.additional_kwargs:
        thinking = response.additional_kwargs.get("thinking", "")
        if thinking:
            return thinking
    if hasattr(response, "response_metadata") and response.response_metadata:
        thinking = response.response_metadata.get("thinking", "")
        if thinking:
            return thinking
    return ""


def _extract_content(response) -> str:
    content = response.content if hasattr(response, "content") else str(response)
    return content.strip()


def _build_gap_terms_text(gap_list: list[str]) -> str:
    if not gap_list:
        return "（无额外术语库，请基于通用大厂标准进行优化）"

    substantive = [t for t in gap_list if len(t) > 6 and not t.startswith("[") and not t.endswith("]")]
    if len(substantive) > 20:
        substantive = substantive[:20]

    lines = []
    for i, term in enumerate(substantive, 1):
        lines.append(f"  {i}. {term}")
    return "\n".join(lines)


def resume_refiner_node(state: GraphState) -> GraphState:
    raw_resume = state.get("raw_resume", "")
    target_jd = state.get("target_jd", "")
    gap_list = state.get("gap_list", [])

    if not raw_resume.strip():
        print("[refiner] 警告：raw_resume 为空，跳过优化")
        state["refined_resume"] = raw_resume
        return state

    gap_terms_text = _build_gap_terms_text(gap_list)

    prompt = REFINER_SYSTEM_PROMPT.format(
        gap_terms=gap_terms_text,
        target_jd=target_jd,
        raw_resume=raw_resume,
    )

    use_pro = os.getenv("USE_PRO_MODEL", "false").lower() == "true"
    model_label = "DeepSeek-V4-Pro (Thinking)" if use_pro else "DeepSeek-V4-Flash"

    print(f"[refiner] 开始调用 {model_label}...")
    print(f"[refiner] Prompt 长度: {len(prompt)} 字符, gap_list 有效术语: {gap_terms_text.count(chr(10))} 条")

    try:
        if use_pro:
            llm = get_pro_client()
        else:
            llm = get_flash_client()

        response = llm.invoke(prompt)

        thinking = _extract_thinking(response)
        refined = _extract_content(response)

        if thinking:
            print(f"[refiner] 模型思考过程 ({len(thinking)} 字符):")
            print("-" * 40)
            print(thinking[:1500])
            print("-" * 40)

        state["refined_resume"] = refined
        state["revision_count"] = state.get("revision_count", 0) + 1

        print(f"[refiner] 优化完成！输出简历长度: {len(refined)} 字符")
        return state

    except Exception as e:
        print(f"[refiner] 模型调用失败 ({type(e).__name__}: {e})")
        import traceback
        traceback.print_exc()
        state["refined_resume"] = raw_resume
        return state
