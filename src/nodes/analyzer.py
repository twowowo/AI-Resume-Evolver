import json
import re
from src.state import GraphState
from src.utils.llm import get_flash_client

JD_ANALYSIS_PROMPT = """你是一个专业资深猎头。请分析以下招聘职位描述（JD），精准提取关键要求，并按以下三类输出：

1. tech_stack：编程语言、框架、工具、数据库、云服务等硬技能
2. soft_skills：沟通、逻辑、管理、业务理解、领导力等软技能
3. business_scene：行业领域、业务场景、项目类型等

请严格以 JSON 格式返回，不要包含任何多余的解释：
{"tech_stack": ["关键词1", "关键词2", ...], "soft_skills": ["关键词1", ...], "business_scene": ["关键词1", ...]}

JD 内容：
{jd_text}"""


def _parse_ai_response(response_text: str) -> dict[str, list[str]]:
    json_match = re.search(r"\{[\s\S]*\}", response_text)
    if not json_match:
        print("[analyzer] AI 返回格式异常，尝试按行解析")
        lines = [line.strip("- ").strip() for line in response_text.split("\n") if line.strip()]
        return {"tech_stack": lines, "soft_skills": [], "business_scene": []}

    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        print("[analyzer] JSON 解析失败，回退到按行解析")
        lines = [line.strip("- ").strip() for line in response_text.split("\n") if line.strip()]
        return {"tech_stack": lines, "soft_skills": [], "business_scene": []}

    result = {
        "tech_stack": [],
        "soft_skills": [],
        "business_scene": [],
    }
    for key in result:
        if key in data and isinstance(data[key], list):
            result[key] = data[key]
    return result


def _flatten_keywords(structured: dict[str, list[str]]) -> list[str]:
    keywords = []
    for items in structured.values():
        keywords.extend(items)
    return keywords


def _enrich_with_rag(keywords: list[str]) -> list[str]:
    try:
        from src.utils.vector_store import get_retriever

        retriever = get_retriever()
        enriched = list(keywords)
        seen = set(keywords)

        for kw in keywords[:5]:
            try:
                docs = retriever.invoke(kw)
                for doc in docs:
                    term = doc.page_content.strip()
                    if term and term not in seen:
                        seen.add(term)
                        enriched.append(term)
            except Exception as inner_e:
                print(f"[analyzer] 关键词 '{kw}' 检索跳过: {inner_e}")

        added = len(enriched) - len(keywords)
        if added > 0:
            print(f"[analyzer] RAG 补充了 {added} 个行业术语")

        return enriched
    except ImportError:
        print("[analyzer] vector_store 模块未就绪，跳过 RAG 增强")
        return keywords
    except Exception as e:
        print(f"[analyzer] RAG 检索失败 ({type(e).__name__}: {e})，使用原始关键词")
        return keywords


def jd_analyzer_node(state: GraphState) -> GraphState:
    jd_text = state.get("target_jd", "")
    state["revision_count"] = state.get("revision_count", 0)

    if not jd_text.strip():
        print("[analyzer] 警告：target_jd 为空，跳过分析")
        state["gap_list"] = []
        return state

    try:
        llm = get_flash_client()
        prompt = JD_ANALYSIS_PROMPT.format(jd_text=jd_text)
        response = llm.invoke(prompt)
        response_text = response.content if hasattr(response, "content") else str(response)

        print(f"[analyzer] AI 原始返回:\n{response_text[:400]}...")

        structured = _parse_ai_response(response_text)
        print(
            f"[analyzer] 结构化提取: "
            f"tech_stack={len(structured['tech_stack'])}项, "
            f"soft_skills={len(structured['soft_skills'])}项, "
            f"business_scene={len(structured['business_scene'])}项"
        )

        keywords = _flatten_keywords(structured)
        print(f"[analyzer] 合并关键词 ({len(keywords)} 项): {keywords}")

        keywords = _enrich_with_rag(keywords)

        state["gap_list"] = keywords
        print(f"[analyzer] 最终 gap_list ({len(keywords)} 项): {keywords}")

    except ValueError as e:
        print(f"[analyzer] 配置错误: {e}")
        state["gap_list"] = []
    except Exception as e:
        print(f"[analyzer] AI 调用失败 ({type(e).__name__}: {e})，保留原始状态")
        if not state.get("gap_list"):
            state["gap_list"] = []

    return state
