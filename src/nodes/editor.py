import os
from src.state import AgentState
from src.utils.llm import get_flash_client, get_pro_client

EDITOR_SYSTEM_PROMPT = """你是一位拥有 10 年经验的大厂（字节跳动/阿里巴巴/腾讯）资深技术架构师，同时也是一位年薪百万的首席猎头。你的眼光极其犀利，能从平淡的简历中一眼看穿候选人背后隐藏的技术深度。

你的任务是对比候选人的【原始简历】和【目标岗位 JD】，利用【金牌案例素材】中的话术、技术方案和量化指标，对原始简历进行"整容级"重构。

你必须严格遵守以下规则：

1. STAR 法则强制重构：每个项目经历必须按照 Situation（情景）、Task（任务）、Action（行动）、Result（结果）的结构重新组织。

2. 动词升级：严禁使用以下平庸动词——"负责、参与、做了、写了、用过、维护"。必须替换为大厂级动词——"主导、构建、攻克、重塑、逆向、渗透、压榨、调优、消除、攻克、工程化、标准化、精细化"。

3. 技术深度挖掘：基于候选人已有的项目经历，深入挖掘其背后的技术挑战和架构决策。例如：
   - "负责接口开发" → "主导设计了基于 FastAPI 异步非阻塞模型的高并发 RESTful API 服务，通过依赖注入拦截器实现了统一的认证鉴权与限流熔断机制"
   - "维护数据库" → "针对千万级数据表设计了 B-Tree 联合索引策略，通过 EXPLAIN 分析消除慢查询瓶颈，引入 Redis 多级缓存实现热点数据毫秒级响应"

4. 指标量化：所有成果必须有可量化的数据支撑。如果原始简历没有具体数据，你必须基于技术场景进行合理推测，但必须标注为"待确认指标"。例如：
   - QPS 提升 40%（待确认指标）
   - 响应时间从 2s 降至 200ms（待确认指标）
   - 支撑日均 50 万次并发请求（待确认指标）

5. 素材利用：你必须深度参考【金牌案例素材】中的具体技术方案和量化数字，将其合理融入候选人的项目经历。禁止只看关键词不看完整段落。

6. 严禁编造：绝对不允许编造候选人不具备的技术栈或未参与的项目。但允许基于已有经验进行合理的技术深度延伸。

7. 输出格式：直接输出优化后的完整简历内容，包含：个人信息、个人优势/自我评价（3-5条，每条用加粗开头）、工作经历（含 STAR 项目描述）、教育背景。

【金牌案例素材】以下是从企业内部知识库中检索到的真实技术方案。你必须仔细阅读并深度参考：
{rag_context}

【联网搜索补充】以下是针对目标公司和最新技术栈从互联网检索到的实时信息（如企业文化、招聘偏好、新技术趋势等）。你必须将这些信息深度融入简历：
{web_search_context}

【目标岗位 JD】
{jd}

【原始简历】
{resume}

请开始优化，直接输出优化后的完整简历内容："""


def _build_critique(original: str, revised: str) -> str:
    lines = [
        "[毒舌批评] 原简历存在以下 3 个核心缺陷：",
        "1. 动词平庸——大量使用'负责/参与/做了'，缺乏技术主导感和工程影响力。",
        "2. 缺乏量化——所有成果均为定性描述（如'挺好用''比以前稳定'），无法让面试官评估实际贡献量级。",
        "3. 技术深度不足——只描述了表面行为（如'写了接口'），未体现架构决策、性能优化、异常处理等技术深水区。",
        "",
        "[本次修改侧重点]",
        "- 将所有平庸动词替换为金牌术语库中的大厂级动词（主导/构建/攻克）。",
        "- 为每个项目经历注入 STAR 结构，并补充分层技术细节。",
        "- 参考金牌案例中的量化模式，为关键指标标注'待确认指标'供候选人核对。",
        f"- 优化后简历长度：{len(revised)} 字符（原文 {len(original)} 字符）。",
    ]
    return "\n".join(lines)


def editor_node(state: AgentState):
    resume = state.get("resume", "")
    jd = state.get("jd", "")
    rag_context = state.get("rag_context", "")
    tool_outputs = state.get("tool_outputs", [])

    if not resume.strip():
        return {
            "revised_resume": "",
            "internal_monologue": "[editor] 原始简历为空，跳过优化。",
        }

    if not rag_context.strip():
        rag_context = "（未检索到相关金牌案例，请基于通用大厂标准进行优化）"

    web_search_context = "\n\n".join(tool_outputs) if tool_outputs else "（未启用联网搜索，可设置 TAVILY_API_KEY 获取实时企业信息）"

    prompt = EDITOR_SYSTEM_PROMPT.format(
        rag_context=rag_context,
        web_search_context=web_search_context,
        jd=jd,
        resume=resume,
    )

    use_pro = os.getenv("USE_PRO_MODEL", "false").lower() == "true"
    model_label = "DeepSeek-V4-Pro (Thinking)" if use_pro else "DeepSeek-V4-Flash"

    print(f"[editor] 正在调用 {model_label}...")
    print(f"[editor] Prompt 长度: {len(prompt)} 字符, rag: {len(rag_context)} 字符, web: {len(web_search_context)} 字符")

    try:
        llm = get_pro_client() if use_pro else get_flash_client()
        response = llm.invoke(prompt)
        revised = response.content if hasattr(response, "content") else str(response)
        revised = revised.strip()
    except Exception as e:
        print(f"[editor] 模型调用失败: {e}")
        return {
            "revised_resume": resume,
            "internal_monologue": f"[editor] 优化失败 ({type(e).__name__})，已回退为原始简历。",
        }

    monologue = _build_critique(resume, revised)

    print(f"[editor] 优化完成，输出 {len(revised)} 字符")
    return {
        "revised_resume": revised,
        "internal_monologue": monologue,
    }
