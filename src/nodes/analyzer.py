import json
import re
from src.state import GraphState
from src.utils.llm import get_flash_client

_PLACEHOLDER_PATTERN = re.compile(r"^\s*\[.+?\]\s*$")
_SECTION_HEADER = re.compile(r"^\s*[一二三四五六七八九十]、|\(Architecture|\(Backend|\(Frontend|\(DevOps|\(Data|\(AI")
_BRACKET_LABEL_ONLY = re.compile(r"^\s*\[.+?\]\s*$")


def _is_placeholder(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if _PLACEHOLDER_PATTERN.match(t):
        return True
    if _BRACKET_LABEL_ONLY.match(t):
        return True
    return False


def _is_quality_context(text: str) -> bool:
    t = text.strip()
    if not t or len(t) < 12:
        return False
    if _is_placeholder(t):
        return False
    if _SECTION_HEADER.search(t):
        return False
    return True


def _filter_rag_results(docs: list) -> list:
    filtered = []
    for doc in docs:
        term = doc.page_content.strip()
        if _is_placeholder(term):
            continue
        filtered.append(doc)
    return filtered

JD_ANALYSIS_PROMPT = """你是一个专业资深猎头。请分析以下招聘职位描述（JD），精准提取关键要求，并按以下三类输出：

1. 技术栈：编程语言、框架、工具、数据库、云服务等硬技能
2. 软技能：沟通、逻辑、管理、业务理解、领导力等软技能
3. 业务场景：行业领域、业务场景、项目类型等

请严格以 JSON 格式返回，不要包含任何多余的解释：
{"tech_stack": ["关键词1", "关键词2", ...], "soft_skills": ["关键词1", ...], "business_scene": ["关键词1", ...]}

JD 内容：
{jd_content}"""


def _parse_ai_response(response_text: str) -> dict[str, list[str]]:
    json_match = re.search(r"\{[\s\S]*?\}", response_text)
    if not json_match:
        print("[analyzer] AI 返回格式异常，尝试按行解析")
        lines = [line.strip("- ").strip() for line in response_text.split("\n") if line.strip()]
        return {"tech_stack": lines, "soft_skills": [], "business_scene": []}

    json_str = json_match.group(0)
    json_str = json_str.replace("'\"", "'").replace('"\'', '"')
    
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"[analyzer] JSON 解析失败: {e}，尝试修复格式")
        try:
            json_str_fixed = json_str.replace("'", '"')
            data = json.loads(json_str_fixed)
        except json.JSONDecodeError:
            print("[analyzer] 修复失败，回退到按行解析")
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


def _enrich_with_rag(keywords: list[str]) -> tuple[list[str], list[str], str]:
    rich_context: list[str] = []
    rag_context_text = ""
    try:
        from src.utils.vector_store import hybrid_retrieve, rebuild_bm25

        rebuild_bm25()

        enriched = list(keywords)
        seen = set(keywords)
        all_full_context: list[str] = []

        for kw in keywords[:5]:
            try:
                docs = hybrid_retrieve(kw, vector_k=10, bm25_k=10, fusion_k=5)
                docs = _filter_rag_results(docs)
                for doc in docs:
                    content = doc.page_content.strip()
                    if content and len(content) > 6:
                        if _is_quality_context(content) and content not in seen:
                            seen.add(content)
                            all_full_context.append(content)
                        term = content[:60] if len(content) > 60 else content
                        if term not in seen:
                            seen.add(term)
                            enriched.append(term)
            except Exception as inner_e:
                print(f"[analyzer] 混合检索关键词 '{kw}' 跳过: {inner_e}")

        added = len(enriched) - len(keywords)
        if added > 0:
            print(f"[analyzer] RAG 补充了 {added} 个行业术语")

        top_context = all_full_context[:3]
        if top_context:
            rich_context = top_context
            rag_context_text = "\n".join(f"{i}. {c}" for i, c in enumerate(top_context, 1))
            print(f"[analyzer] Top-3 金牌案例已注入 rag_context ({len(rag_context_text)} 字符)")

        return enriched, rich_context, rag_context_text
    except ImportError:
        print("[analyzer] vector_store 模块未就绪，跳过 RAG 增强")
        return keywords, rich_context, rag_context_text
    except Exception as e:
        print(f"[analyzer] RAG 检索失败 ({type(e).__name__}: {e})，使用原始关键词")
        return keywords, rich_context, rag_context_text


def jd_analyzer_node(state: GraphState) -> GraphState:
    jd_text = state.get("target_jd", "")
    state["revision_count"] = state.get("revision_count", 0)

    if not jd_text.strip():
        print("[analyzer] 警告：target_jd 为空，跳过分析")
        state["gap_list"] = []
        state["rich_context_list"] = []
        state["rag_context"] = ""
        return state

    try:
        llm = get_flash_client()
        prompt = JD_ANALYSIS_PROMPT.replace("{jd_content}", jd_text)
        response = llm.invoke(prompt)
        response_text = response.content if hasattr(response, "content") else str(response)

        print(f"[analyzer] AI 原始返回:\n{response_text[:800]}...")
        
        json_match = re.search(r"\{[\s\S]*?\}", response_text)
        if json_match:
            print(f"[analyzer] 提取的 JSON 部分: {json_match.group(0)}")

        structured = _parse_ai_response(response_text)
        print(
            f"[analyzer] 结构化提取: "
            f"tech_stack={len(structured['tech_stack'])}项, "
            f"soft_skills={len(structured['soft_skills'])}项, "
            f"business_scene={len(structured['business_scene'])}项"
        )

        keywords = _flatten_keywords(structured)
        print(f"[analyzer] 合并关键词 ({len(keywords)} 项): {keywords}")

        keywords, rich_context, rag_context_text = _enrich_with_rag(keywords)

        state["gap_list"] = keywords
        state["rich_context_list"] = rich_context
        state["rag_context"] = rag_context_text
        print(f"[analyzer] 最终 gap_list ({len(keywords)} 项), rich_context ({len(rich_context)} 条)")

    except ValueError as e:
        print(f"[analyzer] 配置错误: {e}")
        state["gap_list"] = []
        state["rich_context_list"] = []
        state["rag_context"] = ""
    except Exception as e:
        print(f"[analyzer] AI 调用失败 ({type(e).__name__}: {e})，保留原始状态")
        import traceback
        traceback.print_exc()
        if not state.get("gap_list"):
            state["gap_list"] = []
        if not state.get("rich_context_list"):
            state["rich_context_list"] = []
        if not state.get("rag_context"):
            state["rag_context"] = ""

    return state
