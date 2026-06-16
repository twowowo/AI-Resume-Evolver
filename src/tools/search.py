import os
import re
import json
import requests
from src.utils.llm import get_flash_client

try:
    from tavily import TavilyClient as _TavilyClient
    _TAVILY_NATIVE = True
except ImportError:
    _TAVILY_NATIVE = False

_TAVILY_BASE = "https://api.tavily.com/search"

_COMPANY_CULTURE_MAP = {
    "字节": "字节跳动 企业文化 坦诚清晰 招聘偏好 2026",
    "阿里": "阿里巴巴 企业文化 新六脉神剑 招聘标准 2026",
    "腾讯": "腾讯 企业文化 瑞雪 招聘偏好 技术面试 2026",
    "美团": "美团 零售基因 长期有耐心 招聘要求 2026",
    "拼多多": "拼多多 本分 招聘标准 技术面 2026",
    "华为": "华为 以奋斗者为本 招聘偏好 2026",
    "京东": "京东 正道成功 招聘标准 2026",
    "百度": "百度 简单可依赖 技术要求 面试 2026",
    "快手": "快手 招聘偏好 技术栈 面试 2026",
    "小红书": "小红书 招聘标准 技术面试 2026",
    "网易": "网易 招聘偏好 技术栈 2026",
    "滴滴": "滴滴 招聘标准 技术面试 2026",
    "小米": "小米 招聘偏好 技术栈 2026",
    "B站": "哔哩哔哩 招聘标准 技术面试 2026",
    "哔哩哔哩": "哔哩哔哩 招聘标准 技术面试 2026",
    "SHEIN": "SHEIN 招聘标准 技术面试 2026",
    "Shopee": "Shopee 招聘标准 技术面试 2026",
}


def _tavily_search_raw(query: str, max_results: int = 5) -> list[dict]:
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return []

    if _TAVILY_NATIVE:
        try:
            client = _TavilyClient(api_key=api_key)
            response = client.search(query, max_results=max_results, include_raw_content=True)
            return response.get("results", [])
        except Exception as e:
            print(f"[tavily] Native client failed: {e}, falling back to HTTP")

    try:
        resp = requests.post(
            _TAVILY_BASE,
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "include_raw_content": True,
            },
            timeout=120,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("results", [])
        else:
            print(f"[tavily] HTTP {resp.status_code}: {resp.text[:200]}")
            return []
    except Exception as e:
        print(f"[tavily] Request failed: {e}")
        return []


def _detect_company(jd_text: str) -> str | None:
    for name, query in sorted(_COMPANY_CULTURE_MAP.items(), key=lambda x: -len(x[0])):
        if name in jd_text:
            return query
    return None


def _extract_tech_keywords(jd_text: str) -> list[str]:
    patterns = [
        r"\b(DeepSeek[-\s]?V?\d*)\b",
        r"\b(GPT[-\s]?\d[.\d]*)\b",
        r"\b(Claude[-\s]?\d[.\d]*)\b",
        r"\b(Llama[-\s]?\d[.\d]*)\b",
        r"\b(Qwen[-\s]?\d[.\d]*)\b",
        r"\b(Gemini[-\s]?\d[.\d]*)\b",
        r"\b(Mistral[-\s]?\d[.\d]*)\b",
        r"\b(Milvus)\b",
        r"\b(Pinecone)\b",
        r"\b(Weaviate)\b",
        r"\b(LangChain|LangGraph)\b",
        r"\b(LlamaIndex)\b",
        r"\b(HuggingFace)\b",
        r"\b(Kubernetes|K8s)\b",
    ]
    found = []
    for pat in patterns:
        m = re.search(pat, jd_text, re.IGNORECASE)
        if m:
            found.append(m.group(1))
    return list(dict.fromkeys(found))


def build_search_queries(jd: str, resume: str) -> list[str]:
    queries: list[str] = []

    company_query = _detect_company(jd)
    if company_query:
        queries.append(company_query)
    else:
        m = re.search(r"(\S{2,4}(?:公司|科技|集团|网络|在线))", jd)
        if m:
            queries.append(f"{m.group(1)} 招聘标准 技术面试 2026")

    tech_keywords = _extract_tech_keywords(jd)
    for tech in tech_keywords:
        queries.append(f"{tech} STAR 原则 面试 高频描述关键词")

    if not queries:
        queries.append(f"{jd[:80]} 招聘要求 技术栈")

    queries.append(f"{jd[:60]} 企业价值观 技术面试重点 2026")

    return queries[:5]


def optimize_query_with_llm(task: str, jd: str) -> list[str]:
    prompt = """你是一个搜索查询优化器。请将以下求职场景转化为 2-3 个最适合搜索引擎的查询。

规则：
- 如果 JD 中有公司名，自动生成"XXX 企业文化"、"XXX 招聘偏好/面试重点 2026"类查询
- 如果 JD 中有新技术名词（如 DeepSeek-V3），生成技术趋势和 STAR 话术查询
- 查询要求简洁、信息密度高、适合搜索引擎

原始需求：{task}

JD 片段：{jd}

请严格以 Python list 格式返回，不要多余解释：
["查询1", "查询2", "查询3"]"""

    try:
        llm = get_flash_client()
        response = llm.invoke(prompt.format(task=task, jd=jd[:500]))
        text = response.content if hasattr(response, "content") else str(response)

        match = re.search(r"\[([^\]]+)\]", text)
        if match:
            items = re.findall(r'"([^"]+)"', match.group(0))
            return items[:3]
    except Exception:
        pass

    return build_search_queries(jd, task)


def tavily_search_node(state: dict):
    """
    Tavily 联网搜索节点：基于 JD 探测公司文化和新技术趋势，
    累加到 tool_outputs 供 editor_node 参考。
    """
    jd = state.get("jd", "")
    resume = state.get("resume", "")
    monologue = state.get("internal_monologue", "")

    queries = build_search_queries(jd, resume)

    all_results: list[str] = []
    api_key = os.getenv("TAVILY_API_KEY", "").strip()

    if not api_key:
        all_results.append("[web_search] TAVILY_API_KEY 未配置，跳过联网搜索。请在 .env 中设置该密钥以启用联网能力。")
    else:
        for i, query in enumerate(queries):
            try:
                results = _tavily_search_raw(query, max_results=3)
                if results:
                    snippet = f"[搜索 {i+1}] 查询: {query}\n"
                    for j, r in enumerate(results[:3]):
                        snippet += (
                            f"  [{j+1}] {r.get('title', '')}\n"
                            f"       内容: {r.get('content', '')[:300]}\n"
                        )
                    all_results.append(snippet)
                else:
                    all_results.append(f"[搜索 {i+1}] 查询: {query} - 无结果")
            except Exception as e:
                all_results.append(f"[搜索 {i+1}] 查询: {query} - 异常: {e}")

    web_context = "\n\n".join(all_results) if all_results else "[web_search] 无联网搜索结果。"

    log_lines = [
        f"[web_search] 已执行 {len(queries)} 次搜索，获得 {len(all_results)} 组结果",
    ]

    return {
        "tool_outputs": [web_context],
        "internal_monologue": monologue + "\n" + "\n".join(log_lines),
    }
