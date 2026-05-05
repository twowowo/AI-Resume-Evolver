import json
import re
from src.state import GraphState
from src.utils.llm import get_flash_client

_PLACEHOLDER_PATTERN = re.compile(r"^\[.+?\]$")
_BRACKET_PATTERN = re.compile(r"[\[\]]")


def _is_placeholder(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if _BRACKET_PATTERN.search(t):
        return True
    if _PLACEHOLDER_PATTERN.match(t):
        return True
    return False


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
    # 尝试多种 JSON 提取方式
    json_match = re.search(r"\{[\s\S]*?\}", response_text)
    if not json_match:
        print("[analyzer] AI 返回格式异常，尝试按行解析")
        lines = [line.strip("- ").strip() for line in response_text.split("\n") if line.strip()]
        return {"tech_stack": lines, "soft_skills": [], "business_scene": []}

    json_str = json_match.group(0)
    
    # 清理可能的额外引号或格式问题
    json_str = json_str.replace("'\"", "'").replace('"\'', '"')
    
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"[analyzer] JSON 解析失败: {e}，尝试修复格式")
        
        # 尝试修复常见的 JSON 格式问题
        try:
            # 处理可能的单引号问题
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
    
    # 更健壮的键处理
    for key in result:
        if key in data and isinstance(data[key], list):
            result[key] = data[key]
        elif f'"{key}"' in json_str:  # 检查是否有带引号的键
            print(f"[analyzer] 检测到带引号的键 '{key}'，跳过处理")
    
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
                docs = _filter_rag_results(docs)
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
        # 使用字符串替换而不是 format()，避免 JSON 键被误解析
        prompt = JD_ANALYSIS_PROMPT.replace("{jd_content}", jd_text)
        response = llm.invoke(prompt)
        response_text = response.content if hasattr(response, "content") else str(response)

        print(f"[analyzer] AI 原始返回:\n{response_text[:800]}...")
        
        # 调试：打印完整的 JSON 部分
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

        keywords = _enrich_with_rag(keywords)

        state["gap_list"] = keywords
        print(f"[analyzer] 最终 gap_list ({len(keywords)} 项): {keywords}")

    except ValueError as e:
        print(f"[analyzer] 配置错误: {e}")
        state["gap_list"] = []
    except Exception as e:
        print(f"[analyzer] AI 调用失败 ({type(e).__name__}: {e})，保留原始状态")
        import traceback
        traceback.print_exc()
        if not state.get("gap_list"):
            state["gap_list"] = []

    return state
